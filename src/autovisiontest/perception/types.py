"""Shared data types for the perception layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box in pixel coordinates."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class OCRItem:
    """A single OCR detection result."""

    text: str
    bbox: BoundingBox
    confidence: float


@dataclass(frozen=True)
class OCRResult:
    """Full OCR result for an image."""

    items: list[OCRItem]
    image_size: tuple[int, int]


def center(bbox: BoundingBox) -> tuple[int, int]:
    """Return the center point of a bounding box."""
    return (bbox.x + bbox.w // 2, bbox.y + bbox.h // 2)


def find_text(
    result: OCRResult,
    query: str,
    fuzzy: bool = True,
    max_edit_distance: int = 1,
) -> list[OCRItem]:
    """Find OCR items matching *query*.

    Args:
        result: The OCR result to search.
        query: The text to find.
        fuzzy: If True, allow approximate matches within *max_edit_distance*.
        max_edit_distance: Maximum Levenshtein distance for fuzzy matching.

    Returns:
        List of matching OCRItem objects.
    """
    matches: list[OCRItem] = []
    for item in result.items:
        if item.text == query:
            matches.append(item)
        elif fuzzy and _levenshtein(item.text.lower(), query.lower()) <= max_edit_distance:
            matches.append(item)
    return matches


def _levenshtein(s: str, t: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s) < len(t):
        return _levenshtein(t, s)
    if len(t) == 0:
        return len(s)
    prev_row = list(range(len(t) + 1))
    for i, c1 in enumerate(s):
        curr_row = [i + 1]
        for j, c2 in enumerate(t):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]
