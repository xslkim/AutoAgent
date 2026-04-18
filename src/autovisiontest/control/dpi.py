"""DPI awareness and screen geometry utilities for Windows."""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

_DPI_AWARENESS_ENABLED = False


def enable_dpi_awareness() -> None:
    """Enable Per-Monitor V2 DPI awareness (idempotent).

    Tries SetProcessDpiAwareness(2) first, falls back to
    SetProcessDPIAware(), then logs a warning if both fail.
    """
    global _DPI_AWARENESS_ENABLED
    if _DPI_AWARENESS_ENABLED:
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE_V2
        logger.debug("DPI awareness: Per-Monitor V2 enabled")
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            logger.debug("DPI awareness: SetProcessDPIAware fallback enabled")
        except (AttributeError, OSError):
            logger.warning("Could not enable DPI awareness; coordinates may be scaled")

    _DPI_AWARENESS_ENABLED = True


def get_primary_screen_size() -> tuple[int, int]:
    """Return the primary screen size in physical pixels as (width, height)."""
    if sys.platform != "win32":
        raise RuntimeError("get_primary_screen_size is Windows-only")

    enable_dpi_awareness()
    user32 = ctypes.windll.user32
    w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return (w, h)


def get_dpi_scale() -> float:
    """Return the DPI scale factor of the primary monitor (e.g. 1.0, 1.25, 1.5)."""
    if sys.platform != "win32":
        return 1.0

    enable_dpi_awareness()
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except (AttributeError, OSError):
        return 1.0
