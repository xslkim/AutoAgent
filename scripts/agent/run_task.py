"""Python agent — execute one task by spawning an AI coding agent CLI.

Lifecycle (docs/09-orchestration.md §九):
  1. Load the task file from state/in_progress/.
  2. (optional) Set up a fresh git worktree.
  3. Build the prompt from the task spec.
  4. Spawn the agent CLI (default: opencode via `cmd /c`) with an isolated
     env, feeding the prompt on stdin, capturing stdout+stderr (UTF-8) to a
     scrubbed log file.
  5. Classify the outcome (success / awaiting_ci / failed / needs_human).
  6. Write the result back into the task file's `result` field. Atomic.
  7. Exit 0 — the orchestrator inspects the task file, not our exit code.

The orchestrator polls in_progress/ for tasks whose `result` is populated and
moves them to the appropriate bucket (see scripts/orchestrator/collect.py).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Allow `from lib import ...` from sibling orchestrator package.
_HERE = Path(__file__).resolve().parent
_ORCH = _HERE.parent / "orchestrator"
sys.path.insert(0, str(_ORCH))
import _bootstrap  # noqa: F401,E402  (sets up sys.path + reconfigures stdout)
from lib import StateRoot, append_event  # noqa: E402

from classify import classify, Verdict  # noqa: E402
from prompt_template import build_prompt  # noqa: E402
from worktree import WorktreePlan, setup_worktree  # noqa: E402


SECRET_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "AGENT_ANTHROPIC_KEY",
    "DEEPSEEK_API_KEY",
    "AGENT_DEEPSEEK_KEY",
    "GITHUB_TOKEN",
    "AGENT_GITHUB_TOKEN",
)


def isolated_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a minimal env for the child agent process.

    Forwards PATH, HOME/USERPROFILE (so opencode can find ~/.config/opencode/),
    Windows-specific dirs (APPDATA, LOCALAPPDATA), and any keys in `extra`.
    Secret env vars are NOT forwarded — the orchestrator config injects them.
    """
    out: dict[str, str] = {}
    for k in ("PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
              "TEMP", "TMP", "SYSTEMROOT"):
        v = os.environ.get(k)
        if v is not None:
            out[k] = v
    if extra:
        out.update(extra)
    return out


