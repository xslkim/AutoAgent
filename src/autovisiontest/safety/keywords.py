"""Safety blacklist keyword constants.

These lists define the dangerous actions that the safety guard will intercept
before they are executed on the desktop.  The constants are kept in a separate
module so that they can be reviewed and extended without touching matcher logic.
"""

from __future__ import annotations

# ── Click-target keywords ───────────────────────────────────────────────
# If OCR text near a click target matches any of these, the click is flagged.

CLICK_KEYWORDS: list[str] = [
    # Chinese
    "删除",
    "永久删除",
    "清空",
    "清除",
    "重置",
    "格式化",
    "卸载",
    "抹掉",
    "擦除",
    "恢复出厂",
    # English
    "Delete",
    "Remove",
    "Erase",
    "Format",
    "Uninstall",
    "Reset",
    "Wipe",
    "Factory",
]

# ── Key-combo blacklist ─────────────────────────────────────────────────
# Each entry is a tuple of normalized key names (lowercase).
# Matching is case-insensitive and order-insensitive.

KEY_COMBO_BLACKLIST: list[tuple[str, ...]] = [
    ("alt", "f4"),
    ("ctrl", "shift", "del"),
    ("win", "l"),
    ("win", "r"),
    ("win", "e"),
]

# ── Type-content regex patterns ─────────────────────────────────────────
# If the text to be typed matches any of these patterns, it is flagged.

TYPE_CONTENT_PATTERNS: list[str] = [
    r"\bdel\s+/[sq]",
    r"\bformat\s+[a-z]:",
    r"\brm\s+-rf",
    r"\brmdir\s+/s",
]
