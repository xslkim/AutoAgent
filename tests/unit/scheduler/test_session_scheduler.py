"""Tests for session scheduler and session store.

Tests cover:
- SessionStore: save, load, list_all, delete
- SessionScheduler: start_session, get_status, stop, regression preference
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.cases.schema import AppConfig, CaseMetadata, Step, TestCase
from autovisiontest.engine.models import SessionContext, TerminationReason
from autovisiontest.scheduler.session_scheduler import SessionScheduler
from autovisiontest.scheduler.session_store import (
    SessionRecord,
    SessionStatus,
    SessionStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory."""
    return tmp_path


@pytest.fixture
def session_store(tmp_data_dir: Path) -> SessionStore:
    """Create a SessionStore with a temp directory."""
    return SessionStore(data_dir=tmp_data_dir)


@pytest.fixture
def mock_chat_backend() -> MagicMock:
    """Create a mock ChatBackend."""
    backend = MagicMock()
    backend.chat.return_value = MagicMock(
        content='{"reflection": "done", "done": true}',
        raw={},
        usage=None,
    )
    return backend


@pytest.fixture
def mock_grounding_backend() -> MagicMock:
    """Create a mock GroundingBackend."""
    backend = MagicMock()
    backend.ground.return_value = MagicMock(
        x=100, y=100, confidence=0.9, raw={}
    )
    return backend


@pytest.fixture
def scheduler(
    tmp_data_dir: Path,
    mock_chat_backend: MagicMock,
    mock_grounding_backend: MagicMock,
) -> SessionScheduler:
    """Create a SessionScheduler with mock backends."""
    return SessionScheduler(
        chat_backend=mock_chat_backend,
        grounding_backend=mock_grounding_backend,
        data_dir=tmp_data_dir,
        max_steps=30,
        confidence_threshold=0.6,
    )


def _make_test_case(
    goal: str = "open notepad",
    app_path: str = "C:\\Windows\\notepad.exe",
    fingerprint: str = "abc123def4567890",
) -> TestCase:
    """Create a minimal TestCase for testing."""
    return TestCase(
        goal=goal,
        app_config=AppConfig(app_path=app_path),
        steps=[
            Step(
                idx=0,
                planner_intent="launch",
                target_desc="window",
                action={"type": "click", "params": {"x": 100, "y": 100}},
            )
        ],
        metadata=CaseMetadata(
            fingerprint=fingerprint,
            source_session_id="test-session",
            step_count=1,
        ),
    )


# ===========================================================================
# SessionStore Tests
# ===========================================================================


class TestSessionStore:
    """Tests for SessionStore persistence."""

    def test_save_and_load(self, session_store: SessionStore) -> None:
        """Save a record and load it back."""
        record = SessionRecord(
            session_id="abc123",
            goal="test goal",
            app_path="notepad.exe",
            status=SessionStatus.RUNNING,
        )
        session_store.save(record)

        loaded = session_store.load("abc123")
        assert loaded is not None
        assert loaded.session_id == "abc123"
        assert loaded.goal == "test goal"
        assert loaded.status == SessionStatus.RUNNING

    def test_load_nonexistent(self, session_store: SessionStore) -> None:
        """Loading a nonexistent session returns None."""
        assert session_store.load("nonexistent") is None

    def test_list_all(self, session_store: SessionStore) -> None:
        """list_all returns all saved sessions."""
        for sid in ["s1", "s2", "s3"]:
            session_store.save(
                SessionRecord(session_id=sid, goal=f"goal-{sid}")
            )
        records = session_store.list_all()
        assert len(records) == 3
        ids = {r.session_id for r in records}
        assert ids == {"s1", "s2", "s3"}

    def test_delete(self, session_store: SessionStore) -> None:
        """Delete removes the session record."""
        session_store.save(
            SessionRecord(session_id="to-delete", goal="delete me")
        )
        assert session_store.load("to-delete") is not None

        result = session_store.delete("to-delete")
        assert result is True
        assert session_store.load("to-delete") is None

    def test_delete_nonexistent(self, session_store: SessionStore) -> None:
        """Deleting nonexistent returns False."""
        assert session_store.delete("no-such-session") is False

    def test_save_updates_timestamp(self, session_store: SessionStore) -> None:
        """Saving updates the updated_at field."""
        record = SessionRecord(session_id="ts-test", goal="timing")
        session_store.save(record)

        loaded1 = session_store.load("ts-test")
        assert loaded1 is not None
        ts1 = loaded1.updated_at

        # Small delay then save again
        time.sleep(0.01)
        loaded1.status = SessionStatus.COMPLETED
        session_store.save(loaded1)

        loaded2 = session_store.load("ts-test")
        assert loaded2 is not None
        assert loaded2.updated_at >= ts1


