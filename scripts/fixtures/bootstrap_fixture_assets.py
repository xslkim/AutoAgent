#!/usr/bin/env python3
"""Create fixture directory skeletons and placeholder UI PNG assets.

This script is intentionally engine-agnostic and uses only the Python standard
library so it can run before Unity / Unreal / Godot are installed.
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SPRITES = {
    "btn_login_normal.png": (56, 116, 255, 255),
    "btn_login_hover.png": (75, 132, 255, 255),
    "btn_login_pressed.png": (36, 90, 220, 255),
    "btn_login_disabled.png": (126, 136, 150, 255),
    "input_bg_normal.png": (245, 247, 250, 255),
    "input_bg_focused.png": (230, 240, 255, 255),
    "panel_bg.png": (24, 28, 36, 255),
    "slot_bg.png": (64, 70, 82, 255),
}


DIRS = [
    "fixtures/unity-test-project/Assets/Scenes",
    "fixtures/unity-test-project/Assets/Sprites/UI",
    "fixtures/unity-test-project/Assets/Fonts",
    "fixtures/unity-test-project/Packages",
    "fixtures/unity-test-project/ProjectSettings",
    "fixtures/unreal-test-project/Source/AutoAgentTest",
    "fixtures/unreal-test-project/Content/UI/Sprites",
    "fixtures/unreal-test-project/Content/UI/Fonts",
    "fixtures/unreal-test-project/Content/Maps",
    "fixtures/unreal-test-project/Config",
    "fixtures/godot-test-project/scenes",
    "fixtures/godot-test-project/assets/ui",
    "fixtures/godot-test-project/assets/fonts",
    "baselines/unity/windows",
    "baselines/unreal/windows",
    "baselines/godot/linux",
]


def png_bytes(width: int, height: int, rgba: tuple[int, int, int, int]) -> bytes:
    """Return a tiny RGBA PNG with a solid color."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    row = bytes(rgba) * width
    raw = b"".join(b"\x00" + row for _ in range(height))
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw, 9)),
            chunk(b"IEND", b""),
        ]
    )


def write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def bootstrap(overwrite: bool) -> None:
    for rel in DIRS:
        path = ROOT / rel
        path.mkdir(parents=True, exist_ok=True)
        write_text_if_missing(path / ".gitkeep", "")

    for engine_dir in [
        ROOT / "fixtures/unity-test-project/Assets/Sprites/UI",
        ROOT / "fixtures/unreal-test-project/Content/UI/Sprites",
        ROOT / "fixtures/godot-test-project/assets/ui",
    ]:
        for name, color in SPRITES.items():
            path = engine_dir / name
            if overwrite or not path.exists():
                path.write_bytes(png_bytes(64, 64, color))

    for font_dir in [
        ROOT / "fixtures/unity-test-project/Assets/Fonts",
        ROOT / "fixtures/unreal-test-project/Content/UI/Fonts",
        ROOT / "fixtures/godot-test-project/assets/fonts",
    ]:
        write_text_if_missing(
            font_dir / "README.md",
            "Place real fonts here before baseline capture:\n"
            "- NotoSansCJK-Regular.otf\n"
            "- Roboto-Regular.ttf\n"
            "- RobotoMono-Regular.ttf\n",
        )

    manifest = {
        "generated_by": "scripts/fixtures/bootstrap_fixture_assets.py",
        "required_fonts": [
            "NotoSansCJK-Regular.otf",
            "Roboto-Regular.ttf",
            "RobotoMono-Regular.ttf",
        ],
        "placeholder_sprites": sorted(SPRITES),
    }
    manifest_path = ROOT / "fixtures/fixture-assets.json"
    if overwrite or not manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true", help="rewrite placeholder PNG assets")
    args = parser.parse_args()
    bootstrap(overwrite=args.overwrite)
    print("Fixture directories and placeholder sprites are ready.")
    print("Replace placeholder art/fonts before final baseline capture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
