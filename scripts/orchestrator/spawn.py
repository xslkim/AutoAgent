"""Spawn a Python agent for a single task.

Picks one task from `ready/`, moves it to `in_progress/`, and launches
`scripts/agent/run_task.py <TASK-ID>` as a detached subprocess.

The Python agent does its own thing (claude CLI, git push, PR open) and
writes `result.json` next to the task file. Collection happens in collect.py
on the next polling tick.

Phase 0 stub: the run_task.py target is implemented by TASK-0020; this script
just exposes the spawn primitive (so poll loop callers can use it now and
the full path lights up when TASK-0020 lands).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from lib import StateRoot, append_event


def _agent_entrypoint() -> Path:
    """scripts/agent/run_task.py — landed by TASK-0020."""
    return Path(__file__).resolve().parent.parent / "agent" / "run_task.py"


def claim_next_ready(root: StateRoot) -> tuple[str, Path] | None:
    """Move the lowest-id ready task into in_progress/ and return (id, new_path)."""
    ready_files = root.list_task_files("ready")
    if not ready_files:
        return None
    task_id = ready_files[0].stem
    new_path = root.move_task(task_id, "in_progress")
    return task_id, new_path


def _spawn_agent(
    task_id: str,
    *,
    python: str,
    cwd: Path,
    log_path: Path | None = None,
) -> subprocess.Popen:
    """Detached subprocess. Caller does not wait()."""
    entry = _agent_entrypoint()
    log_path = log_path or (cwd / "state" / "logs" / f"{task_id}-{int(datetime.now(timezone.utc).timestamp())}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "wb")
    # Inherit minimal env. Caller can pre-set ANTHROPIC_API_KEY via .env.agent if desired.
    creationflags = 0
    if os.name == "nt":
        # Detach on Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        creationflags = 0x00000008 | 0x00000200
    return subprocess.Popen(
        [python, str(entry), task_id],
        cwd=cwd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        start_new_session=(os.name != "nt"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spawn", description="Spawn one Python agent.")
    parser.add_argument("--state-root", type=Path, default=Path("state"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--task-id", help="Spawn a specific task id rather than the next ready.")
    args = parser.parse_args(argv)

    root = StateRoot(args.state_root)
    if root.is_stopped():
        print("stop_signal present — refusing to spawn")
        return 0

    if args.task_id:
        loc = root.find(args.task_id)
        if loc is None:
            print(f"error: task {args.task_id} not found", file=sys.stderr)
            return 2
        bucket, _ = loc
        if bucket != "ready":
            print(f"error: task {args.task_id} is in {bucket}, not ready", file=sys.stderr)
            return 2

    # Phase 0: enforce serial MAX_CONCURRENT=1
    inflight = root.list_task_ids("in_progress")
    if inflight:
        print(f"in_progress not empty ({inflight}) — Phase 0 serial limit, refusing to spawn")
        return 0

    if args.dry_run:
        ready = root.list_task_ids("ready")
        target = args.task_id or (ready[0] if ready else None)
        if target is None:
            print("无任务可调度")
        else:
            print(f"would spawn {target}")
        return 0

    if args.task_id:
        new_path = root.move_task(args.task_id, "in_progress")
        claimed = (args.task_id, new_path)
    else:
        claimed = claim_next_ready(root)
    if claimed is None:
        print("ready/ empty — nothing to spawn")
        return 0

    task_id, new_path = claimed
    if not _agent_entrypoint().is_file():
        # TASK-0020 hasn't shipped yet. Roll back the move and exit gracefully.
        root.move_task(task_id, "ready")
        print(f"agent entrypoint not yet implemented ({_agent_entrypoint()}); rolled back {task_id}",
              file=sys.stderr)
        return 0

    proc = _spawn_agent(task_id, python=args.python, cwd=args.cwd)

    # Record spawn metadata on the task file.
    data = root.load_task(new_path)
    data["spawn"] = {
        "pid": proc.pid,
        "worktree_path": None,  # agent fills this once it sets up the worktree
        "branch": None,
        "log_path": None,
    }
    data["started_at"] = datetime.now(timezone.utc).isoformat()
    root.write_task(new_path, data)

    append_event(
        root.events_path,
        "task_spawned",
        task_id=task_id,
        pid=proc.pid,
    )
    print(f"spawned {task_id} pid={proc.pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
