"""VLM-based second-check for actions flagged by the blacklist.

When the blacklist matcher flags an action, the ``SecondCheck`` sends the
action context to a VLM (via ``ChatBackend``) and asks whether the action
is truly dangerous given the current goal.  This two-layer approach reduces
false positives while keeping the safety guard effective.

Session-level override limit
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each session may override (i.e. let through) at most ``max_overrides_per_session``
blacklist hits.  Once this limit is exceeded, **all** subsequent blacklist hits
are automatically marked ``"unsafe"`` without consulting the VLM — preventing
an adversarial planner from whittling down the safety barrier one override at
a time.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from autovisiontest.backends.types import Message
from autovisiontest.control.actions import Action

logger = logging.getLogger(__name__)

# Type alias for the verdict returned by ``confirm``.
Verdict = Literal["safe", "unsafe"]


class SecondCheck:
    """VLM-based safety second-checker."""

    def __init__(
        self,
        chat_backend: "ChatBackend",  # noqa: F821 — Protocol, avoid import
        max_overrides_per_session: int = 3,
    ) -> None:
        self._backend = chat_backend
        self._max_overrides = max_overrides_per_session

    def confirm(
        self,
        action: Action,
        hit_reason: str,
        goal: str,
        session_ctx: dict,
    ) -> Verdict:
        """Ask the VLM whether a blacklisted action should be allowed.

        Args:
            action: The action that was flagged.
            hit_reason: Human-readable description of *why* it was flagged.
            goal: The current test session goal.
            session_ctx: Mutable session context dict.  The key
                ``"safety_overrides"`` (int) is read and incremented.

        Returns:
            ``"safe"`` if the VLM confirms the action is benign,
            ``"unsafe"`` otherwise.
        """
        overrides = session_ctx.get("safety_overrides", 0)

        # If override limit exceeded, auto-unsafe without asking VLM
        if overrides >= self._max_overrides:
            logger.warning(
                "safety_override_limit_exceeded",
                extra={"overrides": overrides, "limit": self._max_overrides},
            )
            session_ctx["safety_overrides"] = overrides + 1
            return "unsafe"

        # Build prompt for VLM
        messages = self._build_messages(action, hit_reason, goal)

        try:
            response = self._backend.chat(messages, response_format="json")
            verdict = self._parse_response(response.content)
        except Exception:
            logger.exception("second_check_vlm_error")
            # On any error, default to unsafe
            verdict = "unsafe"

        # Record override if VLM says safe
        session_ctx["safety_overrides"] = overrides + 1

        logger.info(
            "second_check_result",
            extra={"verdict": verdict, "hit_reason": hit_reason, "action": action.type},
        )
        return verdict

    # ── Internal helpers ─────────────────────────────────────────────────

    def _build_messages(
        self,
        action: Action,
        hit_reason: str,
        goal: str,
    ) -> list[Message]:
        """Construct the VLM prompt for second-check."""
        system = (
            "You are a safety checker for a desktop automation agent. "
            "The agent wants to perform an action that was flagged by a keyword blacklist. "
            "Determine whether the action is truly dangerous given the current goal.\n\n"
            'Respond with a single JSON object: {"verdict": "safe" | "unsafe", "reason": "..."}\n'
            "Only mark as 'safe' if you are confident the action is benign given the goal context."
        )
        user = (
            f"Current goal: {goal}\n"
            f"Flagged action: type={action.type}, params={action.params}\n"
            f"Blacklist hit reason: {hit_reason}\n\n"
            "Is this action safe given the goal? Respond with JSON."
        )
        return [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]

    def _parse_response(self, raw: str) -> Verdict:
        """Parse the VLM response and extract the verdict.

        Falls back to ``"unsafe"`` on any parsing error.
        """
        try:
            # Strip markdown fences if present
            content = raw.strip()
            if content.startswith("```"):
                # Remove first and last line (``` fences)
                lines = content.split("\n")
                # Skip first line (```json or ```) and last line (```)
                content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

            data = json.loads(content)
            verdict = data.get("verdict", "unsafe")
            if verdict == "safe":
                return "safe"
            return "unsafe"
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("second_check_parse_error", extra={"raw": raw[:200]})
            return "unsafe"
