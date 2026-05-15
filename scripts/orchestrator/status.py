"""Print a one-shot summary of state/ contents. Read-only.

Empty-state run must not crash — see TASK-0019 verification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from lib import StateRoot
from lib.budget import load_budget, check_limits
from lib.state_io import TASK_BUCKETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="status", description="Print state/ summary.")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path("state"),
        help="Path to state/ directory (default: ./state).",
    )
    args = parser.parse_args(argv)

    root = StateRoot(args.state_root)

    if not args.state_root.is_dir():
        print(f"state/ not found at {args.state_root}", file=sys.stderr)
        # Don't fail — explicit "no state" is a valid story for `--dry-run` audits.
        return 0

    print(f"# AutoAgent state @ {root.root}")
    print()

    # Buckets
    width = max(len(b) for b in TASK_BUCKETS)
    for b in TASK_BUCKETS:
        ids = root.list_task_ids(b)
        marker = " " if not ids else "*"
        print(f"  {marker} {b:<{width}}  ({len(ids)})  {' '.join(ids[:5])}{' …' if len(ids) > 5 else ''}")

    print()

    # Stop signal
    if root.is_stopped():
        reason = root.stop_signal_path.read_text(encoding="utf-8", errors="replace").strip()
        print(f"  ⛔ stop_signal present: {reason or '(no reason)'}")
    else:
        print("  ✓ no stop_signal")

    # Budget
    try:
        budget = load_budget(root.budget_path)
    except ValueError as e:
        print(f"  ! budget unreadable: {e}")
        return 0

    today = budget.get("today", {})
    session = budget.get("session", {})
    print()
    print(f"  today    ${today.get('usd', 0):>7.2f}  "
          f"tasks {today.get('task_count', 0):>3}  "
          f"PRs {today.get('pr_count', 0):>3}  "
          f"CI {today.get('ci_run_count', 0):>3}")
    print(f"  session  ${session.get('usd', 0):>7.2f}  "
          f"tasks {session.get('task_count', 0):>3}  "
          f"CI {session.get('ci_run_count', 0):>3}")

    breaches = check_limits(budget)
    if breaches:
        print(f"  ⚠ budget breach: {breaches}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
