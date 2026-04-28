"""Calculator-targeted MAI-UI-2B grounding probe.

This is the *exact* case where UI-TARS-1.5-7B-AWQ fails: clicking the
multiplication (`×`) operator on Windows Calculator.  We use it here as a
direct A/B comparison — same screen, same goal, different model.

The script will:

1. Launch ``calc.exe`` and wait a few seconds for it to render.
2. Grab the full primary-display screenshot.
3. Fire **three prompt variants** (UI-TARS-style / bare / JSON-only) at the
   MAI-UI vLLM server on ``localhost:8001``.
4. Try to extract click coordinates from each reply — accepting pixel,
   normalised-[0,1] and JSON formats.
5. Draw a crosshair on a copy of the screenshot for every successfully
   extracted coordinate and save the annotated images.

Everything lands in ``data/probes/maiui_calc_<timestamp>/`` so we can diff
the replies and eyeball the hit points.

Usage::

    # Default: launches calc.exe for you, goal is the × button.
    python scripts/probe_maiui_calc.py

    # If calculator is already open and focused, skip the launch.
    python scripts/probe_maiui_calc.py --no-launch --wait 1

    # Try a different target without editing code.
    python scripts/probe_maiui_calc.py --goal "点击计算器上的等号（=）按钮"
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# ---------------------------------------------------------------------------
# Prompt variants — kept in sync with probe_maiui.py.
# ---------------------------------------------------------------------------


def _data_url(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _content_with_image(image_bytes: bytes, text: str) -> list[dict]:
    return [
        {"type": "image_url", "image_url": {"url": _data_url(image_bytes)}},
        {"type": "text", "text": text},
    ]


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


_BARE_STYLE = """You are a GUI agent operating a computer.  Given a screenshot and an instruction, output the next action.  Coordinates must be normalized floats in [0, 1].

