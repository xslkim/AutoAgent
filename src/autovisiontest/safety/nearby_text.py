"""Find OCR texts near a target coordinate.

Used by the safety guard to gather contextual text around a click target,
so that blacklist keyword matching can consider what the user is about
to click on.
"""

from __future__ import annotations

from autovisiontest.perception.types import BoundingBox, OCRItem, OCRResult, center


def find_nearby_texts(
    ocr: OCRResult,
    x: int,
    y: int,
    radius_px: int = 30,
) -> list[str]:
    """Return OCR texts whose bounding-box center is within *radius_px* of (x, y).

    Args:
        ocr: The OCR result for the current screenshot.
        x: Target x-coordinate in pixels.
        y: Target y-coordinate in pixels.
        radius_px: Maximum distance (in pixels) from the target to consider
            an OCR item "nearby".  Defaults to 30.

    Returns:
        List of OCR text strings near the target point.
    """
    nearby: list[str] = []
    for item in ocr.items:
        cx, cy = center(item.bbox)
        distance = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
        if distance <= radius_px:
            nearby.append(item.text)
    return nearby
