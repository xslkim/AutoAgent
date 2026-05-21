"""TASK-0210: Offline unit tests for UE e2e scripts.

Tests the protocol helpers (rpc(), collect_state(), compare_states()) and
CLI parsers without a live adapter connection.  Network-dependent paths
are covered by mocks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "e2e"))  # scripts/e2e

import ue_login_e2e as ule               # noqa: E402
import cross_engine_consistency as cec  # noqa: E402


# ===========================================================================
# ue_login_e2e — offline helpers
# ===========================================================================


class TestRpcHelper:
    """rpc() parses JSON-RPC 2.0 correctly."""

    def _make_ws(self, response: dict) -> MagicMock:
        ws = MagicMock()
        ws.recv.return_value = json.dumps(response)
        return ws

    def test_rpc_returns_result(self):
        ws = self._make_ws({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        result = ule.rpc(ws, "some_method", req_id=1)
        assert result == {"ok": True}

    def test_rpc_raises_on_error(self):
        ws = self._make_ws({
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32601, "message": "method not found"},
        })
        with pytest.raises(ule.E2EFailure, match="method not found"):
            ule.rpc(ws, "bad_method", req_id=1)

    def test_rpc_raises_on_id_mismatch(self):
        ws = self._make_ws({"jsonrpc": "2.0", "id": 99, "result": {}})
        with pytest.raises(ule.E2EFailure, match="id mismatch"):
            ule.rpc(ws, "method", req_id=1)

    def test_rpc_raises_on_missing_result(self):
        ws = self._make_ws({"jsonrpc": "2.0", "id": 1})
        with pytest.raises(ule.E2EFailure, match="neither result"):
            ule.rpc(ws, "method", req_id=1)


class TestCLIParser:
    def test_default_url(self):
        args = ule.build_parser().parse_args([])
        assert args.url == "ws://127.0.0.1:27842"

    def test_custom_url(self):
        args = ule.build_parser().parse_args(["--url", "ws://10.0.0.1:9999"])
        assert args.url == "ws://10.0.0.1:9999"


# ===========================================================================
# cross_engine_consistency — compare_states()
# ===========================================================================


def _make_state(name: str, *, pinned_ids=None, roles=None,
                initial_vis=None, post_vis=None) -> cec.EngineState:
    """Build an EngineState fixture with sensible defaults."""
    if pinned_ids is None:
        pinned_ids = set(cec.SHARED_PINNED_IDS)
    if roles is None:
        roles = {
            "button": ["login_button_bg"],
            "input": ["account_input_bg", "password_input_bg"],
        }
    if initial_vis is None:
        initial_vis = {
            "login_panel": True,
            "welcome_panel": False,
            "welcome_text": False,
            "login_button_bg": True,
            "account_input_bg": True,
            "password_input_bg": True,
            "login_button_label": True,
            "error_label": False,
        }
    if post_vis is None:
        post_vis = {
            "login_panel": False,
            "welcome_panel": True,
            "welcome_text": True,
            "login_button_bg": True,
            "account_input_bg": True,
            "password_input_bg": True,
            "login_button_label": True,
            "error_label": False,
        }
    return cec.EngineState(
        name=name,
        pinned_ids=pinned_ids,
        roles=roles,
        initial_visibility=initial_vis,
        post_login_visibility=post_vis,
    )


class TestCompareStates:
    """compare_states() passes when engines are equivalent, fails otherwise."""

    def test_identical_states_pass(self):
        unity = _make_state("Unity")
        ue = _make_state("UE")
        # Must not raise.
        cec.compare_states(unity, ue)

    def test_missing_id_in_ue_fails(self):
        ue_pinned = set(cec.SHARED_PINNED_IDS) - {"welcome_panel"}
        unity = _make_state("Unity")
        ue = _make_state("UE", pinned_ids=ue_pinned)
        with pytest.raises(cec.ConsistencyFailure, match="welcome_panel"):
            cec.compare_states(unity, ue)

    def test_missing_id_in_unity_fails(self):
        unity_pinned = set(cec.SHARED_PINNED_IDS) - {"login_button_bg"}
        unity = _make_state("Unity", pinned_ids=unity_pinned)
        ue = _make_state("UE")
        with pytest.raises(cec.ConsistencyFailure, match="login_button_bg"):
            cec.compare_states(unity, ue)

    def test_initial_visibility_mismatch_fails(self):
        unity = _make_state("Unity")
        # UE has welcome_panel visible initially (wrong)
        bad_init = {**unity.initial_visibility, "welcome_panel": True}
        ue = _make_state("UE", initial_vis=bad_init)
        with pytest.raises(cec.ConsistencyFailure, match="welcome_panel"):
            cec.compare_states(unity, ue)

    def test_post_login_welcome_hidden_fails(self):
        unity = _make_state("Unity")
        # UE welcome_panel remains hidden after login (wrong)
        bad_post = {**unity.post_login_visibility, "welcome_panel": False}
        ue = _make_state("UE", post_vis=bad_post)
        with pytest.raises(cec.ConsistencyFailure, match="welcome_panel"):
            cec.compare_states(unity, ue)

    def test_post_login_panel_still_visible_fails(self):
        unity = _make_state("Unity")
        # UE login_panel remains visible after login (wrong)
        bad_post = {**unity.post_login_visibility, "login_panel": True}
        ue = _make_state("UE", post_vis=bad_post)
        with pytest.raises(cec.ConsistencyFailure, match="login_panel"):
            cec.compare_states(unity, ue)

    def test_role_mismatch_fails(self):
        unity = _make_state("Unity")
        # UE missing account_input_bg from input role
        bad_roles = {
            "button": ["login_button_bg"],
            "input": ["password_input_bg"],  # account_input_bg missing
        }
        ue = _make_state("UE", roles=bad_roles)
        with pytest.raises(cec.ConsistencyFailure, match="input"):
            cec.compare_states(unity, ue)


class TestCrossEngineCLIParser:
    def test_default_urls(self):
        args = cec.build_parser().parse_args([])
        assert "27842" in args.unity_url
        assert "27843" in args.ue_url

    def test_custom_urls(self):
        args = cec.build_parser().parse_args([
            "--unity-url", "ws://localhost:9001",
            "--ue-url",    "ws://localhost:9002",
        ])
        assert args.unity_url == "ws://localhost:9001"
        assert args.ue_url == "ws://localhost:9002"
