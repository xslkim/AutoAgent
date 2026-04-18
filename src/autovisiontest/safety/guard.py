"""SafetyGuard — the single entry point for safety checks.

Combines the blacklist matcher, nearby-OCR text extraction, and VLM
second-check into one cohesive guard that the step loop calls before
executing any action.

Check order (by priority):
1. **MAX_ACTIONS** — action count exceeded ``max_session_actions``
2. **MAX_DURATION** — session duration exceeded ``max_session_duration_s``
3. **Blacklist + SecondCheck** — action type hits blacklist → VLM confirms/denies
4. Default → **pass**
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from autovisiontest.control.actions import Action
from autovisiontest.perception.types import OCRResult
from autovisiontest.safety.blacklist import (
    click_hits_blacklist,
    key_combo_hits_blacklist,
    type_hits_blacklist,
)
from autovisiontest.safety.nearby_text import find_nearby_texts
from autovisiontest.safety.second_check import SecondCheck

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyVerdict:
    """Result of a safety guard check."""

    decision: str  # "pass" | "blocked" | "timeout"
    reason: str = ""


class SafetyGuard:
    """Unified safety guard for the step loop."""

    def __init__(
        self,
        second_check: SecondCheck,
        max_session_actions: int = 30,
        max_session_duration_s: int = 600,
    ) -> None:
        self._second_check = second_check
        self._max_actions = max_session_actions
        self._max_duration_s = max_session_duration_s

    def check(
        self,
        action: Action,
        coords: tuple[int, int] | None,
        ocr: OCRResult,
        goal: str,
        session_ctx: dict,
    ) -> SafetyVerdict:
        """Run all safety checks for the given action.

        Args:
            action: The action about to be executed.
            coords: Target coordinates (if action needs a target).
            ocr: OCR result of the current screenshot.
            goal: The current test session goal.
            session_ctx: Mutable session context dict, expected to contain
                ``"step_count"`` (int) and ``"start_time"`` (float).

        Returns:
            A ``SafetyVerdict`` with ``decision`` of ``"pass"``, ``"blocked"``,
            or ``"timeout"``.
        """
        # T5: Max actions check
        step_count = session_ctx.get("step_count", 0)
        if step_count >= self._max_actions:
            return SafetyVerdict(decision="blocked", reason="MAX_ACTIONS")

        # T5: Max duration check
        start_time = session_ctx.get("start_time", 0.0)
        if start_time > 0 and (time.time() - start_time) > self._max_duration_s:
            return SafetyVerdict(decision="timeout", reason="MAX_DURATION")

        # Blacklist check based on action type
        hit, hit_reason = self._check_blacklist(action, coords, ocr)
        if hit and hit_reason is not None:
            # Ask VLM second check
            verdict = self._second_check.confirm(action, hit_reason, goal, session_ctx)
            if verdict == "unsafe":
                return SafetyVerdict(decision="blocked", reason=hit_reason)
            # VLM said safe — allow through
            logger.info("safety_override_allowed", extra={"hit_reason": hit_reason})

        return SafetyVerdict(decision="pass")

    def _check_blacklist(
        self,
        action: Action,
        coords: tuple[int, int] | None,
        ocr: OCRResult,
    ) -> tuple[bool, str | None]:
        """Check the action against the appropriate blacklist.

        Returns:
            ``(True, reason)`` if the action hits a blacklist, ``(False, None)`` otherwise.
        """
        if action.type in ("click", "double_click", "right_click"):
            if coords is not None:
                nearby = find_nearby_texts(ocr, coords[0], coords[1])
                hit, keyword = click_hits_blacklist(nearby)
                if hit:
                    return True, f"click near '{keyword}'"
        elif action.type == "type":
            text = action.params.get("text", "")
            hit, pattern = type_hits_blacklist(text)
            if hit:
                return True, f"type matches pattern '{pattern}'"
        elif action.type == "key_combo":
            keys = tuple(action.params.get("keys", []))
            hit, combo = key_combo_hits_blacklist(keys)
            if hit:
                return True, f"key combo '{combo}' is blacklisted"

        return False, None
