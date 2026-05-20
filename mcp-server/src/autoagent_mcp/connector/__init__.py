"""Engine connector — shared WebSocket client singleton.

The MCP server maintains at most one active connection to an engine adapter.
Tools call :func:`get_client` to obtain the current client; session management
tools call :func:`set_client` when connecting / disconnecting.

Tests replace the real client with a mock via :func:`set_client` without
starting a WebSocket server.
"""

from __future__ import annotations

from autoagent_mcp.connector.websocket_client import AdapterError, WebSocketClient

# Module-level singleton — None means "not connected".
_active_client: WebSocketClient | None = None


def get_client() -> WebSocketClient:
    """Return the active WebSocket client.

    Raises:
        RuntimeError: No engine is currently connected
            (``connect_engine`` has not been called).
    """
    if _active_client is None:
        raise RuntimeError(
            "No engine connected. Call the connect_engine tool first."
        )
    return _active_client


def set_client(client: WebSocketClient | None) -> None:
    """Replace (or clear) the active WebSocket client.

    Called by ``connect_engine`` / ``disconnect`` tools and by test fixtures.
    """
    global _active_client
    _active_client = client


__all__ = ["AdapterError", "WebSocketClient", "get_client", "set_client"]
