"""Tests for process management utilities."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.control.process import (
    AppHandle,
    close_app,
    is_alive,
    kill_processes_by_exe,
    launch_app,
)
from autovisiontest.exceptions import AppLaunchError


class TestKillProcessesByExe:
    def test_kill_nonexistent_returns_zero(self) -> None:
        """Killing a process that doesn't exist should return 0."""
        with patch("autovisiontest.control.process.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="ERROR: The process \"nonexistent.exe\" not found.",
                stderr="",
            )
            result = kill_processes_by_exe("nonexistent.exe")
            assert result == 0

    def test_kill_existing_returns_count(self) -> None:
        with patch("autovisiontest.control.process.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="SUCCESS: Sent termination signal to process 1234.\nSUCCESS: Sent termination signal to process 5678.",
                stderr="",
            )
            result = kill_processes_by_exe("notepad.exe")
            assert result == 2


class TestLaunchApp:
    def test_launch_success(self) -> None:
        with patch("autovisiontest.control.process.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 1234
            mock_popen.return_value = mock_proc

            handle = launch_app("notepad.exe")
            assert isinstance(handle, AppHandle)
            assert handle.pid == 1234
            assert handle.exe_name == "notepad.exe"

    def test_launch_not_found_raises(self) -> None:
        with patch("autovisiontest.control.process.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("not found")
            with pytest.raises(AppLaunchError, match="not found"):
                launch_app("nonexistent.exe")


class TestIsAlive:
    def test_is_alive_running(self) -> None:
        mock_popen = MagicMock()
        mock_popen.poll.return_value = None  # Still running
        handle = AppHandle(pid=1234, popen=mock_popen, exe_name="notepad.exe")

        with patch("autovisiontest.control.process.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="notepad.exe  1234 Console  1  5,000 K")
            assert is_alive(handle) is True

    def test_is_alive_false_after_process_exits(self) -> None:
        mock_popen = MagicMock()
        mock_popen.poll.return_value = 0  # Exited
        handle = AppHandle(pid=1234, popen=mock_popen, exe_name="notepad.exe")
        assert is_alive(handle) is False


class TestCloseApp:
    def test_close_graceful(self) -> None:
        mock_popen = MagicMock()
        mock_popen.wait.return_value = 0
        handle = AppHandle(pid=1234, popen=mock_popen, exe_name="notepad.exe")

        with patch("autovisiontest.control.process.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="SUCCESS", stderr="")
            close_app(handle, timeout_s=1.0)
            # Should have called taskkill (graceful)
            assert mock_run.called

    def test_close_force_kill_on_timeout(self) -> None:
        mock_popen = MagicMock()
        mock_popen.wait.side_effect = [subprocess.TimeoutExpired("cmd", 1), None]
        handle = AppHandle(pid=1234, popen=mock_popen, exe_name="notepad.exe")

        with patch("autovisiontest.control.process.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="SUCCESS", stderr="")
            close_app(handle, timeout_s=0.1)
