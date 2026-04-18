"""Planner prompt construction and response parsing.

Builds the message sequence for the Planner VLM call and parses the
JSON response into a structured ``PlannerDecision``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from autovisiontest.backends.types import Message
from autovisiontest.control.actions import Action
from autovisiontest.engine.models import BugHint, StepRecord
from autovisiontest.exceptions import ChatBackendError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT: str | None = None


def _load_system_prompt() -> str:
    """Load the system prompt from the bundled text file (cached)."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        prompt_path = Path(__file__).parent / "planner_system.txt"
        _SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


class PlannerDecision:
    """Parsed result from the Planner's response."""

    def __init__(
        self,
        reflection: str,
        done: bool,
        bug_hints: list[BugHint],
        next_intent: str,
        target_desc: str,
        action: Action,
    ) -> None:
        self.reflection = reflection
        self.done = done
        self.bug_hints = bug_hints
        self.next_intent = next_intent
        self.target_desc = target_desc
        self.action = action

    def __repr__(self) -> str:
        return (
            f"PlannerDecision(intent={self.next_intent!r}, "
            f"done={self.done}, action={self.action.type})"
        )


def build_planner_messages(
    goal: str,
    history: list[StepRecord],
    last_reflection: str | None = None,
    ocr_summary: str = "",
) -> list[Message]:
    """Construct the message sequence for a Planner call.

    Args:
        goal: The test session goal.
        history: List of past step records.
        last_reflection: Reflection from the previous step (if any).
        ocr_summary: Summary of OCR-detected text on the current screen.

    Returns:
        List of ``Message`` objects for the VLM.
    """
    system = _load_system_prompt()

    parts: list[str] = []
    parts.append(f"## Goal\n{goal}")

    if ocr_summary:
        parts.append(f"## OCR Text on Screen\n{ocr_summary}")

    if last_reflection:
        parts.append(f"## Last Step Reflection\n{last_reflection}")

    if history:
        parts.append("## Action History")
        # Show last N steps to avoid context overflow
        display_steps = history[-10:]
        for step in display_steps:
            action_desc = f"{step.action.type}({step.action.params})" if step.action else "N/A"
            parts.append(
                f"- Step {step.idx}: intent={step.planner_intent!r}, "
                f"action={action_desc}, reflection={step.reflection!r}"
            )

    user_content = "\n\n".join(parts)

    return [
        Message(role="system", content=system),
        Message(role="user", content=user_content),
    ]


def parse_planner_response(raw: str) -> PlannerDecision:
    """Parse the Planner's raw text response into a PlannerDecision.

    Handles:
    - Markdown code fences (stripped)
    - Trailing text after JSON
    - Missing optional fields (defaulted)

    Raises:
        ChatBackendError: If the response cannot be parsed as JSON at all.
    """
    content = raw.strip()

    # Strip markdown fences
    if content.startswith("```"):
        lines = content.split("\n")
        # Find the closing fence
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end_idx = i
                break
        # Skip first line (```json or ```) and take until closing fence
        content = "\n".join(lines[1:end_idx])

    # Try to find JSON object in the content
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ChatBackendError(
            f"Planner response contains no JSON object: {raw[:200]}",
            retryable=False,
        )

    json_str = content[start : end + 1]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ChatBackendError(
            f"Planner response JSON parse error: {e}",
            retryable=False,
        )

    # Parse bug_hints
    bug_hints: list[BugHint] = []
    for hint_data in data.get("bug_hints", []):
        if isinstance(hint_data, dict):
            bug_hints.append(
                BugHint(
                    description=hint_data.get("description", ""),
                    confidence=float(hint_data.get("confidence", 0.5)),
                    evidence=hint_data.get("evidence", ""),
                )
            )

    # Parse action
    action_data = data.get("action", {})
    if isinstance(action_data, dict):
        action = Action(
            type=action_data.get("type", "wait"),
            params=action_data.get("params", {}),
        )
    else:
        action = Action(type="wait", params={})

    return PlannerDecision(
        reflection=data.get("reflection", ""),
        done=bool(data.get("done", False)),
        bug_hints=bug_hints,
        next_intent=data.get("next_intent", ""),
        target_desc=data.get("target_desc", ""),
        action=action,
    )
