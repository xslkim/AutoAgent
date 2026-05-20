"""CLI entry: `autoagent-mcp` starts the stdio MCP server."""

from __future__ import annotations

import argparse
import sys

from autoagent_mcp import __version__
from autoagent_mcp.config import DEFAULT_CONFIG_FILE, load_config
from autoagent_mcp.logging import DEFAULT_LOG_FILE, DEFAULT_LEVEL


def cli(argv: list[str] | None = None) -> int:
    # -----------------------------------------------------------------------
    # Phase-1 parse: extract --config before the main parse so we can use
    # the config file's values as argparse defaults.
    # -----------------------------------------------------------------------
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None)
    pre_args, _ = pre.parse_known_args(argv)

    cfg = load_config(pre_args.config)

    # -----------------------------------------------------------------------
    # Main parser
    # -----------------------------------------------------------------------
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
        "--config",
        default=None,
        metavar="PATH",
        help=(
            f"Path to a TOML config file "
            f"(default: {DEFAULT_CONFIG_FILE}). "
            "CLI flags override values from the file."
        ),
    )
    parser.add_argument(
        "--host",
        default=cfg.server.host,
        metavar="HOST",
        help=f"Engine adapter host (default from config: {cfg.server.host}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=cfg.server.port,
        metavar="PORT",
        help=f"Engine adapter port (default from config: {cfg.server.port}).",
    )
    parser.add_argument(
        "--log-file",
        default=cfg.logging.file,
        metavar="PATH",
        help=(
            f"Path for the rotating JSON log file "
            f"(default from config: {cfg.logging.file}). "
            "Pass an empty string to disable file logging."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=cfg.logging.level,
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=f"Minimum log level (default from config: {cfg.logging.level}).",
    )
    args = parser.parse_args(argv)

    if args.list_tools:
        from autoagent_mcp.tools import TOOL_NAMES

        for name in TOOL_NAMES:
            print(name)
        return 0

    from autoagent_mcp.logging import setup_logging
    from autoagent_mcp.server import run_stdio

    setup_logging(
        log_file=args.log_file or False,
        level=args.log_level,
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count,
    )

    from autoagent_mcp.logging import get_logger
    log = get_logger(__name__)
    log.info(
        "autoagent-mcp starting",
        extra={
            "version": __version__,
            "host": args.host,
            "port": args.port,
            "config_source": str(cfg.source) if cfg.source else "defaults",
        },
    )

    run_stdio()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
