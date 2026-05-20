"""TASK-0128: Comprehensive visual-write audit tests.

Covers every rule in visual_write_rules.yml for all three languages
(C#, C++/UE, GDScript), plus:
- File-level exemption via AUTOAGENT_ALLOW_VISUAL marker
- Per-line exemption via allow_if_line_contains
- JSON output mode
- CLI entry points
- The four patterns explicitly required by verification:
    image.color =, transform.position =, rt.anchoredPosition =, SetActive(false)
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_visual_writes as avw  # noqa: E402

RULES = SCRIPT_DIR / "visual_write_rules.yml"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def auditor() -> avw.Auditor:
    config = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return avw.Auditor(config)


def scan(auditor: avw.Auditor, path: Path, src: str):
    """Helper: scan src text as if it were at path, return (violations, exemption)."""
    return auditor.scan_file(path, textwrap.dedent(src))


def violates(auditor: avw.Auditor, path: Path, src: str) -> bool:
    v, _ = scan(auditor, path, src)
    return len(v) > 0


def rule_names(auditor: avw.Auditor, path: Path, src: str) -> set[str]:
    v, _ = scan(auditor, path, src)
    return {x.rule_name for x in v}


# ---------------------------------------------------------------------------
# C# (Unity) rules
# ---------------------------------------------------------------------------


CS = Path("fixtures/unity-test-project/Scripts/LoginController.cs")


class TestCSharpTransformVisual:
    """transform_visual: position / rotation / scale writes."""

    @pytest.mark.parametrize("src", [
        # Bare `transform.X =` (this.transform inside MonoBehaviour)
        "transform.position = new Vector3(0, 0, 0);",
        "transform.localPosition = offset;",
        "transform.rotation = Quaternion.identity;",
        "transform.localRotation = rot;",
        "transform.localScale = Vector3.one;",
        # Via object reference
        "obj.transform.position = target;",
        "target.transform.localScale = scale;",
        # With whitespace around =
        "transform.position  =  Vector3.zero;",
    ])
    def test_catches_transform_writes(self, auditor, src):
        assert violates(auditor, CS, src), f"Expected violation for: {src!r}"

    @pytest.mark.parametrize("src", [
        # Read — no assignment
        "var p = transform.position;",
        # Different property
        "transform.name = 'Foo';",
        # Substring — should not match 'transform' inside longer word
        "myTransform.position = value;",  # still catches via obj.transform? No — myTransform not transform
    ])
    def test_no_false_positive_transform(self, auditor, src):
        viol, _ = scan(auditor, CS, src)
        # myTransform.position doesn't match \btransform\. (not 'transform' at word boundary followed by '.')
        rule_hits = {v.rule_name for v in viol}
        assert "transform_visual" not in rule_hits, f"False positive for: {src!r}"


class TestCSharpRectTransformViaComponent:
    """rect_transform_via_component: .rectTransform.field writes."""

    @pytest.mark.parametrize("src", [
        "rt.rectTransform.anchoredPosition = pos;",
        "rectTransform.sizeDelta = size;",
        "rectTransform.anchorMin = Vector2.zero;",
        "rectTransform.anchorMax = Vector2.one;",
        "rectTransform.pivot = new Vector2(0.5f, 0.5f);",
    ])
    def test_catches_rect_transform_component_writes(self, auditor, src):
        assert violates(auditor, CS, src), f"Expected violation for: {src!r}"


class TestCSharpRectTransformFieldDirect:
    """rect_transform_field_direct: rt.anchoredPosition = (variable access)."""

    @pytest.mark.parametrize("src", [
        # Key verification case: rt variable
        "rt.anchoredPosition = new Vector2(100, 50);",
        "myRect.anchoredPosition = pos;",
        "GetComponent<RectTransform>().anchoredPosition = v;",
        # sizeDelta
        "rt.sizeDelta = new Vector2(200, 100);",
        "myPanel.sizeDelta = size;",
    ])
    def test_catches_rect_transform_direct_writes(self, auditor, src):
        assert "rect_transform_field_direct" in rule_names(auditor, CS, src), (
            f"Expected rect_transform_field_direct violation for: {src!r}"
        )

    def test_read_does_not_trigger(self, auditor):
        src = "var pos = rt.anchoredPosition;"
        assert not violates(auditor, CS, src)


class TestCSharpColorWrite:
    """color_write: .color = (the key verification pattern image.color =)."""

    def test_image_color_assign(self, auditor):
        """Core verification: image.color = must be caught."""
        src = "image.color = Color.red;"
        assert "color_write" in rule_names(auditor, CS, src)

    @pytest.mark.parametrize("src", [
        "image.color = Color.red;",
        "text.color = Color.white;",
        "graphic.color = new Color(1, 0, 0);",
        "renderer.color = c;",
        "  this.image.color = highlight;",
    ])
    def test_catches_color_writes(self, auditor, src):
        assert violates(auditor, CS, src)

    def test_color_read_no_violation(self, auditor):
        src = "var c = image.color;"
        assert not violates(auditor, CS, src)


class TestCSharpSpriteWrite:
    """sprite_write: .sprite = with allow_if_line_contains exemptions."""

    def test_sprite_assign_caught(self, auditor):
        src = "image.sprite = newSprite;"
        assert "sprite_write" in rule_names(auditor, CS, src)

    def test_sprite_state_sprite_exempted(self, auditor):
        src = "image.sprite = stableId.GetStateSprite('pressed');"
        viol, _ = scan(auditor, CS, src)
        sprite_hits = [v for v in viol if v.rule_name == "sprite_write"]
        assert not sprite_hits, "state_sprites helper should be exempted"

    def test_sprite_state_array_exempted(self, auditor):
        src = "image.sprite = stateSprites['normal'];"
        viol, _ = scan(auditor, CS, src)
        sprite_hits = [v for v in viol if v.rule_name == "sprite_write"]
        assert not sprite_hits


class TestCSharpMaterialWrite:
    def test_material_assign_caught(self, auditor):
        src = "renderer.material = mat;"
        assert "material_write" in rule_names(auditor, CS, src)

    def test_material_read_ok(self, auditor):
        src = "var m = renderer.material;"
        assert not violates(auditor, CS, src)


class TestCSharpSetActive:
    """set_active: SetActive(true/false) — the key verification pattern."""

    def test_set_active_false(self, auditor):
        """Core verification: SetActive(false) must be caught."""
        src = "gameObject.SetActive(false);"
        assert "set_active" in rule_names(auditor, CS, src)

    def test_set_active_true(self, auditor):
        src = "child.SetActive(true);"
        assert "set_active" in rule_names(auditor, CS, src)

    def test_set_active_variable_ok(self, auditor):
        src = "gameObject.SetActive(isVisible);"
        assert "set_active" not in rule_names(auditor, CS, src)

    def test_set_active_with_spaces(self, auditor):
        src = "go.SetActive( false );"
        assert "set_active" in rule_names(auditor, CS, src)


class TestCSharpEnabledWrite:
    def test_enabled_assign_caught(self, auditor):
        src = "image.enabled = false;"
        assert "enabled_write" in rule_names(auditor, CS, src)

    def test_enabled_read_ok(self, auditor):
        src = "if (image.enabled) return;"
        assert "enabled_write" not in rule_names(auditor, CS, src)


# ---------------------------------------------------------------------------
# C# comment stripping
# ---------------------------------------------------------------------------


class TestCSharpCommentStripping:
    def test_comment_line_not_flagged(self, auditor):
        src = "// transform.position = Vector3.zero;"
        assert not violates(auditor, CS, src)

    def test_inline_comment_stripped(self, auditor):
        src = "var x = 1; // transform.position = Vector3.zero;"
        assert not violates(auditor, CS, src)

    def test_code_before_comment_flagged(self, auditor):
        src = "transform.position = v; // set it"
        assert violates(auditor, CS, src)


# ---------------------------------------------------------------------------
# C# file-level exemption
# ---------------------------------------------------------------------------


class TestCSharpFileExemption:
    def test_exempt_marker_skips_file(self, auditor):
        src = textwrap.dedent("""\
            // AUTOAGENT_ALLOW_VISUAL: button-press-feedback
            public class ButtonFeedback : MonoBehaviour {
                public void OnPress() { image.color = Color.gray; }
            }
        """)
        viol, exempt = scan(auditor, CS, src)
        assert not viol
        assert exempt is not None
        assert exempt.marker_line_no == 1

    def test_exempt_marker_within_30_lines(self, auditor):
        padding = "\n".join(f"// line {i}" for i in range(25))
        src = padding + "\n// AUTOAGENT_ALLOW_VISUAL: special\n" + "image.color = Color.red;\n"
        viol, exempt = scan(auditor, CS, src)
        assert not viol
        assert exempt is not None

    def test_exempt_marker_beyond_30_lines_not_exempt(self, auditor):
        padding = "\n".join(f"// line {i}" for i in range(35))
        src = padding + "\n// AUTOAGENT_ALLOW_VISUAL: too-late\n" + "image.color = Color.red;\n"
        viol, exempt = scan(auditor, CS, src)
        assert viol  # NOT exempted
        assert exempt is None


# ---------------------------------------------------------------------------
# C# wrong extension — not scanned
# ---------------------------------------------------------------------------


def test_cs_wrong_extension_not_scanned(auditor):
    v, e = scan(auditor, Path("foo.py"), "image.color = Color.red;")
    assert not v
    assert e is None


# ---------------------------------------------------------------------------
# The four required verification patterns (explicit)
# ---------------------------------------------------------------------------


class TestVerificationPatterns:
    """Explicit checks for the 4 patterns named in the task verification."""

    def test_image_color_assign(self, auditor):
        """image.color = is caught."""
        v, _ = scan(auditor, CS, "image.color = Color.red;")
        assert any(x.rule_name == "color_write" for x in v)

    def test_transform_position_bare(self, auditor):
        """transform.position = (bare, no leading object) is caught."""
        v, _ = scan(auditor, CS, "transform.position = new Vector3(1, 2, 3);")
        assert any(x.rule_name == "transform_visual" for x in v), (
            "transform.position = must be caught by transform_visual rule"
        )

    def test_rt_anchored_position(self, auditor):
        """rt.anchoredPosition = (RectTransform variable) is caught."""
        v, _ = scan(auditor, CS, "rt.anchoredPosition = new Vector2(100, 50);")
        assert any(x.rule_name == "rect_transform_field_direct" for x in v), (
            "rt.anchoredPosition = must be caught by rect_transform_field_direct rule"
        )

    def test_set_active_false(self, auditor):
        """SetActive(false) is caught."""
        v, _ = scan(auditor, CS, "gameObject.SetActive(false);")
        assert any(x.rule_name == "set_active" for x in v)


# ---------------------------------------------------------------------------
# C++ (Unreal Engine) rules
# ---------------------------------------------------------------------------


CPP = Path("adapters/unreal/Source/AutoAgentRuntime/Scanner.cpp")
H = Path("adapters/unreal/Source/AutoAgentRuntime/Scanner.h")


class TestCppRules:
    @pytest.mark.parametrize("src,rule", [
        ("MyWidget->SetVisibility(ESlateVisibility::Hidden);", "ue_visibility"),
        ("Btn->SetRenderOpacity(0.5f);", "ue_render_opacity"),
        ("Image->SetColorAndOpacity(FLinearColor::Red);", "ue_color_and_opacity"),
        ("Image->SetBrushFromTexture(Tex);", "ue_brush_from_texture"),
        ("Image->SetBrushFromAsset(Asset);", "ue_brush_from_asset"),
        ("Image->SetBrush(NewBrush);", "ue_set_brush"),
        ("Widget->SetRenderTransform(Transform);", "ue_render_transform"),
        ("Widget->SetRenderScale(FVector2D(1, 1));", "ue_render_scale"),
        ("Widget->SetRenderTranslation(FVector2D(0, 0));", "ue_render_translation"),
    ])
    def test_catches_ue_visual_writes(self, auditor, src, rule):
        assert rule in rule_names(auditor, CPP, src), f"Expected {rule!r} for: {src!r}"

    @pytest.mark.parametrize("src,rule", [
        ("Image->SetBrush(GetStateBrush('pressed'));", "ue_set_brush"),
        ("Image->SetBrush(StateSprite);", "ue_set_brush"),
    ])
    def test_ue_set_brush_exempted(self, auditor, src, rule):
        viol, _ = scan(auditor, CPP, src)
        assert rule not in {v.rule_name for v in viol}

    def test_cpp_comment_stripped(self, auditor):
        src = "// Btn->SetVisibility(ESlateVisibility::Hidden);"
        assert not violates(auditor, CPP, src)

    def test_header_file_also_scanned(self, auditor):
        src = "Widget->SetColorAndOpacity(FLinearColor::White);"
        assert violates(auditor, H, src)

    def test_cpp_wrong_extension(self, auditor):
        v, _ = scan(auditor, Path("foo.cs"), "Widget->SetVisibility(ESlateVisibility::Hidden);")
        # .cs is C# extension — no cpp rules should fire (UE patterns won't match C# context)
        # But the .cs file WILL be scanned — just no UE rules match. C# rules might fire though.
        # Let's just check that the UE rule names are not hit
        rule_set = {x.rule_name for x in v}
        assert "ue_visibility" not in rule_set


# ---------------------------------------------------------------------------
# GDScript rules
# ---------------------------------------------------------------------------


GD = Path("fixtures/godot-test-project/Scripts/login_controller.gd")


class TestGDScriptRules:
    @pytest.mark.parametrize("src,rule", [
        ("position = Vector2(0, 0)", "position_write"),
        ("global_position = Vector2(100, 200)", "global_position_write"),
        ("size = Vector2(800, 600)", "size_write"),
        ("modulate = Color(1, 0, 0, 1)", "modulate_write"),
        ("self_modulate = Color.RED", "self_modulate_write"),
        ("texture = load('res://img.png')", "texture_write"),
        ("icon = preload('res://icon.png')", "icon_write"),
        ("visible = false", "visible_write"),
        ("button.show()", "show_call"),
        ("panel.hide()", "hide_call"),
    ])
    def test_catches_gdscript_visual_writes(self, auditor, src, rule):
        assert rule in rule_names(auditor, GD, src), f"Expected {rule!r} for: {src!r}"

    def test_texture_state_sprite_exempted(self, auditor):
        src = "texture = get_state_texture('normal')"
        viol, _ = scan(auditor, GD, src)
        assert "texture_write" not in {v.rule_name for v in viol}

    def test_texture_state_array_exempted(self, auditor):
        src = "texture = state_sprites['pressed']"
        viol, _ = scan(auditor, GD, src)
        assert "texture_write" not in {v.rule_name for v in viol}

    def test_gdscript_comment_stripped(self, auditor):
        src = "# position = Vector2(0, 0)"
        assert not violates(auditor, GD, src)

    def test_gdscript_inline_comment(self, auditor):
        src = "x = 1  # position = Vector2(0, 0)"
        assert not violates(auditor, GD, src)

    def test_gdscript_read_no_violation(self, auditor):
        src = "var pos = position"
        assert not violates(auditor, GD, src)

    def test_gdscript_wrong_extension(self, auditor):
        v, _ = scan(auditor, Path("foo.py"), "position = Vector2(0, 0)")
        assert not v


# ---------------------------------------------------------------------------
# Multi-violation in one file
# ---------------------------------------------------------------------------


class TestMultiViolation:
    def test_multiple_rules_same_file(self, auditor):
        src = textwrap.dedent("""\
            public void Setup() {
                transform.position = Vector3.zero;
                image.color = Color.white;
                gameObject.SetActive(false);
                rt.anchoredPosition = Vector2.zero;
            }
        """)
        viol, _ = scan(auditor, CS, src)
        names = {v.rule_name for v in viol}
        assert "transform_visual" in names
        assert "color_write" in names
        assert "set_active" in names
        assert "rect_transform_field_direct" in names

    def test_violation_line_numbers_correct(self, auditor):
        src = "// ok\ntransform.position = v;\n// comment\nimage.color = c;\n"
        viol, _ = scan(auditor, CS, src)
        lines = {v.line_no for v in viol}
        assert 2 in lines  # transform.position
        assert 4 in lines  # image.color


# ---------------------------------------------------------------------------
# run() helper
# ---------------------------------------------------------------------------


class TestRunHelper:
    def test_run_no_files(self, tmp_path):
        code, viol, exempt = avw.run([], RULES, tmp_path)
        assert code == 0
        assert not viol

    def test_run_clean_file(self, tmp_path):
        f = tmp_path / "clean.cs"
        f.write_text("public class Foo { void Bar() { int x = 1; } }", encoding="utf-8")
        code, viol, exempt = avw.run([f], RULES, tmp_path)
        assert code == 0
        assert not viol

    def test_run_violating_file(self, tmp_path):
        f = tmp_path / "bad.cs"
        f.write_text("public class Foo { void Bar() { transform.position = Vector3.zero; } }", encoding="utf-8")
        code, viol, exempt = avw.run([f], RULES, tmp_path)
        assert code == 1
        assert len(viol) >= 1

    def test_run_missing_file_skipped(self, tmp_path):
        missing = tmp_path / "nonexistent.cs"
        code, viol, exempt = avw.run([missing], RULES, tmp_path)
        assert code == 0  # skipped, not an error


# ---------------------------------------------------------------------------
# JSON output mode
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_render_json_no_violations(self):
        result = avw.render_json([], [], 0)
        doc = json.loads(result)
        assert doc["summary"]["violation_count"] == 0
        assert doc["summary"]["exit_code"] == 0
        assert doc["violations"] == []
        assert doc["exemptions"] == []

    def test_render_json_with_violation(self):
        viol = [avw.Violation(
            path=Path("foo.cs"),
            line_no=5,
            rule_name="color_write",
            line_text="    image.color = Color.red;",
            reason="Image.color is visual.",
        )]
        result = avw.render_json(viol, [], 1)
        doc = json.loads(result)
        assert doc["summary"]["violation_count"] == 1
        assert doc["summary"]["exit_code"] == 1
        assert doc["violations"][0]["rule"] == "color_write"
        assert doc["violations"][0]["line"] == 5

    def test_render_json_with_exemption(self):
        exempt = [avw.Exemption(path=Path("bar.cs"), marker_line_no=1)]
        result = avw.render_json([], exempt, 0)
        doc = json.loads(result)
        assert doc["summary"]["exemption_count"] == 1
        assert doc["exemptions"][0]["marker_line"] == 1

    def test_cli_json_flag_outputs_json(self, tmp_path):
        f = tmp_path / "bad.cs"
        f.write_text("transform.position = Vector3.zero;", encoding="utf-8")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = avw.main(["--file", str(f), "--json"])
        assert rc == 1
        doc = json.loads(buf.getvalue())
        assert doc["summary"]["violation_count"] >= 1

    def test_cli_json_clean_file(self, tmp_path):
        f = tmp_path / "clean.cs"
        f.write_text("var x = 1;", encoding="utf-8")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = avw.main(["--file", str(f), "--json"])
        assert rc == 0
        doc = json.loads(buf.getvalue())
        assert doc["summary"]["violation_count"] == 0


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCliIntegration:
    def test_cli_file_violation_exit1(self, tmp_path):
        f = tmp_path / "bad.cs"
        f.write_text("image.color = Color.red;", encoding="utf-8")
        rc = avw.main(["--file", str(f), "--quiet"])
        assert rc == 1

    def test_cli_file_clean_exit0(self, tmp_path):
        f = tmp_path / "clean.cs"
        f.write_text("var x = 1;", encoding="utf-8")
        rc = avw.main(["--file", str(f)])
        assert rc == 0

    def test_cli_exempt_file_exit0(self, tmp_path):
        f = tmp_path / "exempt.cs"
        f.write_text("// AUTOAGENT_ALLOW_VISUAL: ok\nimage.color = Color.red;\n", encoding="utf-8")
        rc = avw.main(["--file", str(f), "--quiet"])
        assert rc == 0

    def test_cli_nonexistent_rules_exit2(self, tmp_path):
        rc = avw.main(["--rules", str(tmp_path / "nonexistent.yml")])
        assert rc == 2

    def test_cli_empty_input_exit0(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", iter([]))
        rc = avw.main([])
        assert rc == 0

    def test_cli_paths_file(self, tmp_path):
        src = tmp_path / "bad.cs"
        src.write_text("transform.position = v;", encoding="utf-8")
        paths_file = tmp_path / "paths.txt"
        paths_file.write_text(str(src) + "\n", encoding="utf-8")
        rc = avw.main(["--paths-file", str(paths_file), "--quiet"])
        assert rc == 1

    def test_cli_gdscript_violation(self, tmp_path):
        f = tmp_path / "bad.gd"
        f.write_text("position = Vector2(0, 0)\n", encoding="utf-8")
        rc = avw.main(["--file", str(f), "--quiet"])
        assert rc == 1

    def test_cli_cpp_violation(self, tmp_path):
        f = tmp_path / "bad.cpp"
        f.write_text("Widget->SetVisibility(ESlateVisibility::Hidden);\n", encoding="utf-8")
        rc = avw.main(["--file", str(f), "--quiet"])
        assert rc == 1

    def test_cli_non_source_file_ignored(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"color": "red"}', encoding="utf-8")
        rc = avw.main(["--file", str(f)])
        assert rc == 0

    def test_cli_mixed_files_one_violation(self, tmp_path):
        clean = tmp_path / "clean.cs"
        clean.write_text("var x = 1;", encoding="utf-8")
        bad = tmp_path / "bad.cs"
        bad.write_text("image.color = Color.red;", encoding="utf-8")
        rc = avw.main(["--file", str(clean), "--file", str(bad), "--quiet"])
        assert rc == 1
