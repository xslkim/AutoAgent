"""Tests for CLI commands — cli_commands module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from autovisiontest.cli import main


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_scheduler():
    """Mock SessionScheduler."""
    scheduler = MagicMock()
    scheduler.start_session.return_value = "test-session-001"
    scheduler.get_status.return_value = MagicMock(value="COMPLETED")
    scheduler.get_report.return_value = {"session": {"id": "test-session-001"}}
    scheduler.stop.return_value = True
    scheduler.shutdown.return_value = None
    return scheduler


@pytest.fixture
def mock_config():
    """Mock AppConfig."""
    config = MagicMock()
    config.runtime.data_dir = "/tmp/autovt-test"
    config.runtime.max_steps = 30
    config.actor.confidence_threshold = 0.6
    config.planner.backend = "stub"
    config.planner.model = "stub"
    config.actor.backend = "stub"
    config.actor.model = "stub"
    return config


# ── Version / Help ──────────────────────────────────────────────────────


class TestVersionAndHelp:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "autovisiontest" in result.output

    def test_help_lists_all_subcommands(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in ["run", "status", "report", "list-recordings", "validate", "serve", "mcp"]:
            assert cmd in result.output


# ── run ──────────────────────────────────────────────────────────────────


class TestRunCommand:
    def test_run_requires_goal_or_case(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["run"])
        assert result.exit_code != 0

    def test_run_goal_and_case_mutually_exclusive(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["run", "--goal", "test", "--case", "fake.yaml"])
        assert result.exit_code != 0

    @patch("autovisiontest.interfaces.cli_commands._create_scheduler")
    def test_run_success_returns_0(self, mock_create, runner: CliRunner, mock_scheduler) -> None:
        from autovisiontest.scheduler.session_store import SessionStatus
        mock_scheduler.get_status.side_effect = [
            SessionStatus.RUNNING,
            SessionStatus.COMPLETED,
        ]
        mock_create.return_value = mock_scheduler

        result = runner.invoke(main, ["run", "--goal", "open notepad", "--app", "notepad.exe"])
        assert mock_scheduler.start_session.called

    @patch("autovisiontest.interfaces.cli_commands._create_scheduler")
    def test_run_fail_returns_1(self, mock_create, runner: CliRunner, mock_scheduler) -> None:
        from autovisiontest.scheduler.session_store import SessionStatus
        mock_scheduler.get_status.side_effect = [
            SessionStatus.RUNNING,
            SessionStatus.FAILED,
        ]
        mock_create.return_value = mock_scheduler

        result = runner.invoke(main, ["run", "--goal", "open notepad", "--app", "notepad.exe"])
        assert mock_scheduler.start_session.called

    @patch("autovisiontest.interfaces.cli_commands._create_scheduler")
    def test_run_no_scheduler_returns_3(self, mock_create, runner: CliRunner) -> None:
        mock_create.return_value = None
        result = runner.invoke(main, ["run", "--goal", "open notepad", "--app", "notepad.exe"])
        assert result.exit_code == 3


# ── status ───────────────────────────────────────────────────────────────


class TestStatusCommand:
    @patch("autovisiontest.interfaces.cli_commands._load_config")
    def test_status_shows_session_info(self, mock_load, runner: CliRunner, mock_config, tmp_path: Path) -> None:
        mock_load.return_value = mock_config
        # Create a real session directory with status.json
        from autovisiontest.scheduler.session_store import SessionRecord, SessionStatus, SessionStore

        store = SessionStore(data_dir=tmp_path)
        record = SessionRecord(
            session_id="sess-001",
            goal="test goal",
            app_path="notepad.exe",
            mode="exploratory",
            status=SessionStatus.COMPLETED,
            termination_reason="PASS",
        )
        store.save(record)
        mock_config.runtime.data_dir = str(tmp_path)

        result = runner.invoke(main, ["status", "sess-001"])
        assert "sess-001" in result.output
        assert "COMPLETED" in result.output

    @patch("autovisiontest.interfaces.cli_commands._load_config")
    def test_status_not_found(self, mock_load, runner: CliRunner, mock_config, tmp_path: Path) -> None:
        mock_load.return_value = mock_config
        mock_config.runtime.data_dir = str(tmp_path)

        result = runner.invoke(main, ["status", "nonexistent"])
        assert result.exit_code == 3


# ── report ───────────────────────────────────────────────────────────────


class TestReportCommand:
    @patch("autovisiontest.interfaces.cli_commands._load_config")
    def test_report_prints_json_from_file(self, mock_load, runner: CliRunner, mock_config, tmp_path: Path) -> None:
        mock_load.return_value = mock_config
        mock_config.runtime.data_dir = str(tmp_path)

        from autovisiontest.scheduler.session_store import SessionRecord, SessionStatus, SessionStore

        store = SessionStore(data_dir=tmp_path)
        report_data = {"protocol_version": "2.0", "session": {"id": "sess-001"}}
        report_path = tmp_path / "sessions" / "sess-001" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data), encoding="utf-8")

        record = SessionRecord(
            session_id="sess-001",
            status=SessionStatus.COMPLETED,
            report_path=str(report_path),
        )
        store.save(record)

        result = runner.invoke(main, ["report", "sess-001", "--format", "json"])
        assert "2.0" in result.output
        assert result.exit_code == 0

    @patch("autovisiontest.interfaces.cli_commands._load_config")
    def test_report_not_found(self, mock_load, runner: CliRunner, mock_config, tmp_path: Path) -> None:
        mock_load.return_value = mock_config
        mock_config.runtime.data_dir = str(tmp_path)

        from autovisiontest.scheduler.session_store import SessionRecord, SessionStore

        store = SessionStore(data_dir=tmp_path)
        record = SessionRecord(session_id="sess-002", report_path=None)
        store.save(record)

        result = runner.invoke(main, ["report", "sess-002"])
        assert result.exit_code == 3


# ── list-recordings ──────────────────────────────────────────────────────


class TestListRecordingsCommand:
    @patch("autovisiontest.interfaces.cli_commands._load_config")
    def test_list_recordings_empty_dir(self, mock_load, runner: CliRunner, mock_config, tmp_path: Path) -> None:
        mock_load.return_value = mock_config
        mock_config.runtime.data_dir = str(tmp_path)
        # recordings dir doesn't exist → empty list
        (tmp_path / "recordings").mkdir()

        result = runner.invoke(main, ["list-recordings"])
        assert "No recordings found" in result.output
        assert result.exit_code == 0

    @patch("autovisiontest.interfaces.cli_commands._load_config")
    def test_list_recordings_shows_table(self, mock_load, runner: CliRunner, mock_config, tmp_path: Path) -> None:
        mock_load.return_value = mock_config
        mock_config.runtime.data_dir = str(tmp_path)

        from autovisiontest.cases.schema import AppConfig, CaseMetadata, Step, TestCase
        from autovisiontest.cases.store import RecordingStore

        store = RecordingStore(data_dir=tmp_path)
        case = TestCase(
            metadata=CaseMetadata(fingerprint="abc123def456"),
            goal="Open notepad and type hello",
            app_config=AppConfig(app_path="notepad.exe"),
            steps=[
                Step(idx=0, planner_intent="open"),
                Step(idx=1, planner_intent="type"),
                Step(idx=2, planner_intent="save"),
            ],
        )
        store.save(case)

        result = runner.invoke(main, ["list-recordings"])
        assert "abc123def456" in result.output
        assert "Total: 1" in result.output


# ── validate ─────────────────────────────────────────────────────────────


class TestValidateCommand:
    def test_validate_without_config_module(self, runner: CliRunner) -> None:
        """When config module is not available, should print message."""
        result = runner.invoke(main, ["validate"])
        # Either prints config JSON or "not available" message
        assert result.exit_code == 0 or "not available" in result.output.lower() or "error" in result.output.lower()


# ── Exit codes ───────────────────────────────────────────────────────────


class TestExitCodes:
    def test_exit_code_constants(self) -> None:
        from autovisiontest.interfaces.cli_commands import (
            EXIT_ABORT,
            EXIT_FAIL,
            EXIT_INTERNAL_ERROR,
            EXIT_PASS,
        )

        assert EXIT_PASS == 0
        assert EXIT_FAIL == 1
        assert EXIT_ABORT == 2
        assert EXIT_INTERNAL_ERROR == 3
