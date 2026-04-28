"""Step loop — the main execution loop for a test session.

Per iteration:

1. Capture a snapshot (screenshot + OCR).
2. Check termination conditions (:class:`Terminator`).
3. Ask the :class:`Agent` for the next :class:`AgentDecision`.
4. Short-circuit on ``decision.finished`` (the agent thinks the goal is done).
5. Short-circuit on a needs-target miss (action requires coordinates but
   the agent could not supply them).
6. Run a safety check (:class:`SafetyGuard`).
7. Execute the action (:class:`ActionExecutor`).
8. Wait for UI to settle.
9. Capture an after-screenshot + write evidence.
10. Append the :class:`StepRecord` and iterate.

The single-:class:`Agent` contract replaces the previous Planner → Actor
round-trip: UI-TARS produces reasoning + coordinates in one call, and the
legacy pipeline is available via :class:`LegacyPlannerActorAgent`.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from autovisiontest.control.actions import NEED_TARGET
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.engine.agent import Agent, AgentDecision
from autovisiontest.engine.models import SessionContext, StepRecord, TerminationReason
from autovisiontest.engine.terminator import Terminator
from autovisiontest.perception.facade import Perception
from autovisiontest.safety.guard import SafetyGuard

logger = logging.getLogger(__name__)

_DEFAULT_STEP_WAIT_MS = 500
_CONSECUTIVE_TARGET_FAILURES_LIMIT = 3


class EvidenceWriter(Protocol):
    """Protocol for writing evidence (screenshots, OCR) to disk."""

    def write_step_evidence(
        self,
        session_id: str,
        step_idx: int,
        before_screenshot: bytes,
        after_screenshot: bytes | None,
        ocr_text: str,
    ) -> None: ...


class NullEvidenceWriter:
    """No-op evidence writer used when persistence is not configured."""

    def write_step_evidence(
        self,
        session_id: str,  # noqa: ARG002
        step_idx: int,  # noqa: ARG002
        before_screenshot: bytes,  # noqa: ARG002
        after_screenshot: bytes | None,  # noqa: ARG002
        ocr_text: str,  # noqa: ARG002
    ) -> None:
        return


class StepLoop:
    """Main step loop — drives a single :class:`SessionContext` to termination."""

    def __init__(
        self,
        agent: Agent,
        terminator: Terminator,
        safety_guard: SafetyGuard,
        executor: ActionExecutor,
        perception: Perception,
        evidence_writer: EvidenceWriter | None = None,
        step_wait_ms: int = _DEFAULT_STEP_WAIT_MS,
    ) -> None:
        self._agent = agent
        self._terminator = terminator
        self._safety_guard = safety_guard
        self._executor = executor
        self._perception = perception
        self._evidence_writer = evidence_writer or NullEvidenceWriter()
        self._step_wait_ms = step_wait_ms

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, session: SessionContext) -> TerminationReason:
        if session.start_time == 0.0:
            session.start_time = time.time()

        while True:
            # 1. Snapshot.
            try:
                snapshot = self._perception.capture_snapshot()
            except Exception:
                logger.exception("capture_snapshot_failed")
                session.termination_reason = TerminationReason.CRASH
                return TerminationReason.CRASH

            # 2. Termination.
            term_reason = self._terminator.check(session, snapshot)
            if term_reason is not None:
                session.termination_reason = term_reason
                return term_reason

            # 3. Agent decision (single call — no more Planner+Actor).
            try:
                decision = self._agent.decide(session, snapshot)
            except Exception:
                logger.exception("agent_decide_failed")
                session.termination_reason = TerminationReason.CRASH
                return TerminationReason.CRASH

            session.bug_hints.extend(decision.bug_hints)

            # 4. Finished — agent thinks the goal is done.
            if decision.finished:
                logger.info(
                    "agent_finished",
                    extra={"content": decision.finished_content, "thought": decision.thought[:200]},
                )
                session.termination_reason = TerminationReason.PASS
                return TerminationReason.PASS

            # 5. Needs-target miss — record a failed step, maybe terminate.
            if decision.needs_target():
                logger.warning(
                    "agent_target_missing",
                    extra={"action_type": decision.action.type, "target_desc": decision.target_desc[:120]},
                )
                self._append_step(session, decision, coords=None)
                if self._too_many_target_failures(session):
                    session.termination_reason = TerminationReason.TARGET_NOT_FOUND
                    return TerminationReason.TARGET_NOT_FOUND
                continue

            # 6. Safety.
            session_ctx = {
                "step_count": session.step_count,
                "start_time": session.start_time,
                "safety_overrides": session.safety_overrides,
            }
            verdict = self._safety_guard.check(
                action=decision.action,
                coords=decision.coords,
                ocr=snapshot.ocr,
                goal=session.goal,
                session_ctx=session_ctx,
            )
            session.safety_overrides = session_ctx.get(
                "safety_overrides", session.safety_overrides
            )
            if verdict.decision == "blocked":
                logger.warning("safety_blocked", extra={"reason": verdict.reason})
                session.termination_reason = TerminationReason.UNSAFE
                return TerminationReason.UNSAFE
            if verdict.decision == "timeout":
                logger.warning("safety_timeout", extra={"reason": verdict.reason})
                session.termination_reason = TerminationReason.MAX_STEPS
                return TerminationReason.MAX_STEPS

            # 7. Execute.
            before_screenshot = snapshot.screenshot_png
            try:
                self._executor.execute(decision.action, coords=decision.coords)
            except Exception:
                logger.exception("action_execution_failed")

            # 8. Settle.
            time.sleep(self._step_wait_ms / 1000.0)

            # 9. After-snapshot + evidence.
            try:
                after_snapshot = self._perception.capture_snapshot()
                after_screenshot = after_snapshot.screenshot_png
            except Exception:
                after_screenshot = None

            ocr_text = ", ".join(item.text for item in snapshot.ocr.items[:20])
            self._evidence_writer.write_step_evidence(
                session_id=session.session_id,
                step_idx=session.step_count,
                before_screenshot=before_screenshot,
                after_screenshot=after_screenshot,
                ocr_text=ocr_text,
            )

            # 10. Record step.
            self._append_step(session, decision, coords=decision.coords)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append_step(
        self,
        session: SessionContext,
        decision: AgentDecision,
        coords: tuple[int, int] | None,
    ) -> None:
        """Materialise a :class:`StepRecord` from an :class:`AgentDecision`."""
        step = StepRecord(
            idx=session.step_count,
            planner_intent=decision.thought[:200],
            actor_target_desc=decision.target_desc,
            action=decision.action,
            grounding_confidence=decision.grounding_confidence,
            before_screenshot_path="",
            after_screenshot_path="",
            reflection=decision.thought,
        )
        session.steps.append(step)
        session.step_count += 1
        logger.debug(
            "step_recorded",
            extra={
                "idx": step.idx,
                "action": decision.action.type,
                "coords": coords,
                "confidence": decision.grounding_confidence,
            },
        )

    @staticmethod
    def _too_many_target_failures(session: SessionContext) -> bool:
        """Three consecutive steps with ``action ∈ NEED_TARGET`` but no coords."""
        consecutive = 0
        for step in reversed(session.steps):
            if (
                step.action is not None
                and step.action.type in NEED_TARGET
                and step.grounding_confidence is None
            ):
                consecutive += 1
            else:
                break
        return consecutive >= _CONSECUTIVE_TARGET_FAILURES_LIMIT
