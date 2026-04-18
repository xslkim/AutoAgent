"""Process management — launch, kill, and monitor application processes."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from autovisiontest.control.dpi import enable_dpi_awareness
from autovisiontest.exceptions import AppCrashedError, AppLaunchError

logger = logging.getLogger(__name__)


@dataclass
class AppHandle:
    """Handle to a launched application process."""

    pid: int
    popen: subprocess.Popen
    exe_name: str


def kill_processes_by_exe(exe_name: str) -> int:
    """Kill all processes with the given executable name.

    Uses ``taskkill /IM <exe> /F``. Ignores "process not found" errors.
    Returns the number of processes killed.
    """
    try:
        result = subprocess.run(
            ["taskkill", "/IM", exe_name, "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # taskkill outputs lines like "SUCCESS: ..." for each killed process
        output = result.stdout + result.stderr
        count = output.count("SUCCESS")
        return count
    except subprocess.TimeoutExpired:
        logger.warning("taskkill timed out for %s", exe_name)
        return 0
    except FileNotFoundError:
        logger.warning("taskkill not found")
        return 0


def launch_app(path: str, args: list[str] | None = None) -> AppHandle:
    """Launch an application and return an AppHandle.

    Raises AppLaunchError if the process cannot be started.
    """
    enable_dpi_awareness()
    cmd = [path] + (args or [])
    try:
        popen = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise AppLaunchError(
            f"Application not found: {path}",
            context={"path": path, "args": args},
        ) from e
    except OSError as e:
        raise AppLaunchError(
            f"Failed to launch {path}: {e}",
            context={"path": path, "args": args},
        ) from e

    exe_name = path.rsplit("\\", 1)[-1] if "\\" in path else path.rsplit("/", 1)[-1]
    return AppHandle(pid=popen.pid, popen=popen, exe_name=exe_name)


def is_alive(handle: AppHandle) -> bool:
    """Check if the application process is still running."""
    # First check via popen.poll()
    if handle.popen.poll() is not None:
        return False
    # Additional check: tasklist for the PID
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {handle.pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return str(handle.pid) in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback to popen poll only
        return handle.popen.poll() is None


def close_app(handle: AppHandle, timeout_s: float = 5.0) -> None:
    """Gracefully close the application.

    First sends WM_CLOSE via taskkill (no /F), then force-kills after timeout.
    """
    # Try graceful close first
    try:
        subprocess.run(
            ["taskkill", "/PID", str(handle.pid)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        pass

    # Wait for process to exit
    try:
        handle.popen.wait(timeout=timeout_s)
        return
    except subprocess.TimeoutExpired:
        pass

    # Force kill
    logger.warning("Force-killing PID %d (%s)", handle.pid, handle.exe_name)
    try:
        subprocess.run(
            ["taskkill", "/PID", str(handle.pid), "/F"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        handle.popen.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.error("Failed to kill PID %d", handle.pid)
