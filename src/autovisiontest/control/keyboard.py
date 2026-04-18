"""Keyboard control primitives using pyautogui + pyperclip."""

from __future__ import annotations

import pyautogui
import pyperclip

from autovisiontest.control.dpi import enable_dpi_awareness


def _has_non_ascii(text: str) -> bool:
    """Return True if text contains any codepoint > 127."""
    return any(ord(c) > 127 for c in text)


def type_text(text: str, interval_ms: int = 20) -> None:
    """Type text. Automatically uses clipboard for non-ASCII content.

    For pure ASCII text, uses pyautogui.typewrite.
    For text containing non-ASCII characters (e.g. Chinese), uses
    pyperclip.copy + Ctrl+V to paste.
    """
    enable_dpi_awareness()
    if _has_non_ascii(text):
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.typewrite(text, interval=interval_ms)


def key_combo(*keys: str) -> None:
    """Press a key combination, e.g. key_combo("ctrl", "s")."""
    enable_dpi_awareness()
    pyautogui.hotkey(*keys)


def press(key: str) -> None:
    """Press a single key."""
    enable_dpi_awareness()
    pyautogui.press(key)
