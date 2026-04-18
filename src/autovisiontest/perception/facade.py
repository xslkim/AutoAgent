"""Perception layer facade — unified interface for the execution engine."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from autovisiontest.perception.change_detector import ChangeDetector
from autovisiontest.perception.error_dialog import detect_error_dialog
from autovisiontest.perception.ocr import OCREngine
from autovisiontest.perception.similarity import ssim
from autovisiontest.perception.types import OCRResult


@dataclass(frozen=True)
class FrameSnapshot:
    """A snapshot of the current screen state with OCR results."""

    screenshot: np.ndarray
    screenshot_png: bytes
    ocr: OCRResult
    timestamp: float


class Perception:
    """High-level perception interface for the test execution engine.

    This is the single entry point for the engine to interact with the
    perception layer.  It combines screenshot capture, OCR, error dialog
    detection, SSIM comparison, and stuck detection.
    """

    def __init__(
        self,
        ocr_engine: OCREngine | None = None,
        change_detector: ChangeDetector | None = None,
    ) -> None:
        self._ocr = ocr_engine or OCREngine.get_instance()
        self._change_detector = change_detector or ChangeDetector()

    def capture_snapshot(self) -> FrameSnapshot:
        """Capture a screenshot + OCR in one call.

        Returns:
            FrameSnapshot with screenshot, PNG bytes, OCR results, and timestamp.
        """
        from autovisiontest.control.screenshot import capture_primary_screen, capture_to_ndarray

        screenshot_png = capture_primary_screen()
        screenshot = capture_to_ndarray()
        ocr = self._ocr.recognize(screenshot)
        timestamp = time.time()

        # Push to change detector
        self._change_detector.push(screenshot, t=timestamp)

        return FrameSnapshot(
            screenshot=screenshot,
            screenshot_png=screenshot_png,
            ocr=ocr,
            timestamp=timestamp,
        )

    def detect_error(self, snapshot: FrameSnapshot) -> tuple[bool, str | None]:
        """Check if an error dialog is visible in the snapshot.

        Args:
            snapshot: The frame snapshot to check.

        Returns:
            (hit, matched_keyword) tuple.
        """
        return detect_error_dialog(snapshot.ocr)

    def ssim_between(self, a: FrameSnapshot, b: FrameSnapshot) -> float:
        """Compute SSIM between two frame snapshots.

        Args:
            a: First snapshot.
            b: Second snapshot.

        Returns:
            SSIM score in [0, 1].
        """
        return ssim(a.screenshot, b.screenshot)

    def is_static(self) -> bool:
        """Check if the screen has been static recently.

        Returns:
            True if no visual changes have been detected in the time window.
        """
        return self._change_detector.is_static()
