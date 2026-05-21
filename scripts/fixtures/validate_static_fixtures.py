#!/usr/bin/env python3
"""Validate manually-created static fixture scenes before running engine CI."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    ok: bool
    message: str


def exists(rel: str) -> CheckResult:
    path = ROOT / rel
    return CheckResult(path.exists(), f"{'OK' if path.exists() else 'MISSING'} {rel}")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def check_text_absent(rel_glob: str, pattern: str, label: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    regex = re.compile(pattern)
    paths = sorted(path for path in ROOT.glob(rel_glob) if path.is_file())
    if not paths:
        return [CheckResult(False, f"MISSING files for {rel_glob}")]
    for path in paths:
        text = read_text(path)
        match = regex.search(text)
        results.append(
            CheckResult(
                match is None,
                f"{'OK' if match is None else 'FORBIDDEN'} {path.relative_to(ROOT)}: {label}",
            )
        )
    return results


def check_text_contains(rel: str, tokens: list[str]) -> list[CheckResult]:
    path = ROOT / rel
    text = read_text(path)
    results = [exists(rel)]
    if not path.exists():
        return results
    for token in tokens:
        results.append(
            CheckResult(token in text, f"{'OK' if token in text else 'MISSING'} {rel}: {token}")
        )
    return results


def check_required_assets(engine: str, sprite_dir: str, font_dir: str) -> list[CheckResult]:
    sprites = [
        "btn_login_normal.png",
        "btn_login_hover.png",
        "btn_login_pressed.png",
        "btn_login_disabled.png",
        "input_bg_normal.png",
        "input_bg_focused.png",
    ]
    fonts = ["NotoSansCJK-Regular.otf", "Roboto-Regular.ttf", "RobotoMono-Regular.ttf"]
    results = [exists(f"{sprite_dir}/{name}") for name in sprites]
    results.extend(exists(f"{font_dir}/{name}") for name in fonts)
    if any(not r.ok for r in results[-len(fonts) :]):
        results.append(
            CheckResult(
                False,
                f"MISSING {engine} real fonts: replace font README placeholders before baseline capture",
            )
        )
    return results


def unity_checks() -> list[CheckResult]:
    results = [
        exists("fixtures/unity-test-project/Packages/manifest.json"),
        exists("fixtures/unity-test-project/Assets/Scenes/PocPlaygroundScene.unity"),
        exists("fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"),
    ]
    results.extend(
        check_text_absent(
            "fixtures/unity-test-project/Assets/Scenes/*.unity",
            r"\b(Button|TMP_InputField|InputField|Toggle|Slider|ScrollRect)\b",
            "Unity fixture scenes must not serialize interactive controls",
        )
    )
    results.extend(
        check_required_assets(
            "Unity",
            "fixtures/unity-test-project/Assets/Sprites/UI",
            "fixtures/unity-test-project/Assets/Fonts",
        )
    )
    return results


def godot_checks() -> list[CheckResult]:
    results = [
        exists("fixtures/godot-test-project/project.godot"),
        exists("fixtures/godot-test-project/scenes/poc_playground.tscn"),
        exists("fixtures/godot-test-project/scenes/login.tscn"),
    ]
    results.extend(
        check_text_absent(
            "fixtures/godot-test-project/scenes/*.tscn",
            r'type="(Button|LineEdit|HSlider|VSlider|CheckBox|CheckButton|OptionButton|ScrollContainer|ItemList|Tree)"',
            "Godot fixture scenes must not contain interactive Control nodes",
        )
    )
    for scene in ["poc_playground.tscn", "login.tscn"]:
        results.extend(
            check_text_contains(
                f"fixtures/godot-test-project/scenes/{scene}",
                ["autoagent_pinned_id", "autoagent_logical_role"],
            )
        )
    results.extend(
        check_required_assets(
            "Godot",
            "fixtures/godot-test-project/assets/ui",
            "fixtures/godot-test-project/assets/fonts",
        )
    )
    return results


def unreal_checks() -> list[CheckResult]:
    results = [
        exists("fixtures/unreal-test-project/AutoAgentTest.uproject"),
        exists("fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset"),
        exists("fixtures/unreal-test-project/Content/UI/WBP_PocPlayground.uasset"),
        exists("fixtures/unreal-test-project/Content/Maps/LoginMap.umap"),
        exists("fixtures/unreal-test-project/Content/Maps/PocPlaygroundMap.umap"),
    ]
    results.extend(
        check_text_contains(
            "fixtures/unreal-test-project/Source/AutoAgentTest/LoginUserWidget.h",
            ["AutoAgentId", "AutoAgentLogicalRole", "UImage", "UTextBlock"],
        )
    )
    results.extend(
        check_text_contains(
            "fixtures/unreal-test-project/Source/AutoAgentTest/PocPlaygroundUserWidget.h",
            ["AutoAgentId", "AutoAgentLogicalRole", "UImage"],
        )
    )
    # Widget skeleton headers must not contain delegate-wiring or business logic.
    #
    # UE note: unlike Unity (which adds interactive components at runtime),
    # UMG widget types (UButton, UEditableTextBox, …) ARE declared in widget
    # headers because the widget hierarchy is fixed at design time.  The correct
    # constraint is therefore NOT "no interactive types" but rather
    # "no delegate bindings" — wiring OnClicked.AddDynamic() etc. belongs in
    # the controller (ULoginController), not in the widget declaration itself.
    for widget_glob in (
        "fixtures/unreal-test-project/Source/AutoAgentTest/*Widget*.h",
        "fixtures/unreal-test-project/Source/AutoAgentTest/*Widget*.cpp",
    ):
        results.extend(
            check_text_absent(
                widget_glob,
                r"\.(AddDynamic|BindUObject|AddLambda|AddUObject)\s*\(",
                "UE widget declarations must not wire delegates (controller's responsibility)",
            )
        )
    results.extend(
        check_required_assets(
            "Unreal",
            "fixtures/unreal-test-project/Content/UI/Sprites",
            "fixtures/unreal-test-project/Content/UI/Fonts",
        )
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["all", "unity", "unreal", "godot"], default="all")
    args = parser.parse_args()

    checks: list[CheckResult] = []
    if args.engine in ("all", "unity"):
        checks.extend(unity_checks())
    if args.engine in ("all", "unreal"):
        checks.extend(unreal_checks())
    if args.engine in ("all", "godot"):
        checks.extend(godot_checks())

    for result in checks:
        print(result.message)

    failed = [r for r in checks if not r.ok]
    if failed:
        print(f"\nFAILED: {len(failed)} fixture checks failed.", file=sys.stderr)
        return 1
    print("\nAll static fixture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
