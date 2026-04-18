"""Actor — locates UI elements via grounding + OCR fallback.

The Actor tries three strategies in order:
1. **VLM Grounding**: Call the grounding backend with the target description.
2. **OCR Fallback**: If the target_desc contains quoted text, search OCR for it.
3. **Planner Retry**: Ask the Planner to pick a different target (via callback).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

from autovisiontest.backends.protocol import GroundingBackend
from autovisiontest.perception.facade import FrameSnapshot
from autovisiontest.perception.types import find_text

logger = logging.getLogger(__name__)


@dataclass
class LocateResult:
    """Result of an Actor locate attempt."""

    success: bool
    x: int | None = None
    y: int | None = None
    source: str = ""  # "grounding" | "ocr" | "retry"
    confidence: float = 0.0


class Actor:
    """Locates UI elements using grounding + OCR fallback."""

    def __init__(
        self,
        grounding_backend: GroundingBackend,
        confidence_threshold: float = 0.6,
        max_planner_retries: int = 2,
    ) -> None:
        self._backend = grounding_backend
        self._threshold = confidence_threshold
        self._max_planner_retries = max_planner_retries

    def locate(
        self,
        snapshot: FrameSnapshot,
        target_desc: str,
        on_retry: Callable[[str], str | None] | None = None,
    ) -> LocateResult:
        """Try to locate a UI element matching *target_desc*.

        Args:
            snapshot: Current frame snapshot.
            target_desc: Natural language description of the target.
            on_retry: Optional callback invoked when grounding and OCR both fail.
                Receives the target_desc and should return a new target_desc
                or None to give up.

        Returns:
            A ``LocateResult`` indicating success/failure and coordinates.
        """
        # Strategy 1: VLM Grounding
        result = self._try_grounding(snapshot, target_desc)
        if result.success:
            return result

        # Strategy 2: OCR Fallback (only for quoted text)
        result = self._try_ocr_fallback(snapshot, target_desc)
        if result.success:
            return result

        # Strategy 3: Planner retries
        if on_retry is not None:
            for attempt in range(self._max_planner_retries):
                new_desc = on_retry(target_desc)
                if new_desc is None:
                    break

                # Try grounding with new description
                result = self._try_grounding(snapshot, new_desc)
                if result.success:
                    result.source = "retry"
                    return result

                # Try OCR with new description
                result = self._try_ocr_fallback(snapshot, new_desc)
                if result.success:
                    result.source = "retry"
                    return result

        logger.warning(
            "actor_locate_failed",
            extra={"target_desc": target_desc},
        )
        return LocateResult(success=False)

    def _try_grounding(self, snapshot: FrameSnapshot, target_desc: str) -> LocateResult:
        """Attempt VLM grounding."""
        try:
            response = self._backend.ground(snapshot.screenshot_png, target_desc)
            if response.confidence >= self._threshold:
                return LocateResult(
                    success=True,
                    x=response.x,
                    y=response.y,
                    source="grounding",
                    confidence=response.confidence,
                )
            logger.info(
                "grounding_low_confidence",
                extra={"confidence": response.confidence, "threshold": self._threshold},
            )
        except Exception:
            logger.exception("grounding_error")
        return LocateResult(success=False)

    def _try_ocr_fallback(self, snapshot: FrameSnapshot, target_desc: str) -> LocateResult:
        """Attempt to find quoted text via OCR."""
        # Extract quoted text from target_desc
        quoted = self._extract_quoted_text(target_desc)
        if not quoted:
            return LocateResult(success=False)

        matches = find_text(snapshot.ocr, quoted, fuzzy=True)
        if not matches:
            return LocateResult(success=False)

        # Use the first (best) match
        item = matches[0]
        cx = item.bbox.x + item.bbox.w // 2
        cy = item.bbox.y + item.bbox.h // 2
        return LocateResult(
            success=True,
            x=cx,
            y=cy,
            source="ocr",
            confidence=item.confidence,
        )

    @staticmethod
    def _extract_quoted_text(target_desc: str) -> str | None:
        """Extract text within single or double quotes from target_desc.

        Returns the first quoted string found, or None.
        """
        # Match single or double quoted text
        match = re.search(r'["\']([^"\']+)["\']', target_desc)
        if match:
            return match.group(1)
        return None
