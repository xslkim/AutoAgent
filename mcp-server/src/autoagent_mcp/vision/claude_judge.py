"""Claude Vision second-opinion judge for visual diffs.

:func:`judge_diff` sends the baseline and current screenshots (and optionally
the SSIM diff image) to the Claude Vision API and returns a structured
assessment of what changed.

Stabilisation features (TASK-0404)
------------------------------------
Retry with exponential backoff
    Transient API errors (network failures, rate limits, server 5xx) are
    retried up to *max_retries* times (default 2) with ``1 s, 2 s, …`` delays.
    ``FileNotFoundError`` and ``ValueError`` propagate immediately — they
    indicate caller errors that won't resolve by retrying.

Per-session call limit  (``max_per_session``)
    Pass an integer to cap how many API calls this process makes.  When the
    limit is reached :func:`judge_diff` returns a :class:`JudgeResult` with
    ``skipped=True`` immediately, without touching the API.  The counter is
    shared across all callers; use :func:`reset_session` to reset it (e.g. at
    the start of a new conversation).

Result cache
    Within a session, identical comparisons (same file paths, sizes, and
    modification times, same model) are answered from an in-memory cache
    without a second API call.  The cache is cleared by :func:`reset_session`.

Usage::

    from autoagent_mcp.vision.claude_judge import judge_diff, reset_session

    reset_session()
    result = judge_diff("baseline.png", "current.png", max_per_session=10)
    print(result.description)
    print(result.severity)     # "none" | "minor" | "moderate" | "major"
    print(result.changed)      # bool — Claude's own assessment
    print(result.skipped)      # True if session limit was reached
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
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
        changed:      Claude's own assessment of whether the UI changed
                      meaningfully (may differ from the SSIM threshold).
        description:  Human-readable summary of the observed differences.
        severity:     Qualitative severity — ``"none"``, ``"minor"``,
                      ``"moderate"``, or ``"major"``.
        details:      Bullet-point list of specific changes observed.
        model:        The model used for the assessment.
        raw_response: The raw text Claude returned (for debugging).
        skipped:      ``True`` when the call was skipped because
                      ``max_per_session`` was reached.  All other fields
                      contain placeholder values when ``skipped=True``.
        skip_reason:  Human-readable explanation when ``skipped=True``.
    """

    changed: bool
    description: str
    severity: str
    details: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    raw_response: str = field(default="", repr=False)
    skipped: bool = field(default=False)
    skip_reason: str = field(default="")


# ---------------------------------------------------------------------------
# Session state  (module-level, reset with reset_session())
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_session_count: int = 0
_result_cache: dict[tuple, JudgeResult] = {}


def reset_session() -> None:
    """Reset the per-session API call counter and discard the result cache.

    Call this at the start of each new conversation / test to avoid stale
    state from previous sessions.
    """
    global _session_count, _result_cache
    with _lock:
        _session_count = 0
        _result_cache = {}


