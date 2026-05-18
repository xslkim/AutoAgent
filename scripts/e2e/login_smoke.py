"""End-to-end smoke test — drive a running engine adapter over the wire protocol.

Connects to a running AutoAgent adapter (Unity or Godot), exercises the Login
scene fixture, and validates every dumped node against protocol/schema/node.json.
The protocol, port, and pinned-node set are identical across engines, so this
single script verifies any engine adapter.

Prerequisites
-------------
Run ONE engine adapter so it serves on ws://127.0.0.1:27842, then run this:
  - Unity:  open fixtures/unity-test-project, open LoginScene.unity, press Play.
  - Godot:  open fixtures/godot-test-project (autoagent plugin enabled), run it.
Plus: pip install websockets jsonschema

Run
---
    python scripts/e2e/login_smoke.py

Exit code 0 = all checks passed; non-zero = a check failed.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE_SCHEMA_PATH = REPO_ROOT / "protocol" / "schema" / "node.json"

WS_URL = "ws://127.0.0.1:27842"
SUBPROTOCOL = "autoagent.v1"

# LoginScene key nodes that TASK-0008b pinned (must come back stable_id_source=pinned).
EXPECTED_PINNED = {
    "login_panel", "account_input_bg", "account_input_text",
    "password_input_bg", "password_input_text", "login_button_bg",
    "login_button_label", "error_label", "welcome_panel", "welcome_text",
}


class SmokeFailure(Exception):
    """A protocol check failed."""


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def rpc(ws, method: str, params: dict | None = None, req_id: int = 1):
    """Send one JSON-RPC request, return the `result`, raise on `error`."""
    request = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        request["params"] = params
    ws.send(json.dumps(request))
    response = json.loads(ws.recv())
    if response.get("id") != req_id:
        raise SmokeFailure(f"{method}: response id mismatch ({response.get('id')!r})")
    if "error" in response:
        raise SmokeFailure(f"{method}: server error {response['error']}")
    if "result" not in response:
        raise SmokeFailure(f"{method}: response has neither result nor error")
    return response["result"]


def run_smoke() -> None:
    try:
        from websockets.sync.client import connect
    except ImportError:
        raise SmokeFailure("websockets not installed — run: pip install websockets")

    try:
        import jsonschema
    except ImportError:
        raise SmokeFailure("jsonschema not installed — run: pip install jsonschema")

    node_schema = json.loads(NODE_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(node_schema)

    # ---- connect + subprotocol handshake -------------------------------
    _step("1. Connect + subprotocol handshake")
    try:
        ws = connect(WS_URL, subprotocols=[SUBPROTOCOL], open_timeout=5)
    except (ConnectionRefusedError, OSError) as exc:
        raise SmokeFailure(
            f"cannot reach {WS_URL} ({exc}). Is Unity playing the LoginScene?"
        )

    with ws:
        negotiated = ws.subprotocol
        if negotiated != SUBPROTOCOL:
            raise SmokeFailure(
                f"subprotocol not negotiated: expected {SUBPROTOCOL!r}, got {negotiated!r}"
            )
        _ok(f"connected, subprotocol = {negotiated}")

        # ---- negotiate_version -----------------------------------------
        _step("2. negotiate_version")
        result = rpc(ws, "negotiate_version",
                     {"client_version": "0.1"}, req_id=1)
        if not isinstance(result, dict) or not result.get("accepted"):
            raise SmokeFailure(f"negotiate_version not accepted: {result}")
        _ok(f"server_version = {result.get('server_version')}, accepted = True")

        # ---- dump_tree -------------------------------------------------
        _step("3. dump_tree + schema validation")
        nodes = rpc(ws, "dump_tree", req_id=2)
        if not isinstance(nodes, list) or not nodes:
            raise SmokeFailure(f"dump_tree returned no nodes: {nodes!r}")
        _ok(f"dumped {len(nodes)} nodes")

        schema_errors: list[str] = []
        for node in nodes:
            for err in validator.iter_errors(node):
                schema_errors.append(f"{node.get('id', '?')}: {err.message}")
        if schema_errors:
            raise SmokeFailure(
                "node schema validation failed:\n    "
                + "\n    ".join(schema_errors[:10])
            )
        _ok(f"all {len(nodes)} nodes valid against node.json")

        # ---- pinned-id coverage ----------------------------------------
        _step("4. LoginScene pinned-id coverage")
        by_id = {n["id"]: n for n in nodes}
        missing = EXPECTED_PINNED - by_id.keys()
        if missing:
            raise SmokeFailure(f"missing expected nodes: {sorted(missing)}")
        not_pinned = [
            nid for nid in EXPECTED_PINNED
            if by_id[nid].get("stable_id_source") != "pinned"
        ]
        if not_pinned:
            raise SmokeFailure(
                f"nodes present but not stable_id_source=pinned: {sorted(not_pinned)}"
            )
        _ok(f"all {len(EXPECTED_PINNED)} key nodes present and pinned")

        # parent/children consistency
        for node in nodes:
            for child_id in node.get("children_ids", []):
                child = by_id.get(child_id)
                if child is None:
                    raise SmokeFailure(f"{node['id']}: child {child_id} not in tree")
                if child.get("parent_id") != node["id"]:
                    raise SmokeFailure(
                        f"{child_id}.parent_id != {node['id']} "
                        f"(got {child.get('parent_id')!r})"
                    )
        _ok("parent/children links are consistent")

        # ---- find_widget by logical_role -------------------------------
        _step("5. find_widget by logical_role")
        buttons = rpc(ws, "find_widget", {"logical_role": "button"}, req_id=3)
        if "login_button_bg" not in buttons:
            raise SmokeFailure(f"find_widget(button) missed login_button_bg: {buttons}")
        _ok(f"logical_role=button -> {buttons}")

        inputs = rpc(ws, "find_widget", {"logical_role": "input"}, req_id=4)
        if not {"account_input_bg", "password_input_bg"} <= set(inputs):
            raise SmokeFailure(f"find_widget(input) incomplete: {inputs}")
        _ok(f"logical_role=input -> {inputs}")

        # ---- state_sprites on the button ------------------------------
        _step("6. state_sprites metadata")
        btn = by_id["login_button_bg"]
        sprites = (btn.get("meta") or {}).get("state_sprites") or {}
        if not {"normal", "hover", "pressed", "disabled"} <= sprites.keys():
            raise SmokeFailure(f"login_button_bg state_sprites incomplete: {sprites}")
        _ok(f"login_button_bg state_sprites = {sorted(sprites)}")

        # ---- take_screenshot -------------------------------------------
        _step("7. take_screenshot")
        shot_path = os.path.join(tempfile.gettempdir(), "autoagent_smoke_shot.png")
        shot_result = rpc(ws, "take_screenshot", {"path": shot_path}, req_id=5)
        if not isinstance(shot_result, dict) or not shot_result.get("path"):
            raise SmokeFailure(f"take_screenshot returned no path: {shot_result!r}")
        _ok(f"take_screenshot accepted, path = {shot_result.get('path')}")

    # ---- wrong subprotocol must be rejected ----------------------------
    _step("8. wrong subprotocol is rejected")
    accepted_bad = False
    try:
        bad_ws = connect(WS_URL, subprotocols=["autoagent.bogus"], open_timeout=5)
        try:
            bad_ws.send(json.dumps({
                "jsonrpc": "2.0", "method": "negotiate_version",
                "params": {"client_version": "0.1"}, "id": 99,
            }))
            bad_ws.recv(timeout=3)
            accepted_bad = True  # got a response → server did NOT reject
        except Exception:
            accepted_bad = False  # connection closed / errored → rejected
        finally:
            try:
                bad_ws.close()
            except Exception:
                pass
    except Exception:
        accepted_bad = False  # connect() refused at handshake → rejected
    if accepted_bad:
        raise SmokeFailure("server accepted a connection with a wrong subprotocol")
    _ok("connection with subprotocol 'autoagent.bogus' was rejected")


def main() -> int:
    print("AutoAgent — Login scene e2e smoke test")
    try:
        run_smoke()
    except SmokeFailure as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    print("\nALL CHECKS PASSED — Login scene automation is live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
