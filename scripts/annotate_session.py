"""Annotate a completed session's screenshots with the agent's predicted clicks.

For every step in ``data/sessions/<session_id>/context.json``:

* load ``data/evidence/<session_id>/step_<idx>_before.png``
* draw a red crosshair at the action's ``(x, y)`` (if the action is spatial),
* overlay a short header with step index / action / thought snippet,
* save the result to ``data/evidence/<session_id>/annotated/step_<idx>.png``.

Usage::

    python scripts/annotate_session.py 8fbddc2a426c
    python scripts/annotate_session.py 8fbddc2a426c --data-dir .\\data

Exits 0 if any annotations were written, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

_SPATIAL_ACTIONS = {"click", "double_click", "right_click", "scroll", "drag"}


def _load_font(size: int = 22) -> ImageFont.ImageFont:
    """Try a CJK-capable TrueType font; fall back to PIL's default bitmap."""
    for candidate in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_crosshair(draw: ImageDraw.ImageDraw, xy: tuple[int, int], label: str) -> None:
    x, y = xy
    r = 24
    draw.line([(x - r, y), (x + r, y)], fill="red", width=3)
    draw.line([(x, y - r), (x, y + r)], fill="red", width=3)
    draw.ellipse([(x - 7, y - 7), (x + 7, y + 7)], outline="red", width=3)
    draw.text((x + 12, y + 12), label, fill="red")


def _draw_header(
    draw: ImageDraw.ImageDraw,
    image_w: int,
    lines: list[str],
    font: ImageFont.ImageFont,
) -> None:
    """Translucent banner at the top with the step's intent."""
    padding = 10
    line_h = 28
    box_h = padding * 2 + line_h * len(lines)
    draw.rectangle([(0, 0), (image_w, box_h)], fill=(0, 0, 0, 180))
    for i, text in enumerate(lines):
        draw.text((padding, padding + i * line_h), text, fill="white", font=font)


def _annotate_one(
    step: dict[str, Any],
    before_path: Path,
    out_path: Path,
    font: ImageFont.ImageFont,
) -> bool:
    if not before_path.exists():
        print(f"[skip] step {step.get('idx')}: {before_path.name} missing", file=sys.stderr)
        return False

    img = Image.open(before_path).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    action = step.get("action") or {}
    params = action.get("params") or {}
    a_type = action.get("type", "?")

    # Header
    idx = step.get("idx")
    intent = (step.get("planner_intent") or "").replace("\n", " ")
    target = step.get("actor_target_desc", "")
    header = [
        f"[step {idx}] {a_type}  ←  {target}",
        f"thought: {intent[:120]}{'…' if len(intent) > 120 else ''}",
    ]
    _draw_header(draw, img.width, header, font=font)

    # Crosshair
    wrote_xhair = False
    if a_type in _SPATIAL_ACTIONS and "x" in params and "y" in params:
        xy = (int(params["x"]), int(params["y"]))
        _draw_crosshair(draw, xy, f"(x={xy[0]},y={xy[1]})")
        wrote_xhair = True
        if a_type == "drag" and "to_x" in params and "to_y" in params:
            end_xy = (int(params["to_x"]), int(params["to_y"]))
            _draw_crosshair(draw, end_xy, f"→ ({end_xy[0]},{end_xy[1]})")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    marker = "X" if wrote_xhair else "·"
    print(f"  {marker} step {idx:>2}  {a_type:<12} → {out_path.name}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Annotate a session's screenshots")
    ap.add_argument("session_id", help="Session ID (folder name under data/sessions/)")
    ap.add_argument("--data-dir", default="./data", help="Root data directory (default ./data)")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    ctx_path = data_dir / "sessions" / args.session_id / "context.json"
    evidence_dir = data_dir / "evidence" / args.session_id
    out_dir = evidence_dir / "annotated"

    if not ctx_path.exists():
        print(f"ERROR: session context not found: {ctx_path}", file=sys.stderr)
        return 1
    if not evidence_dir.exists():
        print(f"ERROR: evidence dir not found: {evidence_dir}", file=sys.stderr)
        return 1

    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    steps = ctx.get("steps", [])
    if not steps:
        print("ERROR: session has no steps", file=sys.stderr)
        return 1

    font = _load_font()
    print(f"session: {args.session_id}  goal={ctx.get('goal', '')[:60]}…")
    print(f"output : {out_dir}")

    written = 0
    for step in steps:
        idx = step.get("idx")
        before = evidence_dir / f"step_{idx}_before.png"
        out = out_dir / f"step_{idx}.png"
        if _annotate_one(step, before, out, font=font):
            written += 1

    print(f"\ndone — {written}/{len(steps)} frames annotated → {out_dir}")
    return 0 if written > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
