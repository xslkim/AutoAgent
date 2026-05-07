"""Minimal grounding probe — send a screenshot to UI-TARS and visualise the click coordinates.

Usage:
    python base_test/grounding_probe.py [screenshot] [--goal GOAL] [--config CONFIG]

Defaults:
    screenshot : data/20260506_163541/step_0_before.png
    config     : config/model.yaml
    goal       : 请点击数字键 5

Output (written to base_test/):
    probe_result.png   — original screenshot annotated with the returned click point
    probe_sent.jpg     — image actually sent to the model (after resize)
    probe_result.json  — raw response, parsed coords, scaling info
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # type: ignore

from autovisiontest.backends.uitars import (
    UITarsBackend,
    _resize_for_uitars,
    _unscale_xy,
)
from autovisiontest.config.loader import load_config

_DEFAULT_SCREENSHOT = (
    _REPO_ROOT / "data" / "20260506_163541" / "step_0_before.png"
)
_DEFAULT_GOAL = "请点击计算器上的数字键 5"
_OUT_DIR = Path(__file__).resolve().parent


def _annotate(img: Image.Image, x: int, y: int, label: str, color: str = "red") -> Image.Image:
    """Draw a crosshair + label on a copy of img."""
    out = img.copy().convert("RGB")
    draw = ImageDraw.Draw(out)
    r = max(12, min(img.width, img.height) // 60)
    draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=3)
    draw.line([x - r * 2, y, x + r * 2, y], fill=color, width=2)
    draw.line([x, y - r * 2, x, y + r * 2], fill=color, width=2)
    try:
        font = ImageFont.truetype("arial.ttf", max(16, r))
    except OSError:
        font = ImageFont.load_default()
    draw.text((x + r + 4, y - r), label, fill=color, font=font)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="UI-TARS grounding probe")
    parser.add_argument("screenshot", nargs="?", default=str(_DEFAULT_SCREENSHOT))
    parser.add_argument("--goal", default=_DEFAULT_GOAL)
    parser.add_argument("--config", default=str(_REPO_ROOT / "config" / "model.yaml"))
    args = parser.parse_args()

    screenshot_path = Path(args.screenshot)
    if not screenshot_path.exists():
        print(f"ERROR: screenshot not found: {screenshot_path}")
        sys.exit(1)

    # Load backend config.
    cfg = load_config(Path(args.config))
    agent_cfg = cfg.agent
    backend = UITarsBackend(
        model=agent_cfg.model,
        endpoint=agent_cfg.endpoint,
        max_tokens=agent_cfg.max_tokens,
        temperature=agent_cfg.temperature,
        language=agent_cfg.language,
    )

    image_png = screenshot_path.read_bytes()

    # Get resize info (same path as the real backend).
    _, orig_w, orig_h, sent_w, sent_h = _resize_for_uitars(image_png)
    print(f"Original  : {orig_w}×{orig_h}")
    print(f"Sent      : {sent_w}×{sent_h}")
    print(f"Scale     : x={orig_w/sent_w:.4f}  y={orig_h/sent_h:.4f}")
    print(f"Goal      : {args.goal}\n")

    # Call the model.
    print("Calling UI-TARS backend...")
    decision = backend.decide(image_png=image_png, goal=args.goal)

    print(f"\n--- Raw response ---\n{decision.raw_response}\n")
    print(f"Action    : {decision.action_type}")
    print(f"Coords    : {decision.point_xy}  (screen pixels)")
    if decision.parse_error:
        print(f"Parse err : {decision.parse_error}")

    # Save annotated images.
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Annotate original resolution image.
    orig_img = Image.open(screenshot_path)
    if decision.point_xy:
        sx, sy = decision.point_xy
        label = f"({sx},{sy})"
        annotated = _annotate(orig_img, sx, sy, label)
    else:
        annotated = orig_img.convert("RGB")
    result_path = _OUT_DIR / "probe_result.png"
    annotated.save(result_path)
    print(f"\nSaved: {result_path}")

    # 2. Save the resized image actually sent to the model.
    sent_bytes, *_ = _resize_for_uitars(image_png)
    import io
    sent_img = Image.open(io.BytesIO(sent_bytes))
    if decision.point_xy:
        # Map screen coords back to sent-image coords for the sent view.
        sx, sy = decision.point_xy
        sx_sent = round(sx * sent_w / orig_w)
        sy_sent = round(sy * sent_h / orig_h)
        sent_annotated = _annotate(sent_img, sx_sent, sy_sent, f"({sx_sent},{sy_sent})", color="lime")
    else:
        sent_annotated = sent_img
    sent_path = _OUT_DIR / "probe_sent.jpg"
    sent_annotated.save(sent_path)
    print(f"Saved: {sent_path}")

    # 3. Save JSON summary.
    summary = {
        "screenshot": str(screenshot_path),
        "goal": args.goal,
        "orig_size": [orig_w, orig_h],
        "sent_size": [sent_w, sent_h],
        "action_type": decision.action_type,
        "coords_screen": list(decision.point_xy) if decision.point_xy else None,
        "thought": decision.thought,
        "raw_response": decision.raw_response,
        "parse_error": decision.parse_error,
    }
    json_path = _OUT_DIR / "probe_result.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
