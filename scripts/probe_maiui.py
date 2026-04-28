"""Probe MAI-UI-2B to discover its output dialect.

This script is **not** coupled to any backend.  It sends raw chat completion
requests to the MAI-UI vLLM server (default ``localhost:8001``) and dumps the
verbatim replies so we can see which coordinate / action format the model
actually emits.  That information drives the design of
``src/autovisiontest/backends/maiui.py``.

Usage::

    # Probe against the live desktop with a simple GUI goal.
    python scripts/probe_maiui.py --goal "点击任务栏最左边的 Windows 开始按钮"

    # Or reuse a pre-captured screenshot.
    python scripts/probe_maiui.py --image data/probes/last/screen.png --goal "..."

We try several *prompt variants* in one run so we can compare which phrasing
MAI-UI responds to most reliably.  Raw replies plus the screenshot are saved
under ``data/probes/maiui_<timestamp>/`` for later inspection.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _load_image(image_path: str | None) -> bytes:
    if image_path:
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(p)
        return p.read_bytes()
    from autovisiontest.control.screenshot import capture_primary_screen

    return capture_primary_screen()


# ---------------------------------------------------------------------------
# Prompt variants.  Each callable receives the user goal and returns the
# ``messages`` list that goes into the request body.  We keep them all in one
# place so adding a new dialect is a one-line change.
# ---------------------------------------------------------------------------


def _data_url(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _content_with_image(image_bytes: bytes, text: str) -> list[dict]:
    return [
        {"type": "image_url", "image_url": {"url": _data_url(image_bytes)}},
        {"type": "text", "text": text},
    ]


# Variant A — UI-TARS style "computer use" template.  Checks whether MAI-UI
# happens to understand the same prompt we already use for UI-TARS.
_UITARS_STYLE = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

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
hotkey(key='ctrl c')
type(content='xxx')
scroll(start_box='(x1,y1)', direction='down or up or right or left')
wait()
finished(content='xxx')

## Note
- Use Chinese in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""


def variant_a_uitars_style(image: bytes, goal: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": _content_with_image(image, _UITARS_STYLE.format(instruction=goal)),
        }
    ]


# Variant B — bare MAI-UI prompt per their README snippet (paraphrased).  The
# official Tongyi-MAI/MAI-UI-2B card shows the model was trained to take a
# plain instruction + screenshot and emit ``Action: <name>(...)`` with
# **normalized coordinates in [0, 1]**.  We test this hypothesis directly.
_BARE_STYLE = """You are a GUI agent operating a computer.  Given a screenshot and an instruction, output the next action.  Coordinates must be normalized floats in [0, 1].

Instruction: {instruction}"""


def variant_b_bare(image: bytes, goal: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": _content_with_image(image, _BARE_STYLE.format(instruction=goal)),
        }
    ]


# Variant C — "just tell me where to click".  Strips all action-space
# scaffolding to see what raw grounding looks like.  If this returns clean
# coordinates we know the model has a solid grounding head underneath.
_ASK_COORD_STYLE = (
    "Look at the screenshot.  The user wants to: {instruction}\n"
    "Respond with ONLY the click coordinates as a JSON object of the form "
    '{{"x": <float>, "y": <float>}} where x and y are normalized to the image '
    "width and height in the range [0, 1].  No explanation."
)


def variant_c_ask_coord(image: bytes, goal: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": _content_with_image(image, _ASK_COORD_STYLE.format(instruction=goal)),
        }
    ]


VARIANTS = {
    "a_uitars_style": variant_a_uitars_style,
    "b_bare": variant_b_bare,
    "c_ask_coord": variant_c_ask_coord,
}


# ---------------------------------------------------------------------------


def _call(endpoint: str, model: str, messages: list[dict], max_tokens: int, temperature: float) -> tuple[dict, float]:
    url = endpoint.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    t0 = time.monotonic()
    resp = requests.post(url, json=payload, timeout=120)
    dt = time.monotonic() - t0
    resp.raise_for_status()
    return resp.json(), dt


def _extract_reply(raw: dict) -> str:
    try:
        return raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return json.dumps(raw, ensure_ascii=False, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description="MAI-UI-2B dialect probe")
    ap.add_argument(
        "--goal",
        default="点击任务栏最左边的 Windows 开始按钮。",
        help="Natural-language instruction for the agent.",
    )
    ap.add_argument("--image", default=None, help="Path to PNG; omit to capture the live desktop.")
    ap.add_argument("--endpoint", default="http://localhost:8001/v1")
    ap.add_argument("--model", default="mai-ui-2b")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument(
        "--variants",
        nargs="+",
        default=list(VARIANTS),
        choices=list(VARIANTS),
        help="Which prompt variants to try (default: all).",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Directory to save raw artifacts; default data/probes/maiui_<ts>/.",
    )
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "data" / "probes" / f"maiui_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[probe] goal      : {args.goal}")
    print(f"[probe] endpoint  : {args.endpoint}")
    print(f"[probe] model     : {args.model}")
    print(f"[probe] out_dir   : {out_dir}")
    print(f"[probe] variants  : {args.variants}")
    print()

    img_bytes = _load_image(args.image)
    shot_path = out_dir / "screen.png"
    shot_path.write_bytes(img_bytes)
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(img_bytes))
    print(f"[probe] screenshot: {len(img_bytes)} bytes, size={img.size} -> {shot_path.name}")
    print()

    failures: list[str] = []
    for name in args.variants:
        builder = VARIANTS[name]
        messages = builder(img_bytes, args.goal)
        print("=" * 72)
        print(f"[variant] {name}")
        print("-" * 72)
        try:
            raw, dt = _call(args.endpoint, args.model, messages, args.max_tokens, args.temperature)
        except requests.HTTPError as exc:
            err = f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
            print(f"[error] {err}")
            (out_dir / f"reply_{name}.err.txt").write_text(err, encoding="utf-8")
            failures.append(name)
            continue
        except requests.RequestException as exc:
            err = f"RequestException: {exc}"
            print(f"[error] {err}")
            (out_dir / f"reply_{name}.err.txt").write_text(err, encoding="utf-8")
            failures.append(name)
            continue

        reply = _extract_reply(raw)
        usage = raw.get("usage", {})
        print(f"latency  : {dt*1000:.0f} ms")
        print(f"usage    : prompt={usage.get('prompt_tokens')}  completion={usage.get('completion_tokens')}")
        print("-" * 72)
        print("reply    :")
        print(reply)
        print()

        (out_dir / f"reply_{name}.txt").write_text(reply, encoding="utf-8")
        (out_dir / f"raw_{name}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("=" * 72)
    print(f"[probe] artifacts in {out_dir}")
    if failures:
        print(f"[probe] failed variants: {failures}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
