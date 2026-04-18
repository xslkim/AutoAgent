"""CLI entry point for AutoVisionTest (stub implementation)."""

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
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> int:
    """AutoVisionTest — AI-vision-driven desktop application automated testing framework."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    return 0


@main.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Load and print the current configuration."""
    from autovisiontest.config.loader import load_config
    from pathlib import Path

    config_path = ctx.obj.get("config_path")
    config = load_config(path=Path(config_path) if config_path else None)
    click.echo(config.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
