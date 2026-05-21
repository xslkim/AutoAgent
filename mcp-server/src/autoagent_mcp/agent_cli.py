"""CLI entry points for agent lifecycle management.

Registered in ``pyproject.toml`` as:

    autoagent-stop   = "autoagent_mcp.agent_cli:main_stop"
    autoagent-status = "autoagent_mcp.agent_cli:main_status"

See docs/07-agent-operations.md §8.1 for the stop-sentinel protocol.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# autoagent-stop
# ---------------------------------------------------------------------------


def stop_cli(argv: list[str] | None = None) -> int:
    """CLI handler for ``autoagent-stop``.

    Writes ``~/.autoagent/STOP`` so every background agent halts at its next
    poll (≤ 10 s).  Also appends a line to ``~/.autoagent/last_stop.log``.

    Exit codes:
        0 — STOP file written successfully.
        1 — STOP file already exists and ``--force`` was not given.
        2 — Usage error.
    """
    parser = argparse.ArgumentParser(
        prog="autoagent-stop",
        description=(
            "Write the STOP sentinel file — all background agents halt "
            "at their next poll (≤ 10 s)."
        ),
    )
    parser.add_argument(
        "--reason",
        default="manual stop via autoagent-stop",
        metavar="TEXT",
        help=(
            "Human-readable reason stored in the STOP file and "
            "~/.autoagent/last_stop.log  (default: %(default)r)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing STOP file without error.",
    )
    args = parser.parse_args(argv)

    # Import here so path constants are patchable in tests
    import autoagent_mcp.agent_ctl as ctl

    if ctl.is_stopped() and not args.force:
        info = ctl.read_stop()
        stopped_at = (info or {}).get("stopped_at", "unknown")
        print(
            f"Agent is already stopped "
            f"(STOP file exists, stopped_at={stopped_at}).\n"
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    record = ctl.write_stop(args.reason)
    print(f"STOP file written → {ctl.STOP_FILE}")
    print(f"Reason    : {record['reason']}")
    print(f"Stopped at: {record['stopped_at']}")
    print("All background agents will halt at their next poll (≤ 10 s).")
    return 0


# ---------------------------------------------------------------------------
# autoagent-status
# ---------------------------------------------------------------------------


def status_cli(argv: list[str] | None = None) -> int:
    """CLI handler for ``autoagent-status``.

    Prints the current stop state plus session metadata.

    Exit codes:
        0 — always (status commands should never fail).
    """
    parser = argparse.ArgumentParser(
        prog="autoagent-status",
        description="Show AutoAgent agent / session state.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON to stdout.",
    )
    args = parser.parse_args(argv)

    import autoagent_mcp.agent_ctl as ctl

    status = ctl.get_status()

    if args.json_output:
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0

    # -----------------------------------------------------------------------
    # Human-readable output
    # -----------------------------------------------------------------------
    _hr("AutoAgent Status")

    # Stop state
    if status["stopped"]:
        info = status["stop_info"] or {}
        _field("Agent state", "STOPPED")
        _field("  Reason", info.get("reason", "unknown"))
        _field("  Stopped at", info.get("stopped_at", "unknown"))
        _field("  PID", str(info.get("pid", "unknown")))
    else:
        _field("Agent state", f"RUNNING  (no STOP file at {ctl.STOP_FILE})")

    print()

    # Session summary
    sessions = status["sessions"]
    count = status["session_count"]
    if count == 0:
        _field("Sessions", f"none found in {ctl.SESSIONS_DIR}")
    else:
        _field("Sessions", f"{count} file(s) in {ctl.SESSIONS_DIR}")
        latest = sessions[0]
        _field("  Latest ID", latest["session_id"])
        _field("  Modified", latest["mtime"])
        _field("  Size", f"{latest['size_bytes'] / 1024:.1f} KB")

    return 0


# ---------------------------------------------------------------------------
# Entry-point shims
# ---------------------------------------------------------------------------


def main_stop() -> None:
    sys.exit(stop_cli())


def main_status() -> None:
    sys.exit(status_cli())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hr(title: str) -> None:
    print(title)
    print("=" * len(title))


def _field(label: str, value: str) -> None:
    print(f"{label:<18}: {value}")
