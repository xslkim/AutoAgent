"""TASK-0400: input_layer parameter routing tests.

Verifies that the click / drag / key_press MCP tools forward
input_layer (and button) to the wire protocol call, and that
the default "engine" value is omitted from the wire params to
stay backwards-compatible with older adapter versions.

All tests are pure-Python; no engine connection is required.
The WebSocketClient is mocked at the connector level.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoagent_mcp.connector import WebSocketClient, set_client
from autoagent_mcp.server import build_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_client():
    """Install a mock client that captures wire calls."""
    client = MagicMock(spec=WebSocketClient)
    client.connected = True
    client.call = AsyncMock(return_value=None)
    set_client(client)
    yield client
    set_client(None)


@pytest.fixture()
def mcp():
    return build_server()


# ---------------------------------------------------------------------------
# click
# ---------------------------------------------------------------------------


class TestClickInputLayer:
    @pytest.mark.asyncio
    async def test_default_engine_layer_omitted(self, mcp, _mock_client):
        """Default input_layer="engine" must NOT appear in wire params."""
        await mcp.call_tool("click", {"id": "btn1"})
        args, kwargs = _mock_client.call.call_args
        wire_params = args[1] if len(args) > 1 else kwargs.get("params", {})
        assert "input_layer" not in wire_params, (
            "input_layer should be omitted when using the default 'engine' layer"
        )

    @pytest.mark.asyncio
    async def test_os_layer_forwarded(self, mcp, _mock_client):
        """input_layer='os' must appear in the wire call params."""
        await mcp.call_tool("click", {"id": "btn1", "input_layer": "os"})
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params.get("input_layer") == "os"

    @pytest.mark.asyncio
    async def test_button_left_omitted(self, mcp, _mock_client):
        """Default button="left" must NOT appear in wire params."""
        await mcp.call_tool("click", {"id": "btn1"})
        _, wire_params = _mock_client.call.call_args[0]
        assert "button" not in wire_params

    @pytest.mark.asyncio
    async def test_button_right_forwarded(self, mcp, _mock_client):
        """Non-default button values must appear in wire params."""
        await mcp.call_tool("click", {"id": "btn1", "button": "right"})
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params.get("button") == "right"

    @pytest.mark.asyncio
    async def test_os_layer_and_button_forwarded_together(self, mcp, _mock_client):
        await mcp.call_tool(
            "click", {"id": "btn1", "input_layer": "os", "button": "middle"}
        )
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params.get("input_layer") == "os"
        assert wire_params.get("button") == "middle"

    @pytest.mark.asyncio
    async def test_id_always_forwarded(self, mcp, _mock_client):
        await mcp.call_tool("click", {"id": "my_widget"})
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params["id"] == "my_widget"


# ---------------------------------------------------------------------------
# drag
# ---------------------------------------------------------------------------


class TestDragInputLayer:
    @pytest.mark.asyncio
    async def test_default_engine_layer_omitted(self, mcp, _mock_client):
        await mcp.call_tool("drag", {"from_id": "a", "to_id": "b"})
        _, wire_params = _mock_client.call.call_args[0]
        assert "input_layer" not in wire_params

    @pytest.mark.asyncio
    async def test_os_layer_forwarded(self, mcp, _mock_client):
        await mcp.call_tool(
            "drag", {"from_id": "a", "to_id": "b", "input_layer": "os"}
        )
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params.get("input_layer") == "os"

    @pytest.mark.asyncio
    async def test_duration_ms_forwarded(self, mcp, _mock_client):
        await mcp.call_tool(
            "drag", {"from_id": "a", "to_id": "b", "duration_ms": 500}
        )
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params["duration_ms"] == 500

    @pytest.mark.asyncio
    async def test_from_to_ids_forwarded(self, mcp, _mock_client):
        await mcp.call_tool("drag", {"from_id": "src", "to_id": "dst"})
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params["from_id"] == "src"
        assert wire_params["to_id"] == "dst"


# ---------------------------------------------------------------------------
# key_press
# ---------------------------------------------------------------------------


class TestKeyPressInputLayer:
    @pytest.mark.asyncio
    async def test_default_engine_layer_omitted(self, mcp, _mock_client):
        await mcp.call_tool("key_press", {"id": "field", "key": "Return"})
        _, wire_params = _mock_client.call.call_args[0]
        assert "input_layer" not in wire_params

    @pytest.mark.asyncio
    async def test_os_layer_forwarded(self, mcp, _mock_client):
        await mcp.call_tool(
            "key_press", {"id": "field", "key": "Return", "input_layer": "os"}
        )
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params.get("input_layer") == "os"

    @pytest.mark.asyncio
    async def test_key_always_forwarded(self, mcp, _mock_client):
        await mcp.call_tool("key_press", {"id": "f", "key": "Tab"})
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params["key"] == "Tab"

    @pytest.mark.asyncio
    async def test_id_always_forwarded(self, mcp, _mock_client):
        await mcp.call_tool("key_press", {"id": "my_input", "key": "Escape"})
        _, wire_params = _mock_client.call.call_args[0]
        assert wire_params["id"] == "my_input"

    @pytest.mark.asyncio
    async def test_engine_layer_explicit_still_omitted(self, mcp, _mock_client):
        """Explicitly passing 'engine' should still omit the key from wire params."""
        await mcp.call_tool(
            "key_press", {"id": "f", "key": "Tab", "input_layer": "engine"}
        )
        _, wire_params = _mock_client.call.call_args[0]
        assert "input_layer" not in wire_params
