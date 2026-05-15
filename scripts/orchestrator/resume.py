"""Remove state/stop_signal — clear emergency stop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from lib import StateRoot, append_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resume", description="Remove stop_signal.")
    parser.add_argument("--state-root", type=Path, default=Path("state"))
    args = parser.parse_args(argv)

    root = StateRoot(args.state_root)
    if not root.is_stopped():
        print("no stop_signal to clear")
        return 0
    root.clear_stop_signal()
    append_event(root.events_path, "global_resume")
    print("stop_signal cleared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
