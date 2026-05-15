"""TASK-0004 verification.

Tests for scripts/ci/audit_visual_writes.py and visual_write_rules.yml.

Per docs/tasks-phase0.md TASK-0004:
- image.color = ... (Unity), SetVisibility (UE), .modulate = (Godot) → fail
- File with AUTOAGENT_ALLOW_VISUAL header → skip entirely
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_visual_writes as ava  # noqa: E402

RULES = SCRIPT_DIR / "visual_write_rules.yml"
AUDIT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "audit"


@pytest.fixture(scope="module")
def auditor() -> ava.Auditor:
    return ava.Auditor(yaml.safe_load(RULES.read_text(encoding="utf-8")))


# --- Language detection ----------------------------------------------------

def test_language_for_csharp(auditor):
    lang = auditor.language_for(Path("Foo.cs"))
    assert lang is not None and lang.name == "csharp"


def test_language_for_cpp(auditor):
    assert auditor.language_for(Path("Foo.cpp")).name == "cpp"
    assert auditor.language_for(Path("Foo.h")).name == "cpp"


def test_language_for_gdscript(auditor):
    assert auditor.language_for(Path("foo.gd")).name == "gdscript"


def test_language_for_unknown(auditor):
    assert auditor.language_for(Path("foo.txt")) is None
    assert auditor.language_for(Path("foo.py")) is None
    assert auditor.language_for(Path("foo.unity")) is None


# --- Spec-required: three baseline violation patterns ----------------------

def test_unity_image_color_assignment_fails(auditor):
    """image.color = ... (Unity) → violation."""
    src = "void Foo() { image.color = Color.red; }"
    violations, _ = auditor.scan_file(Path("Foo.cs"), src)
    names = {v.rule_name for v in violations}
    assert "color_write" in names


def test_ue_setvisibility_fails(auditor):
    """SetVisibility (UE) → violation."""
    src = "void UFoo::Construct() { Panel->SetVisibility(ESlateVisibility::Hidden); }"
    violations, _ = auditor.scan_file(Path("Foo.cpp"), src)
    names = {v.rule_name for v in violations}
    assert "ue_visibility" in names


def test_godot_modulate_fails(auditor):
    """.modulate = (Godot) → violation."""
    src = "func _ready():\n    $Panel.modulate = Color.RED\n"
    violations, _ = auditor.scan_file(Path("foo.gd"), src)
    names = {v.rule_name for v in violations}
    assert "modulate_write" in names


# --- AUTOAGENT_ALLOW_VISUAL exemption --------------------------------------

def test_file_with_exemption_marker_is_skipped(auditor):
    src = (
        "// AUTOAGENT_ALLOW_VISUAL: button-press-feedback\n"
        "void Foo() { image.color = Color.red; }\n"
    )
    violations, exempt = auditor.scan_file(Path("Foo.cs"), src)
    assert violations == []
    assert exempt is not None
    assert exempt.marker_line_no == 1


def test_exemption_marker_must_be_near_top(auditor):
    """Marker on line 31 (past the 30-line head) should not exempt."""
    lines = ["// padding\n"] * 30 + ["// AUTOAGENT_ALLOW_VISUAL: too late\n"]
    lines.append("void Foo() { image.color = Color.red; }\n")
    src = "".join(lines)
    violations, exempt = auditor.scan_file(Path("Foo.cs"), src)
    assert exempt is None
    assert any(v.rule_name == "color_write" for v in violations)


# --- Per-line allow_if_line_contains (state_sprites exemption) -------------

def test_sprite_assignment_via_state_sprite_helper_is_allowed(auditor):
    """\\.sprite\\s*= but RHS contains GetStateSprite → skip violation."""
    src = "void Foo() { image.sprite = stableId.GetStateSprite(\"pressed\"); }"
    violations, _ = auditor.scan_file(Path("Foo.cs"), src)
    assert violations == []


def test_sprite_assignment_without_helper_fails(auditor):
    src = "void Foo() { image.sprite = Resources.Load<Sprite>(\"x\"); }"
    violations, _ = auditor.scan_file(Path("Foo.cs"), src)
    assert any(v.rule_name == "sprite_write" for v in violations)


# --- Comment stripping -----------------------------------------------------

def test_violation_inside_line_comment_is_skipped(auditor):
    src = "void Foo() {\n    // image.color = Color.red;\n}"
    violations, _ = auditor.scan_file(Path("Foo.cs"), src)
    assert violations == []


def test_violation_after_inline_comment_is_skipped(auditor):
    """Code on the same line BEFORE a comment is still scanned; only the comment is stripped."""
    src = "void Foo() { var x = 1; // image.color = nope }\n"
    violations, _ = auditor.scan_file(Path("Foo.cs"), src)
    assert violations == []


def test_gdscript_hash_comment_stripped(auditor):
    src = "func _ready():\n    var x = 1   # node.modulate = Color.RED\n"
    violations, _ = auditor.scan_file(Path("foo.gd"), src)
    assert violations == []


# --- Behavior writes (must NOT be flagged) ---------------------------------

@pytest.mark.parametrize("line", [
    "image.raycastTarget = true;",
    "btn.interactable = false;",
    "btn.onClick.AddListener(OnClick);",
    "var btn = go.AddComponent<Button>();",
    "canvasGroup.blocksRaycasts = true;",
])
def test_csharp_behavior_writes_pass(auditor, line):
    src = f"void Foo() {{ {line} }}\n"
    violations, _ = auditor.scan_file(Path("Foo.cs"), src)
    # NB: SetActive(true|false) is in the visual list, but `interactable = true`
    # is a property write that doesn't match any rule.
    assert violations == [], f"unexpected violations for `{line}`: {violations}"


@pytest.mark.parametrize("line", [
    "Btn->SetIsEnabled(true);",
    "Btn->OnClicked.AddDynamic(this, &UFoo::OnClick);",
    "AutoAgentSubsystem->TransferStableId(OldPanel, NewBtn);",
])
def test_cpp_behavior_writes_pass(auditor, line):
    src = f"void UFoo::Construct() {{ {line} }}\n"
    violations, _ = auditor.scan_file(Path("Foo.cpp"), src)
    assert violations == [], f"unexpected violations for `{line}`: {violations}"


@pytest.mark.parametrize("line", [
    "$Panel.mouse_filter = Control.MOUSE_FILTER_STOP",
    "$Btn.disabled = false",
    "$Btn.pressed.connect(_on_btn_pressed)",
])
def test_gdscript_behavior_writes_pass(auditor, line):
    src = f"func _ready():\n    {line}\n"
    violations, _ = auditor.scan_file(Path("foo.gd"), src)
    assert violations == [], f"unexpected violations for `{line}`: {violations}"


# --- Fixture-file driven tests --------------------------------------------

def _scan_fixture(auditor: ava.Auditor, name: str):
    path = AUDIT_FIXTURES / name
    return auditor.scan_file(path, path.read_text(encoding="utf-8"))


def test_violation_unity_fixture_catches_all(auditor):
    violations, exempt = _scan_fixture(auditor, "violation_unity.cs")
    assert exempt is None
    names = {v.rule_name for v in violations}
    expected = {"color_write", "sprite_write", "transform_visual", "set_active", "enabled_write"}
    missing = expected - names
    assert not missing, f"missed rules: {missing}; got: {names}"


def test_violation_ue_fixture_catches_all(auditor):
    violations, exempt = _scan_fixture(auditor, "violation_ue.cpp")
    assert exempt is None
    names = {v.rule_name for v in violations}
    expected = {
        "ue_visibility",
        "ue_render_opacity",
        "ue_color_and_opacity",
        "ue_brush_from_texture",
        "ue_render_transform",
    }
    missing = expected - names
    assert not missing, f"missed rules: {missing}; got: {names}"


def test_violation_godot_fixture_catches_all(auditor):
    violations, exempt = _scan_fixture(auditor, "violation_godot.gd")
    assert exempt is None
    names = {v.rule_name for v in violations}
    expected = {
        "modulate_write",
        "self_modulate_write",
        "position_write",
        "size_write",
        "visible_write",
        "texture_write",
        "show_call",
        "hide_call",
    }
    missing = expected - names
    assert not missing, f"missed rules: {missing}; got: {names}"


def test_clean_unity_fixture_has_no_violations(auditor):
    violations, _ = _scan_fixture(auditor, "clean_unity.cs")
    assert violations == [], f"clean fixture should pass; got: {violations}"


def test_sprite_state_exempt_fixture_passes(auditor):
    violations, _ = _scan_fixture(auditor, "sprite_state_exempt.cs")
    assert violations == [], f"GetStateSprite helper usage should be allowed; got: {violations}"


def test_exempt_unity_fixture_is_exempted(auditor):
    violations, exempt = _scan_fixture(auditor, "exempt_unity.cs")
    assert violations == []
    assert exempt is not None
    assert exempt.marker_line_no == 1


def test_commented_unity_fixture_has_no_violations(auditor):
    violations, _ = _scan_fixture(auditor, "commented_unity.cs")
    assert violations == []


# --- End-to-end CLI / exit-code tests --------------------------------------

def _run(files: list[Path], quiet=True) -> int:
    argv = []
    for f in files:
        argv.extend(["--file", str(f)])
    if quiet:
        argv.append("--quiet")
    return ava.main(argv)


def test_cli_violation_fixture_fails():
    rc = _run([AUDIT_FIXTURES / "violation_unity.cs"])
    assert rc != 0


def test_cli_clean_fixture_passes():
    rc = _run([AUDIT_FIXTURES / "clean_unity.cs"])
    assert rc == 0


def test_cli_exempt_fixture_passes():
    rc = _run([AUDIT_FIXTURES / "exempt_unity.cs"])
    assert rc == 0


def test_cli_mixed_one_violation_fails():
    rc = _run([
        AUDIT_FIXTURES / "clean_unity.cs",
        AUDIT_FIXTURES / "violation_godot.gd",
    ])
    assert rc != 0


def test_cli_empty_input_passes(monkeypatch):
    import io as _io
    monkeypatch.setattr("sys.stdin", _io.StringIO(""))
    rc = ava.main(["--quiet"])
    # No files → 0 exit
    assert rc == 0


def test_cli_nonexistent_file_is_skipped_not_errored(tmp_path):
    """Deleted files should be silently skipped, not raise."""
    rc = _run([tmp_path / "nope.cs"])
    assert rc == 0


def test_cli_unknown_extension_is_skipped(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("image.color = red\n")
    rc = _run([f])
    assert rc == 0


# --- Subprocess sanity ----------------------------------------------------

def test_subprocess_stdin_violation():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "audit_visual_writes.py"), "--quiet"],
        input=str(AUDIT_FIXTURES / "violation_unity.cs") + "\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "color_write" in combined or "sprite_write" in combined


def test_subprocess_stdin_clean():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "audit_visual_writes.py"), "--quiet"],
        input=str(AUDIT_FIXTURES / "clean_unity.cs") + "\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
