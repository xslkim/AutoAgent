"""Write state/stop_signal — global emergency stop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from lib import StateRoot, append_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stop", description="Write stop_signal.")
    parser.add_argument("--state-root", type=Path, default=Path("state"))
    parser.add_argument("--reason", default="manual stop")
    args = parser.parse_args(argv)

    root = StateRoot(args.state_root)
    if root.is_stopped():
        print("stop_signal already present")
        return 0
    root.touch_stop_signal(args.reason)
    append_event(root.events_path, "global_stop", reason=args.reason)
    print(f"stop_signal written: {args.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
