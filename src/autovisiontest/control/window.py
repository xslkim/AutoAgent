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


def find_calculator_window() -> WindowInfo | None:
    """Best-effort match for the Windows Calculator window (desktop or UWP).

    UWP builds may use ``ApplicationFrameHost.exe``; matching by title avoids
    relying on ``Calculator.exe`` appearing in ``tasklist``.
    """
    enable_dpi_awareness()
    try:
        for w in gw.getAllWindows():
            title = (w.title or "").strip()
            if len(title) < 2:
                continue
            tl = title.lower()
            match = False
            if "计算器" in title:
                match = True
            elif "calculator" in tl and "edge" not in tl and "chrome" not in tl:
                match = True
            if not match:
                continue
            try:
                return WindowInfo(
                    title=title,
                    pid=w.processId,
                    handle=w.getHandle(),
                    rect=(w.left, w.top, w.right, w.bottom),
                )
            except Exception:
                continue
    except Exception:
        pass
    return None


def wait_for_app_main_window(
    app_path: str,
    launcher_pid: int,
    timeout_s: float = 20.0,
    poll_interval_s: float = 0.2,
) -> None:
    """Block until a plausible main window exists for *app_path*.

    ``calc.exe`` on Windows 10/11 exits immediately after spawning the real
    UI; we detect it via :func:`find_calculator_window` as well as title
    substring heuristics.
    """
    exe = app_path.rsplit("\\", 1)[-1] if "\\" in app_path else app_path.rsplit("/", 1)[-1]
    exe_l = exe.lower()
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        if find_window_by_pid(launcher_pid) is not None:
            return
        if exe_l == "calc.exe":
            if find_calculator_window() is not None:
                return
            for pattern in ("计算器", "Calculator"):
                if find_window_by_title(pattern) is not None:
                    return
        time.sleep(poll_interval_s)


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
