"""TASK-0117 verification — MCP tools call real wire methods.

Strategy
--------
*Unit tests* (the vast majority): a mock ``WebSocketClient`` is set as the
active client via ``set_client``.  Each test asserts that the tool

  1. Calls ``client.call`` with the correct wire-method name and params.
  2. Maps the result back to the expected MCP-tool return shape.

*Integration test* (``test_integration_*``): a minimal in-process WebSocket
server (the "fake adapter") is started on an ephemeral port.  A real
``WebSocketClient`` connects to it.  Each supported wire method is exercised
end-to-end.

Running
-------
    pytest mcp-server/tests/test_tools.py -v
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
import websockets
import websockets.asyncio.server

from autoagent_mcp.connector import AdapterError, WebSocketClient, set_client
from autoagent_mcp.server import build_server

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """AsyncMock WebSocketClient set as the active connector client."""
    client = AsyncMock(spec=WebSocketClient)
    client.connected = True
    client.call = AsyncMock(return_value=None)
    set_client(client)
    yield client
    set_client(None)


@pytest.fixture
def mcp(mock_client):
    """FastMCP server built with a mock client already installed."""
    return build_server()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _result(tool_result: Any) -> Any:
    """Extract the Python value from a FastMCP call_tool result.

    FastMCP returns ``(content_list, structured_output)`` where
    ``structured_output`` is the tool's return value as a Python object.
    Fall back to parsing the first TextContent if the tuple shape differs.
    """
    if not tool_result:
        return None
    # Primary path: FastMCP 1.x returns (content_list, structured_output)
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    # Fallback: parse first TextContent item
    first = tool_result[0] if tool_result else None
    if hasattr(first, "text"):
        return json.loads(first.text)
    return first


# ---------------------------------------------------------------------------
# dump.py — dump_tree, find_widget, get_widget
# ---------------------------------------------------------------------------


class TestDumpTree:
    @pytest.mark.asyncio
    async def test_calls_dump_tree_wire_method(self, mcp, mock_client):
        mock_client.call.return_value = []
        await mcp.call_tool("dump_tree", {})
        mock_client.call.assert_called_once_with("dump_tree", {})

    @pytest.mark.asyncio
    async def test_filters_invisible_nodes_by_default(self, mcp, mock_client):
        mock_client.call.return_value = [
            {"id": "a", "visual": {"visible": True}},
            {"id": "b", "visual": {"visible": False}},
        ]
        r = _result(await mcp.call_tool("dump_tree", {}))
        ids = [n["id"] for n in r["nodes"]]
        assert "a" in ids
        assert "b" not in ids, "invisible node must be filtered by default"

    @pytest.mark.asyncio
    async def test_include_invisible_keeps_all(self, mcp, mock_client):
        mock_client.call.return_value = [
            {"id": "a", "visual": {"visible": True}},
            {"id": "b", "visual": {"visible": False}},
        ]
        r = _result(await mcp.call_tool("dump_tree", {"include_invisible": True}))
        assert len(r["nodes"]) == 2

    @pytest.mark.asyncio
    async def test_max_depth_prunes_deep_nodes(self, mcp, mock_client):
        mock_client.call.return_value = [
            {"id": "root", "parent_id": None, "visual": {"visible": True}},
            {"id": "child", "parent_id": "root", "visual": {"visible": True}},
            {"id": "grandchild", "parent_id": "child", "visual": {"visible": True}},
        ]
        r = _result(await mcp.call_tool("dump_tree", {"include_invisible": True, "max_depth": 1}))
        ids = [n["id"] for n in r["nodes"]]
        assert "root" in ids
        assert "child" in ids
        assert "grandchild" not in ids, "depth > max_depth must be pruned"

    @pytest.mark.asyncio
    async def test_returns_captured_at_timestamp(self, mcp, mock_client):
        mock_client.call.return_value = []
        before = time.time()
        r = _result(await mcp.call_tool("dump_tree", {}))
        assert r["captured_at"] >= before


class TestFindWidget:
    @pytest.mark.asyncio
    async def test_calls_find_widget_with_logical_role(self, mcp, mock_client):
        mock_client.call.return_value = ["btn1"]
        await mcp.call_tool("find_widget", {"logical_role": "button"})
        mock_client.call.assert_called_once_with(
            "find_widget", {"logical_role": "button"}
        )

    @pytest.mark.asyncio
    async def test_calls_find_widget_with_text(self, mcp, mock_client):
        mock_client.call.return_value = ["label1"]
        await mcp.call_tool("find_widget", {"text": "Login"})
        mock_client.call.assert_called_once_with("find_widget", {"text": "Login"})

    @pytest.mark.asyncio
    async def test_returns_ids_list(self, mcp, mock_client):
        mock_client.call.return_value = ["a", "b"]
        r = _result(await mcp.call_tool("find_widget", {"logical_role": "button"}))
        assert r["ids"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_ids(self, mcp, mock_client):
        mock_client.call.return_value = []
        r = _result(await mcp.call_tool("find_widget", {"text": "ghost"}))
        assert r["ids"] == []


class TestGetWidget:
    @pytest.mark.asyncio
    async def test_calls_get_widget_with_id(self, mcp, mock_client):
        mock_client.call.return_value = {"id": "my_node"}
        await mcp.call_tool("get_widget", {"id": "my_node"})
        mock_client.call.assert_called_once_with("get_widget", {"id": "my_node"})

    @pytest.mark.asyncio
    async def test_returns_node(self, mcp, mock_client):
        node = {"id": "my_node", "type": "Button"}
        mock_client.call.return_value = node
        r = _result(await mcp.call_tool("get_widget", {"id": "my_node"}))
        assert r["node"] == node


# ---------------------------------------------------------------------------
# click.py — click, drag, scroll, key_press
# ---------------------------------------------------------------------------


class TestClick:
    @pytest.mark.asyncio
    async def test_calls_click_with_id(self, mcp, mock_client):
        await mcp.call_tool("click", {"id": "login_btn"})
        mock_client.call.assert_called_once_with("click", {"id": "login_btn"})

    @pytest.mark.asyncio
    async def test_returns_success(self, mcp, mock_client):
        r = _result(await mcp.call_tool("click", {"id": "btn"}))
        assert r["success"] is True


class TestDrag:
    @pytest.mark.asyncio
    async def test_calls_drag_with_params(self, mcp, mock_client):
        await mcp.call_tool("drag", {"from_id": "item", "to_id": "slot"})
        mock_client.call.assert_called_once_with(
            "drag", {"from_id": "item", "to_id": "slot", "duration_ms": 200}
        )

    @pytest.mark.asyncio
    async def test_custom_duration_ms(self, mcp, mock_client):
        await mcp.call_tool("drag", {"from_id": "a", "to_id": "b", "duration_ms": 500})
        args = mock_client.call.call_args
        assert args[0][1]["duration_ms"] == 500


class TestScroll:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("direction,exp_dx,exp_dy", [
        ("up",    0.0,   100.0),
        ("down",  0.0,  -100.0),
        ("left", -100.0,  0.0),
        ("right", 100.0,  0.0),
    ])
    async def test_direction_maps_to_delta(
        self, mcp, mock_client, direction, exp_dx, exp_dy
    ):
        await mcp.call_tool("scroll", {"id": "sv", "direction": direction, "amount": 100.0})
        args = mock_client.call.call_args[0]
        assert args[0] == "scroll"
        assert args[1]["delta_x"] == pytest.approx(exp_dx)
        assert args[1]["delta_y"] == pytest.approx(exp_dy)


class TestKeyPress:
    @pytest.mark.asyncio
    async def test_calls_key_press_with_id_and_key(self, mcp, mock_client):
        await mcp.call_tool("key_press", {"id": "field", "key": "Return"})
        mock_client.call.assert_called_once_with(
            "key_press", {"id": "field", "key": "Return"}
        )


# ---------------------------------------------------------------------------
# text.py — send_text
# ---------------------------------------------------------------------------


class TestSendText:
    @pytest.mark.asyncio
    async def test_calls_send_text_with_params(self, mcp, mock_client):
        await mcp.call_tool("send_text", {"id": "inp", "text": "hello"})
        mock_client.call.assert_called_once_with(
            "send_text", {"id": "inp", "text": "hello", "clear_first": True}
        )

    @pytest.mark.asyncio
    async def test_clear_first_false(self, mcp, mock_client):
        await mcp.call_tool("send_text", {"id": "inp", "text": "x", "clear_first": False})
        args = mock_client.call.call_args[0][1]
        assert args["clear_first"] is False


# ---------------------------------------------------------------------------
# screenshot.py — take_screenshot, wait_for
# ---------------------------------------------------------------------------


class TestTakeScreenshot:
    @pytest.mark.asyncio
    async def test_fullscreen_scope(self, mcp, mock_client):
        mock_client.call.return_value = {"path": "/tmp/shot.png"}
        await mcp.call_tool("take_screenshot", {"save_path": "/tmp/shot.png"})
        mock_client.call.assert_called_once_with(
            "take_screenshot", {"path": "/tmp/shot.png", "mode": "fullscreen"}
        )

    @pytest.mark.asyncio
    async def test_node_scope(self, mcp, mock_client):
        mock_client.call.return_value = {"path": "/tmp/shot.png"}
        await mcp.call_tool(
            "take_screenshot",
            {"save_path": "/tmp/shot.png", "scope": "node", "node_id": "my_btn"},
        )
        args = mock_client.call.call_args[0][1]
        assert args["mode"] == "node"
        assert args["id"] == "my_btn"

    @pytest.mark.asyncio
    async def test_rect_scope(self, mcp, mock_client):
        mock_client.call.return_value = {"path": "/tmp/shot.png"}
        await mcp.call_tool(
            "take_screenshot",
            {"save_path": "/tmp/shot.png", "scope": "rect", "rect": [10, 20, 100, 200]},
        )
        args = mock_client.call.call_args[0][1]
        assert args["mode"] == "rect"
        assert args["x"] == 10
        assert args["y"] == 20
        assert args["w"] == 100
        assert args["h"] == 200

    @pytest.mark.asyncio
    async def test_returns_saved_path(self, mcp, mock_client):
        mock_client.call.return_value = {"path": "/saved/here.png"}
        r = _result(await mcp.call_tool("take_screenshot", {"save_path": "/tmp/x.png"}))
        assert r["saved_path"] == "/saved/here.png"


class TestWaitFor:
    @pytest.mark.asyncio
    async def test_calls_wait_for_with_params(self, mcp, mock_client):
        mock_client.call.return_value = {"success": True, "elapsed_ms": 42}
        await mcp.call_tool(
            "wait_for",
            {"condition": "widget_appeared", "id": "popup", "timeout_ms": 3000},
        )
        mock_client.call.assert_called_once_with(
            "wait_for",
            {"condition": "widget_appeared", "id": "popup", "timeout_ms": 3000},
        )

    @pytest.mark.asyncio
    async def test_expected_value_included_when_given(self, mcp, mock_client):
        mock_client.call.return_value = {"success": True, "elapsed_ms": 10}
        await mcp.call_tool(
            "wait_for",
            {
                "condition": "text_changed",
                "id": "lbl",
                "expected_value": "Hello",
                "timeout_ms": 1000,
            },
        )
        args = mock_client.call.call_args[0][1]
        assert args["expected_value"] == "Hello"

    @pytest.mark.asyncio
    async def test_returns_elapsed_ms(self, mcp, mock_client):
        mock_client.call.return_value = {"success": True, "elapsed_ms": 123}
        r = _result(
            await mcp.call_tool(
                "wait_for", {"condition": "widget_appeared", "id": "x"}
            )
        )
        assert r["elapsed_ms"] == 123


# ---------------------------------------------------------------------------
# meta.py — pin_id, list_orphan_ids
# ---------------------------------------------------------------------------


class TestPinId:
    @pytest.mark.asyncio
    async def test_calls_pin_id_with_params(self, mcp, mock_client):
        await mcp.call_tool("pin_id", {"current_id": "hash_btn", "new_id": "login_btn"})
        mock_client.call.assert_called_once_with(
            "pin_id", {"id": "hash_btn", "pinned_id": "login_btn"}
        )

    @pytest.mark.asyncio
    async def test_returns_pinned_id_in_response(self, mcp, mock_client):
        r = _result(
            await mcp.call_tool(
                "pin_id", {"current_id": "hash_btn", "new_id": "login_btn"}
            )
        )
        assert r["pinned_id"] == "login_btn"
        assert r["success"] is True


class TestListOrphanIds:
    @pytest.mark.asyncio
    async def test_calls_list_orphan_ids_no_params(self, mcp, mock_client):
        mock_client.call.return_value = []
        await mcp.call_tool("list_orphan_ids", {})
        mock_client.call.assert_called_once_with("list_orphan_ids", {})

    @pytest.mark.asyncio
    async def test_returns_orphans_list(self, mcp, mock_client):
        mock_client.call.return_value = ["gone_1", "gone_2"]
        r = _result(await mcp.call_tool("list_orphan_ids", {}))
        assert r["orphans"] == ["gone_1", "gone_2"]


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    @pytest.mark.asyncio
    async def test_adapter_error_returns_structured_dict(self, mcp, mock_client):
        """AdapterError is now caught by @handle_tool_errors → structured dict."""
        mock_client.call.side_effect = AdapterError(-32001, "widget not found")
        raw = await mcp.call_tool("click", {"id": "missing_btn"})
        result = _result(raw)
        assert result["success"] is False
        assert result["error"]["code"] == -32001
        assert result["error"]["error_type"] == "WidgetNotFound"

    @pytest.mark.asyncio
    async def test_not_connected_returns_engine_disconnected(self):
        """No client set → @handle_tool_errors returns EngineDisconnected dict."""
        set_client(None)
        try:
            server = build_server()
            raw = await server.call_tool("dump_tree", {})
            result = _result(raw)
            assert result["success"] is False
            assert result["error"]["error_type"] == "EngineDisconnected"
        finally:
            set_client(None)


# ---------------------------------------------------------------------------
# Integration test — fake adapter
# ---------------------------------------------------------------------------

# Responses the fake adapter returns for each wire method.
_FAKE_RESPONSES: dict[str, Any] = {
    "negotiate_version": {"server_version": "0.1", "accepted": True},
    "dump_tree": [{"id": "root", "type": "RectTransform", "visual": {"visible": True}}],
    "find_widget": ["root"],
    "get_widget": {"id": "root", "type": "RectTransform"},
    "click": None,
    "send_text": None,
    "drag": None,
    "scroll": None,
    "key_press": None,
    "take_screenshot": {"path": "/tmp/integration.png"},
    "wait_for": {"success": True, "elapsed_ms": 1},
    "pin_id": None,
    "list_orphan_ids": ["old_id"],
}


async def _fake_adapter_handler(websocket: Any) -> None:
    """Handle one client connection: parse each JSON-RPC request, respond."""
    async for message in websocket:
        try:
            req = json.loads(message)
        except json.JSONDecodeError:
            continue
        method = req.get("method", "")
        rpc_id = req.get("id")
        if method in _FAKE_RESPONSES:
            resp = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": _FAKE_RESPONSES[method],
            }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            }
        await websocket.send(json.dumps(resp))


@pytest.fixture
async def fake_adapter_port():
    """Start a fake adapter on a random port; yield the port number."""
    server = await websockets.asyncio.server.serve(
        _fake_adapter_handler,
        "127.0.0.1",
        0,
        subprotocols=["autoagent.v1"],
    )
    port = next(iter(server.sockets)).getsockname()[1]
    yield port
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_integration_websocket_client_connect(fake_adapter_port):
    """WebSocketClient connects, negotiates version, and disconnects cleanly."""
    client = WebSocketClient("127.0.0.1", fake_adapter_port)
    result = await client.connect()
    assert result["accepted"] is True
    assert result["server_version"] == "0.1"
    assert client.connected
    await client.disconnect()
    assert not client.connected


@pytest.mark.asyncio
async def test_integration_dump_tree(fake_adapter_port):
    client = WebSocketClient("127.0.0.1", fake_adapter_port)
    await client.connect()
    try:
        nodes = await client.call("dump_tree", {})
        assert isinstance(nodes, list)
        assert nodes[0]["id"] == "root"
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_all_wire_methods(fake_adapter_port):
    """All supported wire methods get a non-error response from the fake adapter."""
    wire_calls: list[tuple[str, dict]] = [
        ("dump_tree", {}),
        ("find_widget", {"logical_role": "button"}),
        ("get_widget", {"id": "root"}),
        ("click", {"id": "root"}),
        ("send_text", {"id": "root", "text": "hi", "clear_first": True}),
        ("drag", {"from_id": "a", "to_id": "b", "duration_ms": 100}),
        ("scroll", {"id": "root", "delta_x": 0.0, "delta_y": -50.0}),
        ("key_press", {"id": "root", "key": "Return"}),
        ("take_screenshot", {"path": "/tmp/x.png", "mode": "fullscreen"}),
        ("wait_for", {"condition": "widget_appeared", "id": "root", "timeout_ms": 100}),
        ("pin_id", {"id": "root", "pinned_id": "pinned_root"}),
        ("list_orphan_ids", {}),
    ]
    client = WebSocketClient("127.0.0.1", fake_adapter_port)
    await client.connect()
    try:
        for method, params in wire_calls:
            result = await client.call(method, params)
            # Verify no AdapterError was raised; result may be None or a value.
            assert method  # just ensures we reached this assertion
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_integration_adapter_error_raises(fake_adapter_port):
    """Unknown wire method → AdapterError(-32601)."""
    client = WebSocketClient("127.0.0.1", fake_adapter_port)
    await client.connect()
    try:
        with pytest.raises(AdapterError) as exc_info:
            await client.call("no_such_method", {})
        assert exc_info.value.code == -32601
    finally:
        await client.disconnect()
