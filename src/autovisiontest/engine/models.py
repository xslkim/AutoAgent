"""Core data models for the execution engine.

Defines the Pydantic models used throughout the engine:
- ``StepRecord`` — per-step execution trace
- ``Assertion`` / ``AssertionResult`` — assertion definition and outcome
- ``TerminationReason`` — enum for why a session ended
- ``BugHint`` — AI-generated bug hypothesis
- ``SessionContext`` — full session state container
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from autovisiontest.control.actions import Action


class TerminationReason(str, Enum):
    """Why a test session ended."""

    CRASH = "CRASH"
    UNSAFE = "UNSAFE"
    PASS = "PASS"
    ERROR_DIALOG = "ERROR_DIALOG"
    MAX_STEPS = "MAX_STEPS"
    STUCK = "STUCK"
    NO_PROGRESS = "NO_PROGRESS"
    USER = "USER"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    ASSERTION_FAILED = "ASSERTION_FAILED"


class BugHint(BaseModel):
    """AI-generated bug hypothesis."""

    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""


class StepRecord(BaseModel):
    """Per-step execution trace."""

    idx: int
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    planner_intent: str = ""
    actor_target_desc: str = ""
    action: Action | None = None
    grounding_confidence: float | None = None
    before_screenshot_path: str = ""
    after_screenshot_path: str = ""
    reflection: str = ""


class Assertion(BaseModel):
    """An assertion to verify during or after execution."""

    type: str  # "ocr_contains", "no_error_dialog", "file_exists", "file_contains", "screenshot_similar", "vlm_element_exists"
    params: dict[str, Any] = {}


class AssertionResult(BaseModel):
    """Result of running an assertion."""

    type: str
    passed: bool
    detail: str = ""


class SessionContext(BaseModel):
    """Full session state container.

    Holds all mutable state for a running test session, including
    history, assertions, safety overrides, and bug hints.
    """

    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str = ""
    mode: str = "exploratory"  # "exploratory" | "regression"
    app_path: str = ""
    app_args: list[str] = Field(default_factory=list)
    steps: list[StepRecord] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    safety_overrides: int = 0
    bug_hints: list[BugHint] = Field(default_factory=list)
    start_time: float = 0.0
    step_count: int = 0
    termination_reason: TerminationReason | None = None
    recording_invalid: bool = False

    model_config = {"arbitrary_types_allowed": True}
