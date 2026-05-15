"""Collect completed Python agents.

Scans `in_progress/` for tasks whose `result` field has been filled in by
the agent. Moves them per `result.status`:

    awaiting_ci  → awaiting_ci/
    failed       → failed/ if retries exhausted, else ready/ for retry
    needs_human  → needs_human/
    success      → done/ (rare: agent decided no CI is needed)
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from lib import StateRoot, append_event


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def collect_one(root: StateRoot, task_path: Path) -> tuple[str | None, str]:
    """Return (target_bucket, reason). target_bucket=None means leave in place."""
    task = root.load_task(task_path)
    result = task.get("result")
    spawn = task.get("spawn") or {}
    pid = spawn.get("pid") or 0

    if result is None:
        # No result yet. Check if pid is alive; if zombie, send back to ready/.
        if pid and not _pid_alive(pid):
            task["retries"] = int(task.get("retries", 0)) + 1
            task["spawn"] = {"pid": None, "worktree_path": None, "branch": None, "log_path": None}
            root.write_task(task_path, task)
            return "ready", f"zombie agent (pid {pid} dead, no result.json)"
        return None, "still running"

    status = result.get("status")
    if status == "awaiting_ci":
        return "awaiting_ci", "agent done, CI pending"
    if status == "needs_human":
        return "needs_human", result.get("needs_human_reason") or "agent flagged"
    if status == "success":
        return "done", "agent reported success"
    if status == "failed":
        retries = int(task.get("retries", 0))
        max_retries = int(task.get("max_retries", 5))
        if retries + 1 >= max_retries:
            return "failed", f"retries exhausted ({retries}/{max_retries})"
        # Bump retries and send back to ready
        task["retries"] = retries + 1
        # Drop the per-attempt result into history; clear current result.
        history = list(task.get("history") or [])
        history.append({"attempt": retries + 1, "result": result})
        task["history"] = history
        task["result"] = None
        task["spawn"] = {"pid": None, "worktree_path": None, "branch": None, "log_path": None}
        root.write_task(task_path, task)
        return "ready", f"retry {retries + 1}/{max_retries}"

    return None, f"unknown status: {status!r}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collect", description="Collect finished agents.")
    parser.add_argument("--state-root", type=Path, default=Path("state"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = StateRoot(args.state_root)
    moved = 0
    for task_path in root.list_task_files("in_progress"):
        target, reason = collect_one(root, task_path)
        if target is None:
            if not args.quiet:
                print(f"  - {task_path.stem}: {reason}")
            continue
        if args.dry_run:
            print(f"  would move {task_path.stem} → {target}  ({reason})")
            continue
        try:
            root.move_task(task_path.stem, target)
            print(f"  moved {task_path.stem} → {target}  ({reason})")
            append_event(
                root.events_path,
                "task_collected",
                task_id=task_path.stem,
                target=target,
                reason=reason,
            )
            moved += 1
        except FileNotFoundError as e:
            print(f"  ! collect {task_path.stem}: {e}", file=sys.stderr)

    if not args.quiet and moved == 0:
        print("nothing to collect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
