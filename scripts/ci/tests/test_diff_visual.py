"""TASK-0005 verification.

Tests for scripts/ci/diff_visual_dump.py.

Per docs/tasks-phase0.md TASK-0005:
- 同一棵树 visual 完全一致 → exit 0
- 某节点 color 变化 → exit 非 0 + 输出节点 ID + 字段
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import diff_visual_dump as dvd  # noqa: E402

DUMP_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dump_diff"


# Helper builders -----------------------------------------------------------

def _node(
    nid: str,
    *,
    parent_id: str | None = None,
    children_ids: list[str] | None = None,
    stable_id_source: str = "pinned",
    visual: dict | None = None,
    behavior: dict | None = None,
    meta: dict | None = None,
) -> dict:
    n = {
        "id": nid,
        "type": "Image",
        "engine_type": "UnityEngine.UI.Image",
        "parent_id": parent_id,
        "children_ids": children_ids or [],
        "stable_id_source": stable_id_source,
        "visual": visual
        or {
            "position": [0.0, 0.0],
            "size": [100.0, 100.0],
            "visible": True,
        },
    }
    if behavior is not None:
        n["behavior"] = behavior
    if meta is not None:
        n["meta"] = meta
    return n


def _envelope(nodes: list[dict]) -> dict:
    return {"nodes": nodes, "captured_at": 1.0}


# extract_nodes -------------------------------------------------------------

def test_extract_nodes_from_envelope():
    nodes = dvd.extract_nodes(_envelope([_node("a")]), "before")
    assert len(nodes) == 1 and nodes[0]["id"] == "a"


def test_extract_nodes_from_raw_array():
    nodes = dvd.extract_nodes([_node("a"), _node("b")], "before")
    assert [n["id"] for n in nodes] == ["a", "b"]


def test_extract_nodes_rejects_garbage():
    with pytest.raises(ValueError):
        dvd.extract_nodes("not a node array", "before")


def test_extract_nodes_rejects_node_without_id():
    bad = [{"type": "Image"}]
    with pytest.raises(ValueError):
        dvd.extract_nodes(bad, "before")


# Identical trees -----------------------------------------------------------

def test_identical_trees_no_diff_no_orphan():
    tree = _envelope([_node("a"), _node("b")])
    diffs, orphans = dvd.run(tree, deepcopy(tree))
    assert diffs == []
    assert orphans == []


def test_empty_trees_no_diff():
    diffs, orphans = dvd.run(_envelope([]), _envelope([]))
    assert diffs == [] and orphans == []


# Visual changes ------------------------------------------------------------

def test_color_change_is_detected():
    """Spec verification: color 变化 → exit 非 0 + 输出节点 ID + 字段."""
    before = _envelope([
        _node("login_button_bg", visual={
            "position": [0.0, 60.0], "size": [240.0, 64.0],
            "visible": True, "color": "#FFFFFFFF",
        }),
    ])
    after = _envelope([
        _node("login_button_bg", visual={
            "position": [0.0, 60.0], "size": [240.0, 64.0],
            "visible": True, "color": "#FF0000FF",
        }),
    ])
    diffs, _ = dvd.run(before, after)
    assert len(diffs) == 1
    d = diffs[0]
    assert d.node_id == "login_button_bg"
    assert d.field == "color"
    assert d.before == "#FFFFFFFF"
    assert d.after == "#FF0000FF"


def test_position_change_is_detected():
    before = _envelope([_node("a", visual={"position": [0.0, 0.0], "size": [10, 10], "visible": True})])
    after = _envelope([_node("a", visual={"position": [5.0, 0.0], "size": [10, 10], "visible": True})])
    diffs, _ = dvd.run(before, after)
    assert len(diffs) == 1
    assert diffs[0].field == "position"


def test_visible_toggle_is_detected():
    before = _envelope([_node("a", visual={"position": [0, 0], "size": [10, 10], "visible": True})])
    after = _envelope([_node("a", visual={"position": [0, 0], "size": [10, 10], "visible": False})])
    diffs, _ = dvd.run(before, after)
    assert any(d.field == "visible" for d in diffs)


def test_sprite_ref_change_is_detected():
    before = _envelope([_node("a", visual={
        "position": [0, 0], "size": [10, 10], "visible": True,
        "sprite_ref": "a.png",
    })])
    after = _envelope([_node("a", visual={
        "position": [0, 0], "size": [10, 10], "visible": True,
        "sprite_ref": "b.png",
    })])
    diffs, _ = dvd.run(before, after)
    assert any(d.field == "sprite_ref" for d in diffs)


def test_multiple_field_changes_all_reported():
    before = _envelope([_node("a", visual={
        "position": [0, 0], "size": [10, 10], "visible": True,
        "color": "#FFFFFFFF", "alpha": 1.0,
    })])
    after = _envelope([_node("a", visual={
        "position": [1, 2], "size": [20, 20], "visible": False,
        "color": "#FF0000FF", "alpha": 0.5,
    })])
    diffs, _ = dvd.run(before, after)
    fields = {d.field for d in diffs}
    assert fields == {"position", "size", "visible", "color", "alpha"}


# behavior/meta should NOT cause violations ---------------------------------

def test_behavior_change_alone_is_not_a_violation():
    before = _envelope([
        _node("a", behavior={"interactable": False, "attached_components": []}),
    ])
    after = _envelope([
        _node("a", behavior={"interactable": True, "attached_components": ["Button"]}),
    ])
    diffs, _ = dvd.run(before, after)
    assert diffs == []


def test_meta_change_alone_is_not_a_violation():
    before = _envelope([_node("a", meta={"tags": []})])
    after = _envelope([_node("a", meta={"tags": ["primary"]})])
    diffs, _ = dvd.run(before, after)
    assert diffs == []


# Orphan ID detection -------------------------------------------------------

def test_pinned_id_missing_in_after_is_orphan():
    before = _envelope([_node("kept", stable_id_source="pinned"),
                        _node("vanished", stable_id_source="pinned")])
    after = _envelope([_node("kept", stable_id_source="pinned")])
    diffs, orphans = dvd.run(before, after)
    assert diffs == []
    assert len(orphans) == 1
    assert orphans[0].node_id == "vanished"
    assert orphans[0].stable_id_source == "pinned"


def test_auto_id_missing_in_after_is_orphan():
    before = _envelope([_node("auto_id", stable_id_source="auto")])
    after = _envelope([])
    _, orphans = dvd.run(before, after)
    assert len(orphans) == 1
    assert orphans[0].stable_id_source == "auto"


def test_hash_id_missing_in_after_is_not_orphan():
    """hash IDs are noise — disappearing is normal."""
    before = _envelope([_node("hash_abc", stable_id_source="hash")])
    after = _envelope([])
    _, orphans = dvd.run(before, after)
    assert orphans == []


def test_orphan_check_can_be_disabled():
    before = _envelope([_node("vanished", stable_id_source="pinned")])
    after = _envelope([])
    _, orphans = dvd.run(before, after, check_orphans=False)
    assert orphans == []


# Added nodes ---------------------------------------------------------------

def test_added_nodes_in_after_are_not_violations():
    """AI wrapping a button etc. adds new auto-generated nodes — that's OK."""
    before = _envelope([_node("a")])
    after = _envelope([_node("a"), _node("new_wrapper", stable_id_source="auto")])
    diffs, orphans = dvd.run(before, after)
    assert diffs == [] and orphans == []


