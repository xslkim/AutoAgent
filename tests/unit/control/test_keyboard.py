"""Tests for keyboard control primitives.

All tests mock pyautogui and pyperclip to avoid triggering real keyboard input.
"""

from __future__ import annotations

from unittest.mock import call, patch

import pytest

from autovisiontest.control.keyboard import key_combo, press, type_text


@pytest.fixture(autouse=True)
def _mock_deps():
    """Mock pyautogui and pyperclip for all tests."""
    with (
        patch("autovisiontest.control.keyboard.pyautogui") as mock_pya,
        patch("autovisiontest.control.keyboard.pyperclip") as mock_clip,
    ):
        yield {"pyautogui": mock_pya, "pyperclip": mock_clip}


class TestTypeText:
    def test_type_ascii_uses_typewrite(self, _mock_deps: dict) -> None:
        type_text("hello")
        _mock_deps["pyautogui"].typewrite.assert_called_once_with("hello", interval=20)
        _mock_deps["pyperclip"].copy.assert_not_called()

    def test_type_chinese_uses_clipboard(self, _mock_deps: dict) -> None:
        type_text("你好")
        _mock_deps["pyperclip"].copy.assert_called_once_with("你好")
        _mock_deps["pyautogui"].hotkey.assert_called_once_with("ctrl", "v")
        _mock_deps["pyautogui"].typewrite.assert_not_called()

    def test_type_mixed_uses_clipboard(self, _mock_deps: dict) -> None:
        """Text with any non-ASCII should go through clipboard."""
        type_text("hello 中文")
        _mock_deps["pyperclip"].copy.assert_called_once_with("hello 中文")
        _mock_deps["pyautogui"].hotkey.assert_called_once_with("ctrl", "v")

    def test_type_custom_interval(self, _mock_deps: dict) -> None:
        type_text("abc", interval_ms=50)
        _mock_deps["pyautogui"].typewrite.assert_called_once_with("abc", interval=50)


class TestKeyCombo:
    def test_key_combo_ctrl_s(self, _mock_deps: dict) -> None:
        key_combo("ctrl", "s")
        _mock_deps["pyautogui"].hotkey.assert_called_once_with("ctrl", "s")

    def test_key_combo_ctrl_shift_esc(self, _mock_deps: dict) -> None:
        key_combo("ctrl", "shift", "esc")
        _mock_deps["pyautogui"].hotkey.assert_called_once_with("ctrl", "shift", "esc")


class TestPress:
    def test_press_enter(self, _mock_deps: dict) -> None:
        press("enter")
        _mock_deps["pyautogui"].press.assert_called_once_with("enter")

    def test_press_tab(self, _mock_deps: dict) -> None:
        press("tab")
        _mock_deps["pyautogui"].press.assert_called_once_with("tab")
