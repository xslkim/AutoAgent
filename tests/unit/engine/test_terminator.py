"""Unit tests for engine/terminator.py."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autovisiontest.control.process import AppHandle
from autovisiontest.engine.models import SessionContext, StepRecord, TerminationReason
from autovisiontest.engine.terminator import Terminator
from autovisiontest.control.actions import Action
from autovisiontest.perception.change_detector import ChangeDetector
from autovisiontest.perception.facade import FrameSnapshot
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ocr_item(text: str, x: int = 0, y: int = 0, w: int = 50, h: int = 20) -> OCRItem:
    return OCRItem(text=text, bbox=BoundingBox(x=x, y=y, w=w, h=h), confidence=0.95)


def _make_ocr(items: list[OCRItem] | None = None) -> OCRResult:
    if items is None:
        items = []
    return OCRResult(items=items, image_size=(1920, 1080))


def _make_snapshot(ocr: OCRResult | None = None, t: float | None = None) -> FrameSnapshot:
    if ocr is None:
        ocr = _make_ocr()
    if t is None:
        t = time.time()
    return FrameSnapshot(
        screenshot=np.zeros((1080, 1920, 3), dtype=np.uint8),
        screenshot_png=b"\x89PNG",
        ocr=ocr,
        timestamp=t,
    )


def _make_app_handle(alive: bool = True) -> AppHandle:
    """Create a mock AppHandle."""
    mock_popen = MagicMock()
    mock_popen.poll.return_value = None if alive else 0
    handle = AppHandle(pid=1234, popen=mock_popen, exe_name="test.exe")
    return handle


def _make_step(action: Action | None = None) -> StepRecord:
    return StepRecord(idx=0, action=action)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTerminator:
    """Tests for the Terminator class."""

    def test_crash_detected(self) -> None:
        """T1: App not alive → CRASH."""
        handle = _make_app_handle(alive=False)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=30, change_detector=detector)
        session = SessionContext(step_count=5)
        snapshot = _make_snapshot()

        result = terminator.check(session, snapshot)
        assert result == TerminationReason.CRASH

    def test_max_steps_triggered(self) -> None:
        """T5: step_count >= max_steps → MAX_STEPS."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=10, change_detector=detector)
        session = SessionContext(step_count=10)
        snapshot = _make_snapshot()

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result == TerminationReason.MAX_STEPS

    def test_error_dialog_triggered(self) -> None:
        """T4: Error dialog in OCR → ERROR_DIALOG."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=30, change_detector=detector)

        # Create OCR with error keyword + button in upper half + nearby
        ocr = _make_ocr([
            _make_ocr_item("错误", x=400, y=200),
            _make_ocr_item("确定", x=420, y=220),
        ])
        session = SessionContext(step_count=5)
        snapshot = _make_snapshot(ocr=ocr)

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result == TerminationReason.ERROR_DIALOG

    def test_stuck_triggered(self) -> None:
        """T6: Screen static over window → STUCK."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector(window_seconds=5.0, static_threshold=0.99)
        terminator = Terminator(app_handle=handle, max_steps=30, change_detector=detector)

        # Push identical frames into detector
        now = time.time()
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for i in range(5):
            detector.push(img, t=now - 4.0 + i * 1.0)

        session = SessionContext(step_count=5)
        snapshot = _make_snapshot(t=now)

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result == TerminationReason.STUCK

    def test_no_progress_triggered(self) -> None:
        """T7: Repeated identical actions → NO_PROGRESS."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(
            app_handle=handle,
            max_steps=30,
            change_detector=detector,
            no_progress_window=3,
        )

        action = Action(type="click", params={"button": "left"})
        steps = [
            StepRecord(idx=i, action=action.model_copy())
            for i in range(3)
        ]
        session = SessionContext(step_count=3, steps=steps)
        snapshot = _make_snapshot()

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result == TerminationReason.NO_PROGRESS

    def test_no_progress_not_triggered_with_different_actions(self) -> None:
        """T7: Different actions should not trigger NO_PROGRESS."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(
            app_handle=handle,
            max_steps=30,
            change_detector=detector,
            no_progress_window=3,
        )

        steps = [
            StepRecord(idx=0, action=Action(type="click", params={"button": "left"})),
            StepRecord(idx=1, action=Action(type="type", params={"text": "hello"})),
            StepRecord(idx=2, action=Action(type="click", params={"button": "left"})),
        ]
        session = SessionContext(step_count=3, steps=steps)
        snapshot = _make_snapshot()

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result is None

    def test_normal_returns_none(self) -> None:
        """No termination condition met → None."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=30, change_detector=detector)

        session = SessionContext(step_count=5)
        snapshot = _make_snapshot()

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result is None

    def test_priority_crash_over_error_dialog(self) -> None:
        """T1 (crash) should be checked before T4 (error dialog)."""
        handle = _make_app_handle(alive=False)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=30, change_detector=detector)

        # OCR has an error dialog
        ocr = _make_ocr([
            _make_ocr_item("错误", x=400, y=200),
            _make_ocr_item("确定", x=420, y=220),
        ])
        session = SessionContext(step_count=5)
        snapshot = _make_snapshot(ocr=ocr)

        result = terminator.check(session, snapshot)
        assert result == TerminationReason.CRASH

    def test_priority_error_dialog_over_max_steps(self) -> None:
        """T4 (error dialog) should be checked before T5 (max steps)."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=5, change_detector=detector)

        ocr = _make_ocr([
            _make_ocr_item("错误", x=400, y=200),
            _make_ocr_item("确定", x=420, y=220),
        ])
        session = SessionContext(step_count=10)
        snapshot = _make_snapshot(ocr=ocr)

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result == TerminationReason.ERROR_DIALOG

    def test_ocr_parameter_override(self) -> None:
        """check() should use the ocr parameter when provided."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(app_handle=handle, max_steps=30, change_detector=detector)

        # Default OCR (no error), but override OCR has error dialog
        default_ocr = _make_ocr()
        override_ocr = _make_ocr([
            _make_ocr_item("错误", x=400, y=200),
            _make_ocr_item("确定", x=420, y=220),
        ])

        session = SessionContext(step_count=5)
        snapshot = _make_snapshot(ocr=default_ocr)

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot, ocr=override_ocr)
        assert result == TerminationReason.ERROR_DIALOG

    def test_no_progress_with_none_action_in_window(self) -> None:
        """NO_PROGRESS should not trigger if any step in window has None action."""
        handle = _make_app_handle(alive=True)
        detector = ChangeDetector()
        terminator = Terminator(
            app_handle=handle,
            max_steps=30,
            change_detector=detector,
            no_progress_window=3,
        )

        action = Action(type="click", params={"button": "left"})
        steps = [
            StepRecord(idx=0, action=action.model_copy()),
            StepRecord(idx=1, action=None),
            StepRecord(idx=2, action=action.model_copy()),
        ]
        session = SessionContext(step_count=3, steps=steps)
        snapshot = _make_snapshot()

        with patch("autovisiontest.engine.terminator.is_alive", return_value=True):
            result = terminator.check(session, snapshot)
        assert result is None
