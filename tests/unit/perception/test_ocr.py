"""Unit tests for OCREngine (mocked PaddleOCR)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autovisiontest.exceptions import OCRError
from autovisiontest.perception.ocr import OCREngine
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the OCREngine singleton between tests."""
    OCREngine.reset_instance()
    yield
    OCREngine.reset_instance()


def _make_fake_ocr_result(text: str, x: int = 50, y: int = 30, w: int = 100, h: int = 30) -> list:
    """Create a fake PaddleOCR output line: [[[box], (text, confidence)]]."""
    box = [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
    ]
    return [[box, (text, 0.95)]]


class TestOCREngine:
    def test_singleton(self) -> None:
        e1 = OCREngine.get_instance()
        e2 = OCREngine.get_instance()
        assert e1 is e2

    def test_reset_instance(self) -> None:
        e1 = OCREngine.get_instance()
        OCREngine.reset_instance()
        e2 = OCREngine.get_instance()
        assert e1 is not e2

    @patch("autovisiontest.perception.ocr.PaddleOCR", create=True)
    def test_recognize_with_ndarray(self, mock_paddle_cls: MagicMock) -> None:
        """Test recognize with a numpy ndarray input."""
        mock_ocr_instance = MagicMock()
        mock_ocr_instance.ocr.return_value = [_make_fake_ocr_result("hello world")]
        mock_paddle_cls.return_value = mock_ocr_instance

        with patch.dict("sys.modules", {"paddleocr": MagicMock(PaddleOCR=mock_paddle_cls)}):
            engine = OCREngine(lang="ch", use_gpu=False)
            # Manually set initialized to avoid actual PaddleOCR import
            engine._ocr = mock_ocr_instance
            engine._initialized = True

            img = np.zeros((100, 400, 3), dtype=np.uint8)
            result = engine.recognize(img)

        assert isinstance(result, OCRResult)
        assert len(result.items) == 1
        assert result.items[0].text == "hello world"
        assert result.items[0].confidence == 0.95
        assert result.image_size == (400, 100)

    @patch("autovisiontest.perception.ocr.PaddleOCR", create=True)
    def test_recognize_with_bytes(self, mock_paddle_cls: MagicMock) -> None:
        """Test recognize with PNG bytes input."""
        import cv2

        # Create a real PNG
        img = np.zeros((100, 400, 3), dtype=np.uint8)
        _, png_bytes = cv2.imencode(".png", img)
        image_bytes = png_bytes.tobytes()

        mock_ocr_instance = MagicMock()
        mock_ocr_instance.ocr.return_value = [_make_fake_ocr_result("test")]
        mock_paddle_cls.return_value = mock_ocr_instance

        with patch.dict("sys.modules", {"paddleocr": MagicMock(PaddleOCR=mock_paddle_cls)}):
            engine = OCREngine()
            engine._ocr = mock_ocr_instance
            engine._initialized = True

            result = engine.recognize(image_bytes)

        assert isinstance(result, OCRResult)
        assert len(result.items) == 1
        assert result.items[0].text == "test"

    def test_recognize_empty_image(self) -> None:
        """When PaddleOCR returns no results, we get an empty items list."""
        mock_ocr_instance = MagicMock()
        mock_ocr_instance.ocr.return_value = [None]

        engine = OCREngine()
        engine._ocr = mock_ocr_instance
        engine._initialized = True

        img = np.ones((100, 400, 3), dtype=np.uint8) * 255
        result = engine.recognize(img)

        assert isinstance(result, OCRResult)
        assert len(result.items) == 0

    def test_recognize_failure_raises_ocr_error(self) -> None:
        """If PaddleOCR raises, we wrap it in OCRError."""
        mock_ocr_instance = MagicMock()
        mock_ocr_instance.ocr.side_effect = RuntimeError("boom")

        engine = OCREngine()
        engine._ocr = mock_ocr_instance
        engine._initialized = True

        img = np.zeros((100, 400, 3), dtype=np.uint8)
        with pytest.raises(OCRError, match="OCR recognition failed"):
            engine.recognize(img)

    def test_ensure_initialized_failure_raises_ocr_error(self) -> None:
        """If PaddleOCR import/init fails, we raise OCRError."""
        engine = OCREngine()

        with patch.dict("sys.modules", {"paddleocr": None}):
            with pytest.raises(OCRError, match="Failed to initialize PaddleOCR"):
                engine._ensure_initialized()

    def test_recognize_multiple_items(self) -> None:
        """Test OCR with multiple detected items."""
        mock_ocr_instance = MagicMock()
        # PaddleOCR returns [[line1, line2, ...]]
        line1 = _make_fake_ocr_result("hello", x=10, y=10, w=80, h=25)[0]
        line2 = _make_fake_ocr_result("world", x=100, y=10, w=80, h=25)[0]
        mock_ocr_instance.ocr.return_value = [[line1, line2]]

        engine = OCREngine()
        engine._ocr = mock_ocr_instance
        engine._initialized = True

        img = np.zeros((100, 400, 3), dtype=np.uint8)
        result = engine.recognize(img)

        assert len(result.items) == 2
        assert result.items[0].text == "hello"
        assert result.items[1].text == "world"
        assert result.items[0].bbox.x == 10
        assert result.items[1].bbox.x == 100
