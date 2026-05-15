"""One polling tick.

Steps (subset of docs/09-orchestration.md §八):
  1. Check stop_signal / budget limits
  2. Compute ready/blocked from queue + blocked buckets
  3. Apply moves (or print actions in --dry-run)

The full polling loop (CI checks, in_progress health, spawn) lives in the
顶层 Claude turn logic — these helpers are building blocks the loop calls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from lib import StateRoot, append_event, compute_ready_and_blocked, find_cycles
from lib.budget import check_limits, load_budget
from lib.state_io import TASK_BUCKETS, load_all_tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poll", description="One polling tick.")
    parser.add_argument("--state-root", type=Path, default=Path("state"))
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned actions, do not move files.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = StateRoot(args.state_root)

    # 1. stop_signal
    if root.is_stopped():
        if not args.quiet:
            print("stop_signal present — refusing to schedule")
        return 0

    # 2. budget limits
    if root.budget_path.is_file():
        try:
            budget = load_budget(root.budget_path)
        except ValueError as e:
            print(f"error: budget.json invalid: {e}", file=sys.stderr)
            return 2
        breaches = check_limits(budget)
        if breaches:
            if not args.quiet:
                print(f"budget breach: {breaches} — set stop_signal manually or wait for rollover")
            return 0

    # 3. cycle check across all task buckets
    all_tasks = {tid: data for tid, (_b, data) in load_all_tasks(root).items()}
    cycles = find_cycles(all_tasks)
    if cycles:
        print(f"error: dependency cycle detected: {cycles}", file=sys.stderr)
        return 2

    # 4. compute ready / blocked decisions
    queue = {tid: data for tid, (b, data) in load_all_tasks(root, ["queue"]).items()}
    blocked = {tid: data for tid, (b, data) in load_all_tasks(root, ["blocked"]).items()}
    done_ids = set(root.list_task_ids("done"))
    failed_ids = set(root.list_task_ids("failed"))
    needs_human_ids = set(root.list_task_ids("needs_human"))

    decisions = compute_ready_and_blocked(
        queue, blocked,
        done_ids=done_ids,
        failed_ids=failed_ids,
        needs_human_ids=needs_human_ids,
    )

    if not decisions:
        if not args.quiet:
            ready_ct = len(root.list_task_ids("ready"))
            inflight_ct = len(root.list_task_ids("in_progress")) + len(root.list_task_ids("awaiting_ci"))
            if ready_ct == 0 and not queue and not blocked and inflight_ct == 0:
                print("无任务可调度")
            else:
                print(f"no state transitions; queue={len(queue)} blocked={len(blocked)} "
                      f"ready={ready_ct} inflight={inflight_ct}")
        return 0

    for d in decisions:
        if args.dry_run:
            print(f"  would move {d.task_id} → {d.target}  ({d.reason})")
        else:
            try:
                root.move_task(d.task_id, d.target)
                if not args.quiet:
                    print(f"  moved {d.task_id} → {d.target}  ({d.reason})")
                append_event(
                    root.events_path,
                    "task_transition",
                    task_id=d.task_id,
                    target=d.target,
                    reason=d.reason,
                )
            except FileNotFoundError as e:
                print(f"  ! could not move {d.task_id}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
