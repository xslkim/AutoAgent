"""Smoke-test the UI-TARS-1.5-7B vLLM service end-to-end.

Usage::

    # Screenshot the primary display and send to localhost:8000.
    python scripts/probe_uitars.py --goal "点击任务栏上的搜索按钮"

    # Use a pre-captured screenshot instead.
    python scripts/probe_uitars.py --image path/to/shot.png --goal "..."

The script prints:
    - the raw assistant reply (Thought + Action),
    - the parsed action type / coordinates / params,
    - the round-trip latency.

If ``--annotate out.png`` is given and the action includes a point, the
image is saved with a crosshair at the predicted coordinates so you can
eye-ball whether grounding is accurate.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from autovisiontest.backends.uitars import UITarsBackend  # noqa: E402


def _load_image(image_path: str | None) -> bytes:
    if image_path:
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(p)
        return p.read_bytes()
    from autovisiontest.control.screenshot import capture_primary_screen

    return capture_primary_screen()


def _annotate(image_png: bytes, xy: tuple[int, int], out_path: str) -> None:
    """Draw a crosshair + label at ``xy`` and save the annotated image."""
    from PIL import Image, ImageDraw
    import io

    img = Image.open(io.BytesIO(image_png)).convert("RGB")
    draw = ImageDraw.Draw(img)
    x, y = xy
    r = 20
    draw.line([(x - r, y), (x + r, y)], fill="red", width=3)
    draw.line([(x, y - r), (x, y + r)], fill="red", width=3)
    draw.ellipse([(x - 6, y - 6), (x + 6, y + 6)], outline="red", width=2)
    draw.text((x + 10, y + 10), f"({x},{y})", fill="red")
    img.save(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="UI-TARS smoke probe")
    ap.add_argument(
        "--goal",
        default="点击任务栏最左边的 Windows 开始按钮。",
        help="Natural-language instruction for the agent.",
    )
    ap.add_argument("--image", default=None, help="Path to a PNG screenshot; omit to grab the desktop.")
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="ui-tars-1.5-7b")
    ap.add_argument("--language", default="Chinese", choices=["Chinese", "English"])
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--annotate", default=None, help="Save annotated screenshot to this path.")
    args = ap.parse_args()

    print(f"[probe] goal      = {args.goal}")
    print(f"[probe] endpoint  = {args.endpoint}")
    print(f"[probe] model     = {args.model}")

    img_bytes = _load_image(args.image)
    print(f"[probe] image     = {len(img_bytes)} bytes ({'file' if args.image else 'screenshot'})")

    backend = UITarsBackend(
        model=args.model,
        endpoint=args.endpoint,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        language=args.language,
    )

    t0 = time.monotonic()
    decision = backend.decide(img_bytes, goal=args.goal)
    dt = time.monotonic() - t0

    print()
    print("=" * 60)
    print(f"latency       : {dt*1000:.0f} ms")
    print(f"action_type   : {decision.action_type}")
    print(f"point_xy      : {decision.point_xy}")
    print(f"end_point_xy  : {decision.end_point_xy}")
    print(f"action_params : {decision.action_params}")
    print(f"finished      : {decision.finished}")
    if decision.parse_error:
        print(f"parse_error   : {decision.parse_error}")
    print("-" * 60)
    print("thought       :")
    print(decision.thought or "(empty)")
    print("-" * 60)
    print("raw response  :")
    print(decision.raw_response[:2000])
    print("=" * 60)

    if args.annotate and decision.point_xy:
        _annotate(img_bytes, decision.point_xy, args.annotate)
        print(f"[probe] annotated screenshot saved to {args.annotate}")

    return 0 if decision.parse_error is None else 2


if __name__ == "__main__":
    sys.exit(main())
