"""Screenshot capture using mss with thread-safe singleton."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import cv2
import numpy as np
from mss import mss

from autovisiontest.control.dpi import enable_dpi_awareness

if TYPE_CHECKING:
    pass

_lock = threading.Lock()
_mss_instance: mss | None = None


def _get_mss() -> mss:
    """Lazily create and reuse the mss instance (thread-safe)."""
    global _mss_instance
    if _mss_instance is None:
        with _lock:
            if _mss_instance is None:
                _mss_instance = mss()
    return _mss_instance


def capture_primary_screen() -> bytes:
    """Capture the primary screen and return PNG bytes."""
    enable_dpi_awareness()
    sct = _get_mss()
    with _lock:
        monitor = sct.monitors[0]  # All monitors combined; use [1] for primary
        # Use monitor[1] for the primary display only
        primary = sct.monitors[1] if len(sct.monitors) > 1 else monitor
        img = sct.grab(primary)
    # mss returns BGRA; convert to PNG
    return _bgra_to_png(img)


def capture_region(x: int, y: int, w: int, h: int) -> bytes:
    """Capture a screen region and return PNG bytes."""
    enable_dpi_awareness()
    sct = _get_mss()
    monitor = {"left": x, "top": y, "width": w, "height": h}
    with _lock:
        img = sct.grab(monitor)
    return _bgra_to_png(img)


def capture_to_ndarray() -> np.ndarray:
    """Capture the primary screen and return a BGR ndarray (H, W, 3)."""
    enable_dpi_awareness()
    sct = _get_mss()
    with _lock:
        primary = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        img = sct.grab(primary)
    # mss returns BGRA; convert to BGR for OpenCV
    arr = np.array(img)
    return arr[:, :, :3]  # Drop alpha channel → BGR


def _bgra_to_png(img: object) -> bytes:
    """Convert mss BGRA screengrab to PNG bytes."""
    arr = np.array(img)
    bgr = arr[:, :, :3]  # Drop alpha → BGR
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("Failed to encode screenshot as PNG")
    return buf.tobytes()