def scrub_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace any occurrence of a secret string with ***. Best-effort."""
    out = text
    for s in secrets:
        if not s or len(s) < 8:
            continue
        out = out.replace(s, "***REDACTED***")
    return out


def _collect_secrets_for_scrubbing() -> tuple[str, ...]:
    return tuple(v for k in SECRET_ENV_KEYS if (v := os.environ.get(k)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_result(task_path: Path, root: StateRoot, *, verdict: Verdict, extras: dict) -> None:
    task = root.load_task(task_path)
    result = {
        "status": verdict.status,
        "reason": verdict.reason,
        "pr_url": verdict.pr_url,
        "commit_sha": None,
        "ci_status": "pending" if verdict.status == "awaiting_ci" else None,
        "error": None if verdict.status in ("success", "awaiting_ci") else verdict.reason,
        "needs_human_reason": verdict.reason if verdict.status == "needs_human" else None,
        **extras,
    }
    task["result"] = result
    task["finished_at"] = _now_iso()
    root.write_task(task_path, task)


def run_single_task(
    task_id: str,
    *,
    state_root: Path,
    claude_argv: list[str],
    repo_root: Path,
    timeout_seconds: int,
    setup_wt: bool = True,
    log_dir: Path | None = None,
) -> Verdict:
    root = StateRoot(state_root)
    location = root.find(task_id)
    if location is None:
        raise FileNotFoundError(f"task {task_id} not found in any bucket")
    bucket, task_path = location
    if bucket != "in_progress":
        # If the orchestrator forgot to move it, do it ourselves to stay correct.
        task_path = root.move_task(task_id, "in_progress")

    task = root.load_task(task_path)
    branch = f"agent/{task_id}"
    worktree_path: Path

    if setup_wt:
        plan = WorktreePlan(repo_root=repo_root, task_id=task_id)
        worktree_path = setup_worktree(plan)
        branch = plan.branch
    else:
        worktree_path = repo_root  # tests run the mock straight in the repo

    # Update spawn metadata
    task.setdefault("spawn", {})
    task["spawn"]["worktree_path"] = str(worktree_path)
    task["spawn"]["branch"] = branch
    task["spawn"]["pid"] = os.getpid()
    task["started_at"] = _now_iso()
    log_dir = log_dir or (state_root / "logs" / task_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{int(datetime.now(timezone.utc).timestamp())}.log"
    task["spawn"]["log_path"] = str(log_path)
    root.write_task(task_path, task)

    prompt = build_prompt(task, worktree_path=worktree_path, branch=branch)
    secrets = _collect_secrets_for_scrubbing()

    timed_out = False
    spawn_error: str | None = None
    try:
        # The agent CLI (opencode / claude) reads the prompt from stdin.
        # UTF-8 is forced — the locale codec (e.g. GBK) chokes on agent output.
        proc = subprocess.run(
            claude_argv,
            cwd=str(worktree_path),
            input=prompt,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=isolated_env(),
            timeout=timeout_seconds,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout.decode("utf-8", errors="replace")
                  if isinstance(e.stdout, bytes) else (e.stdout or ""))
        stderr = (e.stderr.decode("utf-8", errors="replace")
                  if isinstance(e.stderr, bytes) else (e.stderr or ""))
        exit_code = 124  # GNU timeout convention
        timed_out = True
    except (FileNotFoundError, PermissionError, OSError) as e:
        # claude executable not found / blocked / etc. — still write a log
        # and propagate as a structured failure rather than crashing the agent.
        stdout = ""
        stderr = f"spawn error: {type(e).__name__}: {e}"
        exit_code = 127  # POSIX "command not found" convention
        spawn_error = str(e)

    # Scrub anything that looks like a known secret before persisting.
    log_text = scrub_secrets(
        f"--- STDOUT ---\n{stdout}\n--- STDERR ---\n{stderr}\n",
        secrets,
    )
    log_path.write_text(log_text, encoding="utf-8", errors="replace")

    verdict = classify(exit_code, stdout, stderr)
    if timed_out:
        # Override classify if we hit our own timeout.
        verdict = Verdict("failed", f"timeout after {timeout_seconds}s")

    extras = {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "log_path": str(log_path),
        "duration_seconds": None,  # caller may fill from started_at if needed
        "spawn_error": spawn_error,
    }
    write_result(task_path, root, verdict=verdict, extras=extras)

    append_event(
        root.events_path,
        "task_finished",
        task_id=task_id,
        status=verdict.status,
        exit_code=exit_code,
    )
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_task",
        description="Execute one AutoAgent task by spawning claude CLI.",
    )
    parser.add_argument("task_id", help="e.g. TASK-0007")
    parser.add_argument("--state-root", type=Path, default=Path("state"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--claude-cmd",
        default="cmd /c opencode run --dangerously-skip-permissions",
        help="Command to invoke (shlex-split if no --claude-arg given). "
             "Default: opencode via `cmd /c` — the npm-shim .cmd needs a "
             "shell on Windows. The prompt is fed on stdin. "
             "Override for tests: --claude-cmd python --claude-arg=-c ...",
    )
    parser.add_argument(
        "--claude-arg",
        action="append",
        default=[],
        help="Additional argument to pass to the claude command (repeatable).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        help="Hard timeout on the claude subprocess (default 1h).",
    )
    parser.add_argument(
        "--no-worktree",
        action="store_true",
        help="Skip git worktree setup (test mode).",
    )
    args = parser.parse_args(argv)

    # If --claude-arg is given at all, --claude-cmd is treated as a literal
    # executable path (no shlex) and --claude-arg supplies argv verbatim. This
    # avoids backslash-eating from shlex on Windows paths.
    if args.claude_arg:
        claude_argv = [args.claude_cmd] + list(args.claude_arg)
    else:
        claude_argv = shlex.split(args.claude_cmd)

    try:
        verdict = run_single_task(
            args.task_id,
            state_root=args.state_root,
            claude_argv=claude_argv,
            repo_root=args.repo_root.resolve(),
            timeout_seconds=args.timeout_seconds,
            setup_wt=not args.no_worktree,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except subprocess.SubprocessError as e:
        print(f"error: subprocess failed: {e}", file=sys.stderr)
        return 2

    print(f"{args.task_id}: {verdict.status} — {verdict.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
