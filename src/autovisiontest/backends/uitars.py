"""UI-TARS-1.5 agent backend via vLLM.

UI-TARS is a GUI agent built on Qwen2.5-VL-7B + RL finetuning.  Unlike the
previous two-model split (general Planner + dedicated grounding Actor), one
UI-TARS call produces, in a single pass, a free-form ``Thought`` plus an
``Action`` that already carries absolute pixel coordinates.

Reference: https://github.com/bytedance/UI-TARS — prompt template
``COMPUTER_USE_DOUBAO`` in ``codes/ui_tars/prompt.py``.

Expected model output format (single turn)::

    Thought: ... reasoning in natural language ...
    Action: click(start_box='(512,720)')

Prompt dialect
--------------
The community AWQ checkpoint (``flin775/UI-TARS-1.5-7B-AWQ``) was calibrated
on the earlier Doubao 1.0 action schema that uses ``start_box='(x,y)'``
rather than ``point='<point>x y</point>'``.  Instructing it with the newer
``<point>`` syntax caused the model to fall back to its training
distribution — emitting ``start_box`` coords anyway but with noticeably
looser grounding on dense UIs (e.g. a calculator keypad).  We therefore
prompt it in the dialect it was trained on; the parser still accepts both
styles for forward-compat with the official 1.5 weights.

Coordinate space notes
----------------------
The coordinates emitted by the model are relative to the image *as it is
fed to the Qwen2.5-VL vision preprocessor*.  The preprocessor forces the
number of visual tokens to stay within ``[min_pixels, max_pixels]`` (where
``max_pixels = 1344 * 28 * 28`` for UI-TARS-1.5-7B), which means a 1920×1080
screenshot will be silently resized.  To make unscaling deterministic we
resize the image ourselves *before* sending and remember the ratio; the
parser then maps model coords back to original-screen pixels.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from PIL import Image

from autovisiontest.exceptions import ChatBackendError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_ENDPOINT = "http://localhost:8000/v1"
_DEFAULT_TIMEOUT_S = 60.0

# Stop sequences to prevent the AWQ checkpoint from hallucinating a second
# assistant turn in the same completion — a known failure mode observed in
# UI-TARS-1.5-7B-AWQ when the model is confused.  When the model rambles past
# its first ``Action:``, it tends to leak the chat template role name
# (``assistant``) as plain text before starting another ``Thought:`` block; by
# the time ``max_tokens`` hits, the second action is cut mid-word and the
# parser can't recover.  Stopping at those boundaries keeps the completion
# single-turn so the parser always sees a well-formed ``Thought + Action``.
_STOP_SEQUENCES: list[str] = [
    "<|im_end|>",
    "\nassistant\n",
    "\nassistant ",
    # A second ``Thought:`` or ``Action:`` inside one completion means the
    # model is drifting into a multi-turn rollout; stop before the drift
    # corrupts the first (still-valid) action.  We use ``\n\n`` prefixes so
    # the first Thought/Action — which legitimately sit at the start of the
    # reply or right after each other on a single newline — are not hit.
    "\n\nThought:",
    "\n\nAction:",
]

# Qwen2.5-VL vision preprocessor limits (patch size = 28):
# UI-TARS-1.5 is trained with max_pixels = 1344 * 28 * 28 ≈ 1.05M pixels.
# We pre-resize to stay just within this bound so the server-side
# preprocessor does not scale further, giving us a known coordinate frame.
_QWEN_VL_PATCH = 28
_MAX_TOKENS_TARGET = 1344  # -> max pixel budget 1344 * 28 * 28
_MAX_PIXELS = _MAX_TOKENS_TARGET * _QWEN_VL_PATCH * _QWEN_VL_PATCH
_JPEG_QUALITY = 85

# ---------------------------------------------------------------------------
# Prompt template (verbatim from bytedance/UI-TARS/codes/ui_tars/prompt.py,
# COMPUTER_USE_DOUBAO).  We keep it byte-exact so the model lands on its
# training distribution; only {language} and {instruction} are filled in.
# ---------------------------------------------------------------------------

COMPUTER_USE_TEMPLATE = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
```
Thought: ...
Action: ...
```

## Action Space

click(start_box='(x1,y1)')
left_double(start_box='(x1,y1)')
right_single(start_box='(x1,y1)')
drag(start_box='(x1,y1)', end_box='(x2,y2)')
hotkey(key='ctrl c') # Split keys with a space and use lowercase. Also, do not use more than 3 keys in one hotkey action.
type(content='xxx') # Use escape characters \\', \\\", and \\n in content part to ensure we can parse the content in normal python string format. If you want to submit your input, use \\n at the end of content. 
scroll(start_box='(x1,y1)', direction='down or up or right or left') # Show more information on the `direction` side.
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.

## Note
- Use {language} in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class UITarsDecision:
    """A parsed decision from UI-TARS.

    Coordinates (``point_xy`` / ``end_point_xy``) are already in original
    screen pixel space — the backend handles the scale-back from the
    resized image coords emitted by the model.
    """

    thought: str
    action_type: str  # click | left_double | right_single | drag | hotkey | type | scroll | wait | finished | error
    action_params: dict[str, Any] = field(default_factory=dict)
    point_xy: tuple[int, int] | None = None
    end_point_xy: tuple[int, int] | None = None  # for drag
    finished: bool = False
    finished_content: str = ""
    raw_response: str = ""
    parse_error: str | None = None


@dataclass
class HistoryStep:
    """One past step to feed back into the next prompt.

    ``screenshot_png`` is optional — if omitted, only the textual summary
    of the action is included, saving visual tokens.
    """

    thought: str
    action_summary: str  # e.g. "click(start_box='(512,720)')"
    screenshot_png: bytes | None = None


# ---------------------------------------------------------------------------
# Image resizing — run before sending so coord frame is known
# ---------------------------------------------------------------------------


def _resize_for_uitars(image_png: bytes) -> tuple[bytes, int, int, int, int]:
    """Resize ``image_png`` so total pixel count is ≤ ``_MAX_PIXELS``.

    Returns:
        ``(jpeg_bytes, orig_w, orig_h, sent_w, sent_h)`` — the JPEG we
        actually send, together with the original and sent dimensions.
        Call ``_unscale_xy`` with these dimensions to map model output
        coordinates back to original screen space.
    """
    img = Image.open(io.BytesIO(image_png))
    orig_w, orig_h = img.size

    total = orig_w * orig_h
    if total <= _MAX_PIXELS:
        sent_w, sent_h = orig_w, orig_h
        out = img.convert("RGB") if img.mode != "RGB" else img
    else:
        ratio = (_MAX_PIXELS / total) ** 0.5
        sent_w = max(_QWEN_VL_PATCH, int(orig_w * ratio) // _QWEN_VL_PATCH * _QWEN_VL_PATCH)
        sent_h = max(_QWEN_VL_PATCH, int(orig_h * ratio) // _QWEN_VL_PATCH * _QWEN_VL_PATCH)
        out = img.resize((sent_w, sent_h), Image.Resampling.LANCZOS).convert("RGB")

    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buf.getvalue(), orig_w, orig_h, sent_w, sent_h


def _unscale_xy(
    x_sent: float,
    y_sent: float,
    orig_w: int,
    orig_h: int,
    sent_w: int,
    sent_h: int,
) -> tuple[int, int]:
    """Map coordinates from the sent-image frame back to original screen pixels."""
    if sent_w == 0 or sent_h == 0:
        return int(x_sent), int(y_sent)
    x_orig = round(x_sent * orig_w / sent_w)
    y_orig = round(y_sent * orig_h / sent_h)
    # Clamp to [0, orig-1] — model very occasionally emits a coord at the edge
    # boundary which would otherwise be off-screen.
    x_orig = max(0, min(orig_w - 1, x_orig))
    y_orig = max(0, min(orig_h - 1, y_orig))
    return x_orig, y_orig


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_instruction_text(goal: str, language: str = "Chinese") -> str:
    """Fill the COMPUTER_USE template with ``goal`` and the thought language."""
    return COMPUTER_USE_TEMPLATE.format(language=language, instruction=goal.strip())


def build_messages(
    goal: str,
    current_image_b64: str,
    history: list[HistoryStep] | None = None,
    language: str = "Chinese",
    history_images: int = 3,
) -> list[dict[str, Any]]:
    """Assemble an OpenAI-compatible ``messages`` list for UI-TARS /
    MAI-UI in *causal* order — each screenshot precedes the assistant
    turn that reasoned about it.

    Layout::

        [user]      instruction text (goal)
        [user]      screenshot_0          ← what I saw at step 0
        [assistant] Thought_0 + Action_0  ← what I did based on it
        [user]      screenshot_1          ← what I saw at step 1
        [assistant] Thought_1 + Action_1
        ...
        [user]      current_screenshot    ← what I'm seeing NOW

    Earlier history entries whose screenshots have been dropped (to stay
    within ``history_images``) are elided entirely — we do not emit an
    assistant turn without its paired screenshot, because dangling
    assistant turns with no visible context make the model doubt its own
    reasoning and can cause it to keep repeating step-0 intent regardless
    of the latest screenshot (observed with MAI-UI-2B on 2026-04-20,
    where the inverted ordering produced 10 identical thoughts in a row).
    """
    history = history or []
    instruction = build_instruction_text(goal, language=language)

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": instruction}]},
    ]

    n = len(history)
    keep_img_from_idx = max(0, n - history_images)
    for i, step in enumerate(history):
        if step.screenshot_png is None or i < keep_img_from_idx:
            # No visible frame for this step — dropping the whole pair
            # keeps the causal "image → action" structure intact.
            continue
        img_b64 = base64.b64encode(step.screenshot_png).decode("utf-8")
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": f"Thought: {step.thought}\nAction: {step.action_summary}",
            }
        )

    # Current screenshot — what the model must decide about NOW.
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{current_image_b64}"},
                }
            ],
        }
    )
    return messages


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

# Thought is everything between "Thought:" and the first "Action:".
_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?=\n\s*Action:|\Z)", re.DOTALL | re.IGNORECASE)
# Action is everything after "Action:" to end of text.
_ACTION_RE = re.compile(r"Action:\s*(.*?)\Z", re.DOTALL | re.IGNORECASE)

# Parse a top-level call like  `click(start_box='(512,720)')`.
# Captures (fn_name, args_blob).
_CALL_RE = re.compile(r"([a-z_]+)\s*\((.*)\)\s*$", re.DOTALL)
# Looser fallback used when the model's output got truncated mid-call — no
# closing ``)`` on the outermost function.  Captures everything after the
# opening paren; downstream coord extractors must be equally tolerant.
_CALL_LOOSE_RE = re.compile(r"([a-z_]+)\s*\((.*)$", re.DOTALL)

# Coordinate inside <point>...</point> tags (floats allowed just in case).
_POINT_RE = re.compile(r"<point>\s*([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s*</point>")

# Parenthesised pair — used in `start_box='(23,712)'` style dialects emitted
# by various UI-TARS checkpoints (notably the AWQ community builds).  The
# closing ``)`` is optional so we can still recover a point from a truncated
# ``start_box='(560,362`` when a stop sequence cuts the completion early.
_COORD_PAIR_RE = re.compile(
    r"\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*\)?"
)
# Bracketed bounding box — occasionally emitted as `start_box='[x1,y1,x2,y2]'`;
# we collapse it to the box centre.  Closing ``]`` is optional for the same
# truncation-recovery reason as above.
_COORD_BBOX_RE = re.compile(
    r"\[\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,"
    r"\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*\]?"
)

# Kwarg names that carry the *starting* location across all known dialects.
_START_POINT_KEYS = {"point", "start_point", "start_box"}
# Kwarg names that carry the *ending* location (drag's second point).
_END_POINT_KEYS = {"end_point", "end_box"}

# Generic key='value' or key="value" argument extractor (value may contain
# escape sequences and spaces).  Non-greedy to avoid gobbling adjacent args.
_KW_SINGLE_RE = re.compile(r"(\w+)\s*=\s*'((?:\\.|[^'\\])*)'")
_KW_DOUBLE_RE = re.compile(r'(\w+)\s*=\s*"((?:\\.|[^"\\])*)"')


def _extract_kwargs(args_blob: str) -> dict[str, str]:
    """Pull out all ``key='value'`` pairs (single- or double-quoted)."""
    kwargs: dict[str, str] = {}
    for m in _KW_SINGLE_RE.finditer(args_blob):
        kwargs[m.group(1)] = m.group(2)
    for m in _KW_DOUBLE_RE.finditer(args_blob):
        # Don't override a single-quoted hit (first wins — arbitrary but stable).
        kwargs.setdefault(m.group(1), m.group(2))
    return kwargs


def _coord_from_value(val: str) -> tuple[float, float] | None:
    """Extract a single (x, y) from one kwarg value.

    Accepts any of these dialects:
        * ``<point>x y</point>``                 — our preferred format
        * ``(x, y)``                             — `start_box='(23,712)'`
        * ``[x1, y1, x2, y2]``                   — bbox → take centre
    """
    m_pt = _POINT_RE.search(val)
    if m_pt:
        return float(m_pt.group(1)), float(m_pt.group(2))
    m_bb = _COORD_BBOX_RE.search(val)
    if m_bb:
        x1, y1, x2, y2 = (float(g) for g in m_bb.groups())
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0
    m_pa = _COORD_PAIR_RE.search(val)
    if m_pa:
        return float(m_pa.group(1)), float(m_pa.group(2))
    return None


def _extract_points(
    args_blob: str, kwargs: dict[str, str]
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Return ``(start_points, end_points)`` discovered across all dialects.

    The *start* list first pulls any bare ``<point>…</point>`` occurrences in
    the raw args blob (robust to weird formatting), then merges in whatever
    the ``point`` / ``start_point`` / ``start_box`` kwargs expose.  The
    *end* list comes exclusively from ``end_point`` / ``end_box`` kwargs.

    When the model output is *truncated* (e.g. ``click(start_box='(560,362)``
    without the closing quote/paren — a known failure mode when the AWQ
    checkpoint tries to emit a second turn inside one completion and a stop
    sequence cuts mid-string), ``_KW_SINGLE_RE`` can't match the kwarg and
    ``kwargs`` comes back empty.  As a last resort we scan the raw args
    blob directly for any ``(x,y)`` / ``[x1,y1,x2,y2]`` pair so a mangled
    click still produces usable coordinates instead of a parse_error.
    """
    start: list[tuple[float, float]] = [
        (float(m.group(1)), float(m.group(2))) for m in _POINT_RE.finditer(args_blob)
    ]
    end: list[tuple[float, float]] = []

    for key, val in kwargs.items():
        k = key.lower()
        if k in _START_POINT_KEYS:
            coord = _coord_from_value(val)
            if coord is not None:
                start.append(coord)
        elif k in _END_POINT_KEYS:
            coord = _coord_from_value(val)
            if coord is not None:
                end.append(coord)

    if not start and not end:
        m_bb = _COORD_BBOX_RE.search(args_blob)
        if m_bb:
            x1, y1, x2, y2 = (float(g) for g in m_bb.groups())
            start.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
        else:
            m_pa = _COORD_PAIR_RE.search(args_blob)
            if m_pa:
                start.append((float(m_pa.group(1)), float(m_pa.group(2))))
    return start, end


