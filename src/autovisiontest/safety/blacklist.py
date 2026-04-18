"""Blacklist matcher for the safety guard.

Three independent checks:
- *click_hits_blacklist*: does the OCR text near a click target contain a
  dangerous keyword?
- *type_hits_blacklist*: does the text to be typed match a dangerous pattern?
- *key_combo_hits_blacklist*: is the key combination on the blacklist?
"""

from __future__ import annotations

import re

from .keywords import CLICK_KEYWORDS, KEY_COMBO_BLACKLIST, TYPE_CONTENT_PATTERNS


def click_hits_blacklist(ocr_texts_near_target: list[str]) -> tuple[bool, str | None]:
    """Check whether any OCR text near a click target hits the keyword blacklist.

    Args:
        ocr_texts_near_target: OCR-recognized text strings near the click point.

    Returns:
        ``(True, matched_keyword)`` if a hit is found, ``(False, None)`` otherwise.
    """
    for text in ocr_texts_near_target:
        text_lower = text.lower()
        for keyword in CLICK_KEYWORDS:
            if keyword.lower() in text_lower:
                return True, keyword
    return False, None


def type_hits_blacklist(text: str) -> tuple[bool, str | None]:
    """Check whether the text to be typed matches a dangerous pattern.

    Args:
        text: The text that will be typed into the application.

    Returns:
        ``(True, matched_pattern)`` if a hit is found, ``(False, None)`` otherwise.
    """
    for pattern in TYPE_CONTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, pattern
    return False, None


def key_combo_hits_blacklist(keys: tuple[str, ...]) -> tuple[bool, str | None]:
    """Check whether a key combination is on the blacklist.

    Matching is case-insensitive and order-insensitive: the *keys* tuple is
    normalised to a sorted lower-case frozenset before comparison.

    Args:
        keys: Tuple of key names, e.g. ``("ctrl", "s")``.

    Returns:
        ``(True, matched_combo_str)`` if a hit is found, ``(False, None)`` otherwise.
    """
    keys_normalized = frozenset(k.lower() for k in keys)
    for combo in KEY_COMBO_BLACKLIST:
        combo_normalized = frozenset(k.lower() for k in combo)
        if keys_normalized == combo_normalized:
            return True, "+".join(sorted(combo))
    return False, None
