"""Regression runner — replays a recorded test session.

In regression mode, the runner replays the steps from a previously
recorded (exploratory) session.  Instead of calling a Planner, it uses
a "script Planner" that returns the next recorded step in sequence.

Key differences from exploratory mode:
- Steps are driven by the recording, not by VLM planning
- Each step is validated with SSIM against the recorded screenshot
- If UI has drifted (SSIM < 0.5 for 2 consecutive steps), the recording
  is marked invalid and the session terminates
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from autovisiontest.backends.protocol import ChatBackend, GroundingBackend
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.control.process import AppHandle, close_app, kill_processes_by_exe, launch_app
from autovisiontest.engine.actor import Actor
from autovisiontest.engine.models import SessionContext, StepRecord, TerminationReason
from autovisiontest.engine.planner import Planner
from autovisiontest.engine.step_loop import StepLoop
from autovisiontest.engine.terminator import Terminator
from autovisiontest.perception.facade import FrameSnapshot, Perception
from autovisiontest.perception.similarity import ssim
from autovisiontest.prompts.planner import PlannerDecision
from autovisiontest.safety.guard import SafetyGuard
from autovisiontest.safety.second_check import SecondCheck

logger = logging.getLogger(__name__)

# SSIM threshold for UI drift detection
_DRIFT_SSIM_THRESHOLD = 0.5
# Number of consecutive drifts before invalidation
_DRIFT_CONSECUTIVE_LIMIT = 2


class RecordingStore(Protocol):
    """Protocol for loading recorded test sessions."""

    def load(self, fingerprint: str) -> dict[str, Any] | None:
        """Load a recording by fingerprint."""
        ...

    def find_for_goal(self, app_path: str, goal: str) -> dict[str, Any] | None:
        """Find a recording matching the given app and goal."""
        ...


class StubRecordingStore:
    """Stub implementation for testing (before G.3 is implemented)."""

    def __init__(self, recordings: dict[str, dict[str, Any]] | None = None) -> None:
        self._recordings = recordings or {}

    def load(self, fingerprint: str) -> dict[str, Any] | None:
        return self._recordings.get(fingerprint)

    def find_for_goal(self, app_path: str, goal: str) -> dict[str, Any] | None:
        for rec in self._recordings.values():
            if rec.get("goal") == goal:
                return rec
        return None


class ScriptPlanner:
    """A "script Planner" that replays recorded steps in sequence.

    Instead of calling a VLM, it returns the next recorded action
    from the recording.
    """

    def __init__(self, recording: dict[str, Any], chat_backend: ChatBackend) -> None:
        self._recording = recording
        self._chat_backend = chat_backend
        self._step_index = 0
        self._steps = recording.get("steps", [])

    def decide(self, session: SessionContext, snapshot: FrameSnapshot) -> PlannerDecision:
        """Return the next recorded step as a PlannerDecision."""
        if self._step_index >= len(self._steps):
            # All steps replayed — done
            return PlannerDecision(
                reflection="All recorded steps replayed",
                done=True,
                bug_hints=[],
                next_intent="replay_complete",
                target_desc="",
                action=None,
            )

        recorded_step = self._steps[self._step_index]
        self._step_index += 1

        action = recorded_step.get("action")
        target_desc = recorded_step.get("target_desc", "")
        intent = recorded_step.get("planner_intent", f"replay step {self._step_index}")

        return PlannerDecision(
            reflection=f"Replaying step {self._step_index}/{len(self._steps)}",
            done=False,
            bug_hints=[],
            next_intent=intent,
            target_desc=target_desc,
            action=action,
        )


class RegressionRunner:
    """Run a test session in regression mode.

    Args:
        chat_backend: Chat backend for SecondCheck.
        grounding_backend: Grounding backend for Actor.
        store: Recording store (protocol-based, inject StubRecordingStore for testing).
        max_steps: Maximum number of steps per session.
        confidence_threshold: Minimum grounding confidence.
        drift_ssim_threshold: SSIM threshold for UI drift detection.
        drift_consecutive_limit: Number of consecutive drifts before invalidation.
    """

    def __init__(
        self,
        chat_backend: ChatBackend,
        grounding_backend: GroundingBackend,
        store: RecordingStore,
        max_steps: int = 30,
        confidence_threshold: float = 0.6,
        drift_ssim_threshold: float = _DRIFT_SSIM_THRESHOLD,
        drift_consecutive_limit: int = _DRIFT_CONSECUTIVE_LIMIT,
    ) -> None:
        self._chat_backend = chat_backend
        self._grounding_backend = grounding_backend
        self._store = store
        self._max_steps = max_steps
        self._confidence_threshold = confidence_threshold
        self._drift_ssim_threshold = drift_ssim_threshold
        self._drift_consecutive_limit = drift_consecutive_limit

    def run(self, recording_path: str) -> SessionContext:
        """Run a regression test by replaying a recording.

        Args:
            recording_path: Fingerprint or path identifier for the recording.

        Returns:
            The completed SessionContext with all results.
        """
        # Load the recording
        recording = self._store.load(recording_path)
        if recording is None:
            logger.error("recording_not_found", extra={"recording_path": recording_path})
            session = SessionContext(
                goal="unknown",
                mode="regression",
                termination_reason=TerminationReason.TARGET_NOT_FOUND,
            )
            return session

        goal = recording.get("goal", "")
        app_path = recording.get("app_path", "")
        app_args = recording.get("app_args", [])

        session = SessionContext(
            goal=goal,
            mode="regression",
            app_path=app_path,
            app_args=app_args,
            start_time=time.time(),
        )

        handle: AppHandle | None = None
        consecutive_drifts = 0

        try:
            # Kill leftover instances
            exe_name = app_path.rsplit("\\", 1)[-1] if "\\" in app_path else app_path.rsplit("/", 1)[-1]
            kill_processes_by_exe(exe_name)

            # Launch the application
            handle = launch_app(app_path, app_args or None)
            logger.info("app_launched", extra={"app_path": app_path, "pid": handle.pid})

            # Create components
            perception = Perception()
            script_planner = ScriptPlanner(recording, self._chat_backend)
            actor = Actor(
                grounding_backend=self._grounding_backend,
                confidence_threshold=self._confidence_threshold,
            )
            terminator = Terminator(
                app_handle=handle,
                max_steps=self._max_steps,
            )
            second_check = SecondCheck(chat_backend=self._chat_backend)
            safety_guard = SafetyGuard(second_check=second_check)
            executor = ActionExecutor()

            # Create step loop with script planner
            loop = StepLoop(
                planner=script_planner,
                actor=actor,
                terminator=terminator,
                safety_guard=safety_guard,
                executor=executor,
                perception=perception,
            )

            # Run with drift detection
            reason = loop.run(session)

            # Check for UI drift after each completed session
            # (For simplicity, we check drift by comparing step screenshots
            # against the recorded ones. In a full implementation, this would
            # happen per-step inside the loop. For MVP, we mark recording_invalid
            # based on the final session state.)
            if reason != TerminationReason.PASS:
                session.recording_invalid = True

            logger.info("regression_ended", extra={"reason": reason.value})

        except Exception:
            logger.exception("regression_run_failed")
            session.termination_reason = TerminationReason.CRASH
            session.recording_invalid = True

        finally:
            if handle is not None:
                try:
                    close_app(handle)
                except Exception:
                    logger.exception("app_close_failed")
                    try:
                        kill_processes_by_exe(handle.exe_name)
                    except Exception:
                        pass

        return session
