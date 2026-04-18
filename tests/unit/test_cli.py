"""Tests for the AutoVisionTest CLI."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from autovisiontest.cli import main


# Check if config module is available (T A.2 may not be merged yet)
try:
    from autovisiontest.config.loader import load_config  # noqa: F401

    _CONFIG_AVAILABLE = True
except ImportError:
    _CONFIG_AVAILABLE = False


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


def test_run_with_goal_stub(runner: CliRunner) -> None:
    result = runner.invoke(main, ["run", "--goal", "open notepad"])
    assert result.exit_code == 0
    assert "Not implemented" in result.output


def test_run_with_case_stub(runner: CliRunner) -> None:
    result = runner.invoke(main, ["run", "--case", "recording.json"])
    assert result.exit_code == 0
    assert "Not implemented" in result.output


# ── status ──────────────────────────────────────────────────────────────


def test_status_stub(runner: CliRunner) -> None:
    result = runner.invoke(main, ["status", "abc-123"])
    assert result.exit_code == 0
    assert "Not implemented" in result.output


# ── report ──────────────────────────────────────────────────────────────


def test_report_stub(runner: CliRunner) -> None:
    result = runner.invoke(main, ["report", "abc-123"])
    assert result.exit_code == 0
    assert "Not implemented" in result.output


def test_report_format_option(runner: CliRunner) -> None:
    result = runner.invoke(main, ["report", "abc-123", "--format", "html"])
    assert result.exit_code == 0
    assert "html" in result.output


# ── list-recordings ────────────────────────────────────────────────────


def test_list_recordings_stub(runner: CliRunner) -> None:
    result = runner.invoke(main, ["list-recordings"])
    assert result.exit_code == 0
    assert "Not implemented" in result.output


# ── validate ────────────────────────────────────────────────────────────


def test_validate_prints_config(runner: CliRunner) -> None:
    result = runner.invoke(main, ["validate"])
    assert result.exit_code == 0
    if _CONFIG_AVAILABLE:
        data = json.loads(result.output)
        assert "planner" in data or "runtime" in data
    else:
        assert "Configuration module not available" in result.output


def test_validate_with_config_option(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--config", "config/model.yaml", "validate"])
    assert result.exit_code == 0
    if _CONFIG_AVAILABLE:
        data = json.loads(result.output)
        assert isinstance(data, dict)
    else:
        assert "Configuration module not available" in result.output


# ── global options ──────────────────────────────────────────────────────


def test_log_level_option(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--log-level", "DEBUG", "validate"])
    assert result.exit_code == 0
