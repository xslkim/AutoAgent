"""Unit tests for error dialog detection."""

from __future__ import annotations

import pytest

from autovisiontest.perception.error_dialog import detect_error_dialog
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult


def _make_ocr_result(
    items: list[tuple[str, int, int, int, int]],
    screen_size: tuple[int, int] = (1920, 1080),
) -> OCRResult:
    """Helper to build OCRResult from (text, x, y, w, h) tuples."""
    return OCRResult(
        items=[
            OCRItem(text=t, bbox=BoundingBox(x=x, y=y, w=w, h=h), confidence=0.95)
            for t, x, y, w, h in items
        ],
        image_size=screen_size,
    )


class TestDetectErrorDialog:
    def test_no_dialog_returns_false(self) -> None:
        ocr = _make_ocr_result([
            ("File", 10, 10, 50, 20),
            ("Edit", 70, 10, 50, 20),
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is False
        assert keyword is None

    def test_obvious_error_dialog_detected(self) -> None:
        """Error keyword in upper half + OK button nearby → detected."""
        ocr = _make_ocr_result([
            ("Error", 400, 100, 80, 30),   # error keyword in upper half
            ("OK", 450, 200, 40, 25),       # button near the error
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is True
        assert keyword == "Error"

    def test_chinese_error_dialog(self) -> None:
        """Chinese error keyword + 确定 button."""
        ocr = _make_ocr_result([
            ("错误", 400, 100, 80, 30),
            ("确定", 430, 200, 40, 25),
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is True
        assert keyword == "错误"

    def test_keyword_without_button_not_dialog(self) -> None:
        """Error keyword exists but no button text → not detected."""
        ocr = _make_ocr_result([
            ("Error occurred while processing", 100, 200, 300, 30),
            ("Next", 500, 200, 50, 20),
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is False

    def test_keyword_in_lower_half_not_dialog(self) -> None:
        """Error keyword in lower half of screen → not detected."""
        ocr = _make_ocr_result([
            ("Error", 400, 700, 80, 30),    # y=700 > screen_h/2=540
            ("OK", 430, 800, 40, 25),
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is False

    def test_button_too_far_away_not_dialog(self) -> None:
        """Button exists but is too far from error keyword."""
        ocr = _make_ocr_result([
            ("Error", 100, 100, 80, 30),
            ("OK", 1500, 100, 40, 25),      # very far away
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is False

    def test_warning_keyword_detected(self) -> None:
        """Warning keyword should also be detected."""
        ocr = _make_ocr_result([
            ("Warning", 400, 100, 80, 30),
            ("Close", 430, 200, 50, 25),
        ])
        hit, keyword = detect_error_dialog(ocr)
        assert hit is True
        assert keyword == "Warning"

    def test_empty_ocr_returns_false(self) -> None:
        ocr = OCRResult(items=[], image_size=(1920, 1080))
        hit, keyword = detect_error_dialog(ocr)
        assert hit is False
        assert keyword is None

    def test_custom_proximity(self) -> None:
        """Button within default proximity but outside custom proximity."""
        ocr = _make_ocr_result([
            ("Error", 100, 100, 80, 30),
            ("OK", 200, 100, 40, 25),       # ~100px away
        ])
        # Default proximity (150) should detect
        hit1, _ = detect_error_dialog(ocr, proximity_px=150)
        assert hit1 is True

        # Tighter proximity (50) should not
        hit2, _ = detect_error_dialog(ocr, proximity_px=50)
        assert hit2 is False
