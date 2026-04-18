"""Window management using pygetwindow + pywin32 fallback."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pygetwindow as gw

from autovisiontest.control.dpi import enable_dpi_awareness
from autovisiontest.exceptions import AppLaunchError

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """Information about a desktop window."""

    title: str
    pid: int
    handle: int
    rect: tuple[int, int, int, int]  # (left, top, right, bottom)


def list_windows() -> list[WindowInfo]:
    """List all visible windows."""
    enable_dpi_awareness()
    windows: list[WindowInfo] = []
    try:
        for w in gw.getAllWindows():
            if w.title:  # Skip windows with empty titles
                try:
                    windows.append(WindowInfo(
                        title=w.title,
                        pid=w.processId,
                        handle=w.getHandle(),
                        rect=(w.left, w.top, w.right, w.bottom),
                    ))
                except Exception:
                    continue
    except Exception:
        pass
    return windows


def find_window_by_title(pattern: str) -> WindowInfo | None:
    """Find a window by substring match on its title."""
    enable_dpi_awareness()
    try:
        wins = gw.getWindowsWithTitle(pattern)
        if wins:
            w = wins[0]
            return WindowInfo(
                title=w.title,
                pid=w.processId,
                handle=w.getHandle(),
                rect=(w.left, w.top, w.right, w.bottom),
            )
    except Exception:
        # Fallback: try substring match
        for w in gw.getAllWindows():
            if pattern.lower() in w.title.lower():
                return WindowInfo(
                    title=w.title,
                    pid=w.processId,
                    handle=w.getHandle(),
                    rect=(w.left, w.top, w.right, w.bottom),
                )
    return None


def find_window_by_pid(pid: int) -> WindowInfo | None:
    """Find a window by its process ID."""
    enable_dpi_awareness()
    for w in gw.getAllWindows():
        try:
            if w.processId == pid:
                return WindowInfo(
                    title=w.title,
                    pid=w.processId,
                    handle=w.getHandle(),
                    rect=(w.left, w.top, w.right, w.bottom),
                )
        except Exception:
            continue
    return None


def focus(win: WindowInfo) -> bool:
    """Bring window to foreground. Returns True on success."""
    enable_dpi_awareness()
    try:
        windows = gw.getWindowsWithTitle(win.title)
        if windows:
            windows[0].activate()
            return True
    except Exception:
        pass
    return False


def wait_window(
    pattern: str,
    timeout_s: float = 30.0,
    poll_interval_s: float = 0.2,
) -> WindowInfo:
    """Poll until a window matching *pattern* appears.

    Raises AppLaunchError if the window does not appear within *timeout_s*.
    """
    enable_dpi_awareness()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        win = find_window_by_title(pattern)
        if win is not None:
            return win
        time.sleep(poll_interval_s)
    raise AppLaunchError(
        f"Window matching '{pattern}' did not appear within {timeout_s}s",
        context={"pattern": pattern, "timeout_s": timeout_s},
    )
