"""CLI entry point for AutoVisionTest.

Defines all sub-commands and global options.
"""

from __future__ import annotations

import sys

import click

from autovisiontest import __version__


@click.group()
@click.version_option(version=__version__, prog_name="autovisiontest")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False),
    default=None,
    help="Path to config YAML file.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level.",
)
@click.pass_context
def main(ctx: click.Context, config_path: str | None, log_level: str) -> None:
    """AutoVisionTest — AI-vision-driven desktop application automated testing framework."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["log_level"] = log_level.upper()

    # Initialise logging as early as possible
    try:
        from autovisiontest.logging_setup import setup_logging

        setup_logging(level=log_level.upper())
    except ImportError:
        pass  # logging_setup not available yet


# ── run ─────────────────────────────────────────────────────────────────


@main.command()
@click.option("--goal", type=str, default=None, help="Natural language test goal.")
@click.option("--app", "app_path", type=str, default=None, help="Path to the application executable.")
@click.option("--app-args", type=str, default=None, help="Arguments to pass to the application.")
@click.option("--timeout", type=int, default=None, help="Maximum session duration in milliseconds.")
@click.option("--case", "case_path", type=click.Path(exists=False), default=None, help="Path to a recorded test case.")
@click.pass_context
def run(
    ctx: click.Context,
    goal: str | None,
    app_path: str | None,
    app_args: str | None,
    timeout: int | None,
    case_path: str | None,
) -> None:
    """Launch a test session (exploratory or regression)."""
    if goal is None and case_path is None:
        raise click.UsageError("Either --goal or --case must be provided.")
    if goal is not None and case_path is not None:
        raise click.UsageError("--goal and --case are mutually exclusive.")

    from autovisiontest.interfaces.cli_commands import cmd_run

    config_path = ctx.obj.get("config_path")
    exit_code = cmd_run(goal, app_path, app_args, timeout, case_path, config_path)
    sys.exit(exit_code)


# ── status ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("session_id")
@click.pass_context
def status(ctx: click.Context, session_id: str) -> None:
    """Show the status of a test session."""
    from autovisiontest.interfaces.cli_commands import cmd_status

    config_path = ctx.obj.get("config_path")
    exit_code = cmd_status(session_id, config_path)
    sys.exit(exit_code)


# ── report ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("session_id")
@click.option("--format", "fmt", type=click.Choice(["json", "html"]), default="json", help="Output format.")
@click.pass_context
def report(ctx: click.Context, session_id: str, fmt: str) -> None:
    """Generate a test report for a session."""
    from autovisiontest.interfaces.cli_commands import cmd_report

    config_path = ctx.obj.get("config_path")
    exit_code = cmd_report(session_id, fmt, config_path)
    sys.exit(exit_code)


# ── list-recordings ────────────────────────────────────────────────────


@main.command("list-recordings")
@click.pass_context
def list_recordings(ctx: click.Context) -> None:
    """List all recorded test cases."""
    from autovisiontest.interfaces.cli_commands import cmd_list_recordings

    config_path = ctx.obj.get("config_path")
    exit_code = cmd_list_recordings(config_path)
    sys.exit(exit_code)


# ── validate ────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Load and print the current configuration."""
    try:
        from autovisiontest.config.loader import load_config
        from pathlib import Path

        config_path = ctx.obj.get("config_path")
        config = load_config(path=Path(config_path) if config_path else None)
        click.echo(config.model_dump_json(indent=2))
    except ImportError:
        click.echo("Configuration module not available yet.")
    except Exception as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        sys.exit(3)


# ── serve ───────────────────────────────────────────────────────────────


@main.command()
@click.option("--port", type=int, default=8080, help="HTTP server port.")
@click.option("--host", type=str, default="0.0.0.0", help="HTTP server host.")
@click.pass_context
def serve(ctx: click.Context, port: int, host: str) -> None:
    """Start the HTTP API server."""
    try:
        import uvicorn

        from autovisiontest.interfaces.http_server import create_app

        config_path = ctx.obj.get("config_path")
        app = create_app(config_path=config_path)
        uvicorn.run(app, host=host, port=port)
    except ImportError:
        click.echo("Error: fastapi/uvicorn not installed.", err=True)
        sys.exit(3)


# ── mcp ─────────────────────────────────────────────────────────────────


@main.command()
@click.option("--http", "http_addr", type=str, default=None, help="HTTP mode (e.g. :8090). Default: stdio.")
@click.pass_context
def mcp(ctx: click.Context, http_addr: str | None) -> None:
    """Start the MCP server (stdio or HTTP mode)."""
    try:
        from autovisiontest.interfaces.mcp_server import run_mcp_server

        config_path = ctx.obj.get("config_path")
        run_mcp_server(config_path=config_path, http_addr=http_addr)
    except ImportError:
        click.echo("Error: mcp package not installed.", err=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
