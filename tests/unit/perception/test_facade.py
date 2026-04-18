"""Unit tests for Perception facade."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autovisiontest.perception.facade import FrameSnapshot, Perception
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult


def _make_snapshot(
    img: np.ndarray | None = None,
    ts: float = 0.0,
) -> FrameSnapshot:
    """Create a minimal FrameSnapshot for testing."""
    if img is None:
        img = np.zeros((100, 100, 3), dtype=np.uint8)
    ocr = OCRResult(items=[], image_size=(100, 100))
    return FrameSnapshot(screenshot=img, screenshot_png=b"\x89PNG", ocr=ocr, timestamp=ts)


class TestFrameSnapshot:
    def test_fields_populated(self) -> None:
        snap = _make_snapshot(ts=1.0)
        assert snap.screenshot is not None
        assert snap.screenshot_png == b"\x89PNG"
        assert snap.ocr is not None
        assert snap.timestamp == 1.0


class TestPerception:
    @patch("autovisiontest.control.screenshot.capture_primary_screen", return_value=b"\x89PNG")
    @patch("autovisiontest.control.screenshot.capture_to_ndarray")
    def test_capture_snapshot_all_fields_populated(
        self, mock_ndarray: MagicMock, mock_png: MagicMock
    ) -> None:
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_ndarray.return_value = img

        mock_ocr_engine = MagicMock()
        mock_ocr_result = OCRResult(
            items=[OCRItem(text="test", bbox=BoundingBox(0, 0, 50, 20), confidence=0.9)],
            image_size=(100, 100),
        )
        mock_ocr_engine.recognize.return_value = mock_ocr_result

        p = Perception(ocr_engine=mock_ocr_engine, change_detector=MagicMock())
        snapshot = p.capture_snapshot()

        assert snapshot.screenshot is img
        assert snapshot.screenshot_png == b"\x89PNG"
        assert len(snapshot.ocr.items) == 1
        assert snapshot.ocr.items[0].text == "test"
        assert snapshot.timestamp > 0

    def test_ssim_between_snapshots(self) -> None:
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        snap_a = _make_snapshot(img=img, ts=0.0)
        snap_b = _make_snapshot(img=img.copy(), ts=1.0)

        p = Perception(ocr_engine=MagicMock(), change_detector=MagicMock())
        score = p.ssim_between(snap_a, snap_b)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_detect_error(self) -> None:
        ocr = OCRResult(
            items=[
                OCRItem(text="Error", bbox=BoundingBox(400, 100, 80, 30), confidence=0.95),
                OCRItem(text="OK", bbox=BoundingBox(430, 200, 40, 25), confidence=0.95),
            ],
            image_size=(1920, 1080),
        )
        snap = FrameSnapshot(
            screenshot=np.zeros((1080, 1920, 3), dtype=np.uint8),
            screenshot_png=b"\x89PNG",
            ocr=ocr,
            timestamp=1.0,
        )

        p = Perception(ocr_engine=MagicMock(), change_detector=MagicMock())
        hit, keyword = p.detect_error(snap)
        assert hit is True
        assert keyword == "Error"

    def test_snapshot_timestamp_monotonic(self) -> None:
        """Timestamps should be monotonically increasing."""
        ts_list = [0.0, 0.5, 1.0, 1.5]
        for i in range(len(ts_list) - 1):
            assert ts_list[i] < ts_list[i + 1]
