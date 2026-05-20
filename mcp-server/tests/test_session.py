"""TASK-0118 verification — session lifecycle, heartbeat, and auto-reconnect.

Strategy
--------
All tests are pure asyncio unit tests using AsyncMock / Mock.  No real
WebSocket server is needed here because the integration tests in
``test_tools.py`` already cover the end-to-end WebSocket path.

Heartbeat timing tests use a very short ``interval_s`` (50 ms) so the
suite stays fast even on a slow CI machine.

Test groups
-----------
1. ``Session.connect`` — sets the active client, starts heartbeat.
2. ``Session.disconnect`` — stops heartbeat, clears client.
3. ``Heartbeat`` — fires on schedule, stops on cancel.
4. Heartbeat failure → ``Session._reconnect`` — happy path.
5. ``Session._reconnect`` — exhausts retries, clears client.
6. ``connect_engine`` / ``disconnect`` MCP tools.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from autoagent_mcp.connector import get_client, set_client
from autoagent_mcp.connector.heartbeat import Heartbeat
from autoagent_mcp.connector.session import Session
from autoagent_mcp.connector.websocket_client import WebSocketClient
from autoagent_mcp.server import build_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_client(*, connect_result=None, call_result=None, fail_connect=False):
    """Return an AsyncMock shaped like WebSocketClient."""
    client = AsyncMock(spec=WebSocketClient)
    client.connected = True
    if fail_connect:
        client.connect.side_effect = ConnectionRefusedError("refused")
    else:
        client.connect.return_value = connect_result or {
            "server_version": "0.1",
            "accepted": True,
        }
    client.call.return_value = call_result
    client.disconnect.return_value = None
    return client


def make_factory(*clients):
    """Return a factory callable that yields *clients* in order."""
    it = iter(clients)
    return Mock(side_effect=lambda h, p: next(it))


# ---------------------------------------------------------------------------
# Session.connect
# ---------------------------------------------------------------------------


class TestSessionConnect:
    @pytest.mark.asyncio
    async def test_connect_sets_active_client(self):
        mock_client = make_mock_client()
        session = Session(client_factory=make_factory(mock_client))

        try:
            await session.connect("127.0.0.1", 9999)
            assert get_client() is mock_client
        finally:
            await session.disconnect()
            set_client(None)

    @pytest.mark.asyncio
    async def test_connect_calls_client_connect(self):
        mock_client = make_mock_client()
        session = Session(client_factory=make_factory(mock_client))

        try:
            await session.connect("127.0.0.1", 9999)
            mock_client.connect.assert_awaited_once()
        finally:
            await session.disconnect()
            set_client(None)

    @pytest.mark.asyncio
    async def test_connect_starts_heartbeat(self):
        mock_client = make_mock_client()
        hb = Mock(spec=Heartbeat)
        hb.running = False
        hb.stop = Mock()
        hb.start = Mock()
        session = Session(heartbeat=hb, client_factory=make_factory(mock_client))

        try:
            await session.connect("127.0.0.1", 9999)
            hb.start.assert_called_once()
        finally:
            set_client(None)

    @pytest.mark.asyncio
    async def test_connect_returns_negotiate_version_result(self):
        mock_client = make_mock_client(
            connect_result={"server_version": "0.1", "accepted": True}
        )
        session = Session(client_factory=make_factory(mock_client))

        try:
            result = await session.connect("127.0.0.1", 9999)
            assert result["server_version"] == "0.1"
            assert result["accepted"] is True
        finally:
            await session.disconnect()
            set_client(None)

    @pytest.mark.asyncio
    async def test_connect_replaces_existing_connection(self):
        client1 = make_mock_client()
        client2 = make_mock_client()
        session = Session(client_factory=make_factory(client1, client2))

        try:
            await session.connect("127.0.0.1", 9999)
            assert get_client() is client1

            await session.connect("127.0.0.1", 9999)
            assert get_client() is client2
            client1.disconnect.assert_awaited_once()
        finally:
            await session.disconnect()
            set_client(None)

    @pytest.mark.asyncio
    async def test_connect_failure_leaves_no_active_client(self):
        failing = make_mock_client(fail_connect=True)
        session = Session(client_factory=make_factory(failing))
        set_client(None)

        with pytest.raises(ConnectionRefusedError):
            await session.connect("127.0.0.1", 9999)

        # get_client() raises RuntimeError when client is None — that's the
        # expected state after a failed connect.
        with pytest.raises(RuntimeError, match="No engine connected"):
            get_client()


# ---------------------------------------------------------------------------
# Session.disconnect
# ---------------------------------------------------------------------------


class TestSessionDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_stops_heartbeat(self):
        mock_client = make_mock_client()
        hb = Mock(spec=Heartbeat)
        hb.running = False
        hb.stop = Mock()
        hb.start = Mock()
        session = Session(heartbeat=hb, client_factory=make_factory(mock_client))

        await session.connect("127.0.0.1", 9999)
        await session.disconnect()

        hb.stop.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect_clears_active_client(self):
        mock_client = make_mock_client()
        session = Session(client_factory=make_factory(mock_client))

        await session.connect("127.0.0.1", 9999)
        await session.disconnect()

        with pytest.raises(RuntimeError, match="No engine connected"):
            get_client()

    @pytest.mark.asyncio
    async def test_disconnect_calls_client_disconnect(self):
        mock_client = make_mock_client()
        session = Session(client_factory=make_factory(mock_client))

        await session.connect("127.0.0.1", 9999)
        await session.disconnect()

        mock_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected_is_safe(self):
        session = Session()
        set_client(None)
        # Must not raise.
        await session.disconnect()


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_calls_client_periodically(self):
        """Heartbeat fires at the configured interval."""
        mock_client = AsyncMock()
        mock_client.call.return_value = {"server_version": "0.1", "accepted": True}

        on_failure = AsyncMock()
        hb = Heartbeat(interval_s=0.05)  # 50 ms for speed
        hb.start(mock_client, on_failure)

        await asyncio.sleep(0.18)  # ≈ 3 cycles
        hb.stop()

        assert mock_client.call.await_count >= 2, (
            f"expected ≥ 2 heartbeat pings, got {mock_client.call.await_count}"
        )
        on_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heartbeat_calls_on_failure_when_ping_fails(self):
        """A failing ping triggers on_failure exactly once."""
        mock_client = AsyncMock()
        mock_client.call.side_effect = ConnectionResetError("dropped")

        on_failure = AsyncMock()
        hb = Heartbeat(interval_s=0.05)
        hb.start(mock_client, on_failure)

        await asyncio.sleep(0.12)  # give loop time to fire and call on_failure
        hb.stop()

        on_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_heartbeat_running_property(self):
        mock_client = AsyncMock()
        mock_client.call.return_value = None
        hb = Heartbeat(interval_s=60)  # long interval — task stays alive

        assert not hb.running
        hb.start(mock_client, AsyncMock())
        assert hb.running
        hb.stop()
        await asyncio.sleep(0)  # let the cancel propagate
        assert not hb.running

    @pytest.mark.asyncio
    async def test_heartbeat_stop_is_idempotent(self):
        hb = Heartbeat(interval_s=60)
        hb.stop()  # no-op before start
        mock_client = AsyncMock()
        mock_client.call.return_value = None
        hb.start(mock_client, AsyncMock())
        hb.stop()
        hb.stop()  # second stop must not raise

    @pytest.mark.asyncio
    async def test_heartbeat_start_replaces_previous_task(self):
        """Calling start() twice cancels the first loop before starting a new one."""
        mock_client = AsyncMock()
        mock_client.call.return_value = None
        hb = Heartbeat(interval_s=60)

        hb.start(mock_client, AsyncMock())
        first_task = hb._task

        hb.start(mock_client, AsyncMock())  # replaces first
        await asyncio.sleep(0)  # let the event loop process the cancellation

        assert hb._task is not first_task
        assert first_task.done()  # cancelled tasks are done
        hb.stop()


# ---------------------------------------------------------------------------
# Session._reconnect — happy path
# ---------------------------------------------------------------------------


class TestSessionReconnect:
    @pytest.mark.asyncio
    async def test_reconnect_succeeds_on_first_retry(self):
        """Reconnect creates a new client and restores the singleton."""
        new_client = make_mock_client()
        factory = make_factory(new_client)
        hb = Mock(spec=Heartbeat)
        hb.stop = Mock()
        hb.start = Mock()
        hb.running = False

        session = Session(
            heartbeat=hb,
            client_factory=factory,
            reconnect_delays=(0.001,),  # instant
        )
        session._host = "127.0.0.1"
        session._port = 9999
        set_client(None)

        await session._reconnect()

        assert get_client() is new_client
        new_client.connect.assert_awaited_once()
        set_client(None)

    @pytest.mark.asyncio
    async def test_reconnect_retries_after_initial_failures(self):
        """Fails twice, succeeds on the third attempt."""
        fail1 = make_mock_client(fail_connect=True)
        fail2 = make_mock_client(fail_connect=True)
        ok_client = make_mock_client()
        factory = make_factory(fail1, fail2, ok_client)

        hb = Mock(spec=Heartbeat)
        hb.stop = Mock()
        hb.start = Mock()
        hb.running = False

        session = Session(
            heartbeat=hb,
            client_factory=factory,
            reconnect_delays=(0.001, 0.001, 0.001),
        )
        session._host = "127.0.0.1"
        session._port = 9999
        set_client(None)

        await session._reconnect()

        assert get_client() is ok_client
        assert factory.call_count == 3
        set_client(None)

    @pytest.mark.asyncio
    async def test_reconnect_exhausts_all_5_attempts_then_clears_client(self):
        """All 5 attempts fail → active client is set to None."""
        failing_client = make_mock_client(fail_connect=True)
        factory = Mock(return_value=failing_client)

        session = Session(
            client_factory=factory,
            reconnect_delays=(0.001, 0.001, 0.001, 0.001, 0.001),
        )
        session._host = "127.0.0.1"
        session._port = 9999
        set_client(Mock())  # pre-set to something

        await session._reconnect()

        assert factory.call_count == 5
        # get_client() raises RuntimeError when no client is set — that's expected.
        with pytest.raises(RuntimeError, match="No engine connected"):
            get_client()
        set_client(None)

    @pytest.mark.asyncio
    async def test_reconnect_starts_fresh_heartbeat_on_success(self):
        ok_client = make_mock_client()
        hb = Mock(spec=Heartbeat)
        hb.stop = Mock()
        hb.start = Mock()
        hb.running = False

        session = Session(
            heartbeat=hb,
            client_factory=make_factory(ok_client),
            reconnect_delays=(0.001,),
        )
        session._host = "127.0.0.1"
        session._port = 9999
        set_client(None)

        await session._reconnect()

        hb.start.assert_called_once()
        set_client(None)


# ---------------------------------------------------------------------------
# connect_engine / disconnect MCP tools
# ---------------------------------------------------------------------------


class TestConnectEngineTool:
    @pytest.fixture(autouse=True)
    def clean_client(self):
        set_client(None)
        yield
        set_client(None)

    @pytest.mark.asyncio
    async def test_connect_engine_returns_connected_true(self, fake_adapter_port):
        mcp = build_server()
        result_raw = await mcp.call_tool(
            "connect_engine",
            {"host": "127.0.0.1", "port": fake_adapter_port},
        )
        result = _result(result_raw)
        assert result["connected"] is True
        assert result["server_version"] == "0.1"
        await mcp.call_tool("disconnect", {})

    @pytest.mark.asyncio
    async def test_connect_engine_sets_active_client(self, fake_adapter_port):
        mcp = build_server()
        await mcp.call_tool(
            "connect_engine",
            {"host": "127.0.0.1", "port": fake_adapter_port},
        )
        assert get_client() is not None
        assert get_client().connected
        await mcp.call_tool("disconnect", {})

    @pytest.mark.asyncio
    async def test_disconnect_tool_clears_active_client(self, fake_adapter_port):
        mcp = build_server()
        await mcp.call_tool(
            "connect_engine",
            {"host": "127.0.0.1", "port": fake_adapter_port},
        )
        result_raw = await mcp.call_tool("disconnect", {})
        result = _result(result_raw)
        assert result["disconnected"] is True
        with pytest.raises(RuntimeError, match="No engine connected"):
            get_client()


# ---------------------------------------------------------------------------
# Fake adapter fixture (shared with test_tools.py pattern)
# ---------------------------------------------------------------------------

import json
from typing import Any

import websockets.asyncio.server


async def _fake_handler(websocket: Any) -> None:
    async for message in websocket:
        try:
            req = json.loads(message)
        except json.JSONDecodeError:
            continue
        rpc_id = req.get("id")
        method = req.get("method", "")
        if method == "negotiate_version":
            resp = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"server_version": "0.1", "accepted": True},
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
    server = await websockets.asyncio.server.serve(
        _fake_handler,
        "127.0.0.1",
        0,
        subprotocols=["autoagent.v1"],
    )
    port = next(iter(server.sockets)).getsockname()[1]
    yield port
    server.close()
    await server.wait_closed()


def _result(tool_result: Any) -> Any:
    """Extract the Python value from a FastMCP call_tool result."""
    if not tool_result:
        return None
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    first = tool_result[0] if tool_result else None
    if hasattr(first, "text"):
        import json as _json
        return _json.loads(first.text)
    return first
