"""TASK-0001 verification.

Per docs/tasks-phase0.md TASK-0001:
1. All schema files are valid JSON Schema Draft 2020-12.
2. A sample node passes node.json.
3. A sample dump_tree request passes methods.json.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"

SCHEMA_FILES = ["node.json", "methods.json", "events.json", "errors.json"]


def _load(name):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schemas():
    return {name: _load(name) for name in SCHEMA_FILES}


@pytest.fixture(scope="module")
def registry(schemas):
    resources = [
        (s["$id"], Resource(contents=s, specification=DRAFT202012))
        for s in schemas.values()
    ]
    return Registry().with_resources(resources)


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_is_valid_draft_2020_12(schemas, name):
    """Each schema file is itself a valid Draft 2020-12 schema."""
    Draft202012Validator.check_schema(schemas[name])


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_declares_2020_12(schemas, name):
    assert schemas[name]["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_has_id(schemas, name):
    assert schemas[name]["$id"].startswith("https://autoagent.dev/schema/v0.1/")


def test_sample_node_passes(schemas, registry):
    validator = Draft202012Validator(schemas["node.json"], registry=registry)
    sample = {
        "id": "login_button_bg",
        "type": "Image",
        "engine_type": "UnityEngine.UI.Image",
        "parent_id": "login_panel",
        "children_ids": ["login_button_label"],
        "stable_id_source": "pinned",
        "visual": {
            "position": [100.0, 200.0],
            "size": [200.0, 60.0],
            "anchor": [0.5, 0.5],
            "world_bounds": [50.0, 170.0, 250.0, 230.0],
            "visible": True,
            "alpha": 1.0,
            "color": "#FFFFFFFF",
            "sprite_ref": "Assets/UI/btn_login_normal.png",
            "z_order": 5,
        },
        "behavior": {
            "interactable": True,
            "raycast_target": True,
            "event_handlers": ["OnClick"],
            "custom_scripts": ["LoginController"],
            "attached_components": ["UnityEngine.UI.Button"],
        },
        "meta": {
            "logical_role": "button",
            "role": "submit_button",
            "intent": "trigger_login",
            "tags": ["primary", "form"],
            "task_refs": ["TASK-042"],
            "state_sprites": {
                "normal": "Assets/UI/btn_login_normal.png",
                "hover": "Assets/UI/btn_login_hover.png",
                "pressed": "Assets/UI/btn_login_pressed.png",
                "disabled": "Assets/UI/btn_login_disabled.png",
            },
        },
    }
    validator.validate(sample)


def test_minimal_node_passes(schemas, registry):
    """Only the required fields."""
    validator = Draft202012Validator(schemas["node.json"], registry=registry)
    sample = {
        "id": "root",
        "type": "Canvas",
        "engine_type": "UnityEngine.Canvas",
        "parent_id": None,
        "children_ids": [],
        "stable_id_source": "auto",
        "visual": {
            "position": [0.0, 0.0],
            "size": [1920.0, 1080.0],
            "visible": True,
        },
    }
    validator.validate(sample)


def test_node_rejects_unknown_logical_role(schemas, registry):
    validator = Draft202012Validator(schemas["node.json"], registry=registry)
    sample = {
        "id": "x",
        "type": "Image",
        "engine_type": "UnityEngine.UI.Image",
        "parent_id": None,
        "children_ids": [],
        "stable_id_source": "pinned",
        "visual": {"position": [0, 0], "size": [10, 10], "visible": True},
        "meta": {"logical_role": "spaceship"},
    }
    with pytest.raises(ValidationError):
        validator.validate(sample)


def test_node_rejects_hash_id_typo(schemas, registry):
    validator = Draft202012Validator(schemas["node.json"], registry=registry)
    sample = {
        "id": "x",
        "type": "Image",
        "engine_type": "UnityEngine.UI.Image",
        "parent_id": None,
        "children_ids": [],
        "stable_id_source": "hashed",
        "visual": {"position": [0, 0], "size": [10, 10], "visible": True},
    }
    with pytest.raises(ValidationError):
        validator.validate(sample)


def test_node_rejects_unknown_state_sprite(schemas, registry):
    validator = Draft202012Validator(schemas["node.json"], registry=registry)
    sample = {
        "id": "x",
        "type": "Image",
        "engine_type": "UnityEngine.UI.Image",
        "parent_id": None,
        "children_ids": [],
        "stable_id_source": "pinned",
        "visual": {"position": [0, 0], "size": [10, 10], "visible": True},
        "meta": {"state_sprites": {"glowing": "x.png"}},
    }
    with pytest.raises(ValidationError):
        validator.validate(sample)


def test_sample_dump_tree_request_passes(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    request = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "dump_tree",
        "params": {
            "root_id": None,
            "include_invisible": False,
            "max_depth": -1,
            "fields": ["visual", "behavior", "meta"],
        },
    }
    validator.validate(request)


def test_minimal_dump_tree_request_passes(schemas, registry):
    """params is optional for dump_tree."""
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    validator.validate({"jsonrpc": "2.0", "id": "req-1", "method": "dump_tree"})


def test_negotiate_version_request_passes(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    validator.validate({
        "jsonrpc": "2.0",
        "id": "neg-1",
        "method": "negotiate_version",
        "params": {"supported": ["0.1"], "client": "autoagent-mcp/0.1.0"},
    })


def test_click_request_passes(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    validator.validate({
        "jsonrpc": "2.0",
        "id": "click-1",
        "method": "click",
        "params": {"id": "login_button_bg", "button": "left"},
    })


def test_methods_rejects_unknown_method(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    with pytest.raises(ValidationError):
        validator.validate({
            "jsonrpc": "2.0",
            "id": "x",
            "method": "do_evil",
            "params": {},
        })


def test_methods_rejects_wrong_jsonrpc_version(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    with pytest.raises(ValidationError):
        validator.validate({"jsonrpc": "1.0", "id": "x", "method": "ping"})


def test_methods_rejects_click_missing_id(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    with pytest.raises(ValidationError):
        validator.validate({
            "jsonrpc": "2.0",
            "id": "x",
            "method": "click",
            "params": {"button": "left"},
        })


def test_methods_take_screenshot_node_scope_requires_node_id(schemas, registry):
    validator = Draft202012Validator(schemas["methods.json"], registry=registry)
    with pytest.raises(ValidationError):
        validator.validate({
            "jsonrpc": "2.0",
            "id": "x",
            "method": "take_screenshot",
            "params": {"scope": "node"},
        })


def test_sample_event_passes(schemas):
    validator = Draft202012Validator(schemas["events.json"])
    validator.validate({
        "jsonrpc": "2.0",
        "method": "event.scene_changed",
        "params": {"scene_name": "LoginScene", "timestamp": 1715234567.123},
    })


def test_event_rejects_unknown_event(schemas):
    validator = Draft202012Validator(schemas["events.json"])
    with pytest.raises(ValidationError):
        validator.validate({
            "jsonrpc": "2.0",
            "method": "event.everything_exploded",
            "params": {"timestamp": 0},
        })


def test_event_rejects_id_field(schemas):
    """Notifications must not carry a JSON-RPC id."""
    validator = Draft202012Validator(schemas["events.json"])
    with pytest.raises(ValidationError):
        validator.validate({
            "jsonrpc": "2.0",
            "id": "x",
            "method": "event.scene_changed",
            "params": {"scene_name": "x", "timestamp": 0},
        })


def test_sample_error_passes(schemas):
    validator = Draft202012Validator(schemas["errors.json"])
    validator.validate({
        "code": -32001,
        "message": "WidgetNotFound",
        "data": {"id": "missing_id"},
    })


def test_error_rejects_unknown_code(schemas):
    validator = Draft202012Validator(schemas["errors.json"])
    with pytest.raises(ValidationError):
        validator.validate({"code": -42, "message": "Whatever"})