# Field added / removed -----------------------------------------------------

def test_field_appearing_in_after_is_a_diff():
    before = _envelope([_node("a", visual={"position": [0, 0], "size": [10, 10], "visible": True})])
    after = _envelope([_node("a", visual={
        "position": [0, 0], "size": [10, 10], "visible": True, "color": "#FFFFFFFF",
    })])
    diffs, _ = dvd.run(before, after)
    assert any(d.field == "color" and d.before is None for d in diffs)


def test_field_disappearing_in_after_is_a_diff():
    before = _envelope([_node("a", visual={
        "position": [0, 0], "size": [10, 10], "visible": True, "color": "#FFFFFFFF",
    })])
    after = _envelope([_node("a", visual={"position": [0, 0], "size": [10, 10], "visible": True})])
    diffs, _ = dvd.run(before, after)
    assert any(d.field == "color" and d.after is None for d in diffs)


# Render output -------------------------------------------------------------

def test_render_diff_contains_id_and_field():
    diffs = [dvd.VisualDiff(node_id="login_button_bg", field="color",
                            before="#FFFFFFFF", after="#FF0000FF")]
    out = dvd.render(diffs, [])
    assert "login_button_bg" in out
    assert "color" in out
    assert "#FFFFFFFF" in out
    assert "#FF0000FF" in out


def test_render_orphan_contains_id_and_source():
    orphans = [dvd.Orphan(node_id="vanished", stable_id_source="pinned")]
    out = dvd.render([], orphans)
    assert "vanished" in out
    assert "pinned" in out


# Fixture-file driven ------------------------------------------------------

def _run_cli(before_name: str, after_name: str, *extra) -> tuple[int, subprocess.CompletedProcess]:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "diff_visual_dump.py"),
            str(DUMP_FIXTURES / before_name),
            str(DUMP_FIXTURES / after_name),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result


def test_fixture_identical_trees_exit_zero():
    rc, _ = _run_cli("before.json", "after_clean.json")
    assert rc == 0


def test_fixture_color_change_exits_nonzero_with_details():
    rc, result = _run_cli("before.json", "after_color_change.json")
    assert rc != 0
    combined = result.stdout + result.stderr
    assert "login_button_bg" in combined
    assert "color" in combined


def test_fixture_orphan_exits_nonzero():
    rc, result = _run_cli("before.json", "after_orphan.json")
    assert rc != 0
    combined = result.stdout + result.stderr
    assert "login_button_bg" in combined
    assert "orphan" in combined.lower()


def test_fixture_orphan_can_be_ignored():
    rc, _ = _run_cli("before.json", "after_orphan.json", "--no-orphan-check")
    assert rc == 0


# Error handling -----------------------------------------------------------

def test_cli_missing_argument_errors():
    with pytest.raises(SystemExit) as exc:
        dvd.main([])
    assert exc.value.code == 2


def test_cli_nonexistent_file_errors(tmp_path):
    rc = dvd.main([str(tmp_path / "nope.json"), str(tmp_path / "still_nope.json")])
    assert rc == 2


def test_cli_invalid_json_errors(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    rc = dvd.main([str(bad), str(bad)])
    assert rc == 2


def test_cli_flag_form_works(tmp_path):
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text(json.dumps(_envelope([_node("a")])), encoding="utf-8")
    after.write_text(json.dumps(_envelope([_node("a")])), encoding="utf-8")
    rc = dvd.main(["--before", str(before), "--after", str(after), "--quiet"])
    assert rc == 0


def test_raw_array_format_accepted(tmp_path):
    """Both envelope and raw [node, ...] should work."""
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    before.write_text(json.dumps([_node("a")]), encoding="utf-8")
    after.write_text(json.dumps([_node("a")]), encoding="utf-8")
    rc = dvd.main([str(before), str(after), "--quiet"])
    assert rc == 0
