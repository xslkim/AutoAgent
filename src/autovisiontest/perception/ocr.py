"""PaddleOCR engine wrapper for text recognition."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

from autovisiontest.exceptions import OCRError
from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult

logger = logging.getLogger(__name__)

_engine_lock = threading.Lock()
_instance: Optional[OCREngine] = None


class OCREngine:
    """Singleton OCR engine backed by PaddleOCR.

    The PaddleOCR model is loaded lazily on first call to :meth:`recognize`.
    """

    def __init__(self, lang: str = "ch", use_gpu: bool = False) -> None:
        self._lang = lang
        self._use_gpu = use_gpu
        self._ocr: object | None = None  # PaddleOCR instance
        self._initialized = False

    @classmethod
    def get_instance(cls, lang: str = "ch", use_gpu: bool = False) -> OCREngine:
        """Return the singleton OCREngine instance."""
        global _instance
        with _engine_lock:
            if _instance is None:
                _instance = cls(lang=lang, use_gpu=use_gpu)
            return _instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        global _instance
        with _engine_lock:
            _instance = None

    def _ensure_initialized(self) -> None:
        """Lazy-load the PaddleOCR model."""
        if self._initialized:
            return
        try:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self._lang,
                use_gpu=self._use_gpu,
                show_log=False,
            )
            self._initialized = True
            logger.info("PaddleOCR engine initialized (lang=%s, gpu=%s)", self._lang, self._use_gpu)
        except Exception as exc:
            raise OCRError(
                f"Failed to initialize PaddleOCR: {exc}",
                context={"lang": self._lang, "use_gpu": self._use_gpu},
            ) from exc

    def recognize(self, image: bytes | np.ndarray) -> OCRResult:
        """Perform OCR on the given image.

        Args:
            image: PNG/JPEG bytes or a numpy ndarray (BGR or RGB).

        Returns:
            OCRResult with detected text items.

        Raises:
            OCRError: If OCR fails.
        """
        self._ensure_initialized()
        try:
            if isinstance(image, bytes):
                # PaddleOCR can accept bytes via file path; convert to ndarray
                import cv2

                arr = np.frombuffer(image, dtype=np.uint8)
                img_array = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img_array is None:
                    raise OCRError("Failed to decode image bytes")
            else:
                img_array = image

            h, w = img_array.shape[:2]
            result = self._ocr.ocr(img_array, cls=True)

            items: list[OCRItem] = []
            if result and result[0]:
                for line in result[0]:
                    box_points = line[0]
                    text = line[1][0]
                    confidence = float(line[1][1])

                    # Convert 4-point polygon to axis-aligned bbox
                    xs = [p[0] for p in box_points]
                    ys = [p[1] for p in box_points]
                    x_min, x_max = int(min(xs)), int(max(xs))
                    y_min, y_max = int(min(ys)), int(max(ys))

                    items.append(
                        OCRItem(
                            text=text,
                            bbox=BoundingBox(
                                x=x_min,
                                y=y_min,
                                w=x_max - x_min,
                                h=y_max - y_min,
                            ),
                            confidence=confidence,
                        )
                    )

            return OCRResult(items=items, image_size=(w, h))

        except OCRError:
            raise
        except Exception as exc:
            raise OCRError(f"OCR recognition failed: {exc}") from exc
