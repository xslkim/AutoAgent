"""Downscale-then-upscale precision probe.

Pipeline:
    original (1920×1080)
        → manual resize to 960×540  (fits pixel budget → backend sends as-is)
        → UI-TARS returns coords in 960×540 space
        → scale back ×2 → 1920×1080 screen coords
        → annotate original image

This lets us compare whether pre-scaling to an exact ÷2 resolution gives
better button-level accuracy than letting the backend scale 1920×1080
down to 1344×756 (its natural pixel-budget target).

Usage:
    python base_test/downscale_probe.py [screenshot] [--config CONFIG]

Defaults:
    screenshot : data/20260506_163541/step_0_before.png
    config     : config/model.yaml

Output (base_test/):
    downscale_result.png   — original (1920×1080) annotated with scaled-up coords
    downscale_sent.jpg     — 960×540 image actually sent to the model
    downscale_result.json  — full per-key results
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

_DEFAULT_SCREENSHOT = (
    _REPO_ROOT / "data" / "20260506_163541" / "step_0_before.png"
)
_OUT_DIR = Path(__file__).resolve().parent

# Target pre-scale resolution.
_PRESEND_W, _PRESEND_H = 960, 540

# Same button targets as calc_precision.py for a fair comparison.
_PROBE_TARGETS = [
    ("5",  "请只点击计算器键盘上的数字键「5」，不要点击其他任何按键。"),
    ("×",  "请只点击计算器键盘上的乘号键「×」（multiply），不要点击其他任何按键。"),
    ("7",  "请只点击计算器键盘上的数字键「7」，不要点击其他任何按键。"),
    ("=",  "请只点击计算器键盘上的等号键「=」，不要点击其他任何按键。"),
    ("CE", "请只点击计算器键盘上的「CE」清除键，不要点击其他任何按键。"),
]
_COLORS = ["#FF4444", "#44AAFF", "#44DD44", "#FFAA00", "#CC44FF"]


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _annotate_point(
    draw: ImageDraw.ImageDraw,
    x: int, y: int,
    label: str, color: str,
    img_w: int, img_h: int,
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
    parser = argparse.ArgumentParser(description="Downscale-then-upscale precision probe")
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

    # --- Load original and build the pre-scaled version ---
    orig_img = Image.open(screenshot_path).convert("RGB")
    orig_w, orig_h = orig_img.size

    pre_img = orig_img.resize((_PRESEND_W, _PRESEND_H), Image.Resampling.LANCZOS)
    pre_png = _to_png(pre_img)

    # Confirm backend won't resize further.
    _, chk_orig_w, chk_orig_h, chk_sent_w, chk_sent_h = _resize_for_uitars(pre_png)

    scale_x = orig_w / _PRESEND_W   # factor to map model coords → original pixels
    scale_y = orig_h / _PRESEND_H

    print(f"Original   : {orig_w}×{orig_h}")
    print(f"Pre-scaled : {_PRESEND_W}×{_PRESEND_H}  (÷{orig_w/_PRESEND_W:.2g} ×{orig_h/_PRESEND_H:.2g})")
    print(f"Backend sends at : {chk_sent_w}×{chk_sent_h}  "
          f"({'no resize' if chk_sent_w == _PRESEND_W else 'FURTHER RESIZE — check pixel budget'})")
    print(f"Upscale factor   : x={scale_x:.4f}  y={scale_y:.4f}")
    print(f"Probing {len(_PROBE_TARGETS)} targets...\n")

    # --- Canvases ---
    draw_orig = ImageDraw.Draw(orig_img)

    sent_img = pre_img.copy()
    draw_sent = ImageDraw.Draw(sent_img)

    results = []
    for (label, goal), color in zip(_PROBE_TARGETS, _COLORS):
        print(f"  [{label}]  {goal[:40]}...")
        try:
            decision = backend.decide(image_png=pre_png, goal=goal)
        except Exception as exc:
            print(f"        ERROR: {exc}")
            results.append({"label": label, "error": str(exc)})
            continue

        # Coords from backend are in pre-scaled (960×540) space.
        # decision.point_xy goes through _unscale_xy(x, y, 960, 540, 960, 540)
        # which is a no-op, so coords == raw model output in 960×540 pixels.
        model_x, model_y = decision.point_xy if decision.point_xy else (None, None)

        # Scale up to original resolution.
        if model_x is not None and model_y is not None:
            screen_x = round(model_x * scale_x)
            screen_y = round(model_y * scale_y)
        else:
            screen_x = screen_y = None

        print(f"        model=({model_x},{model_y}) → screen=({screen_x},{screen_y})")
        print(f"        raw='{decision.raw_response[:80].strip()}...'")
        if decision.parse_error:
            print(f"        parse_err={decision.parse_error}")
        print()

        results.append({
            "label": label,
            "goal": goal,
            "action_type": decision.action_type,
            "coords_model_960x540": [model_x, model_y] if model_x is not None else None,
            "coords_screen_original": [screen_x, screen_y] if screen_x is not None else None,
            "thought": decision.thought[:200],
            "raw_response": decision.raw_response,
            "parse_error": decision.parse_error,
        })

        if screen_x is not None:
            _annotate_point(draw_orig, screen_x, screen_y, label, color, orig_w, orig_h)
        if model_x is not None:
            _annotate_point(draw_sent, model_x, model_y, label, color, _PRESEND_W, _PRESEND_H)

    # Legend.
    try:
        font_lg = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font_lg = ImageFont.load_default()
    lx = 8
    for (lbl, _), col in zip(_PROBE_TARGETS, _COLORS):
        draw_orig.rectangle([lx - 2, 4, lx + 22, 24], fill=col)
        draw_orig.text((lx + 26, 4), lbl, fill="white", font=font_lg)
        lx += 70

    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    result_path = _OUT_DIR / "downscale_result.png"
    orig_img.save(result_path)
    print(f"Saved: {result_path}")

    sent_path = _OUT_DIR / "downscale_sent.jpg"
    sent_img.save(sent_path, quality=95)
    print(f"Saved: {sent_path}")

    json_path = _OUT_DIR / "downscale_result.json"
    json_path.write_text(
        json.dumps(
            {
                "screenshot": str(screenshot_path),
                "original_size": [orig_w, orig_h],
                "pre_scale_size": [_PRESEND_W, _PRESEND_H],
                "backend_sent_size": [chk_sent_w, chk_sent_h],
                "upscale_factor": [scale_x, scale_y],
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