_ESCAPE_MAP = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "'": "'",
    '"': '"',
    "\\": "\\",
}


def _unescape(s: str) -> str:
    """Undo UI-TARS's documented escape sequences (``\\'``, ``\\"``, ``\\n``).

    Uses a single-pass regex so ``\\\\n`` stays ``\\n`` instead of being
    collapsed twice; non-ASCII bytes (e.g. Chinese) pass through untouched
    because we operate on the str level, not on encoded bytes.
    """
    return re.sub(
        r"\\(.)",
        lambda m: _ESCAPE_MAP.get(m.group(1), m.group(1)),
        s,
    )


def parse_action_response(
    raw: str,
    coord_transform: Callable[[float, float], tuple[int, int]],
) -> UITarsDecision:
    """Parse any GUI-VLA assistant reply that follows the UI-TARS
    ``Thought + Action(name='value', ...)`` convention.

    The raw numeric coordinates emitted by the model are mapped to
    absolute screen pixels via ``coord_transform`` — a callable that
    knows the coordinate system used by the calling backend:

    * **UI-TARS** (sent-image-pixel frame): pass
      ``lambda x, y: _unscale_xy(x, y, orig_w, orig_h, sent_w, sent_h)``.
    * **MAI-UI / Qwen-VL** (``[0, 1000]`` normalised virtual canvas):
      pass ``lambda x, y: (round(x * W / 1000), round(y * H / 1000))``.

    Tolerates the usual format drifts (missing ``Thought:``, stray
    whitespace / backticks, single vs double quotes, truncated trailing
    ``)``) so a mangled but mostly-valid completion still produces a
    usable :class:`UITarsDecision`.
    """
    text = (raw or "").strip()
    decision = UITarsDecision(thought="", action_type="error", raw_response=text)

    if not text:
        decision.parse_error = "empty response"
        return decision

    # --- Thought ---
    t_match = _THOUGHT_RE.search(text)
    if t_match:
        decision.thought = t_match.group(1).strip()

    # --- Action ---
    a_match = _ACTION_RE.search(text)
    if not a_match:
        # Some replies omit "Action:" and put the call on the last line.
        last_line = text.splitlines()[-1].strip()
        if re.match(r"[a-z_]+\s*\(", last_line):
            action_text = last_line
        else:
            decision.parse_error = "no Action: block found"
            return decision
    else:
        action_text = a_match.group(1).strip()

    # Strip stray code fences or leading/trailing backticks the model may add.
    action_text = action_text.strip("`").strip()
    # If the model produced multiple actions, only take the first line.
    action_text = action_text.splitlines()[0].strip()

    call_match = _CALL_RE.match(action_text)
    if not call_match:
        # Fall back to the looser pattern that tolerates a missing outer
        # closing ``)`` — hits when the model's completion was truncated
        # by a stop sequence mid-arg.
        call_match = _CALL_LOOSE_RE.match(action_text)
    if not call_match:
        decision.parse_error = f"action not parseable as call: {action_text!r}"
        return decision

    fn_name = call_match.group(1).lower()
    args_blob = call_match.group(2)
    decision.action_type = fn_name

    kwargs = _extract_kwargs(args_blob)
    start_points, end_points = _extract_points(args_blob, kwargs)

    def _pt(p: tuple[float, float]) -> tuple[int, int]:
        return coord_transform(p[0], p[1])

    if fn_name in {"click", "left_double", "right_single"}:
        if start_points:
            decision.point_xy = _pt(start_points[0])
        else:
            decision.parse_error = f"{fn_name} missing coordinate"
    elif fn_name == "drag":
        # Drag needs exactly one start and one end.  Some checkpoints reuse
        # ``<point>`` twice inside the args instead of start_point/end_point;
        # in that case start_points holds both and end_points is empty.
        if start_points and end_points:
            decision.point_xy = _pt(start_points[0])
            decision.end_point_xy = _pt(end_points[0])
        elif len(start_points) >= 2:
            decision.point_xy = _pt(start_points[0])
            decision.end_point_xy = _pt(start_points[1])
        else:
            decision.parse_error = "drag requires start and end coordinates"
    elif fn_name == "scroll":
        if start_points:
            decision.point_xy = _pt(start_points[0])
        decision.action_params["direction"] = kwargs.get("direction", "down")
    elif fn_name == "hotkey":
        decision.action_params["key"] = kwargs.get("key", "")
    elif fn_name == "type":
        decision.action_params["content"] = _unescape(kwargs.get("content", ""))
    elif fn_name == "wait":
        pass
    elif fn_name == "finished":
        decision.finished = True
        decision.finished_content = _unescape(kwargs.get("content", ""))
    else:
        decision.parse_error = f"unknown action: {fn_name}"

    return decision


