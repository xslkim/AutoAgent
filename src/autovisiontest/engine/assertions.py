"""Assertions — verify conditions during and after test execution.

Each assertion type is a standalone function that checks a specific condition.
The ``run_assertions`` dispatcher maps ``Assertion`` objects to the appropriate
check function and collects the results.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from autovisiontest.engine.models import Assertion, AssertionResult
from autovisiontest.perception.types import OCRResult, find_text
from autovisiontest.perception.similarity import ssim

logger = logging.getLogger(__name__)


# ── Individual assertion functions ───────────────────────────────────────


def assert_ocr_contains(ocr: OCRResult, text: str) -> AssertionResult:
    """Check that the OCR result contains the given text."""
    matches = find_text(ocr, text, fuzzy=True)
    if matches:
        return AssertionResult(type="ocr_contains", passed=True, detail=f"Found '{text}' in OCR")
    return AssertionResult(type="ocr_contains", passed=False, detail=f"'{text}' not found in OCR")


def assert_no_error_dialog(ocr: OCRResult) -> AssertionResult:
    """Check that no error dialog keywords appear in the OCR result."""
    from autovisiontest.perception.error_dialog import ERROR_KEYWORDS
    for item in ocr.items:
        text_lower = item.text.lower()
        for keyword in ERROR_KEYWORDS:
            if keyword.lower() in text_lower:
                return AssertionResult(
                    type="no_error_dialog",
                    passed=False,
                    detail=f"Error keyword '{keyword}' found in '{item.text}'",
                )
    return AssertionResult(type="no_error_dialog", passed=True, detail="No error dialog detected")


def assert_file_exists(path: str) -> AssertionResult:
    """Check that a file exists at the given path."""
    if os.path.isfile(path):
        return AssertionResult(type="file_exists", passed=True, detail=f"File exists: {path}")
    return AssertionResult(type="file_exists", passed=False, detail=f"File not found: {path}")


def assert_file_contains(path: str, text: str) -> AssertionResult:
    """Check that a file exists and contains the given text."""
    if not os.path.isfile(path):
        return AssertionResult(type="file_contains", passed=False, detail=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if text in content:
            return AssertionResult(
                type="file_contains", passed=True,
                detail=f"Text '{text}' found in {path}",
            )
        return AssertionResult(
            type="file_contains", passed=False,
            detail=f"Text '{text}' not found in {path}",
        )
    except Exception as e:
        return AssertionResult(
            type="file_contains", passed=False,
            detail=f"Error reading {path}: {e}",
        )


def assert_screenshot_similar(
    current: Any,
    template: Any,
    threshold: float = 0.9,
) -> AssertionResult:
    """Check that two screenshots are similar (SSIM >= threshold).

    Accepts numpy arrays or PNG bytes for both arguments.
    """
    import numpy as np
    # Convert to numpy if needed
    if isinstance(current, bytes):
        from autovisiontest.perception.similarity import ssim_bytes
        score = ssim_bytes(current, template)
    elif isinstance(current, np.ndarray) and isinstance(template, np.ndarray):
        score = ssim(current, template)
    else:
        return AssertionResult(
            type="screenshot_similar", passed=False,
            detail="Invalid input types for screenshot comparison",
        )

    if score >= threshold:
        return AssertionResult(
            type="screenshot_similar", passed=True,
            detail=f"SSIM={score:.4f} >= {threshold}",
        )
    return AssertionResult(
        type="screenshot_similar", passed=False,
        detail=f"SSIM={score:.4f} < {threshold}",
    )


def assert_vlm_element_exists(
    chat_backend: Any,
    image: bytes,
    element_desc: str,
) -> AssertionResult:
    """Check that a UI element exists using VLM.

    This sends a yes/no question to the VLM about whether the element
    is visible in the screenshot.
    """
    try:
        from autovisiontest.backends.types import Message
        messages = [
            Message(
                role="system",
                content="You are a UI element detector. Answer only 'yes' or 'no'.",
            ),
            Message(
                role="user",
                content=f"Is there a '{element_desc}' visible in this screenshot? Answer yes or no.",
            ),
        ]
        response = chat_backend.chat(messages, images=[image], response_format="text")
        answer = response.content.strip().lower()
        if answer.startswith("yes"):
            return AssertionResult(
                type="vlm_element_exists", passed=True,
                detail=f"VLM confirms '{element_desc}' exists",
            )
        return AssertionResult(
            type="vlm_element_exists", passed=False,
            detail=f"VLM says '{element_desc}' not found",
        )
    except Exception as e:
        return AssertionResult(
            type="vlm_element_exists", passed=False,
            detail=f"VLM check error: {e}",
        )


# ── Dispatcher ───────────────────────────────────────────────────────────

# Map assertion type names to their handler functions
_ASSERTION_HANDLERS: dict[str, Any] = {
    "ocr_contains": assert_ocr_contains,
    "no_error_dialog": assert_no_error_dialog,
    "file_exists": assert_file_exists,
    "file_contains": assert_file_contains,
    "screenshot_similar": assert_screenshot_similar,
    "vlm_element_exists": assert_vlm_element_exists,
}


def run_assertions(
    assertions: list[Assertion],
    ctx: dict,
) -> list[AssertionResult]:
    """Run a list of assertions and return their results.

    Args:
        assertions: List of Assertion objects to check.
        ctx: Context dict with keys needed by assertion handlers:
            - ``"ocr"``: OCRResult (for ocr_contains, no_error_dialog)
            - ``"screenshot"``: numpy array (for screenshot_similar)
            - ``"screenshot_png"``: bytes (for vlm_element_exists)
            - ``"chat_backend"``: ChatBackend (for vlm_element_exists)
            - Additional keys as required by specific assertion types.

    Returns:
        List of AssertionResult objects.
    """
    results: list[AssertionResult] = []

    for assertion in assertions:
        handler = _ASSERTION_HANDLERS.get(assertion.type)
        if handler is None:
            results.append(
                AssertionResult(
                    type=assertion.type,
                    passed=False,
                    detail=f"Unknown assertion type: {assertion.type}",
                )
            )
            continue

        try:
            result = _dispatch(handler, assertion, ctx)
            results.append(result)
        except Exception as e:
            results.append(
                AssertionResult(
                    type=assertion.type,
                    passed=False,
                    detail=f"Assertion error: {e}",
                )
            )

    return results


def _dispatch(handler: Any, assertion: Assertion, ctx: dict) -> AssertionResult:
    """Dispatch an assertion to its handler with the right arguments."""
    atype = assertion.type
    params = assertion.params

    if atype == "ocr_contains":
        return handler(ctx["ocr"], params.get("text", ""))
    elif atype == "no_error_dialog":
        return handler(ctx["ocr"])
    elif atype == "file_exists":
        return handler(params.get("path", ""))
    elif atype == "file_contains":
        return handler(params.get("path", ""), params.get("text", ""))
    elif atype == "screenshot_similar":
        current = ctx.get("screenshot")
        template = params.get("template")
        threshold = params.get("threshold", 0.9)
        return handler(current, template, threshold)
    elif atype == "vlm_element_exists":
        return handler(
            ctx["chat_backend"],
            ctx.get("screenshot_png", b""),
            params.get("element_desc", ""),
        )
    else:
        return AssertionResult(
            type=atype, passed=False,
            detail=f"Unhandled assertion type: {atype}",
        )
