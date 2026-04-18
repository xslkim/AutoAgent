"""Unit tests for safety nearby_text module (T E.2)."""

from __future__ import annotations

from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult
from autovisiontest.safety.nearby_text import find_nearby_texts


def _make_ocr_item(text: str, x: int, y: int, w: int = 50, h: int = 20) -> OCRItem:
    """Helper to create an OCRItem at a given position."""
    return OCRItem(text=text, bbox=BoundingBox(x=x, y=y, w=w, h=h), confidence=0.95)


class TestFindNearbyTexts:
    def test_nearby_within_radius_returned(self) -> None:
        """Items whose center is within radius should be returned."""
        ocr = OCRResult(
            items=[
                _make_ocr_item("删除", x=90, y=90),   # center = (115, 100), dist ~18
                _make_ocr_item("保存", x=200, y=90),   # center = (225, 100), dist ~130
            ],
            image_size=(1920, 1080),
        )
        result = find_nearby_texts(ocr, x=100, y=100, radius_px=30)
        assert "删除" in result
        assert "保存" not in result

    def test_nearby_outside_not_returned(self) -> None:
        """Items outside radius should not be returned."""
        ocr = OCRResult(
            items=[
                _make_ocr_item("远离目标", x=500, y=500),
            ],
            image_size=(1920, 1080),
        )
        result = find_nearby_texts(ocr, x=100, y=100, radius_px=30)
        assert result == []

    def test_empty_ocr_returns_empty_list(self) -> None:
        """Empty OCR result should return empty list."""
        ocr = OCRResult(items=[], image_size=(1920, 1080))
        result = find_nearby_texts(ocr, x=100, y=100, radius_px=30)
        assert result == []

    def test_exactly_on_boundary(self) -> None:
        """Item exactly at radius boundary should be included."""
        # center at (100, 100) — target at (70, 100), radius=30, dist=30
        ocr = OCRResult(
            items=[_make_ocr_item("边界", x=75, y=90, w=50, h=20)],
            image_size=(1920, 1080),
        )
        result = find_nearby_texts(ocr, x=70, y=100, radius_px=30)
        assert "边界" in result

    def test_multiple_nearby(self) -> None:
        """All nearby items should be returned."""
        ocr = OCRResult(
            items=[
                # center of "删除" = (105, 90), dist from (100,90) = 5
                _make_ocr_item("删除", x=80, y=80),
                # center of "确定" = (115, 90), dist from (100,90) = 15
                _make_ocr_item("确定", x=90, y=80),
                # center of "保存" = (525, 510), far away
                _make_ocr_item("保存", x=500, y=500),
            ],
            image_size=(1920, 1080),
        )
        result = find_nearby_texts(ocr, x=100, y=90, radius_px=30)
        assert "删除" in result
        assert "确定" in result
        assert "保存" not in result

    def test_custom_radius(self) -> None:
        """Custom radius should be respected."""
        ocr = OCRResult(
            items=[_make_ocr_item("远处文字", x=300, y=100)],
            image_size=(1920, 1080),
        )
        # With default radius=30, should not be found
        assert find_nearby_texts(ocr, x=100, y=100, radius_px=30) == []
        # With large radius, should be found
        assert "远处文字" in find_nearby_texts(ocr, x=100, y=100, radius_px=300)
