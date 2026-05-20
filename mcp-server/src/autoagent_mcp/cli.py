"""CLI entry: `autoagent-mcp` starts the stdio MCP server."""

from __future__ import annotations

import argparse
import sys

from autoagent_mcp import __version__
from autoagent_mcp.logging import DEFAULT_LOG_FILE, DEFAULT_LEVEL


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autoagent-mcp",
        description="AutoAgent MCP server. Speaks MCP over stdio.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"autoagent-mcp {__version__}",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the names of all registered tools and exit (no server start).",
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_FILE),
        metavar="PATH",
        help=(
            f"Path for the rotating JSON log file "
            f"(default: {DEFAULT_LOG_FILE}). "
            "Pass an empty string to disable file logging."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LEVEL,
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimum log level (default: INFO).",
    )
    args = parser.parse_args(argv)

    if args.list_tools:
        from autoagent_mcp.tools import TOOL_NAMES

        for name in TOOL_NAMES:
            print(name)
        return 0

    from autoagent_mcp.logging import setup_logging
    from autoagent_mcp.server import run_stdio

    setup_logging(log_file=args.log_file or False, level=args.log_level)

    from autoagent_mcp.logging import get_logger
    log = get_logger(__name__)
    log.info("autoagent-mcp starting", extra={"version": __version__})

    run_stdio()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
