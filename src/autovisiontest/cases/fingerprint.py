"""Fingerprint computation for test cases.

Fingerprints uniquely identify a test case based on:
- The application path
- The normalized goal text
- The application version (from PE metadata or file hash)

The fingerprint is the first 16 hex characters of:
    sha256(app_path + normalize_goal(goal) + compute_app_version(app_path))
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import string

logger = logging.getLogger(__name__)

# Common English stop words to remove during normalization
_ENGLISH_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "and", "or", "but", "not", "no", "nor", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "than", "too", "very", "just", "about",
    "above", "after", "before", "into", "through", "during", "between",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "it", "its", "he", "she", "they", "them", "his", "her", "their",
    "i", "me", "my", "we", "us", "our", "you", "your",
})

# Chinese punctuation and common particles to remove
_CN_PUNCTUATION = "，。！？、；：""''【】（）《》…—·"


def normalize_goal(goal: str) -> str:
    """Normalize a goal string for fingerprint computation.

    Steps:
    1. Lowercase
    2. Remove punctuation (Chinese and English)
    3. Split into tokens (whitespace for English, character-level for Chinese)
    4. Remove English stop words
    5. Rejoin with spaces

    Args:
        goal: The goal text to normalize.

    Returns:
        Normalized goal string.
    """
    # Lowercase
    text = goal.lower()

    # Remove punctuation
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    for ch in _CN_PUNCTUATION:
        text = text.replace(ch, " ")

    # Split into tokens
    tokens: list[str] = []
    for word in text.split():
        # For Chinese characters, split each character as a token
        if re.match(r"^[\u4e00-\u9fff]+$", word):
            tokens.extend(word)
        else:
            # English word — skip stop words
            if word not in _ENGLISH_STOP_WORDS:
                tokens.append(word)

    return " ".join(tokens)


def compute_app_version(app_path: str) -> str:
    """Compute the version string for an application.

    Tries to read PE FileVersion metadata first.
    Falls back to SHA-256 hash of the executable (first 12 hex chars).

    Args:
        app_path: Path to the application executable.

    Returns:
        Version string (PE FileVersion or file hash prefix).
    """
    # Try PE metadata via PowerShell (Windows only)
    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    f"(Get-Item '{app_path}').VersionInfo.FileVersion",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = result.stdout.strip()
            if version and version != "0.0.0.0":
                return version
        except Exception:
            logger.debug("pe_version_failed", extra={"app_path": app_path})

    # Fallback: SHA-256 of the file
    try:
        sha = hashlib.sha256()
        with open(app_path, "rb") as f:
            # Read in chunks to handle large files
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()[:12]
    except Exception:
        logger.debug("file_hash_failed", extra={"app_path": app_path})
        return "unknown"


def compute_fingerprint(app_path: str, goal: str) -> str:
    """Compute a fingerprint for a test case.

    The fingerprint is the first 16 hex characters of:
        sha256(app_path + normalize_goal(goal) + compute_app_version(app_path))

    Args:
        app_path: Path to the application executable.
        goal: The test goal text.

    Returns:
        16-character hex fingerprint string.
    """
    normalized = normalize_goal(goal)
    version = compute_app_version(app_path)
    combined = f"{app_path}|{normalized}|{version}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
