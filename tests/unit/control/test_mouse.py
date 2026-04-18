"""Tests for mouse control primitives.

All tests mock pyautogui to avoid triggering real mouse movements.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from autovisiontest.control.mouse import click, double_click, drag, move, right_click, scroll


@pytest.fixture(autouse=True)
def _mock_pyautogui():
    """Mock all pyautogui calls for every test in this module."""
    with (
        patch("autovisiontest.control.mouse.pyautogui.moveTo") as mock_move,
        patch("autovisiontest.control.mouse.pyautogui.click") as mock_click,
        patch("autovisiontest.control.mouse.pyautogui.doubleClick") as mock_dbl,
        patch("autovisiontest.control.mouse.pyautogui.rightClick") as mock_rc,
        patch("autovisiontest.control.mouse.pyautogui.mouseDown") as mock_down,
        patch("autovisiontest.control.mouse.pyautogui.mouseUp") as mock_up,
        patch("autovisiontest.control.mouse.pyautogui.scroll") as mock_scroll,
    ):
        yield {
            "moveTo": mock_move,
            "click": mock_click,
            "doubleClick": mock_dbl,
            "rightClick": mock_rc,
            "mouseDown": mock_down,
            "mouseUp": mock_up,
            "scroll": mock_scroll,
        }


class TestMove:
    def test_move_calls_moveto(self, _mock_pyautogui: dict) -> None:
        move(100, 200, duration_ms=150)
        _mock_pyautogui["moveTo"].assert_called_once_with(100, 200, duration=0.15)


class TestClick:
    def test_click_calls_pyautogui_with_args(self, _mock_pyautogui: dict) -> None:
        click(50, 60, button="right")
        _mock_pyautogui["click"].assert_called_once_with(50, 60, button="right")

    def test_click_default_button_is_left(self, _mock_pyautogui: dict) -> None:
        click(10, 20)
        _mock_pyautogui["click"].assert_called_once_with(10, 20, button="left")


class TestDoubleClick:
    def test_double_click_uses_doubleclick(self, _mock_pyautogui: dict) -> None:
        double_click(100, 100)
        _mock_pyautogui["doubleClick"].assert_called_once_with(100, 100)


class TestRightClick:
    def test_right_click(self, _mock_pyautogui: dict) -> None:
        right_click(200, 300)
        _mock_pyautogui["rightClick"].assert_called_once_with(200, 300)


class TestDrag:
    def test_drag_sequence(self, _mock_pyautogui: dict) -> None:
        drag((10, 20), (30, 40), duration_ms=200)
        # Should call: moveTo(10,20), mouseDown(), moveTo(30,40, duration=0.2), mouseUp()
        assert _mock_pyautogui["moveTo"].call_count == 2
        _mock_pyautogui["moveTo"].assert_any_call(10, 20)
        _mock_pyautogui["moveTo"].assert_any_call(30, 40, duration=0.2)
        _mock_pyautogui["mouseDown"].assert_called_once()
        _mock_pyautogui["mouseUp"].assert_called_once()


class TestScroll:
    def test_scroll_sign(self, _mock_pyautogui: dict) -> None:
        scroll(100, 100, dy=3)
        _mock_pyautogui["moveTo"].assert_called_with(100, 100)
        _mock_pyautogui["scroll"].assert_called_once_with(3)

    def test_scroll_negative(self, _mock_pyautogui: dict) -> None:
        scroll(100, 100, dy=-2)
        _mock_pyautogui["scroll"].assert_called_once_with(-2)
