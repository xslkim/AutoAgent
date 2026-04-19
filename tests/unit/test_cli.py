"""Tests for the AutoVisionTest CLI.

These tests verify CLI argument parsing and routing.  Command implementations
(cli_commands.py) are tested separately in test_cli_commands.py.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from autovisiontest.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── version ─────────────────────────────────────────────────────────────


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


# ── help ────────────────────────────────────────────────────────────────


def test_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("run", "status", "report", "list-recordings", "validate"):
        assert cmd in result.output, f"Subcommand '{cmd}' not found in help output"


# ── run ─────────────────────────────────────────────────────────────────


def test_run_requires_goal_or_case(runner: CliRunner) -> None:
    result = runner.invoke(main, ["run"])
    assert result.exit_code != 0


def test_run_goal_and_case_mutually_exclusive(runner: CliRunner) -> None:
    result = runner.invoke(main, ["run", "--goal", "test", "--case", "some.json"])
    assert result.exit_code != 0


def test_run_with_goal_needs_app(runner: CliRunner) -> None:
    """run --goal without --app should fail because scheduler creation fails."""
    result = runner.invoke(main, ["run", "--goal", "open notepad"])
    # cmd_run tries to create scheduler which needs backends → EXIT_INTERNAL_ERROR
    assert result.exit_code == 3


def test_run_with_case_needs_valid_file(runner: CliRunner) -> None:
    """run --case with nonexistent file should fail."""
    result = runner.invoke(main, ["run", "--case", "nonexistent.json"])
    assert result.exit_code == 3


# ── status ──────────────────────────────────────────────────────────────


def test_status_needs_valid_session(runner: CliRunner) -> None:
    """status with a non-existent session should return error."""
    result = runner.invoke(main, ["status", "nonexistent-session"])
    # cmd_status loads config + session store → will not find session
    assert result.exit_code != 0


# ── report ──────────────────────────────────────────────────────────────


def test_report_needs_valid_session(runner: CliRunner) -> None:
    """report with a non-existent session should return error."""
    result = runner.invoke(main, ["report", "nonexistent-session"])
    assert result.exit_code != 0


def test_report_format_option_accepted(runner: CliRunner) -> None:
    """report --format html is accepted as a valid option."""
    result = runner.invoke(main, ["report", "nonexistent-session", "--format", "html"])
    # Option parsing succeeds; the command fails because session doesn't exist
    assert result.exit_code != 0


# ── list-recordings ────────────────────────────────────────────────────


def test_list_recordings_empty(runner: CliRunner) -> None:
    """list-recordings with no recordings shows a message."""
    result = runner.invoke(main, ["list-recordings"])
    # Succeeds (exit 0) even when no recordings
    assert result.exit_code == 0
    assert "No recordings found" in result.output


# ── validate ────────────────────────────────────────────────────────────


def _extract_json(output: str) -> dict:
    """Extract JSON object from CLI output that may contain log lines."""
    import re

    # Strip ANSI escape sequences
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    # Find the first '{' which starts the JSON output
    idx = clean.find("{")
    assert idx >= 0, f"No JSON found in output: {clean[:200]}"
    return json.loads(clean[idx:])


def test_validate_prints_config(runner: CliRunner) -> None:
    """validate loads and prints config as JSON."""
    result = runner.invoke(main, ["validate"])
    assert result.exit_code == 0
    data = _extract_json(result.output)
    assert isinstance(data, dict)
    # Config should have planner/actor/runtime sections
    assert "planner" in data or "runtime" in data


def test_validate_with_config_option(runner: CliRunner) -> None:
    """validate --config loads the specified config file."""
    result = runner.invoke(main, ["--config", "config/model.yaml", "validate"])
    assert result.exit_code == 0
    data = _extract_json(result.output)
    assert isinstance(data, dict)


# ── global options ──────────────────────────────────────────────────────


def test_log_level_option(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--log-level", "DEBUG", "validate"])
    assert result.exit_code == 0
