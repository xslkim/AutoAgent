"""Action and ActionResult Pydantic models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class Action(BaseModel):
    """A desktop action to be executed."""

    type: Literal[
        "click", "double_click", "right_click", "drag", "scroll",
        "type", "key_combo", "wait",
    ]
    params: dict[str, Any] = {}


# Actions that require a target coordinate (coords must be provided)
NEED_TARGET: set[str] = {"click", "double_click", "right_click", "drag", "scroll"}


class ActionResult(BaseModel):
    """Result of executing an action."""

    success: bool
    error: str | None = None
    duration_ms: int = 0
