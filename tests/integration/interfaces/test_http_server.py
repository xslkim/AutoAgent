"""Tests for HTTP API server — using FastAPI TestClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autovisiontest.interfaces.http_server import create_app


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


@pytest.fixture
def app_with_scheduler(mock_scheduler):
    """Create app with mocked scheduler."""
    app = create_app(config_path=None)
    # Replace the scheduler
    import autovisiontest.interfaces.http_server as server_mod
    server_mod._scheduler = mock_scheduler
    return app


@pytest.fixture
def client(app_with_scheduler) -> TestClient:
    return TestClient(app_with_scheduler)


@pytest.fixture
def app_no_scheduler():
    """Create app with no scheduler (simulates missing backends)."""
    app = create_app(config_path=None)
    import autovisiontest.interfaces.http_server as server_mod
    server_mod._scheduler = None
    return app


@pytest.fixture
def client_no_scheduler(app_no_scheduler) -> TestClient:
    return TestClient(app_no_scheduler)


# ── Health ──────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ── Create session ──────────────────────────────────────────────────────


class TestCreateSession:
    def test_create_session(self, client: TestClient, mock_scheduler) -> None:
        response = client.post(
            "/v1/sessions",
            json={
                "goal": "open notepad",
                "app_path": "notepad.exe",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["session_id"] == "test-session-001"
        mock_scheduler.start_session.assert_called_once()

    def test_create_session_with_args(self, client: TestClient, mock_scheduler) -> None:
        response = client.post(
            "/v1/sessions",
            json={
                "goal": "open notepad",
                "app_path": "notepad.exe",
                "app_args": ["--arg1"],
                "timeout_ms": 30000,
            },
        )
        assert response.status_code == 200

    def test_create_session_no_scheduler(self, client_no_scheduler: TestClient) -> None:
        response = client_no_scheduler.post(
            "/v1/sessions",
            json={"goal": "test", "app_path": "test.exe"},
        )
        assert response.status_code == 503


# ── Get status ──────────────────────────────────────────────────────────


class TestGetStatus:
    def test_get_status_not_found_404(self, client: TestClient, mock_scheduler, tmp_path: Path) -> None:
        # Use real SessionStore with empty dir
        from autovisiontest.scheduler.session_store import SessionStore

        mock_scheduler._data_dir = str(tmp_path)

        response = client.get("/v1/sessions/nonexistent/status")
        assert response.status_code == 404

    def test_get_status_existing_session(self, client: TestClient, mock_scheduler, tmp_path: Path) -> None:
        from autovisiontest.scheduler.session_store import SessionRecord, SessionStatus, SessionStore

        mock_scheduler._data_dir = str(tmp_path)
        store = SessionStore(data_dir=tmp_path)
        record = SessionRecord(
            session_id="sess-001",
            goal="test",
            app_path="notepad.exe",
            mode="exploratory",
            status=SessionStatus.COMPLETED,
            termination_reason="PASS",
        )
        store.save(record)

        response = client.get("/v1/sessions/sess-001/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["session_id"] == "sess-001"


# ── Get report ──────────────────────────────────────────────────────────


class TestGetReport:
    def test_get_report(self, client: TestClient, mock_scheduler) -> None:
        response = client.get("/v1/sessions/test-session-001/report")
        assert response.status_code == 200
        data = response.json()
        assert data["protocol_version"] == "2.0"

    def test_get_report_not_found(self, client: TestClient, mock_scheduler) -> None:
        mock_scheduler.get_report.return_value = None
        response = client.get("/v1/sessions/nonexistent/report")
        assert response.status_code == 404


# ── Stop session ────────────────────────────────────────────────────────


class TestStopSession:
    def test_stop_session(self, client: TestClient, mock_scheduler) -> None:
        response = client.post("/v1/sessions/test-session-001/stop")
        assert response.status_code == 200
        assert response.json()["stopped"] is True

    def test_stop_session_not_found(self, client: TestClient, mock_scheduler) -> None:
        mock_scheduler.stop.return_value = False
        response = client.post("/v1/sessions/nonexistent/stop")
        assert response.status_code == 404


# ── List recordings ─────────────────────────────────────────────────────


class TestListRecordings:
    def test_list_recordings_empty(self, client: TestClient, mock_scheduler) -> None:
        mock_scheduler._store.list_all.return_value = []
        response = client.get("/v1/recordings")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_recordings_with_data(self, client: TestClient, mock_scheduler) -> None:
        case = MagicMock()
        case.metadata.fingerprint = "abc123"
        case.goal = "open notepad"
        case.app_config.app_path = "notepad.exe"
        case.steps = [MagicMock(), MagicMock()]
        mock_scheduler._store.list_all.return_value = [case]

        response = client.get("/v1/recordings")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["fingerprint"] == "abc123"


# ── Delete recording ────────────────────────────────────────────────────


class TestDeleteRecording:
    def test_delete_recording(self, client: TestClient, mock_scheduler) -> None:
        response = client.delete("/v1/recordings/abc123")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    def test_delete_recording_not_found(self, client: TestClient, mock_scheduler) -> None:
        mock_scheduler.invalidate_recording.return_value = False
        response = client.delete("/v1/recordings/nonexistent")
        assert response.status_code == 404
