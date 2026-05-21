"""Cross-engine behavioral consistency check (TASK-0210).

Connects to two running AutoAgent adapters (Unity + Unreal Engine) and verifies
that the same login_ue.yaml / login.yaml task DSL produces semantically identical
behavior: the same stable IDs, the same logical roles, and the same post-login
visibility outcomes.

Usage
-----
    # Both engines must be running simultaneously:
    python scripts/e2e/cross_engine_consistency.py \\
        --unity-url ws://127.0.0.1:27842 \\
        --ue-url    ws://127.0.0.1:27843

Exit codes
----------
  0 — engines are behaviorally consistent
  1 — a consistency check failed
  2 — dependency not installed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

SUBPROTOCOL = "autoagent.v1"

# Stable IDs that MUST be present in both engines' login widget trees.
SHARED_PINNED_IDS = {
    "login_panel",
    "account_input_bg",
    "password_input_bg",
    "login_button_bg",
    "login_button_label",
    "error_label",
    "welcome_panel",
    "welcome_text",
}

# Logical roles expected in both engines.
EXPECTED_ROLES: dict[str, set[str]] = {
    "button": {"login_button_bg"},
    "input":  {"account_input_bg", "password_input_bg"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ConsistencyFailure(Exception):
    pass


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    raise ConsistencyFailure(msg)


def _step(label: str) -> None:
    print(f"\n=== {label} ===")


def rpc(ws, method: str, params: dict | None = None, req_id: int = 1) -> Any:
    payload = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        payload["params"] = params
    ws.send(json.dumps(payload))
    resp = json.loads(ws.recv())
    if resp.get("id") != req_id:
        raise ConsistencyFailure(f"{method}: id mismatch")
    if "error" in resp:
        raise ConsistencyFailure(f"{method}: {resp['error']}")
    if "result" not in resp:
        raise ConsistencyFailure(f"{method}: no result field")
    return resp["result"]


@dataclass
class EngineState:
    name: str
    pinned_ids: set[str]
    roles: dict[str, list[str]]       # role → [node_id, ...]
    initial_visibility: dict[str, bool]  # node_id → visible
    post_login_visibility: dict[str, bool]


def collect_state(ws, engine_name: str) -> EngineState:
    """Run the full login flow on one engine and collect behavioral state."""
    print(f"\n  [{engine_name}] connecting...")

    # negotiate
    ver = rpc(ws, "negotiate_version", {"client_version": "0.1"}, req_id=1)
    if not isinstance(ver, dict) or not ver.get("accepted"):
        raise ConsistencyFailure(f"[{engine_name}] negotiate_version not accepted")
    print(f"  [{engine_name}] server_version = {ver.get('server_version')}")

    # dump_tree — initial state
    nodes = rpc(ws, "dump_tree", req_id=2)
    by_id = {n["id"]: n for n in nodes}

    pinned = {
        nid for nid in by_id
        if by_id[nid].get("stable_id_source") == "pinned"
    }
    initial_vis = {
        nid: by_id[nid].get("visual", {}).get("visible", True)
        for nid in SHARED_PINNED_IDS
        if nid in by_id
    }

    # find_widget by role
    roles: dict[str, list[str]] = {}
    for role in EXPECTED_ROLES:
        found = rpc(ws, "find_widget", {"logical_role": role}, req_id=3 + len(roles))
        roles[role] = found if isinstance(found, list) else []

    # Run login flow
    rpc(ws, "send_text", {"id": "account_input_bg", "text": "admin"}, req_id=10)
    rpc(ws, "send_text", {"id": "password_input_bg", "text": "password"}, req_id=11)
    rpc(ws, "click", {"id": "login_button_bg"}, req_id=12)
    time.sleep(0.25)

    # dump_tree — post-login state
    nodes_post = rpc(ws, "dump_tree", req_id=13)
    by_id_post = {n["id"]: n for n in nodes_post}
    post_vis = {
        nid: by_id_post[nid].get("visual", {}).get("visible", True)
        for nid in SHARED_PINNED_IDS
        if nid in by_id_post
    }

    print(f"  [{engine_name}] collected: {len(pinned)} pinned IDs, "
          f"initial_vis={len(initial_vis)} nodes, post_vis={len(post_vis)} nodes")

    return EngineState(
        name=engine_name,
        pinned_ids=pinned,
        roles=roles,
        initial_visibility=initial_vis,
        post_login_visibility=post_vis,
    )


# ---------------------------------------------------------------------------
# Consistency checks
# ---------------------------------------------------------------------------


def compare_states(unity: EngineState, ue: EngineState) -> None:
    """Assert that Unity and UE behave identically for the login flow."""

    # 1. Both engines must have all shared pinned IDs.
    _step("C1. Shared stable IDs present in both engines")
    for nid in SHARED_PINNED_IDS:
        u_has = nid in unity.pinned_ids
        ue_has = nid in ue.pinned_ids
        if not u_has and not ue_has:
            _fail(f"'{nid}' is missing from BOTH engines")
        if not u_has:
            _fail(f"'{nid}' missing from Unity (present in UE)")
        if not ue_has:
            _fail(f"'{nid}' missing from UE (present in Unity)")
    _ok(f"all {len(SHARED_PINNED_IDS)} shared IDs present in both engines")

    # 2. Logical role coverage must match.
    _step("C2. Logical role → node coverage matches")
    for role, expected_ids in EXPECTED_ROLES.items():
        u_found = set(unity.roles.get(role, []))
        ue_found = set(ue.roles.get(role, []))
        if not expected_ids <= u_found:
            _fail(f"Unity missing nodes for role={role!r}: {expected_ids - u_found}")
        if not expected_ids <= ue_found:
            _fail(f"UE missing nodes for role={role!r}: {expected_ids - ue_found}")
    _ok(f"logical roles {sorted(EXPECTED_ROLES)} match in both engines")

    # 3. Initial visibility must be equivalent.
    _step("C3. Initial visibility state matches")
    vis_keys = SHARED_PINNED_IDS & unity.initial_visibility.keys() \
                                 & ue.initial_visibility.keys()
    mismatches: list[str] = []
    for nid in vis_keys:
        u_vis = unity.initial_visibility[nid]
        ue_vis = ue.initial_visibility[nid]
        if u_vis != ue_vis:
            mismatches.append(
                f"  {nid}: Unity={u_vis}  UE={ue_vis}"
            )
    if mismatches:
        _fail(
            "Initial visibility mismatch between engines:\n"
            + "\n".join(mismatches)
        )
    _ok(f"initial visibility identical across {len(vis_keys)} key nodes")

    # 4. Post-login visibility must be equivalent.
    _step("C4. Post-login visibility state matches")
    post_keys = SHARED_PINNED_IDS & unity.post_login_visibility.keys() \
                                  & ue.post_login_visibility.keys()
    post_mismatches: list[str] = []
    for nid in post_keys:
        u_vis = unity.post_login_visibility[nid]
        ue_vis = ue.post_login_visibility[nid]
        if u_vis != ue_vis:
            post_mismatches.append(
                f"  {nid}: Unity={u_vis}  UE={ue_vis}"
            )
    if post_mismatches:
        _fail(
            "Post-login visibility mismatch between engines:\n"
            + "\n".join(post_mismatches)
        )
    _ok(f"post-login visibility identical across {len(post_keys)} key nodes")

    # 5. Critical post-login assertions.
    _step("C5. Critical post-login assertions (both engines)")
    for eng in (unity, ue):
        post = eng.post_login_visibility
        if not post.get("welcome_panel", False):
            _fail(f"[{eng.name}] welcome_panel not visible after login")
        if not post.get("welcome_text", False):
            _fail(f"[{eng.name}] welcome_text not visible after login")
        if post.get("login_panel", True):
            _fail(f"[{eng.name}] login_panel still visible after login")
    _ok("both engines: welcome visible, login hidden after successful login")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cross_engine_consistency",
        description="Cross-engine behavioral consistency check (TASK-0210).",
    )
    p.add_argument("--unity-url", default="ws://127.0.0.1:27842",
                   help="WebSocket URL for the Unity adapter.")
    p.add_argument("--ue-url", default="ws://127.0.0.1:27843",
                   help="WebSocket URL for the UE adapter.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        from websockets.sync.client import connect
    except ImportError:
        print("ERROR: pip install websockets", file=sys.stderr)
        return 2

    print("AutoAgent — Cross-engine consistency check (TASK-0210)")
    print(f"  Unity adapter : {args.unity_url}")
    print(f"  UE adapter    : {args.ue_url}")

    try:
        _step("Connecting to Unity adapter")
        with connect(args.unity_url, subprotocols=[SUBPROTOCOL],
                     open_timeout=8) as ws_unity:
            unity_state = collect_state(ws_unity, "Unity")

        _step("Connecting to UE adapter")
        with connect(args.ue_url, subprotocols=[SUBPROTOCOL],
                     open_timeout=8) as ws_ue:
            ue_state = collect_state(ws_ue, "UE")

        _step("Running consistency comparisons")
        compare_states(unity_state, ue_state)

    except (ConnectionRefusedError, OSError) as exc:
        print(f"\nFAILED: Cannot connect — {exc}", file=sys.stderr)
        print("  Ensure both Unity and UE adapters are running simultaneously.",
              file=sys.stderr)
        return 1
    except ConsistencyFailure as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nCROSS-ENGINE CONSISTENCY: PASSED — Unity and UE produce identical behavior.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
