"""Calculator button precision test — probe multiple keys on one screenshot.

Sends the same screenshot to UI-TARS multiple times, each time asking to click
a specific calculator button.  All returned coordinates are drawn on a single
annotated image so you can visually verify accuracy and compare backends.

Usage:
    python base_test/calc_precision.py [screenshot] [--config CONFIG]

Defaults:
    screenshot : base_test/computer_720.png
    config     : config/model.yaml

Output (written to base_test/):
    calc_precision_result.png   — screenshot annotated with all predicted clicks
    calc_precision_sent.jpg     — image as sent to the model (after resize)
    calc_precision_result.json  — per-key results with raw response and coords
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # type: ignore

from autovisiontest.backends.uitars import UITarsBackend, _resize_for_uitars
from autovisiontest.config.loader import load_config

_DEFAULT_SCREENSHOT = Path(__file__).resolve().parent / "computer_720.png"
_OUT_DIR = Path(__file__).resolve().parent

# Each entry: (label, goal)
# Goals are tightly scoped so the model focuses on one button at a time.
_PROBE_TARGETS = [
    ("5",  "请只点击计算器键盘上的数字键「5」，不要点击其他任何按键。"),
    ("×",  "请只点击计算器键盘上的乘号键「×」（multiply），不要点击其他任何按键。"),
    ("7",  "请只点击计算器键盘上的数字键「7」，不要点击其他任何按键。"),
    ("=",  "请只点击计算器键盘上的等号键「=」，不要点击其他任何按键。"),
    ("CE", "请只点击计算器键盘上的「CE」清除键，不要点击其他任何按键。"),
]

# Colours assigned to each target in order.
_COLORS = ["#FF4444", "#44AAFF", "#44DD44", "#FFAA00", "#CC44FF"]


def _annotate_point(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    color: str,
    img_w: int,
    img_h: int,
) -> None:
    r = max(10, min(img_w, img_h) // 55)
    draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=3)
    draw.line([x - r * 2, y, x + r * 2, y], fill=color, width=2)
    draw.line([x, y - r * 2, x, y + r * 2], fill=color, width=2)
    try:
        font = ImageFont.truetype("arial.ttf", max(14, r + 2))
    except OSError:
        font = ImageFont.load_default()
    draw.text((x + r + 4, y - r), label, fill=color, font=font)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculator button precision test")
    parser.add_argument("screenshot", nargs="?", default=str(_DEFAULT_SCREENSHOT))
    parser.add_argument("--config", default=str(_REPO_ROOT / "config" / "model.yaml"))
    args = parser.parse_args()

    screenshot_path = Path(args.screenshot)
    if not screenshot_path.exists():
        print(f"ERROR: screenshot not found: {screenshot_path}")
        sys.exit(1)

    cfg = load_config(Path(args.config))
    acfg = cfg.agent
    backend = UITarsBackend(
        model=acfg.model,
        endpoint=acfg.endpoint,
        max_tokens=acfg.max_tokens,
        temperature=acfg.temperature,
        language=acfg.language,
    )

    image_png = screenshot_path.read_bytes()
    _, orig_w, orig_h, sent_w, sent_h = _resize_for_uitars(image_png)

    print(f"Screenshot : {screenshot_path.name}")
    print(f"Original   : {orig_w}×{orig_h}")
    print(f"Sent       : {sent_w}×{sent_h}  (scale x={orig_w/sent_w:.3f} y={orig_h/sent_h:.3f})")
    print(f"Probing {len(_PROBE_TARGETS)} targets...\n")

    # Prepare canvases.
    orig_img = Image.open(screenshot_path).convert("RGB")
    draw_orig = ImageDraw.Draw(orig_img)

    sent_bytes, *_ = _resize_for_uitars(image_png)
    sent_img = Image.open(io.BytesIO(sent_bytes)).convert("RGB")
    draw_sent = ImageDraw.Draw(sent_img)

    results = []
    for (label, goal), color in zip(_PROBE_TARGETS, _COLORS):
        print(f"  [{label}]  {goal[:40]}...")
        try:
            decision = backend.decide(image_png=image_png, goal=goal)
        except Exception as exc:
            print(f"        ERROR: {exc}")
            results.append({"label": label, "goal": goal, "error": str(exc)})
            continue

        sx, sy = decision.point_xy if decision.point_xy else (None, None)
        print(f"        raw='{decision.raw_response[:80].strip()}...'")
        print(f"        coords={decision.point_xy}  parse_err={decision.parse_error}\n")

        entry = {
            "label": label,
            "goal": goal,
            "action_type": decision.action_type,
            "coords_screen": [sx, sy] if sx is not None else None,
            "thought": decision.thought[:200],
            "raw_response": decision.raw_response,
            "parse_error": decision.parse_error,
        }
        results.append(entry)

        if sx is not None and sy is not None:
            _annotate_point(draw_orig, sx, sy, label, color, orig_w, orig_h)
            sx_s = round(sx * sent_w / orig_w)
            sy_s = round(sy * sent_h / orig_h)
            _annotate_point(draw_sent, sx_s, sy_s, label, color, sent_w, sent_h)

    # Legend strip at top of original image.
    try:
        font_lg = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font_lg = ImageFont.load_default()
    legend_x = 8
    for (label, _), color in zip(_PROBE_TARGETS, _COLORS):
        draw_orig.rectangle([legend_x - 2, 4, legend_x + 22, 24], fill=color)
        draw_orig.text((legend_x + 26, 4), label, fill="white", font=font_lg)
        legend_x += 70

    # Save outputs.
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    result_path = _OUT_DIR / "calc_precision_result.png"
    orig_img.save(result_path)
    print(f"Saved: {result_path}")

    sent_path = _OUT_DIR / "calc_precision_sent.jpg"
    sent_img.save(sent_path)
    print(f"Saved: {sent_path}")

    json_path = _OUT_DIR / "calc_precision_result.json"
    json_path.write_text(
        json.dumps(
            {
                "screenshot": str(screenshot_path),
                "orig_size": [orig_w, orig_h],
                "sent_size": [sent_w, sent_h],
                "targets": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
