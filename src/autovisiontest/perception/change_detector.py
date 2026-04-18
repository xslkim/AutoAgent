"""Visual change/stuck detection using SSIM and a ring buffer."""

from __future__ import annotations

import time
from collections import deque

import numpy as np

from autovisiontest.perception.similarity import ssim


class ChangeDetector:
    """Detect whether the screen has been static (stuck) over a time window.

    Uses a ring buffer of screenshots and computes pairwise SSIM to
    determine if the application is visually stuck.

    Args:
        window_seconds: Time window to look back for stuck detection.
        static_threshold: SSIM threshold above which frames are considered
            identical.  A value of 0.99 means frames must be nearly pixel-
            perfect duplicates.
    """

    def __init__(
        self,
        window_seconds: float = 10.0,
        static_threshold: float = 0.99,
    ) -> None:
        self._window_seconds = window_seconds
        self._static_threshold = static_threshold
        self._buffer: deque[tuple[float, np.ndarray]] = deque()

    def push(self, screenshot: np.ndarray, t: float | None = None) -> None:
        """Add a screenshot to the ring buffer.

        Args:
            screenshot: BGR numpy array of the screen.
            t: Timestamp (defaults to time.time()).
        """
        if t is None:
            t = time.time()
        self._buffer.append((t, screenshot))
        self._prune(t)

    def is_static(self, now_t: float | None = None) -> bool:
        """Check if the screen has been static over the time window.

        Returns True if all adjacent pairs within the window have
        SSIM >= static_threshold.  Returns False if there is only
        one frame in the buffer.
        """
        if now_t is None:
            now_t = time.time()
        self._prune(now_t)

        if len(self._buffer) < 2:
            return False

        # Compare all adjacent pairs
        items = list(self._buffer)
        for i in range(len(items) - 1):
            _, img_a = items[i]
            _, img_b = items[i + 1]
            score = ssim(img_a, img_b)
            if score < self._static_threshold:
                return False

        return True

    def reset(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()

    def _prune(self, now_t: float) -> None:
        """Remove entries older than window_seconds from now_t."""
        cutoff = now_t - self._window_seconds
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()
