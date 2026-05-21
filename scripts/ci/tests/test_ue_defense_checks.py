"""TASK-0207: UE-specific defense validation tests.

Verifies that the three CI defence scripts catch Unreal Engine-specific
violations and respect the AUTOAGENT_ALLOW_VISUAL exemption.

防护 coverage
-------------
0.1 — check_changed_paths.py
      · .uasset / .umap  → deny (exit 1)
      · .cpp / .h under adapters/unreal/Source/ → allow (exit 0)
      · fixtures/unreal-test-project/**/*.uasset → deny even for fixture source dir

0.2 — audit_visual_writes.py
      · SetVisibility(...) in a .cpp file → violation
      · SetRenderOpacity(...) in a .h file → violation
      · SetColorAndOpacity(...) in a .cpp with AUTOAGENT_ALLOW_VISUAL → exempt
      · SetBrush(GetStateBrush(...)) → allow_if_line_contains exemption
      · Comment-line SetVisibility → not caught

0.3 — check_visual_baseline.py  (engine convenience flags added in TASK-0206)
      · --engine ue --platform windows --name X resolves baseline to
        baselines/unreal/windows/X.png
      · Missing --name with --engine → exit 2
      · Missing --current with --engine → exit 2
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_changed_paths as ccp  # noqa: E402
import audit_visual_writes as avw  # noqa: E402
import check_visual_baseline as cvb  # noqa: E402

WHITELIST = SCRIPT_DIR / "path_whitelist.yml"
RULES = SCRIPT_DIR / "visual_write_rules.yml"


# ===========================================================================
# Shared fixtures
# ===========================================================================


@pytest.fixture(scope="module")
def checker() -> ccp.WhitelistChecker:
    config = yaml.safe_load(WHITELIST.read_text(encoding="utf-8"))
    return ccp.WhitelistChecker(config)


@pytest.fixture(scope="module")
def auditor() -> avw.Auditor:
    config = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return avw.Auditor(config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_ccp(*paths: str) -> int:
    """Run check_changed_paths.main with --path flags + --quiet."""
    argv: list[str] = ["--quiet"]
    for p in paths:
        argv.extend(["--path", p])
    return ccp.main(argv)


def _scan(auditor: avw.Auditor, path: Path, src: str):
    """Scan src text as if it were at path."""
    return auditor.scan_file(path, textwrap.dedent(src))


def _violates(auditor: avw.Auditor, path: Path, src: str) -> bool:
    v, _ = _scan(auditor, path, src)
    return len(v) > 0


def _rule_names(auditor: avw.Auditor, path: Path, src: str) -> set[str]:
    v, _ = _scan(auditor, path, src)
    return {x.rule_name for x in v}


# ===========================================================================
# 防护 0.1 — check_changed_paths: UE-specific paths
# ===========================================================================


class TestPathWhitelistUEDeny:
    """Binary asset types in fixture directories must be denied."""

    @pytest.mark.parametrize("path", [
        # UBlueprint / Widget Blueprint
        "fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset",
        "fixtures/unreal-test-project/Content/Characters/BP_Player.uasset",
        # Map file
        "fixtures/unreal-test-project/Content/Maps/LoginLevel.umap",
        # Nested content
        "fixtures/unreal-test-project/Content/UI/Icons/BTN_Login.uasset",
    ])
    def test_uasset_umap_denied(self, checker, path):
        result = checker.check(path, set())
        assert result.classification == "deny", (
            f"Expected 'deny' for {path!r}, got {result.classification!r}"
        )

    def test_uasset_via_main_exit1(self):
        rc = _run_ccp("fixtures/unreal-test-project/Content/UI/WBP_Login.uasset")
        assert rc == 1, "uasset must make check_changed_paths exit 1"

    def test_umap_via_main_exit1(self):
        rc = _run_ccp("fixtures/unreal-test-project/Content/Maps/MainLevel.umap")
        assert rc == 1, "umap must make check_changed_paths exit 1"


class TestPathWhitelistUEAllow:
    """Source files under the UE adapter and fixture must be allowed."""

    @pytest.mark.parametrize("path", [
        # Adapter public header
        "adapters/unreal/Source/AutoAgent/Public/AutoAgentSubsystem.h",
        # Adapter private implementation
        "adapters/unreal/Source/AutoAgent/Private/AutoAgentProtocolHandler.cpp",
        # Editor module
        "adapters/unreal/Source/AutoAgentEditor/Public/AutoAgentIdCustomization.h",
        "adapters/unreal/Source/AutoAgentEditor/Private/AutoAgentEditorModule.cpp",
        # Build descriptor
        "adapters/unreal/Source/AutoAgent/AutoAgent.Build.cs",
        # Plugin manifest
        "adapters/unreal/AutoAgent.uplugin",
        # Fixture source files
        "fixtures/unreal-test-project/Source/AutoAgentFixture/LoginWidget.h",
        "fixtures/unreal-test-project/Source/AutoAgentFixture/LoginWidget.cpp",
    ])
    def test_ue_source_allowed(self, checker, path):
        result = checker.check(path, set())
        assert result.classification == "allow", (
            f"Expected 'allow' for {path!r}, got {result.classification!r}"
        )

    def test_ue_source_via_main_exit0(self):
        rc = _run_ccp("adapters/unreal/Source/AutoAgent/Private/AutoAgentSubsystem.cpp")
        assert rc == 0, "UE adapter .cpp must allow (exit 0)"

    def test_mixed_ue_paths_one_deny(self):
        """Allowed source + denied uasset must exit 1 overall."""
        rc = _run_ccp(
            "adapters/unreal/Source/AutoAgent/Private/AutoAgentSubsystem.cpp",
            "fixtures/unreal-test-project/Content/UI/WBP_Login.uasset",
        )
        assert rc == 1, "One denied path must make overall result exit 1"


class TestPathWhitelistUEBaselines:
    """Baselines directory is permanently denied — humans commit baselines."""

    @pytest.mark.parametrize("path", [
        "baselines/unreal/windows/login_screen.png",
        "baselines/unreal/linux/settings_screen.png",
        "baselines/unity/windows/welcome.png",
    ])
    def test_baselines_denied(self, checker, path):
        result = checker.check(path, set())
        assert result.classification == "deny", (
            f"Baseline path {path!r} must be denied"
        )


# ===========================================================================
# 防护 0.2 — audit_visual_writes: UE C++ rules
# ===========================================================================

CPP_PATH = Path("adapters/unreal/Source/AutoAgent/Private/SomeWidget.cpp")
H_PATH = Path("adapters/unreal/Source/AutoAgent/Public/SomeWidget.h")


class TestAuditUEVisualWritesCaught:
    """All UE visual-write rules must fire on matching code."""

    @pytest.mark.parametrize("src,expected_rule", [
        # ue_visibility
        ("MyWidget->SetVisibility(ESlateVisibility::Hidden);", "ue_visibility"),
        ("Widget->SetVisibility(ESlateVisibility::Visible);", "ue_visibility"),
        ("    Btn->SetVisibility(ESlateVisibility::Collapsed);", "ue_visibility"),
        # ue_render_opacity
        ("Image->SetRenderOpacity(0.0f);", "ue_render_opacity"),
        ("Panel->SetRenderOpacity(0.5f);", "ue_render_opacity"),
        # ue_color_and_opacity
        ("Icon->SetColorAndOpacity(FLinearColor::Red);", "ue_color_and_opacity"),
        ("Txt->SetColorAndOpacity(FLinearColor(1,1,1,0));", "ue_color_and_opacity"),
        # ue_brush_from_texture
        ("Img->SetBrushFromTexture(LoadedTex);", "ue_brush_from_texture"),
        # ue_brush_from_asset
        ("Img->SetBrushFromAsset(BrushAsset);", "ue_brush_from_asset"),
        # ue_set_brush
        ("Img->SetBrush(NewBrush);", "ue_set_brush"),
        # ue_render_transform
        ("W->SetRenderTransform(FWidgetTransform());", "ue_render_transform"),
        # ue_render_scale
        ("W->SetRenderScale(FVector2D(2.0f, 2.0f));", "ue_render_scale"),
        # ue_render_translation
        ("W->SetRenderTranslation(FVector2D(10, 0));", "ue_render_translation"),
    ])
    def test_ue_visual_rule_fires(self, auditor, src, expected_rule):
        assert expected_rule in _rule_names(auditor, CPP_PATH, src), (
            f"Expected rule {expected_rule!r} to fire on: {src!r}"
        )

    def test_set_visibility_in_header(self, auditor):
        """ue_visibility must also fire in .h files."""
        src = "virtual void HideWidget() { Widget->SetVisibility(ESlateVisibility::Hidden); }"
        assert "ue_visibility" in _rule_names(auditor, H_PATH, src)

    def test_set_visibility_cli_exit1(self, tmp_path):
        """CLI must exit 1 when a .cpp has SetVisibility."""
        f = tmp_path / "bad_widget.cpp"
        f.write_text("MyWidget->SetVisibility(ESlateVisibility::Hidden);\n",
                     encoding="utf-8")
        rc = avw.main(["--file", str(f), "--quiet"])
        assert rc == 1


class TestAuditUEVisualWritesNotCaught:
    """Comments, reads, and allow_if exemptions must not trigger violations."""

    def test_commented_set_visibility(self, auditor):
        src = "// MyWidget->SetVisibility(ESlateVisibility::Hidden);"
        assert not _violates(auditor, CPP_PATH, src)

    def test_set_visibility_in_comment_block(self, auditor):
        # After the // everything is stripped; no code remains to match.
        src = "    // Widget->SetVisibility(ESlateVisibility::Visible); // old code"
        assert not _violates(auditor, CPP_PATH, src)

    def test_set_brush_state_sprite_exempted(self, auditor):
        """SetBrush(GetStateBrush(...)) is allow_if_line_contains exempted."""
        src = "Img->SetBrush(GetStateBrush(TEXT('pressed')));"
        viol, _ = _scan(auditor, CPP_PATH, src)
        assert "ue_set_brush" not in {v.rule_name for v in viol}

    def test_set_brush_state_sprite_direct_exempted(self, auditor):
        src = "Img->SetBrush(StateSprite);"
        viol, _ = _scan(auditor, CPP_PATH, src)
        assert "ue_set_brush" not in {v.rule_name for v in viol}

    def test_python_file_not_scanned(self, auditor):
        """Non-.cpp/.h files must not be matched by UE rules."""
        py_path = Path("scripts/ci/foo.py")
        src = "widget.SetVisibility(True)"  # Python, not C++
        v, _ = _scan(auditor, py_path, src)
        assert "ue_visibility" not in {x.rule_name for x in v}


class TestAuditUEAutoAgentAllowVisual:
    """AUTOAGENT_ALLOW_VISUAL file-level exemption must work for .cpp files."""

    def test_exemption_marker_skips_cpp(self, auditor):
        src = textwrap.dedent("""\
            // AUTOAGENT_ALLOW_VISUAL: opacity-fade-animation
            #include "CoreMinimal.h"
            void UFadeWidget::FadeOut()
            {
                SetRenderOpacity(0.0f);
                SetVisibility(ESlateVisibility::Hidden);
            }
        """)
        viol, exempt = _scan(auditor, CPP_PATH, src)
        assert not viol, "AUTOAGENT_ALLOW_VISUAL should suppress all violations"
        assert exempt is not None, "Exemption record should be present"
        assert exempt.marker_line_no == 1

    def test_exemption_marker_in_header(self, auditor):
        src = textwrap.dedent("""\
            // AUTOAGENT_ALLOW_VISUAL: debug-overlay
            #pragma once
            class UDebugOverlay : public UUserWidget {
                void Show() { SetVisibility(ESlateVisibility::Visible); }
            };
        """)
        viol, exempt = _scan(auditor, H_PATH, src)
        assert not viol
        assert exempt is not None

    def test_exemption_after_30_lines_not_exempt(self, auditor):
        """Marker beyond line 30 must NOT exempt the file."""
        padding = "\n".join(f"// line {i}" for i in range(35))
        src = padding + "\n// AUTOAGENT_ALLOW_VISUAL: too-late\n"
        src += "Widget->SetVisibility(ESlateVisibility::Hidden);\n"
        viol, exempt = _scan(auditor, CPP_PATH, src)
        assert viol, "Marker past line 30 must not exempt"
        assert exempt is None

    def test_exemption_cli_exit0(self, tmp_path):
        """CLI must exit 0 for an exempted .cpp file."""
        f = tmp_path / "fade.cpp"
        f.write_text(
            "// AUTOAGENT_ALLOW_VISUAL: fade-in\n"
            "Widget->SetVisibility(ESlateVisibility::Hidden);\n",
            encoding="utf-8",
        )
        rc = avw.main(["--file", str(f), "--quiet"])
        assert rc == 0


# ===========================================================================
# 防护 0.3 — check_visual_baseline: UE engine convenience flags (TASK-0206)
# ===========================================================================


class TestCheckVisualBaselineEngineFlags:
    """--engine ue path resolution (added in TASK-0206)."""

    def _make_args(self, **kwargs) -> argparse.Namespace:
        """Build a minimal Namespace that resolve_engine_paths can operate on."""
        defaults = {
            "engine": None,
            "platform": "windows",
            "name": None,
            "baselines_root": Path("baselines"),
            "current": None,
            "baseline": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_ue_engine_resolves_baseline_path(self, tmp_path):
        """--engine ue --platform windows --name X must resolve baseline correctly."""
        current_png = tmp_path / "login_screen.png"
        current_png.write_bytes(b"")  # placeholder

        args = self._make_args(
            engine="ue",
            platform="windows",
            name="login_screen",
            current=current_png,
        )
        rc = cvb.resolve_engine_paths(args)
        assert rc == 0
        assert args.baseline == Path("baselines/unreal/windows/login_screen.png")

    def test_unity_engine_resolves_baseline_path(self):
        """--engine unity must map to baselines/unity/."""
        current_png = Path("/tmp/welcome.png")
        args = self._make_args(
            engine="unity",
            platform="windows",
            name="welcome_screen",
            current=current_png,
        )
        rc = cvb.resolve_engine_paths(args)
        assert rc == 0
        assert args.baseline == Path("baselines/unity/windows/welcome_screen.png")

    def test_godot_engine_resolves_baseline_path(self):
        """--engine godot must map to baselines/godot/."""
        args = self._make_args(
            engine="godot",
            platform="linux",
            name="hud",
            current=Path("/tmp/hud.png"),
        )
        rc = cvb.resolve_engine_paths(args)
        assert rc == 0
        assert args.baseline == Path("baselines/godot/linux/hud.png")

    def test_engine_without_name_returns_2(self):
        """Omitting --name with --engine must exit 2 (usage error)."""
        args = self._make_args(engine="ue", name=None)
        rc = cvb.resolve_engine_paths(args)
        assert rc == 2

    def test_engine_without_current_returns_2(self):
        """Omitting --current with --engine must exit 2 (usage error)."""
        args = self._make_args(engine="ue", name="login_screen", current=None)
        rc = cvb.resolve_engine_paths(args)
        assert rc == 2

    def test_no_engine_is_noop(self):
        """Without --engine the function must be a no-op (return 0, no changes)."""
        args = self._make_args(engine=None, name=None, current=None)
        rc = cvb.resolve_engine_paths(args)
        assert rc == 0
        assert args.baseline is None

    def test_custom_baselines_root(self):
        """--baselines-root must override the default baselines/ prefix."""
        args = self._make_args(
            engine="ue",
            platform="windows",
            name="hud",
            current=Path("/tmp/hud.png"),
            baselines_root=Path("/ci/baselines"),
        )
        rc = cvb.resolve_engine_paths(args)
        assert rc == 0
        assert args.baseline == Path("/ci/baselines/unreal/windows/hud.png")

    def test_cli_engine_missing_name_exit2(self):
        """CLI with --engine but without --name must exit 2."""
        rc = cvb.main(["--engine", "ue", "--current", "/tmp/shot.png"])
        assert rc == 2

    def test_cli_engine_missing_current_exit2(self):
        """CLI with --engine --name but without --current must exit 2."""
        rc = cvb.main(["--engine", "ue", "--name", "login_screen"])
        assert rc == 2


class TestCheckVisualBaselineSSIM:
    """SSIM comparison: identical images pass, different images fail."""

    @pytest.fixture()
    def checkerboard(self, tmp_path):
        """Create a high-contrast checkerboard PNG (16×16 px).

        Checkerboards have strong structural content, making SSIM meaningful
        even for small images.  White/black alternating pattern on 2×2 tiles.
        """
        pytest.importorskip("skimage", reason="scikit-image not installed")
        import numpy as np
        from skimage import io as skio

        img = np.zeros((16, 16, 3), dtype=np.uint8)
        for r in range(16):
            for c in range(16):
                if (r // 2 + c // 2) % 2 == 0:
                    img[r, c] = [255, 255, 255]  # white
        p = tmp_path / "checker.png"
        skio.imsave(str(p), img, check_contrast=False)
        return p

    @pytest.fixture()
    def inverse_checkerboard(self, tmp_path):
        """Inverse of checkerboard (black where checker is white, vice versa)."""
        pytest.importorskip("skimage", reason="scikit-image not installed")
        import numpy as np
        from skimage import io as skio

        img = np.zeros((16, 16, 3), dtype=np.uint8)
        for r in range(16):
            for c in range(16):
                if (r // 2 + c // 2) % 2 != 0:
                    img[r, c] = [255, 255, 255]  # white
        p = tmp_path / "inv_checker.png"
        skio.imsave(str(p), img, check_contrast=False)
        return p

    def test_identical_images_pass(self, checkerboard, tmp_path):
        """Comparing an image with itself must pass at any threshold."""
        import shutil
        copy = tmp_path / "checker_copy.png"
        shutil.copy(checkerboard, copy)
        rc = cvb.main([
            "--baseline", str(checkerboard),
            "--current", str(copy),
            "--threshold", "0.99",
            "--quiet",
        ])
        assert rc == 0

    def test_different_images_fail(self, checkerboard, inverse_checkerboard):
        """Inverse checkerboard vs checkerboard must fail — SSIM is very low.

        Checkerboard and its inverse are maximally different structurally,
        guaranteeing SSIM well below any reasonable threshold.
        """
        rc = cvb.main([
            "--baseline", str(checkerboard),
            "--current", str(inverse_checkerboard),
            "--threshold", "0.95",
            "--quiet",
        ])
        assert rc == 1, (
            "Inverse checkerboard vs checkerboard must have SSIM < 0.95"
        )

    def test_different_images_save_diff(self, checkerboard, inverse_checkerboard,
                                        tmp_path):
        """A diff PNG must be written when --save-diff is supplied and images differ."""
        diff_path = tmp_path / "diff.png"
        rc = cvb.main([
            "--baseline", str(checkerboard),
            "--current", str(inverse_checkerboard),
            "--threshold", "0.95",
            "--save-diff", str(diff_path),
            "--quiet",
        ])
        assert rc == 1
        assert diff_path.exists(), "diff.png must be written on failure"

    def test_missing_current_returns_nonzero(self, checkerboard, tmp_path):
        """A non-existent current image must produce an error (not crash)."""
        rc = cvb.main([
            "--baseline", str(checkerboard),
            "--current", str(tmp_path / "nonexistent.png"),
            "--quiet",
        ])
        assert rc != 0
