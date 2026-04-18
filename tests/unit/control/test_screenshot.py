"""Tests for screenshot capture utilities."""

from __future__ import annotations

import struct

import numpy as np
import pytest

from autovisiontest.control.screenshot import (
    capture_primary_screen,
    capture_region,
    capture_to_ndarray,
)

PNG_MAGIC = b"\x89PNG"


class TestCapturePrimaryScreen:
    def test_capture_primary_screen_returns_png(self) -> None:
        """Returned bytes should start with PNG magic."""
        data = capture_primary_screen()
        assert isinstance(data, bytes)
        assert data[:4] == PNG_MAGIC

    def test_capture_primary_screen_non_empty(self) -> None:
        """Screenshot should be non-trivial in size."""
        data = capture_primary_screen()
        assert len(data) > 1000  # A real screen capture should be at least KBs


class TestCaptureRegion:
    def test_capture_region_size_matches(self) -> None:
        """Capture a 100x100 region; decoded image should be 100x100."""
        data = capture_region(0, 0, 100, 100)
        assert data[:4] == PNG_MAGIC
        # Decode to verify dimensions
        import cv2

        arr = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert arr.shape[:2] == (100, 100)


class TestCaptureToNdarray:
    def test_capture_to_ndarray_shape(self) -> None:
        """Returned array should have shape (H, W, 3)."""
        arr = capture_to_ndarray()
        assert isinstance(arr, np.ndarray)
        assert arr.ndim == 3
        assert arr.shape[2] == 3
        assert arr.shape[0] > 0
        assert arr.shape[1] > 0
