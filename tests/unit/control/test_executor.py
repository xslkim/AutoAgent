"""Tests for the action executor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.control.actions import Action, ActionResult
from autovisiontest.control.executor import ActionExecutor
from autovisiontest.exceptions import ActionExecutionError


@pytest.fixture
def executor() -> ActionExecutor:
    return ActionExecutor()


class TestActionExecute:
    @patch("autovisiontest.control.executor.mouse")
    def test_execute_click(self, mock_mouse: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="click", params={"button": "right"})
        result = executor.execute(action, coords=(100, 200))
        assert result.success is True
        mock_mouse.click.assert_called_once_with(100, 200, button="right")

    @patch("autovisiontest.control.executor.keyboard")
    def test_execute_type_without_coords_ok(self, mock_kb: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="type", params={"text": "hello"})
        result = executor.execute(action)
        assert result.success is True
        mock_kb.type_text.assert_called_once_with("hello", interval_ms=20)

    @patch("autovisiontest.control.executor.mouse")
    def test_execute_click_without_coords_raises(self, mock_mouse: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="click", params={})
        with pytest.raises(ActionExecutionError, match="requires coords"):
            executor.execute(action, coords=None)

    def test_execute_unknown_action_type_raises(self, executor: ActionExecutor) -> None:
        """Test that _dispatch raises for an unrecognized type."""
        action = Action(type="wait")
        # Manually set type to something invalid to test the match fallback
        object.__setattr__(action, "type", "nonexistent")
        with pytest.raises(ActionExecutionError, match="Unknown action type"):
            executor.execute(action, coords=None)

    @patch("autovisiontest.control.executor.mouse")
    def test_execute_double_click(self, mock_mouse: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="double_click", params={})
        result = executor.execute(action, coords=(50, 60))
        assert result.success is True
        mock_mouse.double_click.assert_called_once_with(50, 60)

    @patch("autovisiontest.control.executor.mouse")
    def test_execute_right_click(self, mock_mouse: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="right_click", params={})
        result = executor.execute(action, coords=(10, 20))
        assert result.success is True
        mock_mouse.right_click.assert_called_once_with(10, 20)

    @patch("autovisiontest.control.executor.keyboard")
    def test_execute_key_combo(self, mock_kb: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="key_combo", params={"keys": ["ctrl", "s"]})
        result = executor.execute(action)
        assert result.success is True
        mock_kb.key_combo.assert_called_once_with("ctrl", "s")

    def test_execute_wait(self, executor: ActionExecutor) -> None:
        action = Action(type="wait", params={"duration_s": 0.01})
        result = executor.execute(action)
        assert result.success is True

    @patch("autovisiontest.control.executor.mouse")
    def test_execute_scroll(self, mock_mouse: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="scroll", params={"dy": 3})
        result = executor.execute(action, coords=(100, 100))
        assert result.success is True
        mock_mouse.scroll.assert_called_once_with(100, 100, dy=3)

    @patch("autovisiontest.control.executor.mouse")
    def test_execute_drag(self, mock_mouse: MagicMock, executor: ActionExecutor) -> None:
        action = Action(type="drag", params={"to_x": 200, "to_y": 300, "duration_ms": 500})
        result = executor.execute(action, coords=(10, 20))
        assert result.success is True
        mock_mouse.drag.assert_called_once_with((10, 20), (200, 300), duration_ms=500)
