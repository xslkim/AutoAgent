"""Tests for window management utilities.

Most tests mock pygetwindow since real window operations are environment-dependent.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.control.window import (
    WindowInfo,
    find_window_by_pid,
    find_window_by_title,
    focus,
    list_windows,
    wait_window,
)
from autovisiontest.exceptions import AppLaunchError


class MockWindow:
    """A mock pygetwindow Window."""

    def __init__(
        self,
        title: str = "Test Window",
        pid: int = 1234,
        left: int = 0,
        top: int = 0,
        right: int = 800,
        bottom: int = 600,
    ) -> None:
        self.title = title
        self.processId = pid
        self._left = left
        self._top = top
        self._right = right
        self._bottom = bottom

    @property
    def left(self) -> int:
        return self._left

    @property
    def top(self) -> int:
        return self._top

    @property
    def right(self) -> int:
        return self._right

    @property
    def bottom(self) -> int:
        return self._bottom

    def getHandle(self) -> int:
        return 0xDEAD

    def activate(self) -> None:
        pass


@pytest.fixture
def mock_windows():
    """Provide a set of mock windows."""
    return [
        MockWindow(title="Notepad", pid=100),
        MockWindow(title="Chrome - Google", pid=200),
        MockWindow(title="Visual Studio Code", pid=300),
    ]


class TestListWindows:
    @patch("autovisiontest.control.window.gw")
    def test_list_windows_returns_items(self, mock_gw: MagicMock, mock_windows: list) -> None:
        mock_gw.getAllWindows.return_value = mock_windows
        result = list_windows()
        assert len(result) == 3
        assert all(isinstance(w, WindowInfo) for w in result)


class TestFindWindowByTitle:
    @patch("autovisiontest.control.window.gw")
    def test_find_existing_window(self, mock_gw: MagicMock, mock_windows: list) -> None:
        mock_gw.getWindowsWithTitle.return_value = [mock_windows[0]]
        result = find_window_by_title("Notepad")
        assert result is not None
        assert result.title == "Notepad"

    @patch("autovisiontest.control.window.gw")
    def test_find_nonexistent_returns_none(self, mock_gw: MagicMock) -> None:
        mock_gw.getWindowsWithTitle.return_value = []
        mock_gw.getAllWindows.return_value = []
        result = find_window_by_title("Nonexistent")
        assert result is None


class TestFindWindowByPid:
    @patch("autovisiontest.control.window.gw")
    def test_find_by_pid(self, mock_gw: MagicMock, mock_windows: list) -> None:
        mock_gw.getAllWindows.return_value = mock_windows
        result = find_window_by_pid(200)
        assert result is not None
        assert result.pid == 200

    @patch("autovisiontest.control.window.gw")
    def test_find_by_pid_not_found(self, mock_gw: MagicMock) -> None:
        mock_gw.getAllWindows.return_value = []
        result = find_window_by_pid(9999)
        assert result is None


class TestFocus:
    @patch("autovisiontest.control.window.gw")
    def test_focus_success(self, mock_gw: MagicMock, mock_windows: list) -> None:
        mock_gw.getWindowsWithTitle.return_value = [mock_windows[0]]
        win = WindowInfo(title="Notepad", pid=100, handle=1, rect=(0, 0, 800, 600))
        result = focus(win)
        assert result is True


class TestWaitWindow:
    @patch("autovisiontest.control.window.find_window_by_title")
    def test_wait_window_success(self, mock_find: MagicMock) -> None:
        mock_find.return_value = WindowInfo(title="Notepad", pid=100, handle=1, rect=(0, 0, 800, 600))
        result = wait_window("Notepad", timeout_s=1.0)
        assert result.title == "Notepad"

    @patch("autovisiontest.control.window.find_window_by_title")
    def test_wait_window_timeout(self, mock_find: MagicMock) -> None:
        mock_find.return_value = None
        with pytest.raises(AppLaunchError, match="did not appear"):
            wait_window("Nonexistent", timeout_s=0.3)
