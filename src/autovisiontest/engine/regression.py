"""Regression runner — replays recorded test steps.

Loads a ``TestCase`` from the :class:`RecordingStore`, replays each step
using the saved action + coordinates (no model inference), runs assertions,
and returns a :class:`SessionContext`.

The MVP implementation skips SSIM drift detection (T-2.4); it replays
steps verbatim.  If the UI has changed significantly the regression will
simply fail rather than auto-fallback to exploration.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from autovisiontest.control.actions import Action
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.control.process import AppHandle, close_app, kill_processes_by_exe, launch_app
from autovisiontest.engine.assertions import run_assertions
from autovisiontest.engine.models import (
    Assertion,
    SessionContext,
    StepRecord,
    TerminationReason,
)
from autovisiontest.perception.facade import Perception

logger = logging.getLogger(__name__)


class RegressionRunner:
    """Replay a recorded TestCase step-by-step.

    Args:
        store: The recording store to load test cases from.
        max_steps: Maximum number of steps to replay.
        data_dir: Root data directory for evidence storage.
    """

    def __init__(
        self,
        store: Any,
        max_steps: int = 30,
        data_dir: Path | None = None,
    ) -> None:
        self._store = store
        self._max_steps = max_steps
        self._data_dir = Path(data_dir) if data_dir is not None else None

    def run(
        self,
        recording_path: str,
        assertions: list[Assertion] | None = None,
        session_id: str | None = None,
    ) -> SessionContext:
        """Replay a recorded test case.

        Args:
            recording_path: Fingerprint of the recording to replay.
            assertions: Optional additional assertions to verify after
                replay.  A ``no_error_dialog`` assertion is always
                prepended implicitly.

        Returns:
            SessionContext with the replay results.
        """
        # Load the recorded test case
        case = self._store.load(recording_path)
        if case is None:
            logger.error("recording_not_found", extra={"fingerprint": recording_path})
            ctx = SessionContext(
                goal="",
                mode="regression",
                app_path="",
            )
            ctx.termination_reason = TerminationReason.CRASH
            return ctx

        # If store.load returns the raw dict (old protocol), parse it
        if isinstance(case, dict):
            from autovisiontest.cases.schema import TestCase
            case = TestCase.model_validate(case)

        session = SessionContext(
            goal=case.goal,
            mode="regression",
            app_path=case.app_config.app_path,
            app_args=case.app_config.app_args,
            start_time=time.time(),
        )
        # Keep session_id consistent with the scheduler's directory key
        if session_id:
            session.session_id = session_id

        # Merge caller-supplied assertions with those saved in the recording,
        # then prepend the implicit no_error_dialog.
        merged: list[Assertion] = list(assertions or [])
        for raw in case.assertions:
            try:
                merged.append(Assertion.model_validate(raw))
            except Exception:
                logger.warning("invalid_saved_assertion", extra={"raw": raw})
        _ensure_implicit_assertions(session, merged or None)

        handle: AppHandle | None = None
        executor = ActionExecutor()

        try:
            # Launch the application
            app_path = case.app_config.app_path
            exe_name = app_path.rsplit("\\", 1)[-1] if "\\" in app_path else app_path.rsplit("/", 1)[-1]
            kill_processes_by_exe(exe_name)
            handle = launch_app(app_path, case.app_config.app_args)
            logger.info("regression_app_launched", extra={"app_path": app_path})

            # Wait for app to be ready
            time.sleep(2.0)

            # Replay each step
            for case_step in case.steps:
                if session.step_count >= self._max_steps:
                    session.termination_reason = TerminationReason.MAX_STEPS
                    break

                action = Action(
                    type=case_step.action.get("type", "wait"),
                    params=case_step.action.get("params", {}),
                )

                # Extract saved coordinates
                coords: tuple[int, int] | None = None
                x = action.params.get("x")
                y = action.params.get("y")
                if x is not None and y is not None:
                    coords = (int(x), int(y))

                try:
                    executor.execute(action, coords=coords)
                except Exception:
                    logger.exception(
                        "regression_step_failed",
                        extra={"step_idx": case_step.idx},
                    )

                time.sleep(0.5)

                # Record step
                step_record = StepRecord(
                    idx=session.step_count,
                    planner_intent=case_step.planner_intent,
                    actor_target_desc=case_step.target_desc,
                    action=action,
                    reflection=f"[regression replay] {case_step.planner_intent}",
                )
                session.steps.append(step_record)
                session.step_count += 1

            # If we finished all steps without early termination
            if session.termination_reason is None:
                session.termination_reason = TerminationReason.PASS

        except Exception:
            logger.exception("regression_run_failed")
            session.termination_reason = TerminationReason.CRASH

        finally:
            if handle is not None:
                try:
                    close_app(handle)
                except Exception:
                    try:
                        kill_processes_by_exe(handle.exe_name)
                    except Exception:
                        pass

        # Run assertions
        if session.termination_reason == TerminationReason.PASS:
            try:
                perception = Perception()
                snapshot = perception.capture_snapshot()
                ctx: dict = {
                    "ocr": snapshot.ocr,
                    "screenshot_png": snapshot.screenshot_png,
                }
                results = run_assertions(session.assertions, ctx)
                session.assertion_results = results
                if not all(r.passed for r in results):
                    session.termination_reason = TerminationReason.ASSERTION_FAILED
            except Exception:
                logger.exception("regression_assertion_failed")

        return session


def _ensure_implicit_assertions(
    session: SessionContext,
    explicit: list[Assertion] | None = None,
) -> None:
    """Add implicit assertions and merge user-supplied ones."""
    if explicit:
        session.assertions = list(explicit)

    has_no_error = any(a.type == "no_error_dialog" for a in session.assertions)
    if not has_no_error:
        session.assertions.insert(0, Assertion(type="no_error_dialog"))
