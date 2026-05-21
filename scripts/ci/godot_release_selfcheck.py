#!/usr/bin/env python3
"""Release export self-check for the AutoAgent Godot adapter (TASK-0304).

Verifies that the generated class_db_cache.gd contains the minimum set of
Godot Control classes required by ControlReflector at runtime.  Run this
as part of the release build pipeline to catch missing entries before shipping.

Usage
-----
    python scripts/build/godot_release_selfcheck.py
    python scripts/build/godot_release_selfcheck.py \\
        --cache adapters/godot/addons/autoagent/runtime/class_db_cache.gd

Exit codes
----------
    0 — cache is complete
    1 — one or more required classes are missing from the cache
    2 — cache file not found
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Minimum classes ControlReflector checks with `node is <ClassName>`.
REQUIRED_CLASSES: list[str] = [
    "Control",
    "BaseButton",
    "Button",
    "LineEdit",
    "TextEdit",
    "Label",
    "TextureRect",
    "CanvasLayer",
    "ScrollContainer",
]

_CLASS_LINE_RE = re.compile(r'^\s*"(\w+)",\s*$')


def parse_cache(cache_path: Path) -> set[str]:
    """Extract class names from the CACHED_CLASSES array in the .gd cache."""
    classes: set[str] = set()
    in_array = False
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if "CACHED_CLASSES" in line and "[" in line:
            in_array = True
        if in_array:
            m = _CLASS_LINE_RE.match(line)
            if m:
                classes.add(m.group(1))
            if "]" in line and "CACHED_CLASSES" not in line:
                break
    return classes


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="godot_release_selfcheck",
        description="Verify class_db_cache.gd completeness for release exports.",
    )
    p.add_argument(
        "--cache",
        type=Path,
        default=REPO_ROOT / "adapters" / "godot" / "addons" / "autoagent"
                 / "runtime" / "class_db_cache.gd",
        help="Path to the generated class_db_cache.gd (default: adapter runtime dir)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.cache.is_file():
        print(f"ERROR: cache not found: {args.cache}", file=sys.stderr)
        print(
            "  Run: python scripts/build/godot_cache_classdb.py", file=sys.stderr
        )
        return 2

    cached = parse_cache(args.cache)
    missing = [c for c in REQUIRED_CLASSES if c not in cached]

    if missing:
        print(f"FAIL — {len(missing)} required class(es) missing from cache:")
        for cls in missing:
            print(f"  • {cls}")
        print("\nRegenerate: python scripts/build/godot_cache_classdb.py")
        return 1

    print(
        f"OK — all {len(REQUIRED_CLASSES)} required classes present "
        f"({len(cached)} total in cache)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
