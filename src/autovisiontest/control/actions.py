"""Action and ActionResult Pydantic models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class Action(BaseModel):
    """A desktop action to be executed.

    The canonical internal names (``click`` / ``double_click`` / ``right_click``
    / ``drag`` / ``scroll`` / ``type`` / ``key_combo`` / ``wait``) are the
    ones the executor dispatches on.  ``finished`` is a terminal sentinel
    emitted by UI-TARS that is never actually dispatched; it just lands in
    the step record for debugging.
    """

    type: Literal[
        "click", "double_click", "right_click", "drag", "scroll",
        "type", "key_combo", "wait", "finished",
    ]
    params: dict[str, Any] = {}


NEED_TARGET: set[str] = {"click", "double_click", "right_click", "drag", "scroll"}


class ActionResult(BaseModel):
    """Result of executing an action."""

    success: bool
    error: str | None = None
    duration_ms: int = 0
