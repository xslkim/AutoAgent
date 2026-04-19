"""MAI-UI-2B GUI agent backend via vLLM.

MAI-UI (Tongyi-MAI) is a Qwen3-VL based GUI agent that shares the
``Thought + Action(...)`` output convention of UI-TARS, so we reuse the
UI-TARS prompt template, message builder and regex parser verbatim.
The only meaningful difference is the **coordinate dialect**: MAI-UI
emits coordinates in a ``[0, 1000]`` virtual canvas per axis (the Qwen-VL
training convention), *not* in the sent-image pixel frame that UI-TARS
uses.  The backend therefore:

* **Does not pre-resize** the screenshot.  MAI-UI handles its own vision
  preprocessing; its output is always in ``[0, 1000]`` regardless of the
  input resolution.
* **Converts PNG → JPEG** (quality 85) purely for network efficiency; a
  1920×1080 PNG drops from ~250KB to ~100KB without any grounding cost.
* **Does not inject stop sequences**.  Empirically MAI-UI-2B produces
  clean single-turn completions without the chat-template leakage that
  plagues the UI-TARS-AWQ 7B checkpoint.

The coordinate convention was verified against Windows Calculator on
2026-04-20: 6 targets (digits, operators, text labels) all grounded
within 5 pixels of true centre once ``model_xy * (W, H) / 1000`` was
applied — see ``data/probes/maiui_matrix_20260420_004911`` for the
evidence baseline.
"""

from __future__ import annotations

import base64
import io
import logging

import httpx
from PIL import Image

from autovisiontest.backends.uitars import (
    HistoryStep,
    UITarsDecision,
    build_messages,
    parse_action_response,
)
from autovisiontest.exceptions import ChatBackendError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_DEFAULT_ENDPOINT = "http://localhost:8001/v1"
_DEFAULT_MODEL = "mai-ui-2b"
_DEFAULT_TIMEOUT_S = 60.0

# Virtual canvas size used by Qwen-VL family training.  Model-emitted
# coordinates are always in ``[0, _NORM_SCALE]`` per axis; rescaling by
# the true image width/height recovers absolute screen pixels.
_NORM_SCALE = 1000.0

# Recompression to JPEG saves bandwidth without perceptibly changing the
# grounding — MAI-UI is robust to mild JPEG artefacts at q=85.
_JPEG_QUALITY = 85


# ---------------------------------------------------------------------------
# Image handling — no resize, just PNG → JPEG
# ---------------------------------------------------------------------------


def _prepare_image(image_png: bytes) -> tuple[bytes, int, int]:
    """Return ``(jpeg_bytes, orig_w, orig_h)``.

    Unlike the UI-TARS backend we intentionally skip resizing: MAI-UI is
    trained to preprocess its own vision input and emit normalised
    coordinates regardless of the raw input resolution.
    """
    img = Image.open(io.BytesIO(image_png))
    orig_w, orig_h = img.size
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buf.getvalue(), orig_w, orig_h


def _make_norm1000_transform(orig_w: int, orig_h: int):
    """Build the coord transform that maps ``[0, 1000]`` → screen pixels.

    Clamped to ``[0, orig-1]`` so an edge-of-canvas prediction (e.g.
    ``1000``) never lands one pixel past the right edge.
    """

    def _transform(x: float, y: float) -> tuple[int, int]:
        x_px = int(round(x * orig_w / _NORM_SCALE))
        y_px = int(round(y * orig_h / _NORM_SCALE))
        x_px = max(0, min(orig_w - 1, x_px))
        y_px = max(0, min(orig_h - 1, y_px))
        return x_px, y_px

    return _transform


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------


class MAIUIBackend:
    """Single-model GUI agent backed by MAI-UI-2B (Qwen3-VL) via vLLM.

    Shape-compatible with :class:`autovisiontest.backends.uitars.UITarsBackend`
    — ``decide(image_png, goal, history) -> UITarsDecision`` — so any
    :class:`UITarsAgent` or live probe script can swap backends by just
    changing the constructor call.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        endpoint: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        language: str = "Chinese",
        history_images: int = 3,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._model = model
        self._endpoint = (endpoint or _DEFAULT_ENDPOINT).rstrip("/")
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._language = language
        self._history_images = history_images
        self._timeout_s = timeout_s

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def decide(
        self,
        image_png: bytes,
        goal: str,
        history: list[HistoryStep] | None = None,
    ) -> UITarsDecision:
        """Produce a :class:`UITarsDecision` for ``image_png``.

        Coordinates in the returned decision are already in absolute
        screen-pixel space — the ``[0, 1000]`` → pixel mapping is applied
        inside :func:`parse_action_response` via ``coord_transform``.
        """
        sent_bytes, orig_w, orig_h = _prepare_image(image_png)
        b64 = base64.b64encode(sent_bytes).decode("utf-8")

        messages = build_messages(
            goal=goal,
            current_image_b64=b64,
            history=history,
            language=self._language,
            history_images=self._history_images,
        )

        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }

        url = f"{self._endpoint}/chat/completions"
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout_s)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ChatBackendError(
                f"MAI-UI HTTP error: {exc}",
                retryable=True,
            ) from exc
        except ValueError as exc:
            raise ChatBackendError(
                f"MAI-UI response not valid JSON: {exc}",
                retryable=False,
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            raise ChatBackendError(
                f"MAI-UI response has no choices: {data!r}",
                retryable=False,
            )
        content = choices[0].get("message", {}).get("content", "")

        transform = _make_norm1000_transform(orig_w, orig_h)
        decision = parse_action_response(content, transform)
        logger.debug(
            "maiui_decision action=%s point=%s finished=%s thought=%.80s",
            decision.action_type,
            decision.point_xy,
            decision.finished,
            decision.thought.replace("\n", " "),
        )
        if decision.parse_error:
            logger.warning(
                "maiui_parse_error: %s | raw=%s", decision.parse_error, content[:300]
            )
        return decision