def parse_uitars_response(
    raw: str,
    orig_w: int,
    orig_h: int,
    sent_w: int,
    sent_h: int,
) -> UITarsDecision:
    """Parse a UI-TARS assistant reply — thin wrapper around
    :func:`parse_action_response` that builds the sent-image-pixel
    coordinate transform specific to the UI-TARS dialect.
    """

    def _transform(x: float, y: float) -> tuple[int, int]:
        return _unscale_xy(x, y, orig_w, orig_h, sent_w, sent_h)

    return parse_action_response(raw, _transform)


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------


class UITarsBackend:
    """Single-model GUI agent backed by UI-TARS-1.5-7B via vLLM.

    This replaces the previous Planner (``VLLMChatBackend`` with JSON
    schema) + Actor (``ShowUIGroundingBackend``) split.  One call returns a
    :class:`UITarsDecision` containing both the reasoning and the action
    (with absolute screen coordinates).
    """

    def __init__(
        self,
        model: str = "ui-tars-1.5-7b",
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
        """Produce a single :class:`UITarsDecision` for ``image_png``.

        The image is resized to the UI-TARS-friendly budget before being
        sent; the resulting coordinates in the decision are already in
        original-screen pixel space.
        """
        sent_bytes, orig_w, orig_h, sent_w, sent_h = _resize_for_uitars(image_png)
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
            "stop": _STOP_SEQUENCES,
        }

        url = f"{self._endpoint}/chat/completions"
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout_s)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ChatBackendError(
                f"UI-TARS HTTP error: {exc}",
                retryable=True,
            ) from exc
        except ValueError as exc:
            raise ChatBackendError(
                f"UI-TARS response not valid JSON: {exc}",
                retryable=False,
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            raise ChatBackendError(
                f"UI-TARS response has no choices: {data!r}",
                retryable=False,
            )
        content = choices[0].get("message", {}).get("content", "")

        decision = parse_uitars_response(content, orig_w, orig_h, sent_w, sent_h)
        logger.debug(
            "uitars_decision action=%s point=%s finished=%s thought=%.80s",
            decision.action_type,
            decision.point_xy,
            decision.finished,
            decision.thought.replace("\n", " "),
        )
        if decision.parse_error:
            logger.warning("uitars_parse_error: %s | raw=%s", decision.parse_error, content[:300])
        return decision
