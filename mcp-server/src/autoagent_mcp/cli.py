"""CLI entry: `autoagent-mcp` starts the stdio MCP server."""

from __future__ import annotations

import argparse
import sys

from autoagent_mcp import __version__


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="autoagent-mcp",
        description="AutoAgent MCP server (Phase 0 stub). Speaks MCP over stdio.",
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
    args = parser.parse_args(argv)

    if args.list_tools:
        from autoagent_mcp.tools import TOOL_NAMES

        for name in TOOL_NAMES:
            print(name)
        return 0

    from autoagent_mcp.server import run_stdio

    run_stdio()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
