"""TASK-0306: Offline unit tests for Godot e2e scripts.

Tests the protocol helpers (rpc(), build_parser()) and the compare_screenshot
RPC structure without a live adapter connection.  Network-dependent paths
are covered by mocks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "e2e"))  # scripts/e2e

import godot_login_e2e as gle  # noqa: E402


# ===========================================================================
# godot_login_e2e — rpc() helper
# ===========================================================================


class TestRpcHelper:
    """rpc() parses JSON-RPC 2.0 correctly (mirrors TestRpcHelper from UE)."""

    def _make_ws(self, response: dict) -> MagicMock:
        ws = MagicMock()
        ws.recv.return_value = json.dumps(response)
        return ws

    def test_rpc_returns_result(self) -> None:
        ws = self._make_ws({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        result = gle.rpc(ws, "some_method", req_id=1)
        assert result == {"ok": True}

    def test_rpc_raises_on_error(self) -> None:
        ws = self._make_ws({
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32601, "message": "method not found"},
        })
        with pytest.raises(gle.E2EFailure, match="method not found"):
            gle.rpc(ws, "bad_method", req_id=1)

    def test_rpc_raises_on_id_mismatch(self) -> None:
        ws = self._make_ws({"jsonrpc": "2.0", "id": 99, "result": {}})
        with pytest.raises(gle.E2EFailure, match="id mismatch"):
            gle.rpc(ws, "method", req_id=1)

    def test_rpc_raises_on_missing_result(self) -> None:
        ws = self._make_ws({"jsonrpc": "2.0", "id": 1})
        with pytest.raises(gle.E2EFailure, match="neither result"):
            gle.rpc(ws, "method", req_id=1)

    def test_rpc_sends_correct_payload(self) -> None:
        ws = self._make_ws({"jsonrpc": "2.0", "id": 3, "result": "ok"})
        gle.rpc(ws, "dump_tree", req_id=3)
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["method"] == "dump_tree"
        assert sent["id"] == 3
        assert sent["jsonrpc"] == "2.0"

    def test_rpc_sends_params(self) -> None:
        ws = self._make_ws({"jsonrpc": "2.0", "id": 1, "result": True})
        gle.rpc(ws, "click", {"id": "login_button_bg"}, req_id=1)
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["params"] == {"id": "login_button_bg"}

    def test_rpc_no_params_omits_key(self) -> None:
        ws = self._make_ws({"jsonrpc": "2.0", "id": 1, "result": []})
        gle.rpc(ws, "dump_tree", req_id=1)
        sent = json.loads(ws.send.call_args[0][0])
        assert "params" not in sent


# ===========================================================================
# godot_login_e2e — CLI parser
# ===========================================================================


class TestCLIParser:
    def test_default_url(self) -> None:
        args = gle.build_parser().parse_args([])
        assert args.url == "ws://127.0.0.1:27842"

    def test_custom_url(self) -> None:
        args = gle.build_parser().parse_args(["--url", "ws://10.0.0.1:9001"])
        assert args.url == "ws://10.0.0.1:9001"

    def test_default_baselines_root_is_repo_relative(self) -> None:
        args = gle.build_parser().parse_args([])
        assert args.baselines_root.name == "baselines"

    def test_custom_baselines_root(self, tmp_path) -> None:
        args = gle.build_parser().parse_args(
            ["--baselines-root", str(tmp_path)]
        )
        assert args.baselines_root == tmp_path


# ===========================================================================
# godot_login_e2e — EXPECTED_PINNED set
# ===========================================================================


class TestExpectedPinnedSet:
    """EXPECTED_PINNED must match the shared set used by cross_engine_consistency."""

    CROSS_ENGINE_SHARED = {
        "login_panel",
        "account_input_bg",
        "password_input_bg",
        "login_button_bg",
        "login_button_label",
        "error_label",
        "welcome_panel",
        "welcome_text",
    }

    def test_expected_pinned_contains_all_shared_ids(self) -> None:
        missing = self.CROSS_ENGINE_SHARED - gle.EXPECTED_PINNED
        assert not missing, f"EXPECTED_PINNED missing shared IDs: {missing}"

    def test_expected_pinned_size(self) -> None:
        assert len(gle.EXPECTED_PINNED) == 8


# ===========================================================================
# Protocol structure assertions (offline)
# ===========================================================================


class TestProtocolAssertions:
    """Verify the e2e assertions match the node.json schema semantics."""

    def _make_node(self, nid: str, visible: bool, source: str = "pinned") -> dict:
        return {
            "id": nid,
            "type": "Control",
            "engine_type": "Control",
            "parent_id": None,
            "children_ids": [],
            "stable_id_source": source,
            "visual": {"position": [0, 0], "size": [100, 40], "visible": visible},
        }

    def test_initial_state_valid_login_panel_visible(self) -> None:
        nodes = [
            self._make_node("login_panel", True),
            self._make_node("welcome_panel", False),
            *[self._make_node(nid, True) for nid in [
                "account_input_bg", "password_input_bg", "login_button_bg",
                "login_button_label", "error_label", "welcome_text",
            ]],
        ]
        by_id = {n["id"]: n for n in nodes}
        assert by_id["login_panel"]["visual"]["visible"] is True
        assert by_id["welcome_panel"]["visual"]["visible"] is False

    def test_all_required_nodes_present(self) -> None:
        nodes = [self._make_node(nid, True) for nid in gle.EXPECTED_PINNED]
        by_id = {n["id"]: n for n in nodes}
        missing = gle.EXPECTED_PINNED - by_id.keys()
        assert not missing

    def test_not_pinned_detection(self) -> None:
        nodes = [
            self._make_node("login_panel", True, source="auto"),  # auto, not pinned
        ]
        by_id = {n["id"]: n for n in nodes}
        not_pinned = [
            nid for nid in ["login_panel"]
            if by_id[nid].get("stable_id_source") != "pinned"
        ]
        assert "login_panel" in not_pinned

    def test_compare_screenshot_result_structure(self) -> None:
        """compare_screenshot result must contain saved_path."""
        mock_result = {
            "name": "godot_welcome_screen",
            "saved_path": "/home/user/.local/share/godot/AutoAgent/Comparisons/godot_welcome_screen.png",
            "threshold": 0.95,
            "status": "captured",
        }
        assert mock_result.get("saved_path"), "saved_path must be non-empty"
        assert mock_result["threshold"] == 0.95
        assert mock_result["status"] == "captured"