def get_session_count() -> int:
    """Return the number of successful (non-cached, non-skipped) API calls
    made since the last :func:`reset_session`."""
    with _lock:
        return _session_count


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
    max_retries: int = 2,
    max_per_session: int | None = None,
    _client: Any = None,
) -> JudgeResult:
    """Call Claude Vision to assess what changed between two screenshots.

    Args:
        baseline_path:   Reference (before) screenshot.
        current_path:    Candidate (after) screenshot.
        diff_path:       Optional SSIM diff image to include as a third image.
        model:           Anthropic model identifier (default ``claude-opus-4-5``).
        max_tokens:      Maximum response tokens (default 512).
        max_retries:     How many times to retry on transient API errors
                         (default 2; total attempts = max_retries + 1).
                         Exponential backoff: 1 s, 2 s, … between attempts.
                         ``FileNotFoundError`` / ``ValueError`` are not retried.
        max_per_session: If set, skip the API call and return a skipped result
                         once this many real calls have been made this session.
                         Useful for capping token spend.  ``None`` = unlimited.
        _client:         Injectable ``anthropic.Anthropic`` instance (testing).

    Returns:
        :class:`JudgeResult`.  Check ``result.skipped`` before using other
        fields — when ``True`` the comparison was not performed.

    Raises:
        FileNotFoundError: An image path does not exist.
        anthropic.APIError: All retry attempts exhausted.
    """
    global _session_count

    p_base = Path(baseline_path)
    p_cur  = Path(current_path)
    p_diff = Path(diff_path) if diff_path is not None else None

    # File existence — raise immediately (no retry, no session charge).
    if not p_base.exists():
        raise FileNotFoundError(f"Image not found: {p_base} (baseline screenshot)")
    if not p_cur.exists():
        raise FileNotFoundError(f"Image not found: {p_cur} (current screenshot)")
    if p_diff is not None and not p_diff.exists():
        raise FileNotFoundError(f"Image not found: {p_diff} (SSIM diff heat-map)")

    # Cache lookup — use file signatures so stale entries are avoided after
    # a screenshot is overwritten at the same path.
    cache_key = _make_cache_key(p_base, p_cur, p_diff, model)
    with _lock:
        cached = _result_cache.get(cache_key)
    if cached is not None:
        return cached

    # Session limit check.
    if max_per_session is not None:
        with _lock:
            if _session_count >= max_per_session:
                return JudgeResult(
                    changed=False,
                    description="Skipped: session judge limit reached.",
                    severity="none",
                    model=model,
                    skipped=True,
                    skip_reason=(
                        f"max_per_session={max_per_session} reached "
                        f"(current count: {_session_count})"
                    ),
                )

    # Build API payload.
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()

    images = [
        _image_block(p_base, "baseline screenshot"),
        _image_block(p_cur, "current screenshot"),
    ]
    if p_diff is not None:
        images.append(_image_block(p_diff, "SSIM diff heat-map"))

    user_text = _USER_PROMPT_WITH_DIFF if p_diff else _USER_PROMPT
    content: list[dict] = [*images, {"type": "text", "text": user_text}]

    # API call with retry.
    raw = _call_with_retry(
        _client,
        model=model,
        max_tokens=max_tokens,
        content=content,
        max_retries=max_retries,
    )
    result = _parse_response(raw, model=model)

    # Persist to cache and increment counter.
    with _lock:
        _session_count += 1
        _result_cache[cache_key] = result

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_cache_key(
    p_base: Path,
    p_cur: Path,
    p_diff: Path | None,
    model: str,
) -> tuple:
    """Build a cache key from file signatures (path + size + mtime_ms)."""

    def _sig(p: Path) -> tuple:
        try:
            s = p.stat()
            return (str(p), s.st_size, int(s.st_mtime * 1_000))
        except OSError:
            return (str(p), -1, -1)

    return (
        _sig(p_base),
        _sig(p_cur),
        _sig(p_diff) if p_diff is not None else None,
        model,
    )


def _call_with_retry(
    client: Any,
    *,
    model: str,
    max_tokens: int,
    content: list[dict],
    max_retries: int,
) -> str:
    """Call ``client.messages.create`` up to *max_retries + 1* times.

    Sleeps ``2**attempt`` seconds between attempts (1 s, 2 s, …).
    Any exception propagates immediately on the final attempt.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            return response.content[0].text if response.content else ""
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # 1 s, 2 s, 4 s …
    assert last_exc is not None
    raise last_exc


def _image_block(path: Path, label: str) -> dict:
    """Build an Anthropic image content block from a local PNG file."""
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path} ({label})")
    data = base64.standard_b64encode(path.read_bytes()).decode()
    ext = path.suffix.lower()
    media_type = {
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif":  "image/gif",
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
    text = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        doc: dict = json.loads(text)
    except (json.JSONDecodeError, ValueError):
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
