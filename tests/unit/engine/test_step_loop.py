"""Unit tests for engine/step_loop.py."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autovisiontest.control.actions import Action, ActionResult
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.engine.actor import Actor, LocateResult
from autovisiontest.engine.models import BugHint, SessionContext, StepRecord, TerminationReason
from autovisiontest.engine.planner import Planner
from autovisiontest.engine.step_loop import StepLoop
from autovisiontest.engine.terminator import Terminator
from autovisiontest.perception.facade import FrameSnapshot, Perception
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult
from autovisiontest.prompts.planner import PlannerDecision
from autovisiontest.safety.guard import SafetyGuard, SafetyVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ocr() -> OCRResult:
    return OCRResult(items=[], image_size=(1920, 1080))


def _make_snapshot(t: float | None = None) -> FrameSnapshot:
    return FrameSnapshot(
        screenshot=np.zeros((1080, 1920, 3), dtype=np.uint8),
        screenshot_png=b"\x89PNG",
        ocr=_make_ocr(),
        timestamp=t or time.time(),
    )


def _make_decision(
    action_type: str = "click",
    done: bool = False,
    target_desc: str = "the button",
    reflection: str = "",
    next_intent: str = "test",
    bug_hints: list[BugHint] | None = None,
) -> PlannerDecision:
    return PlannerDecision(
        reflection=reflection,
        done=done,
        bug_hints=bug_hints or [],
        next_intent=next_intent,
        target_desc=target_desc,
        action=Action(type=action_type, params={}),
    )


def _make_step_loop(
    planner: Planner | None = None,
    actor: Actor | None = None,
    terminator: Terminator | None = None,
    safety_guard: SafetyGuard | None = None,
    executor: ActionExecutor | None = None,
    perception: Perception | None = None,
    step_wait_ms: int = 0,  # No wait in tests
) -> StepLoop:
    return StepLoop(
        planner=planner or MagicMock(spec=Planner),
        actor=actor or MagicMock(spec=Actor),
        terminator=terminator or MagicMock(spec=Terminator),
        safety_guard=safety_guard or MagicMock(spec=SafetyGuard),
        executor=executor or MagicMock(spec=ActionExecutor),
        perception=perception or MagicMock(spec=Perception),
        step_wait_ms=step_wait_ms,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStepLoop:
    """Tests for the StepLoop class."""

    def test_run_happy_path_pass(self) -> None:
        """Planner returns done=True after a few steps → PASS."""
        mock_planner = MagicMock(spec=Planner)
        mock_planner.decide.side_effect = [
            _make_decision(action_type="click", done=False, reflection="step 1"),
            _make_decision(action_type="type", done=False, reflection="step 2"),
            _make_decision(action_type="wait", done=True, reflection="done"),
        ]

        mock_actor = MagicMock(spec=Actor)
        mock_actor.locate.return_value = LocateResult(
            success=True, x=100, y=200, source="grounding", confidence=0.8
        )

        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = None

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_safety.check.return_value = SafetyVerdict(decision="pass")

        mock_executor = MagicMock(spec=ActionExecutor)
        mock_executor.execute.return_value = ActionResult(success=True)

        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            actor=mock_actor,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.PASS
        assert session.termination_reason == TerminationReason.PASS
        assert session.step_count == 2  # 2 steps before done

    def test_run_crash_terminates(self) -> None:
        """Terminator detects crash → CRASH."""
        mock_planner = MagicMock(spec=Planner)
        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = TerminationReason.CRASH

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_executor = MagicMock(spec=ActionExecutor)
        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.CRASH
        assert session.termination_reason == TerminationReason.CRASH

    def test_run_max_steps_terminates(self) -> None:
        """Terminator detects max steps → MAX_STEPS."""
        mock_planner = MagicMock(spec=Planner)
        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = TerminationReason.MAX_STEPS

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_executor = MagicMock(spec=ActionExecutor)
        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.MAX_STEPS

    def test_run_safety_blocks(self) -> None:
        """SafetyGuard blocks → UNSAFE."""
        mock_planner = MagicMock(spec=Planner)
        mock_planner.decide.return_value = _make_decision(action_type="click", done=False)

        mock_actor = MagicMock(spec=Actor)
        mock_actor.locate.return_value = LocateResult(
            success=True, x=100, y=200, source="grounding", confidence=0.8
        )

        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = None

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_safety.check.return_value = SafetyVerdict(decision="blocked", reason="click near '删除'")

        mock_executor = MagicMock(spec=ActionExecutor)
        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            actor=mock_actor,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.UNSAFE

    def test_run_safety_timeout(self) -> None:
        """SafetyGuard returns timeout → MAX_STEPS."""
        mock_planner = MagicMock(spec=Planner)
        mock_planner.decide.return_value = _make_decision(action_type="wait", done=False)

        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = None

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_safety.check.return_value = SafetyVerdict(decision="timeout", reason="MAX_DURATION")

        mock_executor = MagicMock(spec=ActionExecutor)
        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.MAX_STEPS

    def test_run_target_not_found_continues(self) -> None:
        """When Actor fails to locate, step is recorded and loop continues."""
        mock_planner = MagicMock(spec=Planner)
        mock_planner.decide.side_effect = [
            _make_decision(action_type="click", done=False, target_desc="missing button"),
            _make_decision(action_type="wait", done=True),  # Second call succeeds
        ]

        mock_actor = MagicMock(spec=Actor)
        # First locate fails, second not called (wait doesn't need target)
        mock_actor.locate.return_value = LocateResult(success=False)

        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = None

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_safety.check.return_value = SafetyVerdict(decision="pass")

        mock_executor = MagicMock(spec=ActionExecutor)
        mock_executor.execute.return_value = ActionResult(success=True)

        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            actor=mock_actor,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.PASS
        # First step was recorded even though target wasn't found
        assert len(session.steps) >= 1

    def test_run_capture_snapshot_crash(self) -> None:
        """If capture_snapshot fails, return CRASH."""
        mock_planner = MagicMock(spec=Planner)
        mock_terminator = MagicMock(spec=Terminator)
        mock_safety = MagicMock(spec=SafetyGuard)
        mock_executor = MagicMock(spec=ActionExecutor)

        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.side_effect = RuntimeError("screenshot failed")

        loop = _make_step_loop(
            planner=mock_planner,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.CRASH

    def test_run_sets_start_time(self) -> None:
        """If session.start_time is 0, it should be set."""
        mock_planner = MagicMock(spec=Planner)
        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = TerminationReason.CRASH

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_executor = MagicMock(spec=ActionExecutor)
        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal", start_time=0.0)
        loop.run(session)
        assert session.start_time > 0.0

    def test_run_bug_hints_collected(self) -> None:
        """Bug hints from Planner decisions are accumulated in session."""
        hint = BugHint(description="test bug", confidence=0.8)

        mock_planner = MagicMock(spec=Planner)
        mock_planner.decide.side_effect = [
            _make_decision(action_type="click", done=False, bug_hints=[hint]),
            _make_decision(action_type="wait", done=True),
        ]

        mock_actor = MagicMock(spec=Actor)
        mock_actor.locate.return_value = LocateResult(
            success=True, x=100, y=200, source="grounding", confidence=0.8
        )

        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = None

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_safety.check.return_value = SafetyVerdict(decision="pass")

        mock_executor = MagicMock(spec=ActionExecutor)
        mock_executor.execute.return_value = ActionResult(success=True)

        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            actor=mock_actor,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        loop.run(session)
        assert len(session.bug_hints) == 1
        assert session.bug_hints[0].description == "test bug"

    def test_run_action_not_needing_target(self) -> None:
        """Actions that don't need a target (type, key_combo, wait) skip Actor."""
        mock_planner = MagicMock(spec=Planner)
        mock_planner.decide.side_effect = [
            _make_decision(action_type="type", done=False, target_desc=""),
            _make_decision(action_type="wait", done=True),
        ]

        mock_actor = MagicMock(spec=Actor)
        mock_terminator = MagicMock(spec=Terminator)
        mock_terminator.check.return_value = None

        mock_safety = MagicMock(spec=SafetyGuard)
        mock_safety.check.return_value = SafetyVerdict(decision="pass")

        mock_executor = MagicMock(spec=ActionExecutor)
        mock_executor.execute.return_value = ActionResult(success=True)

        mock_perception = MagicMock(spec=Perception)
        mock_perception.capture_snapshot.return_value = _make_snapshot()

        loop = _make_step_loop(
            planner=mock_planner,
            actor=mock_actor,
            terminator=mock_terminator,
            safety_guard=mock_safety,
            executor=mock_executor,
            perception=mock_perception,
        )

        session = SessionContext(goal="test goal")
        result = loop.run(session)

        assert result == TerminationReason.PASS
        # Actor.locate should NOT be called for type action
        mock_actor.locate.assert_not_called()
