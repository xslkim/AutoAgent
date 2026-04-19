"""Termination condition checker — implements T1–T8 check logic.

Checks termination conditions in priority order (per §5.3):
- T1: Application crash (app_handle not alive)
- T2: Safety block (handled by SafetyGuard, not here)
- T3: Planner says done (handled by step loop, not here)
- T4: Error dialog detected
- T5: Max steps exceeded
- T6: Stuck (screen static over time window)
- T7: No progress (repeated identical actions)
- T8: User termination (handled externally, not here)

This module checks T1, T4, T5, T6, T7.  T2, T3, T8 are handled
elsewhere and fed into the step loop.
"""

from __future__ import annotations

import logging
from typing import Sequence

from autovisiontest.control.process import AppHandle, is_alive
from autovisiontest.engine.models import SessionContext, StepRecord, TerminationReason
from autovisiontest.perception.change_detector import ChangeDetector
from autovisiontest.perception.error_dialog import detect_error_dialog
from autovisiontest.perception.facade import FrameSnapshot
from autovisiontest.perception.types import OCRResult

logger = logging.getLogger(__name__)

# Number of consecutive identical actions to trigger NO_PROGRESS
_DEFAULT_NO_PROGRESS_WINDOW = 3


class Terminator:
    """Check whether a test session should terminate.

    Args:
        app_handle: Handle to the application under test (for crash detection).
        max_steps: Maximum allowed step count before MAX_STEPS.
        change_detector: Change detector instance (for stuck detection).
        no_progress_window: Number of consecutive identical actions for NO_PROGRESS.
    """

    def __init__(
        self,
        app_handle: AppHandle | None,
        max_steps: int = 30,
        change_detector: ChangeDetector | None = None,
        no_progress_window: int = _DEFAULT_NO_PROGRESS_WINDOW,
    ) -> None:
        self._app_handle = app_handle
        self._max_steps = max_steps
        self._change_detector = change_detector or ChangeDetector()
        self._no_progress_window = no_progress_window

    def check(
        self,
        session: SessionContext,
        snapshot: FrameSnapshot,
        ocr: OCRResult | None = None,
    ) -> TerminationReason | None:
        """Check all termination conditions in priority order.

        Args:
            session: Current session context.
            snapshot: Current frame snapshot.
            ocr: OCR result (defaults to snapshot.ocr if not provided).

        Returns:
            TerminationReason if a condition is met, otherwise None.
        """
        if ocr is None:
            ocr = snapshot.ocr

        # T1: Application crash.  Skipped in attach mode (app_handle is None).
        if self._app_handle is not None and not is_alive(self._app_handle):
            logger.warning("T1: Application crash detected (PID %d)", self._app_handle.pid)
            return TerminationReason.CRASH

        # T4: Error dialog detected
        hit, keyword = detect_error_dialog(ocr)
        if hit:
            logger.warning("T4: Error dialog detected (keyword=%s)", keyword)
            return TerminationReason.ERROR_DIALOG

        # T5: Max steps exceeded
        if session.step_count >= self._max_steps:
            logger.warning("T5: Max steps exceeded (%d >= %d)", session.step_count, self._max_steps)
            return TerminationReason.MAX_STEPS

        # T6: Stuck (screen static)
        if self._change_detector.is_static(now_t=snapshot.timestamp):
            logger.warning("T6: Screen stuck detected")
            return TerminationReason.STUCK

        # T7: No progress (repeated identical actions)
        if self._check_no_progress(session.steps):
            logger.warning("T7: No progress (repeated identical actions)")
            return TerminationReason.NO_PROGRESS

        return None

    def _check_no_progress(self, steps: Sequence[StepRecord]) -> bool:
        """Check if the last N actions are identical (no progress).

        Two actions are considered identical when they share the *same*
        ``action.type``, ``action.params`` **and** ``actor_target_desc``.
        The target description is critical: without it, three
        ``click({})`` actions against three different buttons (which all
        have empty ``params``) would be falsely flagged as a loop.

        For backward compatibility, a step with an empty ``actor_target_desc``
        compares only by action type + params (matches the pre-UI-TARS
        behaviour).
        """
        if len(steps) < self._no_progress_window:
            return False

        recent = steps[-self._no_progress_window:]
        first = recent[0]
        if first.action is None:
            return False

        def _key(step: StepRecord) -> tuple[str, str, str]:
            assert step.action is not None
            # Use repr of sorted param items so nested lists / dicts remain
            # comparable even though some values may not be sortable.
            params_repr = repr(sorted(step.action.params.items(), key=lambda kv: kv[0]))
            return (step.action.type, params_repr, step.actor_target_desc or "")

        first_key = _key(first)
        for step in recent[1:]:
            if step.action is None:
                return False
            if _key(step) != first_key:
                return False

        return True
