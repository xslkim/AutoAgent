"""Planner — wraps the ChatBackend call for test step planning.

The Planner receives the session context and current screenshot,
constructs the VLM prompt, calls the backend, and returns a
structured ``PlannerDecision``.
"""

from __future__ import annotations

import logging

from autovisiontest.backends.protocol import ChatBackend
from autovisiontest.engine.models import BugHint, SessionContext, StepRecord, TerminationReason
from autovisiontest.perception.facade import FrameSnapshot
from autovisiontest.prompts.planner import PlannerDecision, build_planner_messages, parse_planner_response

logger = logging.getLogger(__name__)


class Planner:
    """Wraps ChatBackend calls for planning and summarization."""

    def __init__(
        self,
        chat_backend: ChatBackend,
        max_history_steps: int = 10,
    ) -> None:
        self._backend = chat_backend
        self._max_history = max_history_steps

    def decide(
        self,
        session: SessionContext,
        snapshot: FrameSnapshot,
    ) -> PlannerDecision:
        """Ask the Planner VLM for the next action.

        Args:
            session: Current session context with goal and history.
            snapshot: Current frame snapshot with screenshot and OCR.

        Returns:
            A ``PlannerDecision`` with the next action, reflection, etc.
        """
        # Truncate history if too long: keep first 2 + last (max_history - 2)
        history = self._truncate_history(session.steps)

        # Get last reflection
        last_reflection = ""
        if session.steps:
            last_reflection = session.steps[-1].reflection

        # Build OCR summary
        ocr_summary = self._summarize_ocr(snapshot)

        # Construct messages
        messages = build_planner_messages(
            goal=session.goal,
            history=history,
            last_reflection=last_reflection,
            ocr_summary=ocr_summary,
        )

        # Call backend with screenshot image
        response = self._backend.chat(
            messages,
            images=[snapshot.screenshot_png],
            response_format="json",
        )

        # Parse response
        decision = parse_planner_response(response.content)

        logger.info(
            "planner_decision",
            extra={
                "intent": decision.next_intent,
                "action": decision.action.type,
                "done": decision.done,
            },
        )

        return decision

    def summarize_on_terminate(
        self,
        session: SessionContext,
        reason: TerminationReason,
    ) -> list[BugHint]:
        """Ask the Planner to summarize the session when it terminates.

        This generates final bug hints based on the full session history.

        Args:
            session: The completed session.
            reason: Why the session ended.

        Returns:
            List of ``BugHint`` objects.
        """
        # If there are already bug hints, return them
        if session.bug_hints:
            return session.bug_hints

        # For PASS, no bug hints needed
        if reason == TerminationReason.PASS:
            return []

        # For failures, generate a basic hint from the reason
        hint = BugHint(
            description=f"Session terminated with reason: {reason.value}",
            confidence=0.6,
            evidence=f"Goal: {session.goal}, Steps: {len(session.steps)}",
        )
        return [hint]

    def _truncate_history(self, steps: list[StepRecord]) -> list[StepRecord]:
        """Truncate step history to max_history steps.

        Keeps the first 2 steps (for context) and the most recent steps.
        """
        if len(steps) <= self._max_history:
            return steps

        # Keep first 2 + last (max_history - 2)
        head = steps[:2]
        tail = steps[-(self._max_history - 2):]
        return head + tail

    def _summarize_ocr(self, snapshot: FrameSnapshot) -> str:
        """Create a brief text summary of OCR results."""
        if not snapshot.ocr.items:
            return ""

        texts = [item.text for item in snapshot.ocr.items[:20]]  # Limit to first 20
        return ", ".join(texts)