# ===========================================================================
# SessionScheduler Tests
# ===========================================================================


class TestSessionScheduler:
    """Tests for SessionScheduler routing and lifecycle."""

    def test_start_returns_session_id(self, scheduler: SessionScheduler) -> None:
        """start_session returns a non-empty session_id."""
        # Mock runners to avoid actual execution
        with patch.object(scheduler, "_run_session"):
            session_id = scheduler.start_session(
                goal="test goal", app_path="notepad.exe"
            )
        assert len(session_id) == 12
        assert session_id.isalnum()

    @patch("autovisiontest.scheduler.session_scheduler.SessionScheduler._run_session")
    def test_get_status_pending_then_running_then_completed(
        self,
        mock_run: MagicMock,
        scheduler: SessionScheduler,
    ) -> None:
        """Session transitions PENDING → RUNNING → COMPLETED."""
        # The actual _run_session is called in background thread,
        # but we mock it. The initial status is RUNNING.
        session_id = scheduler.start_session(
            goal="test goal", app_path="notepad.exe"
        )

        # After start_session, status should be RUNNING
        status = scheduler.get_status(session_id)
        assert status == SessionStatus.RUNNING

        # Simulate completion by updating record directly
        record = scheduler._session_store.load(session_id)
        assert record is not None
        record.status = SessionStatus.COMPLETED
        scheduler._session_store.save(record)

        status = scheduler.get_status(session_id)
        assert status == SessionStatus.COMPLETED

    def test_get_status_nonexistent(self, scheduler: SessionScheduler) -> None:
        """Nonexistent session returns None."""
        assert scheduler.get_status("nonexistent") is None

    def test_stop_running_session(self, scheduler: SessionScheduler) -> None:
        """stop() returns True for a running session."""
        with patch.object(scheduler, "_run_session"):
            session_id = scheduler.start_session(
                goal="test goal", app_path="notepad.exe"
            )

        result = scheduler.stop(session_id)
        assert result is True
        assert session_id in scheduler._stop_requested

    def test_stop_nonexistent(self, scheduler: SessionScheduler) -> None:
        """stop() returns False for nonexistent session."""
        result = scheduler.stop("nonexistent")
        assert result is False

    def test_stop_completed_session(self, scheduler: SessionScheduler) -> None:
        """stop() returns False for a completed session."""
        with patch.object(scheduler, "_run_session"):
            session_id = scheduler.start_session(
                goal="test goal", app_path="notepad.exe"
            )

        # Mark as completed
        record = scheduler._session_store.load(session_id)
        assert record is not None
        record.status = SessionStatus.COMPLETED
        scheduler._session_store.save(record)

        result = scheduler.stop(session_id)
        assert result is False

    def test_regression_preferred_over_exploration(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """When a recording exists, session runs in regression mode."""
        # Save a recording to the store
        case = _make_test_case()
        scheduler._store.save(case)

        with patch.object(scheduler, "_run_session") as mock_run:
            session_id = scheduler.start_session(
                goal="open notepad",
                app_path="C:\\Windows\\notepad.exe",
            )

        # Verify the record has regression mode
        record = scheduler._session_store.load(session_id)
        assert record is not None
        assert record.mode == "regression"
        assert record.fingerprint == case.metadata.fingerprint

    def test_exploratory_mode_when_no_recording(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """When no recording exists, session runs in exploratory mode."""
        with patch.object(scheduler, "_run_session"):
            session_id = scheduler.start_session(
                goal="brand new goal", app_path="notepad.exe"
            )

        record = scheduler._session_store.load(session_id)
        assert record is not None
        assert record.mode == "exploratory"
        assert record.fingerprint is None

    def test_get_report_none_when_not_completed(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """get_report returns None for sessions without reports."""
        with patch.object(scheduler, "_run_session"):
            session_id = scheduler.start_session(
                goal="test goal", app_path="notepad.exe"
            )

        assert scheduler.get_report(session_id) is None

    def test_get_report_nonexistent(self, scheduler: SessionScheduler) -> None:
        """get_report returns None for nonexistent session."""
        assert scheduler.get_report("nonexistent") is None

    def test_shutdown(self, scheduler: SessionScheduler) -> None:
        """shutdown() does not raise."""
        scheduler.shutdown()

    def test_get_session_context_none(self, scheduler: SessionScheduler) -> None:
        """get_session_context returns None when no context saved."""
        with patch.object(scheduler, "_run_session"):
            session_id = scheduler.start_session(
                goal="test goal", app_path="notepad.exe"
            )

        assert scheduler.get_session_context(session_id) is None
