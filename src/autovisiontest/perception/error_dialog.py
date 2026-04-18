"""Error dialog detection via OCR keyword matching."""

from __future__ import annotations

from autovisiontest.perception.types import OCRResult

# Error keywords in Chinese and English
ERROR_KEYWORDS: list[str] = [
    "错误",
    "异常",
    "失败",
    "Error",
    "Exception",
    "Failed",
    "Warning",
    "警告",
]

# Button-like text that should appear near the error keyword
BUTTON_KEYWORDS: list[str] = [
    "确定",
    "OK",
    "关闭",
    "取消",
    "Cancel",
    "Close",
    "是",
    "否",
    "Yes",
    "No",
    "重试",
    "Retry",
    "忽略",
    "Ignore",
    "Abort",
    "中止",
]

# Maximum pixel distance between error keyword and button text
_DEFAULT_PROXIMITY_PX = 150


def detect_error_dialog(
    ocr: OCRResult,
    proximity_px: int = _DEFAULT_PROXIMITY_PX,
) -> tuple[bool, str | None]:
    """Detect whether an error dialog is visible in the OCR result.

    Detection rules:
    1. An OCR item matches one of ERROR_KEYWORDS (case-insensitive).
    2. The matched item is in the upper half of the screen (y < screen_h / 2).
    3. A BUTTON_KEYWORDS item exists within *proximity_px* pixels of the error keyword.

    Args:
        ocr: The OCR result for the current screen.
        proximity_px: Maximum pixel distance between error keyword and button.

    Returns:
        (hit, matched_keyword) — hit is True if an error dialog is detected,
        matched_keyword is the error keyword that was found (or None).
    """
    screen_h = ocr.image_size[1]

    # Collect all error keyword matches in the upper half
    error_hits: list[tuple[str, int, int]] = []  # (keyword, center_x, center_y)
    for item in ocr.items:
        text_lower = item.text.lower()
        for kw in ERROR_KEYWORDS:
            if kw.lower() in text_lower:
                cx = item.bbox.x + item.bbox.w // 2
                cy = item.bbox.y + item.bbox.h // 2
                # Must be in upper half of screen
                if cy < screen_h / 2:
                    error_hits.append((kw, cx, cy))
                break  # One keyword match per item is enough

    if not error_hits:
        return (False, None)

    # Check if any button keyword exists near an error hit
    button_items: list[tuple[int, int]] = []  # (center_x, center_y)
    for item in ocr.items:
        text_lower = item.text.strip().lower()
        for bk in BUTTON_KEYWORDS:
            if text_lower == bk.lower():
                cx = item.bbox.x + item.bbox.w // 2
                cy = item.bbox.y + item.bbox.h // 2
                button_items.append((cx, cy))
                break

    if not button_items:
        return (False, None)

    # Check proximity
    for kw, ex, ey in error_hits:
        for bx, by in button_items:
            dist = ((ex - bx) ** 2 + (ey - by) ** 2) ** 0.5
            if dist <= proximity_px:
                return (True, kw)

    return (False, None)
