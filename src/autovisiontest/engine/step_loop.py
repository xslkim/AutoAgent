"""Step loop — the main execution loop for a test session.

Each iteration:
1. Capture snapshot (screenshot + OCR)
2. Check termination conditions (Terminator)
3. Ask Planner for next action
4. If action needs target, locate it (Actor)
5. Run safety check (SafetyGuard)
6. Execute the action (ActionExecutor)
7. Wait for UI to settle
8. Write evidence
9. Update session context
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from autovisiontest.control.actions import Action, NEED_TARGET
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.engine.actor import Actor, LocateResult
from autovisiontest.engine.models import SessionContext, StepRecord, TerminationReason
from autovisiontest.engine.planner import Planner
from autovisiontest.engine.terminator import Terminator
from autovisiontest.perception.facade import FrameSnapshot, Perception
from autovisiontest.prompts.planner import PlannerDecision
from autovisiontest.safety.guard import SafetyGuard, SafetyVerdict

logger = logging.getLogger(__name__)

# Default wait time between steps (ms)
_DEFAULT_STEP_WAIT_MS = 500


class EvidenceWriter(Protocol):
    """Protocol for writing evidence (screenshots, OCR) to disk."""

    def write_step_evidence(
        self,
        session_id: str,
        step_idx: int,
        before_screenshot: bytes,
        after_screenshot: bytes | None,
        ocr_text: str,
    ) -> None:
        """Write evidence for a single step."""
        ...


class NullEvidenceWriter:
    """No-op evidence writer for testing."""

    def write_step_evidence(
        self,
        session_id: str,
        step_idx: int,
        before_screenshot: bytes,
        after_screenshot: bytes | None,
        ocr_text: str,
    ) -> None:
        pass


class StepLoop:
    """Main step loop for test execution.

    Args:
        planner: Planner for deciding next actions.
        actor: Actor for locating UI elements.
        terminator: Terminator for checking termination conditions.
        safety_guard: SafetyGuard for safety checks.
        executor: ActionExecutor for executing actions.
        perception: Perception for capturing snapshots.
        evidence_writer: Writer for saving evidence.
        step_wait_ms: Milliseconds to wait between steps.
    """

    def __init__(
        self,
        planner: Planner,
        actor: Actor,
        terminator: Terminator,
        safety_guard: SafetyGuard,
        executor: ActionExecutor,
        perception: Perception,
        evidence_writer: EvidenceWriter | None = None,
        step_wait_ms: int = _DEFAULT_STEP_WAIT_MS,
    ) -> None:
        self._planner = planner
        self._actor = actor
        self._terminator = terminator
        self._safety_guard = safety_guard
        self._executor = executor
        self._perception = perception
        self._evidence_writer = evidence_writer or NullEvidenceWriter()
        self._step_wait_ms = step_wait_ms

    def run(self, session: SessionContext) -> TerminationReason:
        """Execute the main step loop until termination.

        Args:
            session: The session context (mutated in place).

        Returns:
            The TerminationReason that ended the session.
        """
        if session.start_time == 0.0:
            session.start_time = time.time()

        while True:
            # Step 1: Capture snapshot
            try:
                snapshot = self._perception.capture_snapshot()
            except Exception:
                logger.exception("capture_snapshot_failed")
                return TerminationReason.CRASH

            # Step 2: Check termination conditions
            term_reason = self._terminator.check(session, snapshot)
            if term_reason is not None:
                session.termination_reason = term_reason
                return term_reason

            # Step 3: Ask Planner for next action
            try:
                decision = self._planner.decide(session, snapshot)
            except Exception:
                logger.exception("planner_failed")
                session.termination_reason = TerminationReason.CRASH
                return TerminationReason.CRASH

            # T3: Planner says done
            if decision.done:
                session.termination_reason = TerminationReason.PASS
                return TerminationReason.PASS

            # Collect bug hints from planner
            session.bug_hints.extend(decision.bug_hints)

            # Step 4: Locate target (if action needs one)
            action = decision.action
            coords: tuple[int, int] | None = None
            grounding_confidence: float | None = None

            if action.type in NEED_TARGET and decision.target_desc:
                locate_result = self._locate_with_retry(snapshot, decision, session)
                if locate_result.success:
                    coords = (locate_result.x, locate_result.y)
                    grounding_confidence = locate_result.confidence
                else:
                    # Target not found — record step and continue
                    logger.warning(
                        "target_not_found",
                        extra={"target_desc": decision.target_desc},
                    )
                    step = StepRecord(
                        idx=session.step_count,
                        planner_intent=decision.next_intent,
                        actor_target_desc=decision.target_desc,
                        action=action,
                        grounding_confidence=grounding_confidence,
                        before_screenshot_path="",
                        after_screenshot_path="",
                        reflection=decision.reflection,
                    )
                    session.steps.append(step)
                    session.step_count += 1

                    # Check if we should terminate due to repeated failures
                    if self._too_many_target_failures(session):
                        session.termination_reason = TerminationReason.TARGET_NOT_FOUND
                        return TerminationReason.TARGET_NOT_FOUND
                    continue

            # Step 5: Safety check
            session_ctx = {
                "step_count": session.step_count,
                "start_time": session.start_time,
                "safety_overrides": session.safety_overrides,
            }
            verdict = self._safety_guard.check(
                action=action,
                coords=coords,
                ocr=snapshot.ocr,
                goal=session.goal,
                session_ctx=session_ctx,
            )
            # Update session from guard
            session.safety_overrides = session_ctx.get("safety_overrides", session.safety_overrides)

            if verdict.decision == "blocked":
                logger.warning(
                    "safety_blocked",
                    extra={"reason": verdict.reason},
                )
                session.termination_reason = TerminationReason.UNSAFE
                return TerminationReason.UNSAFE

            if verdict.decision == "timeout":
                logger.warning(
                    "safety_timeout",
                    extra={"reason": verdict.reason},
                )
                session.termination_reason = TerminationReason.MAX_STEPS
                return TerminationReason.MAX_STEPS

            # Step 6: Execute the action
            before_screenshot = snapshot.screenshot_png
            action_result = None
            try:
                action_result = self._executor.execute(action, coords=coords)
            except Exception:
                logger.exception("action_execution_failed")

            # Step 7: Wait for UI to settle
            time.sleep(self._step_wait_ms / 1000.0)

            # Capture after-screenshot
            try:
                after_snapshot = self._perception.capture_snapshot()
                after_screenshot = after_snapshot.screenshot_png
            except Exception:
                after_screenshot = None

            # Step 8: Write evidence
            ocr_text = ", ".join(item.text for item in snapshot.ocr.items[:20])
            self._evidence_writer.write_step_evidence(
                session_id=session.session_id,
                step_idx=session.step_count,
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                ocr_text=ocr_text,
            )

            # Step 9: Update session
            step = StepRecord(
                idx=session.step_count,
                planner_intent=decision.next_intent,
                actor_target_desc=decision.target_desc,
                action=action,
                grounding_confidence=grounding_confidence,
                before_screenshot_path="",
                after_screenshot_path="",
                reflection=decision.reflection,
            )
            session.steps.append(step)
            session.step_count += 1

    def _locate_with_retry(
        self,
        snapshot: FrameSnapshot,
        decision: PlannerDecision,
        session: SessionContext,
    ) -> LocateResult:
        """Locate a target element with optional retry callback."""

        def on_retry(target_desc: str) -> str | None:
            """Ask Planner for a new target description."""
            try:
                new_decision = self._planner.decide(session, snapshot)
                if new_decision.target_desc and new_decision.target_desc != target_desc:
                    return new_decision.target_desc
            except Exception:
                logger.exception("retry_planner_failed")
            return None

        return self._actor.locate(snapshot, decision.target_desc, on_retry=on_retry)

    def _too_many_target_failures(self, session: SessionContext) -> bool:
        """Check if there are too many consecutive target-not-found failures."""
        consecutive_failures = 0
        for step in reversed(session.steps):
            if step.grounding_confidence is None and step.action is not None and step.action.type in NEED_TARGET:
                consecutive_failures += 1
            else:
                break
        return consecutive_failures >= 3
