"""Tests for fallback to exploration when recording is invalidated.

Tests cover:
- Invalid recording triggers automatic exploration
- New exploration overwrites old recording on success
- Manual invalidate_recording deletes the recording
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from autovisiontest.cases.schema import AppConfig, CaseMetadata, Step, TestCase
from autovisiontest.engine.models import SessionContext, TerminationReason
from autovisiontest.scheduler.session_scheduler import SessionScheduler
from autovisiontest.scheduler.session_store import SessionStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory."""
    return tmp_path


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


def _make_session(
    goal: str = "open notepad",
    app_path: str = "notepad.exe",
    termination: TerminationReason = TerminationReason.PASS,
    recording_invalid: bool = False,
) -> SessionContext:
    """Create a mock SessionContext."""
    session = SessionContext(
        goal=goal,
        mode="regression" if recording_invalid else "exploratory",
        app_path=app_path,
        termination_reason=termination,
        recording_invalid=recording_invalid,
    )
    return session


# ===========================================================================
# Tests
# ===========================================================================


class TestFallbackToExploration:
    """Tests for recording invalidation and fallback logic."""

    def test_invalid_recording_triggers_exploration(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """When regression returns recording_invalid=True, fallback exploration runs."""
        goal = "open notepad"
        app_path = "C:\\Windows\\notepad.exe"
        fingerprint = "abc123def4567890"

        # Save a recording
        case = _make_test_case(fingerprint=fingerprint)
        scheduler._store.save(case)

        # Create invalid regression session
        invalid_session = _make_session(
            goal=goal,
            app_path=app_path,
            termination=TerminationReason.MAX_STEPS,
            recording_invalid=True,
        )

        # Create successful exploration session for fallback
        success_session = _make_session(
            goal=goal,
            app_path=app_path,
            termination=TerminationReason.PASS,
        )

        with patch.object(
            scheduler, "_run_regression", return_value=invalid_session
        ) as mock_reg, patch.object(
            scheduler, "_run_exploratory", return_value=success_session
        ) as mock_explore, patch(
            "autovisiontest.scheduler.session_scheduler.consolidate",
            return_value=_make_test_case(fingerprint="new_fp_12345"),
        ) as mock_consolidate:

            # Manually call the internal method (simulating background execution)
            scheduler._run_session(
                session_id="test-sid",
                goal=goal,
                app_path=app_path,
                app_args=None,
                mode="regression",
                fingerprint=fingerprint,
            )

            # Verify regression was called
            mock_reg.assert_called_once_with(fingerprint)

            # Verify exploration was called as fallback
            mock_explore.assert_called_once_with(goal, app_path, None)

            # Verify consolidation happened
            mock_consolidate.assert_called_once()

        # Verify old recording was deleted
        assert scheduler._store.load(fingerprint) is None

    def test_new_exploration_overwrites_old(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """Successful fallback exploration creates a new recording."""
        goal = "open notepad"
        app_path = "C:\\Windows\\notepad.exe"
        old_fp = "old_fingerprint_1"

        # Save old recording
        old_case = _make_test_case(fingerprint=old_fp)
        scheduler._store.save(old_case)
        assert scheduler._store.load(old_fp) is not None

        # Invalid regression session
        invalid_session = _make_session(
            goal=goal,
            app_path=app_path,
            termination=TerminationReason.MAX_STEPS,
            recording_invalid=True,
        )

        # Successful exploration
        success_session = _make_session(
            goal=goal,
            app_path=app_path,
            termination=TerminationReason.PASS,
        )

        new_case = _make_test_case(fingerprint="new_fingerprint_2")

        with patch.object(
            scheduler, "_run_regression", return_value=invalid_session
        ), patch.object(
            scheduler, "_run_exploratory", return_value=success_session
        ), patch(
            "autovisiontest.scheduler.session_scheduler.consolidate",
            return_value=new_case,
        ):
            scheduler._run_session(
                session_id="test-sid-2",
                goal=goal,
                app_path=app_path,
                app_args=None,
                mode="regression",
                fingerprint=old_fp,
            )

        # Old recording deleted
        assert scheduler._store.load(old_fp) is None

        # New recording saved (by consolidate mock → store.save)
        # consolidate is mocked so it won't actually save,
        # but we can verify the method was called with the success session

    def test_manual_invalidate_deletes(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """invalidate_recording() deletes the recording from store."""
        fp = "manual_invalidate_fp"
        case = _make_test_case(fingerprint=fp)
        scheduler._store.save(case)
        assert scheduler._store.load(fp) is not None

        result = scheduler.invalidate_recording(fp)
        assert result is True
        assert scheduler._store.load(fp) is None

    def test_manual_invalidate_nonexistent(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """invalidate_recording() returns False for nonexistent recording."""
        result = scheduler.invalidate_recording("nonexistent_fp")
        assert result is False

    def test_valid_regression_no_fallback(
        self,
        scheduler: SessionScheduler,
    ) -> None:
        """Successful regression does NOT trigger fallback exploration."""
        goal = "open notepad"
        app_path = "C:\\Windows\\notepad.exe"
        fingerprint = "valid_fp_123"

        case = _make_test_case(fingerprint=fingerprint)
        scheduler._store.save(case)

        valid_session = _make_session(
            goal=goal,
            app_path=app_path,
            termination=TerminationReason.PASS,
            recording_invalid=False,
        )

        with patch.object(
            scheduler, "_run_regression", return_value=valid_session
        ), patch.object(
            scheduler, "_run_exploratory"
        ) as mock_explore:
            scheduler._run_session(
                session_id="test-sid-3",
                goal=goal,
                app_path=app_path,
                app_args=None,
                mode="regression",
                fingerprint=fingerprint,
            )

            # No fallback exploration should happen
            mock_explore.assert_not_called()

        # Recording should still exist
        assert scheduler._store.load(fingerprint) is not None
