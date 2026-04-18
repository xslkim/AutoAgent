"""Tests for MCP Server tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autovisiontest.interfaces.mcp_server import (
    _set_scheduler,
    get_session_report,
    get_session_status,
    invalidate_recording,
    list_recordings,
    start_test_session,
    stop_session,
)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_scheduler():
    """Mock SessionScheduler."""
    scheduler = MagicMock()
    scheduler.start_session.return_value = "test-session-001"
    scheduler._data_dir = "/tmp/autovt-test"
    scheduler.get_report.return_value = {
        "protocol_version": "2.0",
        "session": {"id": "test-session-001"},
    }
    scheduler.stop.return_value = True
    scheduler.invalidate_recording.return_value = True
    return scheduler


@pytest.fixture(autouse=True)
def setup_scheduler(mock_scheduler):
    """Set scheduler before each test."""
    _set_scheduler(mock_scheduler)
    yield
    _set_scheduler(None)


# ── Tool tests ──────────────────────────────────────────────────────────


class TestListTools:
    """Verify all tools are registered."""

    def test_start_test_session_callable(self) -> None:
        result = start_test_session("open notepad", "notepad.exe")
        data = json.loads(result)
        assert "session_id" in data

    def test_get_session_status_callable(self, mock_scheduler, tmp_path: Path) -> None:
        from autovisiontest.scheduler.session_store import SessionRecord, SessionStatus, SessionStore

        mock_scheduler._data_dir = str(tmp_path)
        store = SessionStore(data_dir=tmp_path)
        store.save(SessionRecord(session_id="test-session-001", status=SessionStatus.RUNNING))

        result = get_session_status("test-session-001")
        data = json.loads(result)
        assert "status" in data

    def test_get_session_report_callable(self) -> None:
        result = get_session_report("test-session-001")
        data = json.loads(result)
        assert "protocol_version" in data

    def test_stop_session_callable(self) -> None:
        result = stop_session("test-session-001")
        data = json.loads(result)
        assert "stopped" in data

    def test_list_recordings_callable(self, mock_scheduler) -> None:
        mock_scheduler._store.list_all.return_value = []
        result = list_recordings()
        data = json.loads(result)
        assert isinstance(data, list)

    def test_invalidate_recording_callable(self) -> None:
        result = invalidate_recording("abc123")
        data = json.loads(result)
        assert "deleted" in data


class TestStartTestSession:
    def test_start_test_session_returns_id(self, mock_scheduler) -> None:
        result = start_test_session("open notepad", "notepad.exe")
        data = json.loads(result)
        assert data["session_id"] == "test-session-001"
        mock_scheduler.start_session.assert_called_once()

    def test_start_test_session_with_args(self, mock_scheduler) -> None:
        result = start_test_session("open notepad", "notepad.exe", "--arg1")
        data = json.loads(result)
        assert data["session_id"] == "test-session-001"

    def test_start_test_session_no_scheduler(self) -> None:
        _set_scheduler(None)
        result = start_test_session("open notepad", "notepad.exe")
        data = json.loads(result)
        assert "error" in data


class TestGetSessionStatus:
    def test_get_status_existing_session(self, mock_scheduler, tmp_path: Path) -> None:
        from autovisiontest.scheduler.session_store import SessionRecord, SessionStatus, SessionStore

        mock_scheduler._data_dir = str(tmp_path)
        store = SessionStore(data_dir=tmp_path)
        record = SessionRecord(
            session_id="sess-001",
            goal="test",
            app_path="notepad.exe",
            status=SessionStatus.COMPLETED,
            termination_reason="PASS",
        )
        store.save(record)

        result = get_session_status("sess-001")
        data = json.loads(result)
        assert data["status"] == "COMPLETED"

    def test_get_status_not_found(self, mock_scheduler, tmp_path: Path) -> None:
        mock_scheduler._data_dir = str(tmp_path)
        result = get_session_status("nonexistent")
        data = json.loads(result)
        assert "error" in data


class TestGetSessionReport:
    def test_get_session_report_includes_resources(self, mock_scheduler) -> None:
        result = get_session_report("test-session-001")
        data = json.loads(result)
        assert "protocol_version" in data
        assert data["protocol_version"] == "2.0"

    def test_get_session_report_not_found(self, mock_scheduler) -> None:
        mock_scheduler.get_report.return_value = None
        result = get_session_report("nonexistent")
        data = json.loads(result)
        assert "error" in data


class TestStopSession:
    def test_stop_session_success(self, mock_scheduler) -> None:
        result = stop_session("test-session-001")
        data = json.loads(result)
        assert data["stopped"] is True

    def test_stop_session_not_running(self, mock_scheduler) -> None:
        mock_scheduler.stop.return_value = False
        result = stop_session("nonexistent")
        data = json.loads(result)
        assert data["stopped"] is False


class TestListRecordings:
    def test_list_recordings_empty(self, mock_scheduler) -> None:
        mock_scheduler._store.list_all.return_value = []
        result = list_recordings()
        data = json.loads(result)
        assert data == []

    def test_list_recordings_with_data(self, mock_scheduler) -> None:
        case = MagicMock()
        case.metadata.fingerprint = "abc123"
        case.goal = "open notepad"
        case.app_config.app_path = "notepad.exe"
        case.steps = [MagicMock(), MagicMock()]
        mock_scheduler._store.list_all.return_value = [case]

        result = list_recordings()
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["fingerprint"] == "abc123"


class TestInvalidateRecording:
    def test_invalidate_success(self, mock_scheduler) -> None:
        result = invalidate_recording("abc123")
        data = json.loads(result)
        assert data["deleted"] is True

    def test_invalidate_not_found(self, mock_scheduler) -> None:
        mock_scheduler.invalidate_recording.return_value = False
        result = invalidate_recording("nonexistent")
        data = json.loads(result)
        assert data["deleted"] is False
