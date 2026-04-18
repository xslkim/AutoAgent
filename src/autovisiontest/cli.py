"""CLI entry point for AutoVisionTest.

Defines all sub-commands (stub implementations for now) and global options.
"""

from __future__ import annotations

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
        pass  # logging_setup not available yet (e.g. before T A.3 is merged)


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
    click.echo("Not implemented: run")


# ── status ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("session_id")
@click.pass_context
def status(ctx: click.Context, session_id: str) -> None:
    """Show the status of a test session."""
    click.echo(f"Not implemented: status {session_id}")


# ── report ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("session_id")
@click.option("--format", "fmt", type=click.Choice(["json", "html"]), default="json", help="Output format.")
@click.pass_context
def report(ctx: click.Context, session_id: str, fmt: str) -> None:
    """Generate a test report for a session."""
    click.echo(f"Not implemented: report {session_id} --format {fmt}")


# ── list-recordings ────────────────────────────────────────────────────


@main.command("list-recordings")
@click.pass_context
def list_recordings(ctx: click.Context) -> None:
    """List all recorded test cases."""
    click.echo("Not implemented: list-recordings")


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


if __name__ == "__main__":
    main()
