"""Session tools: connect_engine, disconnect, ping, get_engine_info.

``connect_engine`` and ``disconnect`` manage the WebSocket session lifecycle
via :mod:`autoagent_mcp.connector.session`.  ``ping`` is a fast liveness check
and ``get_engine_info`` returns adapter metadata (stub until the wire method
is implemented in the adapter).
"""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import AdapterError, get_client
from autoagent_mcp.connector import session as _session_module


def register(mcp: FastMCP) -> None:
    """Register connect_engine, disconnect, ping, and get_engine_info on *mcp*."""

    @mcp.tool()
    async def connect_engine(
        host: str = "127.0.0.1",
        port: int = 27842,
        engine: Literal["unity", "unreal", "godot"] = "unity",
    ) -> dict[str, Any]:
        """Connect to a running engine adapter.

        Must be called before any other tool that communicates with the
        engine.  Replaces any existing connection.  The adapter must already
        be running (e.g. Unity Editor with the AutoAgent package loaded).

        Args:
            host:   Adapter host (default ``127.0.0.1``).
            port:   Adapter port (default ``27842``).
            engine: Engine type hint for display purposes only.

        Returns:
            ``{"connected": True, "server_version": "...", "engine": "..."}``
        """
        result = await _session_module.connect(host, port)
        return {
            "connected": True,
            "server_version": result.get("server_version", "?"),
            "engine": engine,
            "host": host,
            "port": port,
        }

    @mcp.tool()
    async def disconnect() -> dict[str, Any]:
        """Disconnect from the engine adapter.

        Stops the heartbeat and closes the WebSocket.  Subsequent tool calls
        will fail until ``connect_engine`` is called again.
        """
        await _session_module.disconnect()
        return {"disconnected": True}

    @mcp.tool()
    async def ping() -> dict[str, Any]:
        """Liveness check — confirms the adapter is reachable and responsive.

        Returns ``{"pong": True, "latency_ms": N}`` on success or
        ``{"pong": False, "error": "..."}`` if not connected / unreachable.
        """
        t0 = time.monotonic()
        try:
            client = get_client()
            await client.call("negotiate_version", {"client_version": "0.1"})
            latency = round((time.monotonic() - t0) * 1000)
            return {"pong": True, "latency_ms": latency}
        except (RuntimeError, AdapterError, OSError) as exc:
            return {"pong": False, "error": str(exc)}

    @mcp.tool()
    async def get_engine_info() -> dict[str, Any]:
        """Return engine / adapter / protocol version metadata.

        The wire method ``get_engine_info`` is not yet implemented in the
        adapter, so this tool returns a stub response.
        """
        return {
            "engine": "Unity",
            "engine_version": "unknown",
            "adapter_version": "0.1.0",
            "protocol_version": "0.1",
            "platform": "unknown",
            "build_type": "unknown",
            "note": "stub — wire method not yet implemented in adapter",
        }
