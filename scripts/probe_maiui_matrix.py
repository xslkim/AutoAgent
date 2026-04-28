"""Diagnostic matrix: run MAI-UI-2B over a fixed screenshot with many goals.

We use this when a single-goal probe shows a mis-grounding and we need to
know *whether the failure is class-specific*.  By firing several goals
(digits / operators / text labels / different columns) at the **same**
screenshot we separate three failure modes:

* Symbol-only: digit/text goals succeed, ``×`` fails.
* All-operators: every operator column-4 target fails.
* Column-4 bias: both operator and non-operator targets in column 4 fail.

Only variant A (UI-TARS-style prompt, the one we plan to use in production)
is exercised here — the other variants were only for dialect discovery.

Usage::

    # Reuse the screenshot captured by probe_maiui_calc.py
    python scripts/probe_maiui_matrix.py \
        --image data\\probes\\maiui_calc_20260420_003406\\screen.png

    # Or capture a fresh one (countdown + optional calc launch handled)
    python scripts/probe_maiui_matrix.py

Default goal set is the Windows-Calculator diagnostic matrix.  Override
with ``--goals "a" "b" ...`` if you want a custom list.
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


# --- Prompt (variant A only — UI-TARS style) -------------------------------


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


_DEFAULT_GOALS = [
    "点击数字按钮 8。",
    "点击数字按钮 9。",
    "点击乘号（×）按钮。",
    "点击除号（÷）按钮。",
    "点击减号（−）按钮。",
    "点击清除按钮 CE。",
]


def _data_url(image_bytes: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _build_messages(image: bytes, goal: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _data_url(image)}},
                {"type": "text", "text": _UITARS_STYLE.format(instruction=goal)},
            ],
        }
    ]


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


# --- Coord extraction — tolerant, same as probe_maiui_calc -----------------


_STARTBOX_RE = re.compile(r"start_box\s*=\s*['\"]?\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)?['\"]?")
_POINT_TAG_RE = re.compile(r"<point>\s*(-?\d*\.?\d+)[\s,]+(-?\d*\.?\d+)\s*</point>?", re.IGNORECASE)
_BBOX_RE = re.compile(
    r"\[\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\]"
)
_TUPLE_RE = re.compile(r"\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)")


def extract_xy(
    reply: str,
    image_size: tuple[int, int],
    coord_space: str = "pixel",
) -> tuple[tuple[int, int], str] | None:
    """Pull the first coordinate we can find from ``reply``.

    ``coord_space`` decides how we interpret the raw numbers:

    * ``"pixel"`` — numbers are pixel coords in the original image, unless
      both fall in [0, 1] in which case we treat them as [0, 1] normalised.
    * ``"norm1000"`` — numbers are in a virtual [0, 1000] canvas per axis
      (Qwen-VL / MAI-UI training convention).  Rescale by
      ``(w, h) / 1000`` to recover true pixel coords.
    """
    w, h = image_size
    m = _STARTBOX_RE.search(reply)
    if m:
        x_raw, y_raw = float(m.group(1)), float(m.group(2))
        return _normalise_xy(x_raw, y_raw, w, h, "start_box", coord_space)
    m = _POINT_TAG_RE.search(reply)
    if m:
        x_raw, y_raw = float(m.group(1)), float(m.group(2))
        return _normalise_xy(x_raw, y_raw, w, h, "point_tag", coord_space)
    m = _BBOX_RE.search(reply)
    if m:
        x1, y1, x2, y2 = (float(g) for g in m.groups())
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        return _normalise_xy(cx, cy, w, h, "bbox_center", coord_space)
    m = _TUPLE_RE.search(reply)
    if m:
        x_raw, y_raw = float(m.group(1)), float(m.group(2))
        return _normalise_xy(x_raw, y_raw, w, h, "tuple", coord_space)
    return None


def _normalise_xy(
    x_raw: float,
    y_raw: float,
    w: int,
    h: int,
    tag: str,
    coord_space: str,
) -> tuple[tuple[int, int], str]:
    if coord_space == "norm1000":
        return (
            (int(round(x_raw * w / 1000.0)), int(round(y_raw * h / 1000.0))),
            f"{tag}/norm1000",
        )
    # coord_space == "pixel": auto-detect [0,1] normalisation on the fly.
    if 0.0 <= x_raw <= 1.0 and 0.0 <= y_raw <= 1.0:
        return (int(round(x_raw * w)), int(round(y_raw * h))), f"{tag}/normalized"
    return (int(round(x_raw)), int(round(y_raw))), f"{tag}/pixel"


# --- Annotation ------------------------------------------------------------


_PALETTE = [
    "red",
    "blue",
    "green",
    "orange",
    "purple",
    "brown",
    "magenta",
    "darkcyan",
]


def annotate_all(image_png: bytes, hits: list[dict], out_path: Path) -> None:
    """Draw every successful hit on a single combined image."""
    img = Image.open(io.BytesIO(image_png)).convert("RGB")
    draw = ImageDraw.Draw(img)
    for i, h in enumerate(hits):
        xy = h.get("xy")
        if not xy:
            continue
        color = _PALETTE[i % len(_PALETTE)]
        x, y = xy
        r = 20
        draw.line([(x - r, y), (x + r, y)], fill=color, width=4)
        draw.line([(x, y - r), (x, y + r)], fill=color, width=4)
        draw.ellipse([(x - 7, y - 7), (x + 7, y + 7)], outline=color, width=3)
        draw.text((x + 10, y + 10), f"#{i} {h['goal_short']} ({x},{y})", fill=color)
    img.save(out_path)


def annotate_single(image_png: bytes, xy: tuple[int, int], label: str, out_path: Path) -> None:
    img = Image.open(io.BytesIO(image_png)).convert("RGB")
    draw = ImageDraw.Draw(img)
    x, y = xy
    r = 24
    draw.line([(x - r, y), (x + r, y)], fill="red", width=4)
    draw.line([(x, y - r), (x, y + r)], fill="red", width=4)
    draw.ellipse([(x - 8, y - 8), (x + 8, y + 8)], outline="red", width=3)
    draw.text((x + 12, y + 12), f"{label} ({x},{y})", fill="red")
    img.save(out_path)


# --- Main ------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="MAI-UI-2B grounding matrix probe")
    ap.add_argument(
        "--image",
        default=None,
        help="Path to an existing PNG; omit to capture a fresh desktop screenshot.",
    )
    ap.add_argument(
        "--goals",
        nargs="+",
        default=_DEFAULT_GOALS,
        help="List of goals to test on the same screenshot.",
    )
    ap.add_argument("--endpoint", default="http://localhost:8001/v1")
    ap.add_argument("--model", default="mai-ui-2b")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument(
        "--coord-space",
        choices=["pixel", "norm1000"],
        default="norm1000",
        help=(
            "How to interpret raw coordinates in the model reply.  "
            "MAI-UI / Qwen-VL outputs in the [0, 1000] virtual canvas — "
            "leave this as the default unless you know otherwise."
        ),
    )
    ap.add_argument("--out-dir", default=None)
    # Capture-only options (used when --image is not provided).
    ap.add_argument(
        "--no-launch",
        action="store_true",
        help="When capturing fresh, skip calc.exe launch.",
    )
    ap.add_argument(
        "--countdown",
        type=int,
        default=10,
        help="Fresh-capture countdown before screenshot (0 to disable).",
    )
    ap.add_argument(
        "--wait",
        type=float,
        default=4.0,
        help="Fresh-capture: seconds to wait after launching calc.exe.",
    )
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "data" / "probes" / f"maiui_matrix_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[matrix] endpoint : {args.endpoint}")
    print(f"[matrix] model    : {args.model}")
    print(f"[matrix] goals    : {len(args.goals)}")
    print(f"[matrix] out_dir  : {out_dir}")

    # --- Obtain the screenshot --------------------------------------------
    if args.image:
        img_path = Path(args.image)
        if not img_path.exists():
            print(f"[matrix] image not found: {img_path}")
            return 3
        img_bytes = img_path.read_bytes()
        print(f"[matrix] reusing  : {img_path}")
    else:
        if args.countdown > 0:
            print()
            print(f"=== 倒计时 {args.countdown}s，请立刻 Win+D 清前台 ===")
            for remaining in range(args.countdown, 0, -1):
                print(f"  T-{remaining:02d}", flush=True)
                time.sleep(1)
        if not args.no_launch:
            print("[matrix] launching calc.exe ...")
            try:
                subprocess.Popen(
                    ["calc.exe"],
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                    close_fds=True,
                )
            except FileNotFoundError:
                print("[matrix] calc.exe not found — open it manually and rerun with --no-launch")
                return 3
            print(f"[matrix] waiting {args.wait}s for calc to render ...")
            time.sleep(args.wait)
        print("=== CAPTURE ===")
        from autovisiontest.control.screenshot import capture_primary_screen

        img_bytes = capture_primary_screen()

    shot_path = out_dir / "screen.png"
    shot_path.write_bytes(img_bytes)
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    print(f"[matrix] shot     : {len(img_bytes)} bytes, size={img.size} -> {shot_path.name}")
    print()

    # --- Run each goal ----------------------------------------------------
    hits: list[dict] = []
    for idx, goal in enumerate(args.goals):
        short = goal.strip().split("。")[0][:16]
        print("=" * 72)
        print(f"[goal #{idx}] {goal}")
        print("-" * 72)
        try:
            raw, dt = _call(args.endpoint, args.model, _build_messages(img_bytes, goal), args.max_tokens, args.temperature)
        except requests.HTTPError as exc:
            err = f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
            print(f"[error] {err}")
            (out_dir / f"goal_{idx:02d}.err.txt").write_text(err, encoding="utf-8")
            hits.append({"idx": idx, "goal": goal, "goal_short": short, "xy": None, "error": err})
            continue

        reply = _extract_reply(raw)
        usage = raw.get("usage", {})
        extracted = extract_xy(reply, (w, h), coord_space=args.coord_space)
        if extracted is not None:
            xy, how = extracted
            print(f"latency  : {dt*1000:.0f} ms  |  completion_tokens={usage.get('completion_tokens')}")
            print(f"extracted: {xy}  via {how}")
            annotate_single(img_bytes, xy, f"#{idx} {short}", out_dir / f"goal_{idx:02d}.png")
        else:
            xy, how = None, None
            print(f"latency  : {dt*1000:.0f} ms  |  completion_tokens={usage.get('completion_tokens')}")
            print("extracted: <none>")
        print("-" * 72)
        print("reply    :")
        print(reply)
        print()

        (out_dir / f"goal_{idx:02d}.reply.txt").write_text(reply, encoding="utf-8")
        hits.append(
            {
                "idx": idx,
                "goal": goal,
                "goal_short": short,
                "latency_ms": round(dt * 1000),
                "completion_tokens": usage.get("completion_tokens"),
                "xy": list(xy) if xy else None,
                "extractor": how,
                "reply_head": reply[:200],
            }
        )

    # --- Summary ----------------------------------------------------------
    combined_path = out_dir / "all_hits.png"
    annotate_all(img_bytes, hits, combined_path)
    print("=" * 72)
    print(f"[matrix] combined annotations: {combined_path}")

    summary = {
        "endpoint": args.endpoint,
        "model": args.model,
        "image_size": [w, h],
        "goals": hits,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[matrix] summary  : {out_dir / 'summary.json'}")

    failures = [h for h in hits if h.get("xy") is None]
    if failures:
        print(f"[matrix] parse-failed goals: {[h['idx'] for h in failures]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
