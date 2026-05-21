"""TASK-0300: Godot-specific defense validation tests.

Verifies that the three CI defence scripts catch Godot-specific violations
and respect the AUTOAGENT_ALLOW_VISUAL exemption in GDScript files.

防护 coverage
-------------
0.1 — check_changed_paths.py
      · .tscn / .import / project.godot       → deny (exit 1)
      · .gd under adapters/godot/addons/       → allow (exit 0)
      · .gd under fixtures/godot-test-project/scripts/ → allow (exit 0)
      · assets/ui/*.png in fixture             → deny (binary art asset)

0.2 — audit_visual_writes.py (gdscript language block)
      · position =, size =, visible =, modulate =,
        self_modulate =, texture =, icon =, .show(), .hide() → violation
      · Comment-line violations               → not caught
      · texture = get_state_texture(...)      → allow_if_line_contains exemption
      · AUTOAGENT_ALLOW_VISUAL in first 30 lines → entire file exempt

0.3 — node schema validation (jsonschema)
      · Minimal valid Godot node              → passes node.json schema
      · Node with behavior dict               → passes
      · Node with engine_extras.godot         → passes
      · Missing required field                → fails (schema rejection)
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

import check_changed_paths as ccp  # noqa: E402
import audit_visual_writes as avw  # noqa: E402

WHITELIST = SCRIPT_DIR / "path_whitelist.yml"
RULES = SCRIPT_DIR / "visual_write_rules.yml"
NODE_SCHEMA_PATH = SCRIPT_DIR.parent.parent / "protocol" / "schema" / "node.json"


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


@pytest.fixture(scope="module")
def node_schema() -> dict:
    return json.loads(NODE_SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_ccp(*paths: str) -> int:
    argv: list[str] = ["--quiet"]
    for p in paths:
        argv.extend(["--path", p])
    return ccp.main(argv)


def _scan(auditor: avw.Auditor, path: Path, src: str):
    return auditor.scan_file(path, textwrap.dedent(src))


def _violates(auditor: avw.Auditor, path: Path, src: str) -> bool:
    v, _ = _scan(auditor, path, src)
    return len(v) > 0


def _rule_names(auditor: avw.Auditor, path: Path, src: str) -> set[str]:
    v, _ = _scan(auditor, path, src)
    return {x.rule_name for x in v}


def _gd(name: str = "login_controller.gd") -> Path:
    return Path(f"fixtures/godot-test-project/scripts/{name}")


# ===========================================================================
# 防护 0.1 — check_changed_paths: Godot-specific paths
# ===========================================================================


class TestPathWhitelistGodotDeny:
    """Scene, import, project.godot, and art asset paths must be denied."""

    @pytest.mark.parametrize("path", [
        "fixtures/godot-test-project/scenes/login.tscn",
        "fixtures/godot-test-project/scenes/poc_playground.tscn",
        "fixtures/godot-test-project/assets/ui/btn_login_normal.png",
        "fixtures/godot-test-project/assets/ui/input_bg_normal.png",
        "fixtures/godot-test-project/assets/fonts/Roboto-Regular.ttf",
        "fixtures/godot-test-project/project.godot",
    ])
    def test_godot_asset_denied(self, checker: ccp.WhitelistChecker, path: str) -> None:
        result = checker.check(path, set())
        assert result.classification in ("deny", "default_deny"), (
            f"Expected deny/default_deny for {path!r}, got {result.classification!r}"
        )

    def test_tscn_via_main_exit1(self) -> None:
        rc = _run_ccp("fixtures/godot-test-project/scenes/login.tscn")
        assert rc == 1, "login.tscn must exit 1"

    def test_project_godot_via_main_exit1(self) -> None:
        rc = _run_ccp("fixtures/godot-test-project/project.godot")
        assert rc == 1, "project.godot must exit 1"

    def test_art_asset_via_main_exit1(self) -> None:
        rc = _run_ccp("fixtures/godot-test-project/assets/ui/btn_login_normal.png")
        assert rc == 1, "art asset PNG must exit 1"


class TestPathWhitelistGodotAllow:
    """Adapter GDScript and fixture controller scripts must be allowed."""

    @pytest.mark.parametrize("path", [
        "adapters/godot/addons/autoagent/runtime/reflection/control_reflector.gd",
        "adapters/godot/addons/autoagent/runtime/server/websocket_server.gd",
        "adapters/godot/addons/autoagent/runtime/server/protocol_handler.gd",
        "adapters/godot/addons/autoagent/runtime/input/engine_input_driver.gd",
        "adapters/godot/addons/autoagent/runtime/autoagent.gd",
        "adapters/godot/addons/autoagent/plugin.gd",
        "fixtures/godot-test-project/scripts/LoginController.gd",
        "fixtures/godot-test-project/scripts/MockApi.gd",
    ])
    def test_gd_source_allowed(self, checker: ccp.WhitelistChecker, path: str) -> None:
        result = checker.check(path, set())
        assert result.classification == "allow", (
            f"Expected ALLOW for {path!r}, got {result.classification!r}"
        )

    def test_adapter_gd_via_main_exit0(self) -> None:
        rc = _run_ccp(
            "adapters/godot/addons/autoagent/runtime/reflection/control_reflector.gd"
        )
        assert rc == 0, "adapter .gd file must exit 0"

    def test_fixture_script_via_main_exit0(self) -> None:
        rc = _run_ccp("fixtures/godot-test-project/scripts/LoginController.gd")
        assert rc == 0, "fixture LoginController.gd must exit 0"

    def test_mixed_deny_wins(self) -> None:
        rc = _run_ccp(
            "adapters/godot/addons/autoagent/runtime/autoagent.gd",
            "fixtures/godot-test-project/scenes/login.tscn",
        )
        assert rc == 1, "one deny path must make the batch exit 1"


class TestPathWhitelistGodotImport:
    """.import sidecar files must be denied (binary Godot importer artefacts)."""

    @pytest.mark.parametrize("path", [
        "fixtures/godot-test-project/assets/ui/btn_login_normal.png.import",
        "fixtures/godot-test-project/assets/fonts/Roboto-Regular.ttf.import",
    ])
    def test_import_sidecar_denied(self, checker: ccp.WhitelistChecker, path: str) -> None:
        result = checker.check(path, set())
        # .import files are inside the assets tree which is fully denied.
        assert result.classification in ("deny", "default_deny"), (
            f"Expected deny for {path!r}, got {result.classification!r}"
        )


# ===========================================================================
# 防护 0.2 — audit_visual_writes.py: GDScript rules
# ===========================================================================

_GD = Path("fixtures/godot-test-project/scripts/login_controller.gd")


class TestAuditGodotVisualWritesCaught:
    """Each GDScript visual-write rule must fire on a matching .gd line."""

    @pytest.mark.parametrize("src, expected_rule", [
        ("position = Vector2(0, 0)\n", "position_write"),
        ("self.position = Vector2(100, 50)\n", "position_write"),
        ("global_position = get_parent().position\n", "global_position_write"),
        ("size = Vector2(200, 40)\n", "size_write"),
        ("modulate = Color(1, 1, 1, 0)\n", "modulate_write"),
        ("self_modulate = Color.WHITE\n", "self_modulate_write"),
        ("texture = load('res://a.png')\n", "texture_write"),
        ("icon = normal_icon\n", "icon_write"),
        ("visible = false\n", "visible_write"),
        ("node.show()\n", "show_call"),
        ("node.hide()\n", "hide_call"),
    ])
    def test_gdscript_rule_fires(
        self, auditor: avw.Auditor, src: str, expected_rule: str
    ) -> None:
        assert expected_rule in _rule_names(auditor, _GD, src), (
            f"Rule {expected_rule!r} did not fire for: {src!r}"
        )

    def test_visible_write_in_header_catches(self, auditor: avw.Auditor) -> None:
        src = "func _ready():\n    visible = false\n"
        assert _violates(auditor, _GD, src)

    def test_show_call_cli_exit1(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.gd"
        bad.write_text("node.show()\n", encoding="utf-8")
        import audit_visual_writes as _avw
        rc = _avw.main(["--file", str(bad), "--quiet"])
        assert rc == 1


class TestAuditGodotVisualWritesNotCaught:
    """Commented-out violations and allow_if_line_contains must not fire."""

    def test_commented_position_write(self, auditor: avw.Auditor) -> None:
        src = "# position = Vector2(0, 0)  # visual\n"
        assert not _violates(auditor, _GD, src)

    def test_position_in_block_comment(self, auditor: avw.Auditor) -> None:
        # GDScript uses # for all comments; block comments are just multiple lines
        src = "# This sets position = some_offset\n"
        assert not _violates(auditor, _GD, src)

    def test_texture_allow_if_line_contains_get_state_texture(
        self, auditor: avw.Auditor
    ) -> None:
        src = "texture = get_state_texture('normal')\n"
        assert not _violates(auditor, _GD, src)

    def test_texture_allow_if_line_contains_state_sprites(
        self, auditor: avw.Auditor
    ) -> None:
        src = "texture = state_sprites['normal']\n"
        assert not _violates(auditor, _GD, src)

    def test_python_file_not_scanned(self, auditor: avw.Auditor) -> None:
        py_path = Path("scripts/ci/some_tool.py")
        src = "node.visible = False\n"
        v, _ = auditor.scan_file(py_path, src)
        assert len(v) == 0, "Python files must not be scanned by GDScript rules"

    def test_cs_file_not_scanned_by_gd_rules(self, auditor: avw.Auditor) -> None:
        cs_path = Path("some.cs")
        src = "node.hide()\n"
        # .cs is scanned by csharp rules (not gdscript), so hide() won't match
        # (csharp rules don't have hide_call).
        rules = _rule_names(auditor, cs_path, src)
        assert "hide_call" not in rules


class TestAuditGodotAutoAgentAllowVisual:
    """File-level AUTOAGENT_ALLOW_VISUAL exemption must skip the whole file."""

    def test_exemption_marker_skips_gd(self, auditor: avw.Auditor) -> None:
        src = textwrap.dedent("""\
            # AUTOAGENT_ALLOW_VISUAL: login-flow-state-machine
            extends Node
            func _on_login_success():
                visible = false
                welcome_panel.show()
        """)
        v, exempt = auditor.scan_file(_GD, src)
        assert len(v) == 0, "Exempted file must have no violations"
        assert exempt is not None, "Exemption must be recorded"
        assert exempt.marker_line_no == 1

    def test_exemption_marker_anywhere_in_first_30_lines(
        self, auditor: avw.Auditor
    ) -> None:
        lines = ["# line %d\n" % i for i in range(1, 29)]
        lines.append("# AUTOAGENT_ALLOW_VISUAL: reason\n")
        lines.append("visible = false\n")
        v, exempt = auditor.scan_file(_GD, "".join(lines))
        assert len(v) == 0
        assert exempt is not None

    def test_exemption_after_30_lines_not_exempt(self, auditor: avw.Auditor) -> None:
        lines = ["# filler line %d\n" % i for i in range(31)]
        lines.append("# AUTOAGENT_ALLOW_VISUAL: too late\n")
        lines.append("visible = false\n")
        v, _ = auditor.scan_file(_GD, "".join(lines))
        assert len(v) > 0, "Marker past line 30 must not exempt the file"

    def test_exemption_cli_exit0(self, tmp_path: Path) -> None:
        good = tmp_path / "exempted.gd"
        good.write_text(
            "# AUTOAGENT_ALLOW_VISUAL: visibility-state-machine\nvisible = false\n",
            encoding="utf-8",
        )
        import audit_visual_writes as _avw
        rc = _avw.main(["--file", str(good), "--quiet"])
        assert rc == 0, "Exempted file must exit 0"


# ===========================================================================
# 防护 0.3 — node.json schema: Godot-shaped node output
# ===========================================================================


def _minimal_node() -> dict:
    return {
        "id": "login_panel",
        "type": "PanelContainer",
        "engine_type": "PanelContainer",
        "parent_id": None,
        "children_ids": [],
        "stable_id_source": "pinned",
        "visual": {
            "position": [0.0, 0.0],
            "size": [1280.0, 720.0],
            "visible": True,
        },
    }


class TestGodotNodeSchema:
    """Godot-shaped nodes must pass the AutoAgent node.json schema."""

    def test_minimal_node_passes(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        jsonschema.validate(_minimal_node(), node_schema)

    def test_node_with_behavior_passes(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        node["behavior"] = {"interactable": True, "raycast_target": True}
        jsonschema.validate(node, node_schema)

    def test_node_with_engine_extras_passes(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        node["engine_extras"] = {"godot": {"text": "Login", "placeholder": ""}}
        jsonschema.validate(node, node_schema)

    def test_node_with_meta_passes(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        node["meta"] = {
            "logical_role": "button",
            "state_sprites": {"normal": "btn_login_normal", "hover": "btn_login_hover"},
        }
        jsonschema.validate(node, node_schema)

    def test_hash_stable_id_source_passes(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        node["id"] = "h_1a2b3c4d"
        node["stable_id_source"] = "hash"
        jsonschema.validate(node, node_schema)

    def test_missing_required_field_fails(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        del node["stable_id_source"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(node, node_schema)

    def test_invalid_stable_id_source_fails(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        node["stable_id_source"] = "generated"  # not in enum
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(node, node_schema)

    def test_missing_visual_fails(self, node_schema: dict) -> None:
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        del node["visual"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(node, node_schema)

    def test_behavior_unknown_field_fails(self, node_schema: dict) -> None:
        """behavior has additionalProperties: false."""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        node = _minimal_node()
        node["behavior"] = {"interactable": True, "unknown_extra": "bad"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(node, node_schema)
