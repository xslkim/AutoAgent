"""Unit tests for engine/regression.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.control.actions import Action
from autovisiontest.control.process import AppHandle
from autovisiontest.engine.models import SessionContext, TerminationReason
from autovisiontest.engine.regression import RegressionRunner, ScriptPlanner, StubRecordingStore
from autovisiontest.engine.step_loop import StepLoop
from autovisiontest.prompts.planner import PlannerDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recording(
    goal: str = "test goal",
    app_path: str = "notepad.exe",
    steps: list[dict] | None = None,
) -> dict:
    return {
        "goal": goal,
        "app_path": app_path,
        "app_args": [],
        "steps": steps or [
            {
                "action": Action(type="click", params={"button": "left"}),
                "target_desc": "the button",
                "planner_intent": "click the button",
            },
        ],
    }


class TestStubRecordingStore:
    """Tests for StubRecordingStore."""

    def test_load_found(self) -> None:
        store = StubRecordingStore({"fp1": {"goal": "test"}})
        result = store.load("fp1")
        assert result is not None
        assert result["goal"] == "test"

    def test_load_not_found(self) -> None:
        store = StubRecordingStore({})
        result = store.load("fp1")
        assert result is None

    def test_find_for_goal(self) -> None:
        store = StubRecordingStore({"fp1": {"goal": "open notepad"}})
        result = store.find_for_goal("notepad.exe", "open notepad")
        assert result is not None
        assert result["goal"] == "open notepad"

    def test_find_for_goal_not_found(self) -> None:
        store = StubRecordingStore({"fp1": {"goal": "open notepad"}})
        result = store.find_for_goal("notepad.exe", "open calculator")
        assert result is None


class TestScriptPlanner:
    """Tests for ScriptPlanner."""

    def test_returns_recorded_steps_in_order(self) -> None:
        recording = _make_recording(steps=[
            {
                "action": Action(type="click", params={"button": "left"}),
                "target_desc": "button 1",
                "planner_intent": "click first",
            },
            {
                "action": Action(type="type", params={"text": "hello"}),
                "target_desc": "",
                "planner_intent": "type text",
            },
        ])
        planner = ScriptPlanner(recording, chat_backend=MagicMock())
        session = SessionContext(goal="test")

        # First step
        decision1 = planner.decide(session, MagicMock())
        assert decision1.next_intent == "click first"
        assert decision1.action.type == "click"
        assert not decision1.done

        # Second step
        decision2 = planner.decide(session, MagicMock())
        assert decision2.next_intent == "type text"
        assert decision2.action.type == "type"
        assert not decision2.done

        # After all steps — done
        decision3 = planner.decide(session, MagicMock())
        assert decision3.done is True

    def test_empty_recording_returns_done(self) -> None:
        recording = {"goal": "test", "app_path": "test.exe", "app_args": [], "steps": []}
        planner = ScriptPlanner(recording, chat_backend=MagicMock())
        session = SessionContext(goal="test")

        decision = planner.decide(session, MagicMock())
        assert decision.done is True


class TestRegressionRunner:
    """Tests for RegressionRunner."""

    def _make_runner(self, store: StubRecordingStore | None = None) -> RegressionRunner:
        mock_chat = MagicMock()
        mock_grounding = MagicMock()
        return RegressionRunner(
            chat_backend=mock_chat,
            grounding_backend=mock_grounding,
            store=store or StubRecordingStore(),
        )

    @patch("autovisiontest.engine.regression.kill_processes_by_exe")
    @patch("autovisiontest.engine.regression.launch_app")
    @patch("autovisiontest.engine.regression.close_app")
    @patch("autovisiontest.engine.regression.StepLoop")
    @patch("autovisiontest.engine.regression.Perception")
    @patch("autovisiontest.engine.regression.Actor")
    @patch("autovisiontest.engine.regression.Terminator")
    @patch("autovisiontest.engine.regression.SecondCheck")
    @patch("autovisiontest.engine.regression.SafetyGuard")
    @patch("autovisiontest.engine.regression.ActionExecutor")
    def test_run_regression_pass(
        self,
        mock_executor_cls: MagicMock,
        mock_safety_cls: MagicMock,
        mock_second_check_cls: MagicMock,
        mock_terminator_cls: MagicMock,
        mock_actor_cls: MagicMock,
        mock_perception_cls: MagicMock,
        mock_step_loop_cls: MagicMock,
        mock_close_app: MagicMock,
        mock_launch_app: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        """Successful regression run returns session with PASS."""
        recording = _make_recording()
        store = StubRecordingStore({"fp1": recording})

        mock_handle = MagicMock(spec=AppHandle)
        mock_handle.pid = 1234
        mock_handle.exe_name = "notepad.exe"
        mock_launch_app.return_value = mock_handle

        mock_step_loop = MagicMock(spec=StepLoop)
        mock_step_loop.run.return_value = TerminationReason.PASS
        mock_step_loop_cls.return_value = mock_step_loop

        runner = self._make_runner(store)
        session = runner.run("fp1")

        assert session.mode == "regression"
        assert session.goal == "test goal"
        assert not session.recording_invalid
        mock_close_app.assert_called_once_with(mock_handle)

    def test_run_recording_not_found(self) -> None:
        """If recording is not found, returns session with TARGET_NOT_FOUND."""
        store = StubRecordingStore({})
        runner = self._make_runner(store)
        session = runner.run("nonexistent")

        assert session.termination_reason == TerminationReason.TARGET_NOT_FOUND

    @patch("autovisiontest.engine.regression.kill_processes_by_exe")
    @patch("autovisiontest.engine.regression.launch_app")
    @patch("autovisiontest.engine.regression.close_app")
    @patch("autovisiontest.engine.regression.StepLoop")
    @patch("autovisiontest.engine.regression.Perception")
    @patch("autovisiontest.engine.regression.Actor")
    @patch("autovisiontest.engine.regression.Terminator")
    @patch("autovisiontest.engine.regression.SecondCheck")
    @patch("autovisiontest.engine.regression.SafetyGuard")
    @patch("autovisiontest.engine.regression.ActionExecutor")
    def test_run_regression_invalidation_on_failure(
        self,
        mock_executor_cls: MagicMock,
        mock_safety_cls: MagicMock,
        mock_second_check_cls: MagicMock,
        mock_terminator_cls: MagicMock,
        mock_actor_cls: MagicMock,
        mock_perception_cls: MagicMock,
        mock_step_loop_cls: MagicMock,
        mock_close_app: MagicMock,
        mock_launch_app: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        """If the session does not PASS, recording_invalid should be True."""
        recording = _make_recording()
        store = StubRecordingStore({"fp1": recording})

        mock_handle = MagicMock(spec=AppHandle)
        mock_handle.pid = 1234
        mock_handle.exe_name = "notepad.exe"
        mock_launch_app.return_value = mock_handle

        mock_step_loop = MagicMock(spec=StepLoop)
        mock_step_loop.run.return_value = TerminationReason.MAX_STEPS
        mock_step_loop_cls.return_value = mock_step_loop

        runner = self._make_runner(store)
        session = runner.run("fp1")

        assert session.recording_invalid is True
