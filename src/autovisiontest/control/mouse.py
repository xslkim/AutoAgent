"""Mouse control primitives using pyautogui."""

from __future__ import annotations

from typing import Literal

import pyautogui

from autovisiontest.control.dpi import enable_dpi_awareness

# Keep FAILSAFE enabled — moving mouse to screen corner triggers emergency stop
pyautogui.FAILSAFE = True


def move(x: int, y: int, duration_ms: int = 100) -> None:
    """Move mouse to (x, y) in physical pixels."""
    enable_dpi_awareness()
    pyautogui.moveTo(x, y, duration=duration_ms / 1000.0)


def click(
    x: int,
    y: int,
    button: Literal["left", "right", "middle"] = "left",
) -> None:
    """Click at (x, y) with the specified button."""
    enable_dpi_awareness()
    pyautogui.click(x, y, button=button)


def double_click(x: int, y: int) -> None:
    """Double-click at (x, y)."""
    enable_dpi_awareness()
    pyautogui.doubleClick(x, y)


def right_click(x: int, y: int) -> None:
    """Right-click at (x, y)."""
    enable_dpi_awareness()
    pyautogui.rightClick(x, y)


def drag(
    from_xy: tuple[int, int],
    to_xy: tuple[int, int],
    duration_ms: int = 300,
) -> None:
    """Drag from one point to another."""
    enable_dpi_awareness()
    fx, fy = from_xy
    tx, ty = to_xy
    pyautogui.moveTo(fx, fy)
    pyautogui.mouseDown()
    pyautogui.moveTo(tx, ty, duration=duration_ms / 1000.0)
    pyautogui.mouseUp()


def scroll(x: int, y: int, dy: int) -> None:
    """Scroll at (x, y). Positive dy scrolls up, negative scrolls down."""
    enable_dpi_awareness()
    pyautogui.moveTo(x, y)
    pyautogui.scroll(dy)
