"""Agent layer — the unified per-step decision interface.

A single UI-TARS call returns ``Thought + Action`` where the action
already carries absolute pixel coordinates, replacing the former
two-call pipeline (Planner VLM + Actor grounding VLM).  The
:class:`Agent` protocol captures that new contract and :class:`StepLoop`
is coded against it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from autovisiontest.backends.uitars import HistoryStep, UITarsDecision
from autovisiontest.control.actions import NEED_TARGET, Action
from autovisiontest.engine.models import BugHint, SessionContext
from autovisiontest.perception.facade import FrameSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AgentDecision — what the step loop sees per step.
# ---------------------------------------------------------------------------


@dataclass
class AgentDecision:
    """One agent step: a reasoning trace plus an executable action.

    Coordinates, when present, are already in absolute screen-pixel space.
    ``target_desc`` is a short human-readable label that identifies *what*
    the agent is trying to click; it is carried so the terminator's
    no-progress check can distinguish "two clicks at different buttons"
    from "two clicks at the same button".
    """

    action: Action
    thought: str = ""
    target_desc: str = ""
    coords: tuple[int, int] | None = None
    end_coords: tuple[int, int] | None = None  # second point, for drag
    grounding_confidence: float | None = None
    finished: bool = False
    finished_content: str = ""
    done_reason: str = ""  # human-readable why we stopped
    bug_hints: list[BugHint] = field(default_factory=list)

    def needs_target(self) -> bool:
        """True if the action requires a coordinate but one was not resolved."""
        return self.action.type in NEED_TARGET and self.coords is None


# ---------------------------------------------------------------------------
# Protocol — what the step loop calls.
# ---------------------------------------------------------------------------


@runtime_checkable
class Agent(Protocol):
    """Any object that can decide the next action for a session step."""

    def decide(
        self,
        session: SessionContext,
        snapshot: FrameSnapshot,
    ) -> AgentDecision:
        """Return the next :class:`AgentDecision` for ``snapshot``."""
        ...


# ---------------------------------------------------------------------------
# UI-TARS agent — the new single-model path.
# ---------------------------------------------------------------------------


# UI-TARS native action name → AutoVT canonical ``Action.type``.
_UITARS_TO_INTERNAL: dict[str, str] = {
    "click": "click",
    "left_double": "double_click",
    "right_single": "right_click",
    "drag": "drag",
    "scroll": "scroll",
    "hotkey": "key_combo",
    "type": "type",
    "wait": "wait",
    "finished": "finished",
}


def _uitars_to_action(decision: UITarsDecision) -> Action:
    """Project a UI-TARS parser output onto the internal :class:`Action` model.

    For spatial actions the absolute-screen coordinates are additionally
    written into ``params`` (``x``/``y``, plus ``to_x``/``to_y`` for drag)
    so the persisted step record is self-describing — evidence annotation
    and post-hoc analysis don't need to re-parse ``target_desc``.
    """
    internal = _UITARS_TO_INTERNAL.get(decision.action_type, "wait")
    params: dict = {}

    if internal in {"click", "double_click", "right_click"}:
        if decision.point_xy is not None:
            params["x"] = decision.point_xy[0]
            params["y"] = decision.point_xy[1]
    elif internal == "drag":
        if decision.point_xy is not None:
            params["x"] = decision.point_xy[0]
            params["y"] = decision.point_xy[1]
        if decision.end_point_xy is not None:
            # ``to_x``/``to_y`` are the names the executor's drag branch reads,
            # so keep them in sync with the AgentDecision.end_coords.
            params["to_x"] = decision.end_point_xy[0]
            params["to_y"] = decision.end_point_xy[1]
    elif internal == "scroll":
        if decision.point_xy is not None:
            params["x"] = decision.point_xy[0]
            params["y"] = decision.point_xy[1]
        params["direction"] = decision.action_params.get("direction", "down")
    elif internal == "type":
        # Executor accepts both 'text' and 'content'; use 'text' for clarity.
        params["text"] = decision.action_params.get("content", "")
    elif internal == "key_combo":
        # Executor accepts both keys=[...] and key='ctrl s'.
        params["key"] = decision.action_params.get("key", "")
    elif internal == "finished":
        params["content"] = decision.finished_content

    return Action(type=internal, params=params)  # type: ignore[arg-type]


def _format_target_desc(decision: UITarsDecision) -> str:
    """Short label used for progress detection and logs.

    UI-TARS does not give us an element name, so we use the ``Action:`` line
    the model emitted — it encodes the coordinates and parameters and is
    unique enough that two different clicks produce two different labels.
    """
    raw = decision.raw_response or ""
    if "Action:" in raw:
        tail = raw.split("Action:", 1)[1].strip()
        # Only the first line — the rest is noise / follow-up actions.
        return tail.splitlines()[0].strip()[:200]
    return decision.action_type


@runtime_checkable
class _DecideBackend(Protocol):
    """Structural type for anything this agent can drive.

    :class:`UITarsBackend` and :class:`MAIUIBackend` both satisfy this —
    they share an identical ``decide`` surface but differ internally in
    prompt dialect (same), coordinate transform (sent-pixel vs
    [0, 1000]) and stop-sequence handling.  Using a Protocol here keeps
    the agent layer agnostic to the concrete checkpoint family.
    """

    def decide(
        self,
        image_png: bytes,
        goal: str,
        history: list[HistoryStep] | None = None,
    ) -> UITarsDecision:
        ...


class UITarsAgent:
    """Single-model agent driven by any UI-TARS-dialect backend.

    Maintains an in-memory rolling history of
    ``(thought, action_summary, screenshot)`` triples so the prompt
    reflects the ByteDance reference format.  History is bounded by
    ``max_history`` (default 10 steps; only the most recent few carry
    screenshots per the backend's own ``history_images`` limit).

    The concrete backend can be either the UI-TARS vLLM backend or the
    MAI-UI backend — the agent only cares about the structural ``decide``
    contract (see :class:`_DecideBackend`).  The class keeps its
    ``UITars`` name for backward compatibility with existing imports.
    """

    def __init__(
        self,
        backend: _DecideBackend,
        max_history: int = 10,
    ) -> None:
        self._backend = backend
        self._max_history = max_history
        self._history: list[HistoryStep] = []
        # One step of deferred bookkeeping: the assistant turn produced in
        # the previous ``decide`` call is only committed after the action
        # has been executed (i.e. at the start of the next ``decide``).
        self._pending_step: HistoryStep | None = None

    def decide(
        self,
        session: SessionContext,
        snapshot: FrameSnapshot,
    ) -> AgentDecision:
        # 1. Commit the previous step into history.
        if self._pending_step is not None:
            self._history.append(self._pending_step)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._pending_step = None

        # 2. Ask UI-TARS.
        ui = self._backend.decide(
            image_png=snapshot.screenshot_png,
            goal=session.goal,
            history=self._history,
        )

        # 3. Remember this turn for the next ``decide``.
        action_summary = _format_target_desc(ui)
        self._pending_step = HistoryStep(
            thought=ui.thought,
            action_summary=action_summary or ui.action_type,
            screenshot_png=snapshot.screenshot_png,
        )

        # 4. Project onto the engine's AgentDecision.
        action = _uitars_to_action(ui)
        decision = AgentDecision(
            action=action,
            thought=ui.thought,
            target_desc=action_summary,
            coords=ui.point_xy,
            end_coords=ui.end_point_xy,
            grounding_confidence=None,
            finished=ui.finished,
            finished_content=ui.finished_content,
            done_reason=ui.finished_content if ui.finished else "",
        )
        if ui.parse_error:
            logger.warning("uitars_parse_error forwarded to step loop: %s", ui.parse_error)
        return decision
