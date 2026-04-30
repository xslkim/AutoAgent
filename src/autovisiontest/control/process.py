"""Process management — launch, kill, and monitor application processes."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from autovisiontest.control.dpi import enable_dpi_awareness
from autovisiontest.exceptions import AppCrashedError, AppLaunchError

logger = logging.getLogger(__name__)

# ``tasklist`` IMAGENAME values when the launcher stub exits before the real
# binary name is obvious.  Do **not** add generic hosts like
# ``ApplicationFrameHost.exe`` — use ``AppHandle.monitor_pid`` instead.
_MONITOR_IMAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "calc.exe": ("Calculator.exe",),
}


@dataclass
class AppHandle:
    """Handle to a launched application process."""

    pid: int
    popen: subprocess.Popen
    exe_name: str
    #: Real UI process PID when the launcher stub exits (e.g. Windows Calculator).
    monitor_pid: int | None = None


def kill_related_processes(handle: AppHandle) -> None:
    """``taskkill`` every monitored image name for this launch (best-effort)."""
    if handle.monitor_pid is not None:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(handle.monitor_pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    for imagename in _monitor_imagenames(handle):
        kill_processes_by_exe(imagename)


def kill_stale_instances_for_app(app_path: str) -> None:
    """Kill stray processes from a previous run before launching *app_path*."""
    exe_name = app_path.rsplit("\\", 1)[-1] if "\\" in app_path else app_path.rsplit("/", 1)[-1]
    kill_processes_by_exe(exe_name)
    for imagename in _MONITOR_IMAGE_ALIASES.get(exe_name.lower(), ()):
        kill_processes_by_exe(imagename)


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


def _tasklist_pid_running(pid: int) -> bool:
    """Return True if *tasklist* still lists this PID."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return str(pid) in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _tasklist_image_running(imagename: str) -> bool:
    """Return True if *any* process with this image name is listed."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {imagename}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = result.stdout.lower()
        return imagename.lower() in out
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _monitor_imagenames(handle: AppHandle) -> list[str]:
    """Executable image names that count as *this* app still running."""
    key = handle.exe_name.lower()
    extra = _MONITOR_IMAGE_ALIASES.get(key, ())
    return [handle.exe_name, *extra]


def _powershell_calc_main_window_present() -> bool:
    """Whether any process exposes a calculator-like *MainWindowTitle*."""
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$p = Get-Process | Where-Object { $_.MainWindowTitle -match '计算器|Calculator' } | Select-Object -First 1; "
                "if ($null -ne $p) { exit 0 } else { exit 1 }",
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _powershell_calc_main_pid() -> int | None:
    """Best PID for the calculator main window (works better than pygetwindow on UWP)."""
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$p = Get-Process | Where-Object { $_.MainWindowTitle -match '计算器|Calculator' } | Select-Object -First 1; "
                "if ($null -ne $p) { Write-Output $p.Id }",
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        line = (r.stdout or "").strip().splitlines()
        if not line:
            return None
        return int(line[-1].strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _calc_application_alive() -> bool:
    """Detect modern Windows Calculator after ``calc.exe`` stub has exited."""
    try:
        from autovisiontest.control.window import find_calculator_window

        win = find_calculator_window()
        if win is not None:
            if win.pid > 0 and _tasklist_pid_running(win.pid):
                return True
            # UWP: pygetwindow often reports 0 or a non-tasklist PID — trust title match.
            if find_calculator_window() is not None:
                return True
    except Exception:
        logger.debug("calc_window_alive_failed", exc_info=True)
    return _powershell_calc_main_window_present()


def pick_calculator_monitor_pid() -> int | None:
    """PID suitable for ``taskkill`` after launching ``calc.exe`` (pygetwindow + PowerShell)."""
    try:
        from autovisiontest.control.window import find_calculator_window

        cw = find_calculator_window()
        if cw is not None and cw.pid > 0:
            return cw.pid
    except Exception:
        pass
    pid = _powershell_calc_main_pid()
    return pid if pid and pid > 0 else None


def is_alive(handle: AppHandle) -> bool:
    """Check if the application process is still running.

    Handles stub-launcher apps (e.g. modern Windows notepad.exe): the
    original subprocess may exit quickly while spawning the real process
    with a different PID.  When the direct PID is gone, we fall back to
    checking whether *any* process with the same executable name is still
    running.
    """
    # Fast path: direct subprocess still alive
    if handle.popen.poll() is None:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {handle.pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if str(handle.pid) in result.stdout:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True  # Assume alive when check fails

    # Modern Microsoft Calculator: stub exits; UWP / pygetwindow PIDs are unreliable.
    if handle.exe_name.lower() == "calc.exe" and _calc_application_alive():
        return True

    # Resolved window PID (set after launch for calc.exe / similar).
    if handle.monitor_pid is not None and _tasklist_pid_running(handle.monitor_pid):
        return True

    # Direct PID gone (stub exited or process truly died).
    # Check by exe name (+ known aliases like calc.exe → Calculator.exe).
    for imagename in _monitor_imagenames(handle):
        if _tasklist_image_running(imagename):
            return True

    return False


def close_app(handle: AppHandle, timeout_s: float = 5.0) -> None:
    """Gracefully close the application.

    First sends WM_CLOSE via taskkill (no /F), then force-kills after timeout.
    """
    # Stub apps: tear down the real UI process if we tracked it.
    if handle.monitor_pid is not None:
        subprocess.run(
            ["taskkill", "/PID", str(handle.monitor_pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    if handle.exe_name.lower() == "calc.exe":
        subprocess.run(
            ["taskkill", "/IM", "Calculator.exe", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )

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
