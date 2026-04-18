"""Unit tests for engine/exploratory.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.control.process import AppHandle
from autovisiontest.engine.exploratory import ExploratoryRunner
from autovisiontest.engine.models import TerminationReason
from autovisiontest.engine.step_loop import StepLoop


class TestExploratoryRunner:
    """Tests for ExploratoryRunner."""

    def _make_runner(self) -> ExploratoryRunner:
        """Create a runner with mock backends."""
        mock_chat = MagicMock()
        mock_grounding = MagicMock()
        return ExploratoryRunner(
            chat_backend=mock_chat,
            grounding_backend=mock_grounding,
            max_steps=30,
            confidence_threshold=0.6,
        )

    @patch("autovisiontest.engine.exploratory.kill_processes_by_exe")
    @patch("autovisiontest.engine.exploratory.launch_app")
    @patch("autovisiontest.engine.exploratory.close_app")
    @patch("autovisiontest.engine.exploratory.StepLoop")
    @patch("autovisiontest.engine.exploratory.Perception")
    @patch("autovisiontest.engine.exploratory.Planner")
    @patch("autovisiontest.engine.exploratory.Actor")
    @patch("autovisiontest.engine.exploratory.Terminator")
    @patch("autovisiontest.engine.exploratory.SecondCheck")
    @patch("autovisiontest.engine.exploratory.SafetyGuard")
    @patch("autovisiontest.engine.exploratory.ActionExecutor")
    def test_run_happy_path(
        self,
        mock_executor_cls: MagicMock,
        mock_safety_cls: MagicMock,
        mock_second_check_cls: MagicMock,
        mock_terminator_cls: MagicMock,
        mock_actor_cls: MagicMock,
        mock_planner_cls: MagicMock,
        mock_perception_cls: MagicMock,
        mock_step_loop_cls: MagicMock,
        mock_close_app: MagicMock,
        mock_launch_app: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        """Happy path: app launched, loop runs, app closed."""
        mock_handle = MagicMock(spec=AppHandle)
        mock_handle.pid = 5678
        mock_handle.exe_name = "notepad.exe"
        mock_launch_app.return_value = mock_handle

        mock_step_loop = MagicMock(spec=StepLoop)
        mock_step_loop.run.return_value = TerminationReason.PASS
        mock_step_loop_cls.return_value = mock_step_loop

        runner = self._make_runner()
        session = runner.run(goal="open notepad", app_path="notepad.exe")

        assert session.mode == "exploratory"
        assert session.goal == "open notepad"
        mock_kill.assert_called_once_with("notepad.exe")
        mock_launch_app.assert_called_once()
        mock_close_app.assert_called_once_with(mock_handle)

    @patch("autovisiontest.engine.exploratory.kill_processes_by_exe")
    @patch("autovisiontest.engine.exploratory.launch_app")
    @patch("autovisiontest.engine.exploratory.close_app")
    @patch("autovisiontest.engine.exploratory.StepLoop")
    @patch("autovisiontest.engine.exploratory.Perception")
    @patch("autovisiontest.engine.exploratory.Planner")
    @patch("autovisiontest.engine.exploratory.Actor")
    @patch("autovisiontest.engine.exploratory.Terminator")
    @patch("autovisiontest.engine.exploratory.SecondCheck")
    @patch("autovisiontest.engine.exploratory.SafetyGuard")
    @patch("autovisiontest.engine.exploratory.ActionExecutor")
    def test_run_cleans_up_on_exception(
        self,
        mock_executor_cls: MagicMock,
        mock_safety_cls: MagicMock,
        mock_second_check_cls: MagicMock,
        mock_terminator_cls: MagicMock,
        mock_actor_cls: MagicMock,
        mock_planner_cls: MagicMock,
        mock_perception_cls: MagicMock,
        mock_step_loop_cls: MagicMock,
        mock_close_app: MagicMock,
        mock_launch_app: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        """If StepLoop.run raises, the app should still be closed."""
        mock_handle = MagicMock(spec=AppHandle)
        mock_handle.pid = 1234
        mock_handle.exe_name = "test.exe"
        mock_launch_app.return_value = mock_handle

        mock_step_loop = MagicMock(spec=StepLoop)
        mock_step_loop.run.side_effect = RuntimeError("something broke")
        mock_step_loop_cls.return_value = mock_step_loop

        runner = self._make_runner()
        session = runner.run(goal="test goal", app_path="C:\\test.exe")

        # App should be closed even after exception
        mock_close_app.assert_called_once_with(mock_handle)
        assert session.termination_reason == TerminationReason.CRASH

    @patch("autovisiontest.engine.exploratory.kill_processes_by_exe")
    @patch("autovisiontest.engine.exploratory.launch_app")
    @patch("autovisiontest.engine.exploratory.close_app")
    @patch("autovisiontest.engine.exploratory.StepLoop")
    @patch("autovisiontest.engine.exploratory.Perception")
    @patch("autovisiontest.engine.exploratory.Planner")
    @patch("autovisiontest.engine.exploratory.Actor")
    @patch("autovisiontest.engine.exploratory.Terminator")
    @patch("autovisiontest.engine.exploratory.SecondCheck")
    @patch("autovisiontest.engine.exploratory.SafetyGuard")
    @patch("autovisiontest.engine.exploratory.ActionExecutor")
    def test_run_close_fallback_to_kill(
        self,
        mock_executor_cls: MagicMock,
        mock_safety_cls: MagicMock,
        mock_second_check_cls: MagicMock,
        mock_terminator_cls: MagicMock,
        mock_actor_cls: MagicMock,
        mock_planner_cls: MagicMock,
        mock_perception_cls: MagicMock,
        mock_step_loop_cls: MagicMock,
        mock_close_app: MagicMock,
        mock_launch_app: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        """If close_app fails, fallback to kill_processes_by_exe."""
        mock_handle = MagicMock(spec=AppHandle)
        mock_handle.pid = 9999
        mock_handle.exe_name = "test.exe"
        mock_launch_app.return_value = mock_handle

        mock_step_loop = MagicMock(spec=StepLoop)
        mock_step_loop.run.return_value = TerminationReason.PASS
        mock_step_loop_cls.return_value = mock_step_loop

        # close_app raises, kill should be called as fallback
        mock_close_app.side_effect = RuntimeError("close failed")

        runner = self._make_runner()
        session = runner.run(goal="test", app_path="C:\\test.exe")

        # kill_processes_by_exe was called twice: once at start, once as fallback
        assert mock_kill.call_count == 2