Instruction: {instruction}"""


_ASK_COORD_STYLE = (
    "Look at the screenshot.  The user wants to: {instruction}\n"
    "Respond with ONLY the click coordinates as a JSON object of the form "
    '{{"x": <float>, "y": <float>}} where x and y are normalized to the image '
    "width and height in the range [0, 1].  No explanation."
)


def _build_messages(template: str, image: bytes, goal: str) -> list[dict]:
    return [
        {"role": "user", "content": _content_with_image(image, template.format(instruction=goal))},
    ]


VARIANTS: dict[str, str] = {
    "a_uitars_style": _UITARS_STYLE,
    "b_bare": _BARE_STYLE,
    "c_ask_coord": _ASK_COORD_STYLE,
}


# ---------------------------------------------------------------------------
# HTTP call.
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


# ---------------------------------------------------------------------------
# Coordinate extraction — tolerant to several dialects.
# ---------------------------------------------------------------------------


# UI-TARS style: click(start_box='(123,456)')  OR  click(start_box='(0.42,0.68)')
_STARTBOX_RE = re.compile(r"start_box\s*=\s*['\"]?\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)?['\"]?")
# <point>123 456</point>  OR  <point>0.42 0.68</point>
_POINT_TAG_RE = re.compile(r"<point>\s*(-?\d*\.?\d+)[\s,]+(-?\d*\.?\d+)\s*</point>?", re.IGNORECASE)
# JSON: {"x": 0.42, "y": 0.68}  (allow single quotes)
_JSON_XY_RE = re.compile(
    r"[\"']x[\"']\s*:\s*(-?\d*\.?\d+)\s*,\s*[\"']y[\"']\s*:\s*(-?\d*\.?\d+)"
)
# Bare tuple in plain text: (0.42, 0.68) — used as last resort
_TUPLE_RE = re.compile(r"\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)")


def extract_xy(reply: str, image_size: tuple[int, int]) -> tuple[tuple[int, int], str] | None:
    """Try every regex in order, return (pixel_xy, how_we_found_it)."""
    w, h = image_size
    for name, pattern in (
        ("start_box", _STARTBOX_RE),
        ("point_tag", _POINT_TAG_RE),
        ("json_xy", _JSON_XY_RE),
        ("tuple", _TUPLE_RE),
    ):
        m = pattern.search(reply)
        if not m:
            continue
        x_raw, y_raw = float(m.group(1)), float(m.group(2))
        if 0.0 <= x_raw <= 1.0 and 0.0 <= y_raw <= 1.0:
            x, y = int(round(x_raw * w)), int(round(y_raw * h))
            kind = f"{name}/normalized"
        else:
            x, y = int(round(x_raw)), int(round(y_raw))
            kind = f"{name}/pixel"
        return (x, y), kind
    return None


# ---------------------------------------------------------------------------
# Annotation helper.
# ---------------------------------------------------------------------------


def annotate(image_png: bytes, xy: tuple[int, int], label: str, out_path: Path) -> None:
    img = Image.open(io.BytesIO(image_png)).convert("RGB")
    draw = ImageDraw.Draw(img)
    x, y = xy
    r = 24
    draw.line([(x - r, y), (x + r, y)], fill="red", width=4)
    draw.line([(x, y - r), (x, y + r)], fill="red", width=4)
    draw.ellipse([(x - 8, y - 8), (x + 8, y + 8)], outline="red", width=3)
    draw.text((x + 12, y + 12), f"{label} ({x},{y})", fill="red")
    img.save(out_path)


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="MAI-UI-2B calculator grounding probe")
    ap.add_argument(
        "--goal",
        default="点击计算器上的乘号（×）按钮。",
        help="Instruction for the model (default: click the × button).",
    )
    ap.add_argument("--endpoint", default="http://localhost:8001/v1")
    ap.add_argument("--model", default="mai-ui-2b")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument(
        "--no-launch",
        action="store_true",
        help="Skip `calc.exe` launch (use if calculator is already open).",
    )
    ap.add_argument(
        "--wait",
        type=float,
        default=4.0,
        help="Seconds to wait after launching calc.exe before capturing.",
    )
    ap.add_argument(
        "--countdown",
        type=int,
        default=10,
        help=(
            "Seconds of pre-capture countdown — use this window to Win+D so "
            "Cursor / IDE / terminal do not end up in the screenshot.  "
            "Set to 0 to disable."
        ),
    )
    ap.add_argument(
        "--variants",
        nargs="+",
        default=list(VARIANTS),
        choices=list(VARIANTS),
    )
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "data" / "probes" / f"maiui_calc_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[probe] goal      : {args.goal}")
    print(f"[probe] endpoint  : {args.endpoint}")
    print(f"[probe] model     : {args.model}")
    print(f"[probe] out_dir   : {out_dir}")

    # 1. Pre-capture countdown first — clean the desktop BEFORE launching
    # calc.exe, otherwise calc will get minimised together with Cursor when
    # the user hits Win+D.
    if args.countdown > 0:
        print()
        print(f"=== 倒计时 {args.countdown}s，请立刻 Win+D 把前台窗口全压下去 ===")
        print("    (倒计时结束后脚本会替你启动 calc.exe，不要自己开)")
        for remaining in range(args.countdown, 0, -1):
            print(f"  T-{remaining:02d}", flush=True)
            time.sleep(1)

    # 2. Launch calc.exe (so it comes up *after* the desktop has been
    # cleared and stays the only foreground window before capture).
    if not args.no_launch:
        print("[probe] launching calc.exe ...")
        try:
            subprocess.Popen(
                ["calc.exe"],
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                close_fds=True,
            )
        except FileNotFoundError:
            print("[probe] calc.exe not found on PATH — open it manually and rerun with --no-launch")
            return 3
        print(f"[probe] waiting {args.wait}s for calculator to render ...")
        time.sleep(args.wait)
    else:
        print("[probe] --no-launch: using current desktop state as-is")
    print("=== CAPTURE ===")

    # 3. Capture.
    from autovisiontest.control.screenshot import capture_primary_screen

    img_bytes = capture_primary_screen()
    shot_path = out_dir / "screen.png"
    shot_path.write_bytes(img_bytes)

    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    print(f"[probe] screenshot: {len(img_bytes)} bytes, size={img.size} -> {shot_path.name}")
    print()

    # 3 + 4 + 5. Call each variant, extract + annotate.
    summary: list[dict] = []
    failures: list[str] = []
    for name in args.variants:
        template = VARIANTS[name]
        messages = _build_messages(template, img_bytes, args.goal)
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

        extracted = extract_xy(reply, (w, h))
        if extracted is not None:
            xy, how = extracted
            print(f"extracted: {xy}  via {how}")
            annotated_path = out_dir / f"annotated_{name}.png"
            annotate(img_bytes, xy, name, annotated_path)
            print(f"annotated: {annotated_path.name}")
        else:
            xy, how = None, None
            print("extracted: <none> — no known coordinate pattern matched")

        print("-" * 72)
        print("reply    :")
        print(reply)
        print()

        (out_dir / f"reply_{name}.txt").write_text(reply, encoding="utf-8")
        (out_dir / f"raw_{name}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append(
            {
                "variant": name,
                "latency_ms": round(dt * 1000),
                "completion_tokens": usage.get("completion_tokens"),
                "extracted_xy": xy,
                "extractor": how,
                "reply_head": reply[:200],
            }
        )

    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "goal": args.goal,
                "endpoint": args.endpoint,
                "model": args.model,
                "image_size": [w, h],
                "variants": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 72)
    print(f"[probe] summary  : {out_dir / 'summary.json'}")
    print(f"[probe] artifacts: {out_dir}")
    if failures:
        print(f"[probe] failed variants: {failures}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
