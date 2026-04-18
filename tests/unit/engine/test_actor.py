"""Unit tests for engine actor module (T F.4)."""

from __future__ import annotations

from autovisiontest.backends.types import GroundingResponse
from autovisiontest.engine.actor import Actor, LocateResult
from autovisiontest.perception.facade import FrameSnapshot
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult

import numpy as np


def _make_snapshot(texts: list[tuple[str, int, int]] | None = None) -> FrameSnapshot:
    """Create a minimal FrameSnapshot for testing."""
    items = []
    if texts:
        for t, x, y in texts:
            items.append(OCRItem(text=t, bbox=BoundingBox(x=x, y=y, w=50, h=20), confidence=0.9))
    ocr = OCRResult(items=items, image_size=(1920, 1080))
    return FrameSnapshot(
        screenshot=np.zeros((100, 100, 3), dtype=np.uint8),
        screenshot_png=b"\x89PNG" + b"\x00" * 10,
        ocr=ocr,
        timestamp=1.0,
    )


class _MockGroundingBackend:
    """Mock GroundingBackend with configurable response."""

    def __init__(self, x: int = 100, y: int = 200, confidence: float = 0.9) -> None:
        self._x = x
        self._y = y
        self._confidence = confidence
        self.last_query: str | None = None

    def ground(self, image: bytes, query: str) -> GroundingResponse:
        self.last_query = query
        return GroundingResponse(
            x=self._x, y=self._y, confidence=self._confidence, raw={}
        )


class _FailingGroundingBackend:
    """Mock backend that always raises."""

    def ground(self, image: bytes, query: str) -> GroundingResponse:
        raise RuntimeError("grounding failed")


class TestActor:
    def test_locate_grounding_success(self) -> None:
        backend = _MockGroundingBackend(x=150, y=250, confidence=0.85)
        actor = Actor(grounding_backend=backend, confidence_threshold=0.6)
        snapshot = _make_snapshot()

        result = actor.locate(snapshot, "the save button")

        assert result.success is True
        assert result.x == 150
        assert result.y == 250
        assert result.source == "grounding"
        assert result.confidence == 0.85

    def test_locate_grounding_low_conf_ocr_fallback_success(self) -> None:
        """When grounding confidence is below threshold, OCR fallback should kick in."""
        backend = _MockGroundingBackend(confidence=0.3)  # Below threshold
        actor = Actor(grounding_backend=backend, confidence_threshold=0.6)
        # Put "Save" in OCR at position (300, 400)
        snapshot = _make_snapshot(texts=[("Save", 300, 400)])

        result = actor.locate(snapshot, 'the "Save" button')

        assert result.success is True
        assert result.source == "ocr"
        # OCR center = (300 + 25, 400 + 10) = (325, 410)
        assert result.x == 325
        assert result.y == 410

    def test_locate_all_methods_fail(self) -> None:
        backend = _FailingGroundingBackend()
        actor = Actor(grounding_backend=backend, confidence_threshold=0.6)
        snapshot = _make_snapshot()  # No OCR text

        result = actor.locate(snapshot, "nonexistent element")

        assert result.success is False

    def test_locate_ocr_fallback_needs_quoted_text(self) -> None:
        """OCR fallback should NOT activate without quoted text in target_desc."""
        backend = _MockGroundingBackend(confidence=0.3)  # Low confidence, triggers fallback
        actor = Actor(grounding_backend=backend, confidence_threshold=0.6)
        # OCR has "Save" but target_desc doesn't quote it
        snapshot = _make_snapshot(texts=[("Save", 300, 400)])

        result = actor.locate(snapshot, "the save button")  # No quotes

        # Grounding failed (low conf), OCR fallback skipped (no quotes)
        assert result.success is False

    def test_locate_with_retry_success(self) -> None:
        """Retry callback should be called and can succeed."""
        call_count = 0
        grounding_call_count = 0

        class _SelectiveBackend:
            def ground(self, image: bytes, query: str) -> GroundingResponse:
                nonlocal grounding_call_count
                grounding_call_count += 1
                # Fail on first call (low confidence), succeed on retry
                if grounding_call_count <= 1:
                    return GroundingResponse(x=0, y=0, confidence=0.2, raw={})
                return GroundingResponse(x=150, y=250, confidence=0.8, raw={})

        def on_retry(target_desc: str) -> str | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "the OK button"
            return None

        backend = _SelectiveBackend()
        actor = Actor(grounding_backend=backend, confidence_threshold=0.6, max_planner_retries=2)
        snapshot = _make_snapshot()

        result = actor.locate(snapshot, "unknown element", on_retry=on_retry)

        assert result.success is True
        assert result.source == "retry"
        assert call_count == 1

    def test_locate_retry_gives_up(self) -> None:
        """Retry should give up after max_planner_retries."""
        call_count = 0

        def on_retry(target_desc: str) -> str | None:
            nonlocal call_count
            call_count += 1
            return f"try {call_count}"

        backend = _FailingGroundingBackend()
        actor = Actor(grounding_backend=backend, confidence_threshold=0.6, max_planner_retries=2)
        snapshot = _make_snapshot()

        result = actor.locate(snapshot, "element", on_retry=on_retry)

        assert result.success is False
        # Should be called max_planner_retries times
        assert call_count == 2

    def test_extract_quoted_text(self) -> None:
        assert Actor._extract_quoted_text('the "Save" button') == "Save"
        assert Actor._extract_quoted_text("the 'OK' button") == "OK"
        assert Actor._extract_quoted_text("no quotes here") is None
        assert Actor._extract_quoted_text('""') is None  # Empty string between quotes
