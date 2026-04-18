"""Consolidator — converts exploratory sessions into regression test cases.

The consolidator extracts steps from a successful exploratory session,
computes expectations (SSIM hashes, key OCR text), and saves the
resulting TestCase to the RecordingStore for future regression runs.
"""

from __future__ import annotations

import logging
from typing import Any

from autovisiontest.cases.fingerprint import compute_fingerprint
from autovisiontest.cases.schema import AppConfig, CaseMetadata, Expect, Step, TestCase
from autovisiontest.cases.store import RecordingStore
from autovisiontest.control.actions import Action
from autovisiontest.engine.models import SessionContext, TerminationReason

logger = logging.getLogger(__name__)


def consolidate(
    session: SessionContext,
    store: RecordingStore,
    ocr_keywords_per_step: list[list[str]] | None = None,
) -> TestCase | None:
    """Convert a successful exploratory session into a regression TestCase.

    Steps are extracted from the session's step history. Retry steps and
    steps with None actions are filtered out.

    Args:
        session: The completed exploratory SessionContext.
        store: The RecordingStore to save the resulting TestCase.
        ocr_keywords_per_step: Optional per-step OCR keywords for expectations.
            If not provided, empty expectations are created.

    Returns:
        The saved TestCase if consolidation succeeded, None if the session
        was not successful (non-PASS termination).
    """
    # Only consolidate successful sessions
    if session.termination_reason != TerminationReason.PASS:
        logger.info(
            "consolidate_skipped",
            extra={"reason": session.termination_reason},
        )
        return None

    # Extract steps, filtering out retries and None actions
    case_steps: list[Step] = []
    for idx, step_record in enumerate(session.steps):
        if step_record.action is None:
            continue

        # Skip retry steps (steps where grounding failed)
        if step_record.grounding_confidence is None and step_record.action.type in ("click", "double_click", "right_click", "drag", "scroll"):
            continue

        # Build expectation
        ocr_keywords: list[str] = []
        if ocr_keywords_per_step and idx < len(ocr_keywords_per_step):
            ocr_keywords = ocr_keywords_per_step[idx]

        expect = Expect(
            ssim_hash=step_record.before_screenshot_path or "",
            ocr_keywords=ocr_keywords,
        )

        # Serialize action
        action_dict = step_record.action.model_dump()

        case_step = Step(
            idx=len(case_steps),
            planner_intent=step_record.planner_intent,
            target_desc=step_record.actor_target_desc,
            action=action_dict,
            expect=expect,
        )
        case_steps.append(case_step)

    if not case_steps:
        logger.warning("consolidate_no_valid_steps")
        return None

    # Compute fingerprint
    fingerprint = compute_fingerprint(session.app_path, session.goal)

    # Build TestCase
    case = TestCase(
        goal=session.goal,
        app_config=AppConfig(
            app_path=session.app_path,
            app_args=session.app_args,
        ),
        steps=case_steps,
        metadata=CaseMetadata(
            fingerprint=fingerprint,
            source_session_id=session.session_id,
            step_count=len(case_steps),
        ),
    )

    # Save to store
    store.save(case)
    logger.info(
        "consolidate_saved",
        extra={"fingerprint": fingerprint, "step_count": len(case_steps)},
    )

    return case
