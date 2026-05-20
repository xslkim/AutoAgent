"""Claude Vision second-opinion judge for visual diffs.

:func:`judge_diff` sends the baseline and current screenshots (and optionally
the SSIM diff image) to the Claude Vision API and returns a structured
assessment of what changed.

This is a "second opinion" layer on top of SSIM: SSIM tells you *where* pixels
changed and by how much; Claude Vision tells you *what* the change means in
human terms (e.g. "the Submit button label changed from 'OK' to 'Confirm'").

The Anthropic client is injectable via the ``_client`` parameter so tests can
substitute a mock without a real API key.

Usage::

    from autoagent_mcp.vision.claude_judge import judge_diff

    result = judge_diff("baseline.png", "current.png", diff_path="diff.png")
    print(result.description)
    print(result.severity)     # "none" | "minor" | "moderate" | "major"
    print(result.changed)      # bool — Claude's own assessment
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

VALID_SEVERITIES = frozenset({"none", "minor", "moderate", "major"})

DEFAULT_MODEL = "claude-opus-4-5"


@dataclass
class JudgeResult:
    """Structured result from the Claude Vision judge.

    Attributes:
        changed:     Claude's own assessment of whether the UI changed
                     meaningfully (may differ from the SSIM threshold).
        description: Human-readable summary of the observed differences.
        severity:    Qualitative severity — ``"none"``, ``"minor"``,
                     ``"moderate"``, or ``"major"``.
        details:     Bullet-point list of specific changes observed.
        model:       The model used for the assessment.
        raw_response: The raw text Claude returned (for debugging).
    """

    changed: bool
    description: str
    severity: str
    details: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    raw_response: str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a UI visual regression testing assistant.
You will be shown two screenshots — a baseline (reference) and a current screenshot.
Your task is to identify and describe any visual differences between them.

Respond with a JSON object (no markdown fences) with these fields:
{
  "changed": true or false,
  "severity": "none" | "minor" | "moderate" | "major",
  "description": "<one-sentence summary of the overall change>",
  "details": ["<specific change 1>", "<specific change 2>", ...]
}

Severity guide:
- none:     No perceptible difference.
- minor:    Cosmetic change (colour tweak, pixel-level shift, anti-aliasing).
- moderate: Visible layout or text change that does not break user flow.
- major:    Missing element, broken layout, wrong screen, or functional regression.
"""

_USER_PROMPT = "Compare the baseline screenshot (first image) with the current screenshot (second image) and return your assessment."
_USER_PROMPT_WITH_DIFF = "Compare the baseline screenshot (first image) with the current screenshot (second image). The third image is an SSIM diff heat-map (brighter = more change). Return your assessment."


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def judge_diff(
    baseline_path: str | os.PathLike,
    current_path: str | os.PathLike,
    *,
    diff_path: str | os.PathLike | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 512,
    _client: Any = None,
) -> JudgeResult:
    """Call Claude Vision to assess what changed between two screenshots.

    Args:
        baseline_path: Reference (before) screenshot.
        current_path:  Candidate (after) screenshot.
        diff_path:     Optional SSIM diff image to include as a third image.
        model:         Anthropic model identifier (default ``claude-opus-4-5``).
        max_tokens:    Maximum response tokens (default 512).
        _client:       Injectable ``anthropic.Anthropic`` instance for testing.

    Returns:
        :class:`JudgeResult`.

    Raises:
        FileNotFoundError: An image path does not exist.
        anthropic.APIError: The API call failed.
    """
    # Lazy import so the package loads even without ANTHROPIC_API_KEY set
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()

    images = [
        _image_block(baseline_path, "baseline screenshot"),
        _image_block(current_path, "current screenshot"),
    ]
    if diff_path is not None:
        images.append(_image_block(diff_path, "SSIM diff heat-map"))

    user_text = _USER_PROMPT_WITH_DIFF if diff_path else _USER_PROMPT

    content: list[dict] = [*images, {"type": "text", "text": user_text}]

    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text if response.content else ""
    return _parse_response(raw, model=model)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _image_block(path: str | os.PathLike, label: str) -> dict:
    """Build an Anthropic image content block from a local PNG file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p} ({label})")
    data = base64.standard_b64encode(p.read_bytes()).decode()
    # Infer media type from extension
    ext = p.suffix.lower()
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/png")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def _parse_response(raw: str, model: str) -> JudgeResult:
    """Parse Claude's JSON response, with graceful fallback on malformed output."""
    # Strip optional markdown fences
    text = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        doc: dict = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Fallback: treat the whole response as a description
        return JudgeResult(
            changed=True,
            description=raw.strip() or "Claude returned an unstructured response.",
            severity="moderate",
            details=[],
            model=model,
            raw_response=raw,
        )

    severity = str(doc.get("severity", "moderate")).lower()
    if severity not in VALID_SEVERITIES:
        severity = "moderate"

    changed = bool(doc.get("changed", severity != "none"))

    return JudgeResult(
        changed=changed,
        description=str(doc.get("description", "")),
        severity=severity,
        details=[str(d) for d in doc.get("details", [])],
        model=model,
        raw_response=raw,
    )
