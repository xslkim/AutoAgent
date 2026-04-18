"""Unit tests for cases/consolidator.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autovisiontest.cases.consolidator import consolidate
from autovisiontest.cases.store import RecordingStore
from autovisiontest.control.actions import Action
from autovisiontest.engine.models import SessionContext, StepRecord, TerminationReason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    goal: str = "open notepad",
    app_path: str = "notepad.exe",
    termination_reason: TerminationReason = TerminationReason.PASS,
    steps: list[StepRecord] | None = None,
) -> SessionContext:
    session = SessionContext(
        goal=goal,
        app_path=app_path,
        termination_reason=termination_reason,
    )
    if steps is not None:
        session.steps = steps
        session.step_count = len(steps)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConsolidator:
    """Tests for the consolidate function."""

    def test_consolidate_from_session(self, tmp_path: Path) -> None:
        """Successful session should produce a TestCase."""
        from unittest.mock import patch

        store = RecordingStore(data_dir=tmp_path)
        steps = [
            StepRecord(
                idx=0,
                planner_intent="click button",
                actor_target_desc="the OK button",
                action=Action(type="click", params={"button": "left"}),
                grounding_confidence=0.8,
            ),
            StepRecord(
                idx=1,
                planner_intent="type text",
                actor_target_desc="",
                action=Action(type="type", params={"text": "hello"}),
                grounding_confidence=None,
            ),
        ]
        session = _make_session(steps=steps)

        with patch("autovisiontest.cases.consolidator.compute_fingerprint", return_value="fp123"):
            case = consolidate(session, store)

        assert case is not None
        assert case.goal == "open notepad"
        assert case.app_config.app_path == "notepad.exe"
        assert len(case.steps) == 2
        assert case.steps[0].action["type"] == "click"
        assert case.steps[1].action["type"] == "type"
        assert case.metadata.step_count == 2

    def test_consolidate_ignores_failed_session(self, tmp_path: Path) -> None:
        """Non-PASS session should return None."""
        store = RecordingStore(data_dir=tmp_path)
        session = _make_session(termination_reason=TerminationReason.CRASH)

        result = consolidate(session, store)
        assert result is None

    def test_consolidate_ignores_max_steps_session(self, tmp_path: Path) -> None:
        """MAX_STEPS session should return None."""
        store = RecordingStore(data_dir=tmp_path)
        session = _make_session(termination_reason=TerminationReason.MAX_STEPS)

        result = consolidate(session, store)
        assert result is None

    def test_consolidate_filters_none_actions(self, tmp_path: Path) -> None:
        """Steps with None action should be filtered out."""
        from unittest.mock import patch

        store = RecordingStore(data_dir=tmp_path)
        steps = [
            StepRecord(idx=0, action=None),
            StepRecord(
                idx=1,
                planner_intent="type",
                action=Action(type="type", params={"text": "hello"}),
            ),
        ]
        session = _make_session(steps=steps)

        with patch("autovisiontest.cases.consolidator.compute_fingerprint", return_value="fp1"):
            case = consolidate(session, store)

        assert case is not None
        assert len(case.steps) == 1

    def test_consolidate_with_ocr_keywords(self, tmp_path: Path) -> None:
        """OCR keywords should be included in expectations."""
        from unittest.mock import patch

        store = RecordingStore(data_dir=tmp_path)
        steps = [
            StepRecord(
                idx=0,
                action=Action(type="click", params={}),
                grounding_confidence=0.9,
            ),
        ]
        session = _make_session(steps=steps)
        ocr_keywords = [["OK", "Cancel"]]

        with patch("autovisiontest.cases.consolidator.compute_fingerprint", return_value="fp1"):
            case = consolidate(session, store, ocr_keywords_per_step=ocr_keywords)

        assert case is not None
        assert case.steps[0].expect.ocr_keywords == ["OK", "Cancel"]

    def test_consolidate_no_valid_steps(self, tmp_path: Path) -> None:
        """Session with no valid steps should return None."""
        store = RecordingStore(data_dir=tmp_path)
        steps = [
            StepRecord(idx=0, action=None),
        ]
        session = _make_session(steps=steps)

        result = consolidate(session, store)
        assert result is None

    def test_consolidate_saves_to_store(self, tmp_path: Path) -> None:
        """Consolidated TestCase should be saved to the store."""
        from unittest.mock import patch

        store = RecordingStore(data_dir=tmp_path)
        steps = [
            StepRecord(
                idx=0,
                action=Action(type="wait", params={"duration_s": 1.0}),
            ),
        ]
        session = _make_session(steps=steps)

        with patch("autovisiontest.cases.consolidator.compute_fingerprint", return_value="fp_save"):
            case = consolidate(session, store)

        assert case is not None
        # Verify it's persisted
        loaded = store.load("fp_save")
        assert loaded is not None
        assert loaded.goal == "open notepad"
