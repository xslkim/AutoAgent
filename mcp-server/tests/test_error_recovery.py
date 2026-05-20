"""TASK-0119: error-handler integration tests.

Verifies that MCP tools convert adapter / transport exceptions into the
canonical structured error dict instead of letting raw exceptions propagate.

All tests inject failures via ``mock_client.call.side_effect``; no real
WebSocket connection is required.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from autoagent_mcp.connector import WebSocketClient, set_client
from autoagent_mcp.connector.websocket_client import AdapterError, EngineDisconnectedError
from autoagent_mcp.server import build_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """Provide an AsyncMock WebSocketClient as the active client."""
    client = AsyncMock(spec=WebSocketClient)
    client.connected = True
    set_client(client)
    yield client
    set_client(None)


def _result(tool_result) -> dict:
    """Extract the structured dict from FastMCP call_tool() return value."""
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    return tool_result


# ---------------------------------------------------------------------------
# AdapterError → structured error dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_click_widget_not_found(mock_client):
    """Adapter returns -32001 WidgetNotFound → tool returns structured error."""
    mock_client.call.side_effect = AdapterError(-32001, "widget not found: btn_foo")
    mcp = build_server()
    raw = await mcp.call_tool("click", {"id": "btn_foo"})
    result = _result(raw)
    assert result["success"] is False
    err = result["error"]
    assert err["code"] == -32001
    assert err["error_type"] == "WidgetNotFound"
    assert "btn_foo" in err["message"]


@pytest.mark.asyncio
async def test_click_widget_not_interactable(mock_client):
    mock_client.call.side_effect = AdapterError(-32002, "widget not interactable")
    mcp = build_server()
    result = _result(await mcp.call_tool("click", {"id": "some_id"}))
    assert result["success"] is False
    assert result["error"]["code"] == -32002
    assert result["error"]["error_type"] == "WidgetNotInteractable"


@pytest.mark.asyncio
async def test_dump_tree_internal_error(mock_client):
    mock_client.call.side_effect = AdapterError(-32603, "unexpected exception in dump")
    mcp = build_server()
    result = _result(await mcp.call_tool("dump_tree", {}))
    assert result["success"] is False
    assert result["error"]["code"] == -32603
    assert result["error"]["error_type"] == "InternalError"


@pytest.mark.asyncio
async def test_find_widget_adapter_error(mock_client):
    mock_client.call.side_effect = AdapterError(-32602, "missing required param: logical_role or text")
    mcp = build_server()
    result = _result(await mcp.call_tool("find_widget", {}))
    assert result["success"] is False
    assert result["error"]["code"] == -32602
    assert result["error"]["error_type"] == "InvalidParams"


@pytest.mark.asyncio
async def test_get_widget_not_found(mock_client):
    mock_client.call.side_effect = AdapterError(-32001, "widget not found: node_99")
    mcp = build_server()
    result = _result(await mcp.call_tool("get_widget", {"id": "node_99"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "WidgetNotFound"


@pytest.mark.asyncio
async def test_send_text_not_found(mock_client):
    mock_client.call.side_effect = AdapterError(-32001, "widget not found: input_box")
    mcp = build_server()
    result = _result(await mcp.call_tool("send_text", {"id": "input_box", "text": "hello"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "WidgetNotFound"


@pytest.mark.asyncio
async def test_drag_adapter_error(mock_client):
    mock_client.call.side_effect = AdapterError(-32002, "target not interactable")
    mcp = build_server()
    result = _result(await mcp.call_tool("drag", {"from_id": "a", "to_id": "b"}))
    assert result["success"] is False
    assert result["error"]["code"] == -32002


@pytest.mark.asyncio
async def test_scroll_adapter_error(mock_client):
    mock_client.call.side_effect = AdapterError(-32001, "scroll container not found")
    mcp = build_server()
    result = _result(await mcp.call_tool("scroll", {"id": "scroll_view"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "WidgetNotFound"


@pytest.mark.asyncio
async def test_key_press_adapter_error(mock_client):
    mock_client.call.side_effect = AdapterError(-32006, "input injection failed")
    mcp = build_server()
    result = _result(await mcp.call_tool("key_press", {"id": "field", "key": "Return"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "InputInjectionFailed"


@pytest.mark.asyncio
async def test_pin_id_not_found(mock_client):
    mock_client.call.side_effect = AdapterError(-32001, "widget not found: old_id")
    mcp = build_server()
    result = _result(await mcp.call_tool("pin_id", {"current_id": "old_id", "new_id": "new_id"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "WidgetNotFound"


@pytest.mark.asyncio
async def test_take_screenshot_failed(mock_client):
    mock_client.call.side_effect = AdapterError(-32008, "screenshot capture failed")
    mcp = build_server()
    result = _result(await mcp.call_tool("take_screenshot", {"save_path": "/tmp/ss.png"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "ScreenshotFailed"


@pytest.mark.asyncio
async def test_wait_for_timeout(mock_client):
    mock_client.call.side_effect = AdapterError(-32005, "wait_for timed out after 5000 ms")
    mcp = build_server()
    result = _result(await mcp.call_tool(
        "wait_for",
        {"condition": "widget_appeared", "id": "btn", "timeout_ms": 5000},
    ))
    assert result["success"] is False
    assert result["error"]["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_list_orphan_ids_adapter_error(mock_client):
    mock_client.call.side_effect = AdapterError(-32603, "internal error")
    mcp = build_server()
    result = _result(await mcp.call_tool("list_orphan_ids", {}))
    assert result["success"] is False
    assert result["error"]["code"] == -32603


# ---------------------------------------------------------------------------
# EngineDisconnectedError (transport / process crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_click_engine_disconnected(mock_client):
    """Transport failure mid-call → EngineDisconnected structured error."""
    mock_client.call.side_effect = EngineDisconnectedError("Connection lost during click")
    mcp = build_server()
    result = _result(await mcp.call_tool("click", {"id": "btn"}))
    assert result["success"] is False
    err = result["error"]
    assert err["code"] == -32099
    assert err["error_type"] == "EngineDisconnected"
    assert "Connection lost" in err["message"]


@pytest.mark.asyncio
async def test_dump_tree_engine_disconnected(mock_client):
    mock_client.call.side_effect = EngineDisconnectedError("WebSocket closed unexpectedly")
    mcp = build_server()
    result = _result(await mcp.call_tool("dump_tree", {}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "EngineDisconnected"


@pytest.mark.asyncio
async def test_send_text_engine_disconnected(mock_client):
    mock_client.call.side_effect = EngineDisconnectedError()
    mcp = build_server()
    result = _result(await mcp.call_tool("send_text", {"id": "field", "text": "hi"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "EngineDisconnected"


@pytest.mark.asyncio
async def test_take_screenshot_engine_disconnected(mock_client):
    mock_client.call.side_effect = EngineDisconnectedError()
    mcp = build_server()
    result = _result(await mcp.call_tool("take_screenshot", {"save_path": "/tmp/x.png"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "EngineDisconnected"


@pytest.mark.asyncio
async def test_pin_id_engine_disconnected(mock_client):
    mock_client.call.side_effect = EngineDisconnectedError()
    mcp = build_server()
    result = _result(await mcp.call_tool("pin_id", {"current_id": "a", "new_id": "b"}))
    assert result["success"] is False
    assert result["error"]["code"] == -32099


# ---------------------------------------------------------------------------
# "No engine connected" (get_client() raises RuntimeError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_click_no_engine_connected():
    """get_client() raises RuntimeError when no session → EngineDisconnected."""
    set_client(None)
    mcp = build_server()
    result = _result(await mcp.call_tool("click", {"id": "btn"}))
    assert result["success"] is False
    err = result["error"]
    assert err["error_type"] == "EngineDisconnected"
    assert err["code"] == -32099


@pytest.mark.asyncio
async def test_dump_tree_no_engine_connected():
    set_client(None)
    mcp = build_server()
    result = _result(await mcp.call_tool("dump_tree", {}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "EngineDisconnected"


@pytest.mark.asyncio
async def test_send_text_no_engine_connected():
    set_client(None)
    mcp = build_server()
    result = _result(await mcp.call_tool("send_text", {"id": "f", "text": "x"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "EngineDisconnected"


# ---------------------------------------------------------------------------
# Verify success path still works after applying the decorator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_click_success_still_works(mock_client):
    """@handle_tool_errors is transparent on the happy path."""
    mock_client.call.return_value = None
    mcp = build_server()
    result = _result(await mcp.call_tool("click", {"id": "btn"}))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_dump_tree_success_still_works(mock_client):
    mock_client.call.return_value = [{"id": "root", "visual": {"visible": True}}]
    mcp = build_server()
    result = _result(await mcp.call_tool("dump_tree", {}))
    assert "nodes" in result
    assert len(result["nodes"]) == 1


@pytest.mark.asyncio
async def test_pin_id_success_still_works(mock_client):
    mock_client.call.return_value = None
    mcp = build_server()
    result = _result(await mcp.call_tool("pin_id", {"current_id": "x", "new_id": "y"}))
    assert result["success"] is True
    assert result["pinned_id"] == "y"


# ---------------------------------------------------------------------------
# Unknown error code gets "UnknownError" type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_error_code_fallback(mock_client):
    """An unrecognised error code falls back to 'UnknownError'."""
    mock_client.call.side_effect = AdapterError(-99999, "something unexpected")
    mcp = build_server()
    result = _result(await mcp.call_tool("click", {"id": "btn"}))
    assert result["success"] is False
    assert result["error"]["error_type"] == "UnknownError"
    assert result["error"]["code"] == -99999
