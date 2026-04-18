"""CLI entry point for AutoVisionTest (stub implementation)."""

import click

from autovisiontest import __version__


@click.group()
@click.version_option(version=__version__, prog_name="autovisiontest")
def main() -> int:
    """AutoVisionTest — AI-vision-driven desktop application automated testing framework."""
    return 0


if __name__ == "__main__":
    main()
