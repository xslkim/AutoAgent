"""Unit tests for perception types (BoundingBox, OCRItem, OCRResult, find_text)."""

from __future__ import annotations

from autovisiontest.perception.types import (
    BoundingBox,
    OCRItem,
    OCRResult,
    center,
    find_text,
)


class TestBoundingBox:
    def test_center(self) -> None:
        bbox = BoundingBox(x=10, y=20, w=100, h=60)
        assert center(bbox) == (60, 50)

    def test_center_odd_dimensions(self) -> None:
        bbox = BoundingBox(x=0, y=0, w=99, h=99)
        assert center(bbox) == (49, 49)


class TestOCRResult:
    def test_empty_result(self) -> None:
        result = OCRResult(items=[], image_size=(1920, 1080))
        assert len(result.items) == 0
        assert result.image_size == (1920, 1080)

    def test_find_text_exact(self) -> None:
        items = [
            OCRItem(text="hello", bbox=BoundingBox(0, 0, 50, 20), confidence=0.99),
            OCRItem(text="world", bbox=BoundingBox(60, 0, 50, 20), confidence=0.95),
        ]
        result = OCRResult(items=items, image_size=(400, 100))
        found = find_text(result, "hello", fuzzy=False)
        assert len(found) == 1
        assert found[0].text == "hello"

    def test_find_text_no_match(self) -> None:
        items = [
            OCRItem(text="hello", bbox=BoundingBox(0, 0, 50, 20), confidence=0.99),
        ]
        result = OCRResult(items=items, image_size=(400, 100))
        found = find_text(result, "xyz", fuzzy=False)
        assert len(found) == 0

    def test_find_text_fuzzy_match(self) -> None:
        """'helo' (typo) should match 'hello' with edit distance 1."""
        items = [
            OCRItem(text="hello", bbox=BoundingBox(0, 0, 50, 20), confidence=0.99),
        ]
        result = OCRResult(items=items, image_size=(400, 100))
        found = find_text(result, "helo", fuzzy=True, max_edit_distance=1)
        assert len(found) == 1
        assert found[0].text == "hello"

    def test_find_text_fuzzy_too_far(self) -> None:
        """'abcde' (5 edits from 'hello') should NOT match with max_edit_distance=1."""
        items = [
            OCRItem(text="hello", bbox=BoundingBox(0, 0, 50, 20), confidence=0.99),
        ]
        result = OCRResult(items=items, image_size=(400, 100))
        found = find_text(result, "abcde", fuzzy=True, max_edit_distance=1)
        assert len(found) == 0

    def test_find_text_case_insensitive_fuzzy(self) -> None:
        items = [
            OCRItem(text="Hello", bbox=BoundingBox(0, 0, 50, 20), confidence=0.99),
        ]
        result = OCRResult(items=items, image_size=(400, 100))
        found = find_text(result, "helo", fuzzy=True, max_edit_distance=1)
        assert len(found) == 1


class TestOCRItem:
    def test_fields(self) -> None:
        bbox = BoundingBox(x=10, y=20, w=30, h=40)
        item = OCRItem(text="test", bbox=bbox, confidence=0.95)
        assert item.text == "test"
        assert item.bbox == bbox
        assert item.confidence == 0.95
