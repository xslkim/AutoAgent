#!/usr/bin/env python3
"""Copy fonts into the three engine fixture font directories.

Uses Windows system fonts as substitutes (NotoSansSC, Arial, Consolas) renamed
to the canonical names expected by validate_static_fixtures.py. The user noted
fonts aren't strict — these substitutes load fine in all three engines.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIN_FONTS = Path("C:/Windows/Fonts")

ENGINE_FONT_DIRS = [
    ROOT / "fixtures/unity-test-project/Assets/Fonts",
    ROOT / "fixtures/unreal-test-project/Content/UI/Fonts",
    ROOT / "fixtures/godot-test-project/assets/fonts",
]

# target_name -> ordered list of source candidates (first found wins)
MAPPING = {
    "NotoSansCJK-Regular.otf": ["NotoSansSC-VF.ttf", "NotoSansCJK-Regular.otf", "msyh.ttc"],
    "Roboto-Regular.ttf": ["Roboto-Regular.ttf", "arial.ttf", "tahoma.ttf"],
    "RobotoMono-Regular.ttf": ["RobotoMono-Regular.ttf", "consola.ttf"],
}


def find_source(candidates):
    for name in candidates:
        path = WIN_FONTS / name
        if path.exists():
            return path
    return None


def main() -> int:
    misses = []
    for engine_dir in ENGINE_FONT_DIRS:
        engine_dir.mkdir(parents=True, exist_ok=True)
        for target_name, candidates in MAPPING.items():
            src = find_source(candidates)
            dst = engine_dir / target_name
            if src is None:
                misses.append(f"{engine_dir.relative_to(ROOT)} <- {target_name} (no candidate found)")
                continue
            shutil.copy2(src, dst)
            print(f"{engine_dir.relative_to(ROOT)} <- {target_name} (from {src.name})")
    if misses:
        print("\nMISSING:", file=sys.stderr)
        for m in misses:
            print(f"  {m}", file=sys.stderr)
        return 1
    print("\nFont substitutes installed in all 3 engine dirs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
