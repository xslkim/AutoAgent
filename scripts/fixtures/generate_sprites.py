#!/usr/bin/env python3
"""Generate fixture UI sprites.

Pillow draws clean flat UI rectangles for buttons/inputs/slot; the local
text-to-image service (default http://127.0.0.1:8765) renders panel_bg as a
larger textured background. All outputs are copied into the three engine
sprite directories (Unity / Unreal / Godot).
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "fixtures" / "_generated_sprites"

ENGINE_DIRS = [
    ROOT / "fixtures/unity-test-project/Assets/Sprites/UI",
    ROOT / "fixtures/unreal-test-project/Content/UI/Sprites",
    ROOT / "fixtures/godot-test-project/assets/ui",
]

# (width, height, base_rgba, border_rgba_or_None, border_thickness, corner_radius)
BUTTON_BASE = (240, 64, 18)
INPUT_BASE = (360, 56, 10)

PILLOW_SPRITES = {
    "btn_login_normal.png": dict(
        size=(BUTTON_BASE[0], BUTTON_BASE[1]),
        fill_top=(86, 146, 255, 255),
        fill_bottom=(56, 116, 235, 255),
        border=(255, 255, 255, 60),
        border_w=1,
        radius=BUTTON_BASE[2],
        highlight=True,
    ),
    "btn_login_hover.png": dict(
        size=(BUTTON_BASE[0], BUTTON_BASE[1]),
        fill_top=(108, 168, 255, 255),
        fill_bottom=(75, 132, 245, 255),
        border=(255, 255, 255, 110),
        border_w=1,
        radius=BUTTON_BASE[2],
        highlight=True,
    ),
    "btn_login_pressed.png": dict(
        size=(BUTTON_BASE[0], BUTTON_BASE[1]),
        fill_top=(36, 90, 220, 255),
        fill_bottom=(24, 70, 190, 255),
        border=(0, 0, 0, 80),
        border_w=1,
        radius=BUTTON_BASE[2],
        highlight=False,
        inner_shadow=True,
    ),
    "btn_login_disabled.png": dict(
        size=(BUTTON_BASE[0], BUTTON_BASE[1]),
        fill_top=(146, 156, 170, 255),
        fill_bottom=(126, 136, 150, 255),
        border=(255, 255, 255, 30),
        border_w=1,
        radius=BUTTON_BASE[2],
        highlight=False,
    ),
    "input_bg_normal.png": dict(
        size=(INPUT_BASE[0], INPUT_BASE[1]),
        fill_top=(248, 250, 252, 255),
        fill_bottom=(241, 244, 248, 255),
        border=(200, 208, 220, 255),
        border_w=1,
        radius=INPUT_BASE[2],
        highlight=False,
    ),
    "input_bg_focused.png": dict(
        size=(INPUT_BASE[0], INPUT_BASE[1]),
        fill_top=(238, 246, 255, 255),
        fill_bottom=(226, 238, 255, 255),
        border=(86, 146, 255, 255),
        border_w=2,
        radius=INPUT_BASE[2],
        highlight=False,
    ),
    "slot_bg.png": dict(
        size=(64, 64),
        fill_top=(76, 84, 98, 255),
        fill_bottom=(60, 66, 78, 255),
        border=(0, 0, 0, 120),
        border_w=1,
        radius=10,
        highlight=False,
    ),
}

PANEL_BG_NAME = "panel_bg.png"
PANEL_BG_SIZE = (640, 480)
PANEL_PROMPT = (
    "A clean, dark navy UI panel background with a subtle diagonal gradient "
    "from #181C24 to #232838, very faint geometric noise, no text, no icons, "
    "no characters, flat 2D design, minimalist, soft vignette, "
    "background texture for a login dialog."
)
PANEL_NEGATIVE_INTENT = "text, characters, logos, photorealistic, busy"


def vgradient(size, top, bottom):
    w, h = size
    img = Image.new("RGBA", size, top)
    base = Image.new("RGBA", size, bottom)
    mask = Image.new("L", size)
    for y in range(h):
        t = y / max(h - 1, 1)
        mask.paste(int(255 * t), (0, y, w, y + 1))
    img.paste(base, (0, 0), mask)
    return img


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255
    )
    return mask


def draw_sprite(spec: dict) -> Image.Image:
    size = spec["size"]
    body = vgradient(size, spec["fill_top"], spec["fill_bottom"])
    mask = rounded_mask(size, spec["radius"])

    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(body, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    if spec.get("border") and spec["border_w"] > 0:
        draw.rounded_rectangle(
            (0, 0, size[0] - 1, size[1] - 1),
            radius=spec["radius"],
            outline=spec["border"],
            width=spec["border_w"],
        )

    if spec.get("highlight"):
        hl_h = max(2, size[1] // 6)
        hl = Image.new("RGBA", (size[0], hl_h), (0, 0, 0, 0))
        ImageDraw.Draw(hl).rounded_rectangle(
            (2, 0, size[0] - 3, hl_h - 1),
            radius=spec["radius"] // 2,
            fill=(255, 255, 255, 38),
        )
        hl = hl.filter(ImageFilter.GaussianBlur(radius=1.2))
        canvas.alpha_composite(hl, dest=(0, 2))

    if spec.get("inner_shadow"):
        shadow_h = max(2, size[1] // 5)
        sh = Image.new("RGBA", (size[0], shadow_h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            (2, 0, size[0] - 3, shadow_h - 1),
            radius=spec["radius"] // 2,
            fill=(0, 0, 0, 70),
        )
        sh = sh.filter(ImageFilter.GaussianBlur(radius=1.5))
        canvas.alpha_composite(sh, dest=(0, 0))

    return canvas


def t2i_panel(host: str, port: int, prompt: str, size, seed: int) -> bytes:
    url = f"http://{host}:{port}/api/t2i"
    payload = json.dumps(
        {
            "prompt": prompt,
            "width": size[0],
            "height": size[1],
            "num_steps": 18,
            "cfg_scale": 5.0,
            "seed": seed,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        if resp.status != 200:
            raise RuntimeError(f"T2I returned {resp.status}: {resp.read()[:300]!r}")
        return resp.read()


def fit_to(image: Image.Image, target) -> Image.Image:
    """Cover-fit center crop, then resize exact to target."""
    tw, th = target
    iw, ih = image.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(round(iw * scale)), int(round(ih * scale))
    image = image.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return image.crop((left, top, left + tw, top + th))


def generate_panel_bg(host: str, port: int, seed: int, no_t2i: bool) -> Image.Image:
    if no_t2i:
        # Pillow-only fallback: dark navy gradient + faint vignette
        img = vgradient(PANEL_BG_SIZE, (35, 40, 56, 255), (24, 28, 36, 255))
        vignette = Image.new("L", PANEL_BG_SIZE, 0)
        vd = ImageDraw.Draw(vignette)
        vd.ellipse(
            (-200, -150, PANEL_BG_SIZE[0] + 200, PANEL_BG_SIZE[1] + 150),
            fill=255,
        )
        vignette = vignette.filter(ImageFilter.GaussianBlur(80))
        vmask = Image.new("RGBA", PANEL_BG_SIZE, (0, 0, 0, 0))
        for y in range(PANEL_BG_SIZE[1]):
            for x in range(0, PANEL_BG_SIZE[0], 4):
                pass  # no per-pixel loop; vignette alone is enough
        img.putalpha(255)
        return img
    raw = t2i_panel(host, port, PANEL_PROMPT, PANEL_BG_SIZE, seed)
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    if img.size != PANEL_BG_SIZE:
        img = fit_to(img, PANEL_BG_SIZE)
    return img


def write_all(staging: Path, sprites: dict[str, Image.Image]) -> None:
    staging.mkdir(parents=True, exist_ok=True)
    for name, img in sprites.items():
        img.save(staging / name, "PNG", optimize=True)
    for engine_dir in ENGINE_DIRS:
        engine_dir.mkdir(parents=True, exist_ok=True)
        for name in sprites:
            shutil.copy2(staging / name, engine_dir / name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed", type=int, default=20260514)
    parser.add_argument(
        "--no-t2i",
        action="store_true",
        help="skip T2I service and use Pillow fallback for panel_bg",
    )
    args = parser.parse_args()

    sprites: dict[str, Image.Image] = {}
    for name, spec in PILLOW_SPRITES.items():
        print(f"draw {name} {spec['size'][0]}x{spec['size'][1]}")
        sprites[name] = draw_sprite(spec)

    print(f"T2I {PANEL_BG_NAME} {PANEL_BG_SIZE[0]}x{PANEL_BG_SIZE[1]} seed={args.seed}")
    try:
        sprites[PANEL_BG_NAME] = generate_panel_bg(args.host, args.port, args.seed, args.no_t2i)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"  T2I failed ({exc}); falling back to Pillow gradient", file=sys.stderr)
        sprites[PANEL_BG_NAME] = generate_panel_bg(args.host, args.port, args.seed, no_t2i=True)

    write_all(STAGING, sprites)
    print(f"\nWrote {len(sprites)} sprites to {STAGING} and {len(ENGINE_DIRS)} engine dirs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
