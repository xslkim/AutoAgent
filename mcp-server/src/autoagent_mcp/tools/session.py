"""Session tools: ping, get_engine_info.

Full session management (connect_engine / disconnect / heartbeat / retry)
is implemented in TASK-0118.  These two tools are thin stubs whose real
wire equivalents are not yet in the adapter.
"""

from __future__ import annotations

import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import AdapterError, get_client


def register(mcp: FastMCP) -> None:
    """Register ping and get_engine_info on *mcp*."""

    @mcp.tool()
    async def ping() -> dict[str, Any]:
        """Liveness check — confirms the adapter is reachable and responsive.

        Attempts a ``negotiate_version`` round-trip and returns
        ``{"pong": True, "latency_ms": N}`` on success.
        Falls back to ``{"pong": False, "error": "..."}`` if not connected.
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
        adapter, so this tool returns a stub response.  TASK-0118 will wire
        this to a real adapter call once the method is available.
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
