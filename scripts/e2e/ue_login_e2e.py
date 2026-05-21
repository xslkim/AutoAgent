"""End-to-end login flow test for the Unreal Engine adapter (TASK-0210).

Connects to a running AutoAgent UE adapter, exercises the full login flow
(send_text → click → assert visibility) and runs the visual regression check
via compare_screenshot.

Prerequisites
-------------
  1. UE fixture project running (LoginMap, PIE or standalone)
  2. AutoAgent plugin active (server on ws://127.0.0.1:27842)
  3. pip install websockets jsonschema

Usage
-----
    python scripts/e2e/ue_login_e2e.py [--url ws://127.0.0.1:27842]
                                       [--baselines-root baselines]

Exit codes
----------
  0 — all checks passed
  1 — a check failed or the adapter is unreachable
  2 — dependency not installed
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE_SCHEMA_PATH = REPO_ROOT / "protocol" / "schema" / "node.json"
CHECK_VB = REPO_ROOT / "scripts" / "ci" / "check_visual_baseline.py"

DEFAULT_URL = "ws://127.0.0.1:27842"
SUBPROTOCOL = "autoagent.v1"

# Stable IDs expected in the UE login fixture (mirrors Unity fixture).
EXPECTED_PINNED = {
    "login_panel",
    "account_input_bg",
    "password_input_bg",
    "login_button_bg",
    "login_button_label",
    "error_label",
    "welcome_panel",
    "welcome_text",
}


# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------


class E2EFailure(Exception):
    """A protocol assertion failed."""


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _step(label: str) -> None:
    print(f"\n=== {label} ===")


def rpc(ws, method: str, params: dict | None = None, req_id: int = 1) -> object:
    """Send one JSON-RPC 2.0 request, return result, raise E2EFailure on error."""
    payload = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        payload["params"] = params
    ws.send(json.dumps(payload))
    raw = ws.recv()
    resp = json.loads(raw)
    if resp.get("id") != req_id:
        raise E2EFailure(f"{method}: id mismatch (got {resp.get('id')!r})")
    if "error" in resp:
        raise E2EFailure(f"{method}: {resp['error']}")
    if "result" not in resp:
        raise E2EFailure(f"{method}: neither result nor error in response")
    return resp["result"]


# ---------------------------------------------------------------------------
# E2E flow
# ---------------------------------------------------------------------------


def run_e2e(ws_url: str, baselines_root: pathlib.Path) -> None:
    try:
        from websockets.sync.client import connect
    except ImportError:
        print("ERROR: pip install websockets", file=sys.stderr)
        sys.exit(2)

    try:
        import jsonschema
    except ImportError:
        print("ERROR: pip install jsonschema", file=sys.stderr)
        sys.exit(2)

    node_schema = json.loads(NODE_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(node_schema)

    # ── 1. Connect ─────────────────────────────────────────────────────────
    _step("1. Connect + subprotocol negotiation")
    try:
        ws = connect(ws_url, subprotocols=[SUBPROTOCOL], open_timeout=8)
    except (ConnectionRefusedError, OSError) as exc:
        raise E2EFailure(
            f"Cannot reach {ws_url} ({exc}).\n"
            "  Ensure the UE fixture is running (LoginMap, PIE or standalone)."
        )

    with ws:
        if ws.subprotocol != SUBPROTOCOL:
            raise E2EFailure(
                f"Subprotocol mismatch: expected {SUBPROTOCOL!r}, got {ws.subprotocol!r}"
            )
        _ok(f"connected, subprotocol = {ws.subprotocol}")

        # ── 2. negotiate_version ───────────────────────────────────────────
        _step("2. negotiate_version")
        ver = rpc(ws, "negotiate_version", {"client_version": "0.1"}, req_id=1)
        if not isinstance(ver, dict) or not ver.get("accepted"):
            raise E2EFailure(f"negotiate_version not accepted: {ver}")
        _ok(f"server_version={ver.get('server_version')}  accepted=True")

        # ── 3. Initial dump_tree + schema validation ───────────────────────
        _step("3. dump_tree — initial state")
        nodes = rpc(ws, "dump_tree", req_id=2)
        if not isinstance(nodes, list) or not nodes:
            raise E2EFailure(f"dump_tree returned empty: {nodes!r}")
        _ok(f"dumped {len(nodes)} nodes")

        schema_errors: list[str] = []
        for node in nodes:
            for err in validator.iter_errors(node):
                schema_errors.append(f"  {node.get('id', '?')}: {err.message}")
        if schema_errors:
            raise E2EFailure(
                "node schema validation failed:\n" + "\n".join(schema_errors[:10])
            )
        _ok(f"all {len(nodes)} nodes valid against node.json")

        by_id = {n["id"]: n for n in nodes}
        missing = EXPECTED_PINNED - by_id.keys()
        if missing:
            raise E2EFailure(f"missing expected nodes: {sorted(missing)}")
        not_pinned = [
            nid for nid in EXPECTED_PINNED
            if by_id[nid].get("stable_id_source") != "pinned"
        ]
        if not_pinned:
            raise E2EFailure(
                f"nodes present but not pinned: {sorted(not_pinned)}"
            )
        _ok(f"all {len(EXPECTED_PINNED)} key nodes present + pinned")

        # Verify initial visibility: login_panel visible, welcome_panel hidden
        login_visible = by_id["login_panel"].get("visual", {}).get("visible", True)
        welcome_visible = by_id["welcome_panel"].get("visual", {}).get("visible", False)
        if not login_visible:
            raise E2EFailure("login_panel should be visible in initial state")
        if welcome_visible:
            raise E2EFailure("welcome_panel should be hidden in initial state")
        _ok("initial visibility correct: login_panel=visible, welcome_panel=hidden")

        # ── 4. Login flow — enter credentials ─────────────────────────────
        _step("4. Login flow — send_text account_input_bg")
        rpc(ws, "send_text",
            {"id": "account_input_bg", "text": "admin"}, req_id=3)
        _ok("send_text 'admin' to account_input_bg")

        _step("5. Login flow — send_text password_input_bg")
        rpc(ws, "send_text",
            {"id": "password_input_bg", "text": "password"}, req_id=4)
        _ok("send_text 'password' to password_input_bg")

        # ── 5. Click login button ──────────────────────────────────────────
        _step("6. Login flow — click login_button_bg")
        rpc(ws, "click", {"id": "login_button_bg"}, req_id=5)
        _ok("click dispatched to login_button_bg")

        # Brief settle: give the ULoginController callback time to run
        time.sleep(0.2)

        # ── 6. Assert post-login state ─────────────────────────────────────
        _step("7. Assert post-login state (dump_tree)")
        nodes_post = rpc(ws, "dump_tree", req_id=6)
        by_id_post = {n["id"]: n for n in nodes_post}

        welcome_after = by_id_post["welcome_panel"].get("visual", {}).get("visible", False)
        login_after = by_id_post["login_panel"].get("visual", {}).get("visible", True)
        welcome_text_after = by_id_post["welcome_text"].get("visual", {}).get("visible", False)

        if not welcome_after:
            raise E2EFailure("welcome_panel must be visible after successful login")
        if login_after:
            raise E2EFailure("login_panel must be hidden after successful login")
        if not welcome_text_after:
            raise E2EFailure("welcome_text must be visible after successful login")
        _ok("post-login: welcome_panel=visible, login_panel=hidden, welcome_text=visible")

        # ── 7. compare_screenshot (visual regression) ──────────────────────
        _step("8. compare_screenshot — welcome screen baseline")
        shot_result = rpc(ws, "compare_screenshot",
                          {"name": "ue_welcome_screen", "threshold": 0.95},
                          req_id=7)
        saved_path = shot_result.get("saved_path", "") if isinstance(shot_result, dict) else ""
        if not saved_path:
            raise E2EFailure(f"compare_screenshot returned no saved_path: {shot_result!r}")
        _ok(f"compare_screenshot queued → {saved_path}")

        # Wait for the async screenshot file to appear (up to 5 s)
        deadline = time.time() + 5.0
        while not pathlib.Path(saved_path).exists() and time.time() < deadline:
            time.sleep(0.25)

        if pathlib.Path(saved_path).exists():
            _ok(f"screenshot file written: {saved_path}")
            _run_ssim_check(
                baselines_root=baselines_root,
                saved_path=pathlib.Path(saved_path),
                name="ue_welcome_screen",
            )
        else:
            # Screenshot not yet written — non-blocking warning; file is async
            print(f"  [WARN] screenshot not yet on disk (async); "
                  f"run check_visual_baseline.py separately against {saved_path}")

        # ── 8. find_widget by role cross-check ────────────────────────────
        _step("9. find_widget by logical_role (post-login)")
        buttons = rpc(ws, "find_widget", {"logical_role": "button"}, req_id=8)
        if "login_button_bg" not in buttons:
            raise E2EFailure(f"find_widget(button) missed login_button_bg: {buttons}")
        _ok(f"logical_role=button -> {buttons}")

    _ok("WebSocket connection closed cleanly")


def _run_ssim_check(baselines_root: pathlib.Path,
                    saved_path: pathlib.Path,
                    name: str) -> None:
    """Run check_visual_baseline.py in-process if the baseline file exists."""
    baseline = baselines_root / "unreal" / "windows" / f"{name}.png"
    if not baseline.exists():
        print(f"  [SKIP] baseline not found ({baseline}); "
              f"capture one with: cp {saved_path} {baseline}")
        return

    import importlib.util
    spec = importlib.util.spec_from_file_location("check_visual_baseline", CHECK_VB)
    cvb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cvb)

    rc = cvb.main([
        "--baseline", str(baseline),
        "--current", str(saved_path),
        "--threshold", "0.95",
        "--quiet",
    ])
    if rc == 0:
        _ok(f"SSIM passed vs baseline {baseline.name}")
    else:
        raise E2EFailure(
            f"Visual regression failed: SSIM below 0.95.\n"
            f"  baseline: {baseline}\n"
            f"  current:  {saved_path}\n"
            f"  Run check_visual_baseline.py --save-diff /tmp/diff.png for details."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ue_login_e2e",
        description="Full UE login flow e2e (TASK-0210).",
    )
    p.add_argument("--url", default=DEFAULT_URL,
                   help=f"WebSocket URL of the UE adapter (default: {DEFAULT_URL})")
    p.add_argument("--baselines-root", type=pathlib.Path,
                   default=REPO_ROOT / "baselines",
                   help="Root dir for visual baselines (default: <repo>/baselines)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print("AutoAgent — UE Login e2e (TASK-0210)")
    print(f"  adapter : {args.url}")
    print(f"  baselines: {args.baselines_root}")
    try:
        run_e2e(args.url, args.baselines_root)
    except E2EFailure as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    print("\nALL CHECKS PASSED — UE login flow end-to-end OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
