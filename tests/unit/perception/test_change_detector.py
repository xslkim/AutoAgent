"""Unit tests for ChangeDetector (visual stuck detection)."""

from __future__ import annotations

import numpy as np
import pytest

from autovisiontest.perception.change_detector import ChangeDetector


class TestChangeDetector:
    def test_single_frame_not_static(self) -> None:
        """With only one frame, is_static returns False."""
        det = ChangeDetector(window_seconds=10.0, static_threshold=0.99)
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        det.push(img, t=0.0)
        assert det.is_static(now_t=0.0) is False

    def test_identical_frames_over_window_is_static(self) -> None:
        """Multiple identical frames within the window → static."""
        det = ChangeDetector(window_seconds=10.0, static_threshold=0.99)
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        for t in [0.0, 1.0, 2.0, 3.0]:
            det.push(img.copy(), t=t)
        assert det.is_static(now_t=3.0) is True

    def test_change_breaks_static(self) -> None:
        """A visual change between frames breaks the static condition."""
        det = ChangeDetector(window_seconds=10.0, static_threshold=0.99)
        img_a = np.zeros((100, 100, 3), dtype=np.uint8)
        img_b = np.full((100, 100, 3), 255, dtype=np.uint8)
        det.push(img_a, t=0.0)
        det.push(img_b, t=1.0)
        assert det.is_static(now_t=1.0) is False

    def test_reset_clears_buffer(self) -> None:
        """After reset, is_static returns False even with prior frames."""
        det = ChangeDetector(window_seconds=10.0, static_threshold=0.99)
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        det.push(img, t=0.0)
        det.push(img.copy(), t=1.0)
        assert det.is_static(now_t=1.0) is True
        det.reset()
        assert det.is_static(now_t=1.0) is False

    def test_old_frames_pruned(self) -> None:
        """Frames outside the time window are pruned."""
        det = ChangeDetector(window_seconds=5.0, static_threshold=0.99)
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        det.push(img, t=0.0)
        det.push(img.copy(), t=1.0)
        # At t=7.0, only frames from t >= 2.0 remain
        det.push(img.copy(), t=7.0)
        # Only one frame left in buffer (t=7.0)
        assert det.is_static(now_t=7.0) is False

    def test_slightly_different_frames_below_threshold(self) -> None:
        """Small visual differences may still be detected as non-static."""
        det = ChangeDetector(window_seconds=10.0, static_threshold=0.999)
        img_a = np.full((100, 100, 3), 128, dtype=np.uint8)
        img_b = img_a.copy()
        img_b[50, 50] = [200, 200, 200]  # tiny change
        det.push(img_a, t=0.0)
        det.push(img_b, t=1.0)
        # With a very high threshold, even tiny changes break static
        result = det.is_static(now_t=1.0)
        # Result depends on whether the tiny change is below 0.999 SSIM
        # It should be non-static with such a high threshold
        assert result is False

    def test_low_threshold_tolerates_small_changes(self) -> None:
        """With a lower threshold, small changes are still considered static."""
        det = ChangeDetector(window_seconds=10.0, static_threshold=0.90)
        img_a = np.full((100, 100, 3), 128, dtype=np.uint8)
        img_b = img_a.copy()
        img_b[50, 50] = [200, 200, 200]
        det.push(img_a, t=0.0)
        det.push(img_b, t=1.0)
        assert det.is_static(now_t=1.0) is True
