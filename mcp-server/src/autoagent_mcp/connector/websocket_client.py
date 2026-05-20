"""AutoAgent wire-protocol WebSocket client.

JSON-RPC 2.0 over WebSocket with subprotocol ``autoagent.v1``.

Typical lifecycle::

    client = WebSocketClient()
    await client.connect()              # WS handshake + negotiate_version
    nodes  = await client.call("dump_tree", {})
    await client.disconnect()

``connect()`` returns the adapter's ``negotiate_version`` result dict so
the caller can verify ``accepted == True`` and log the server version.
"""

from __future__ import annotations

import json
from typing import Any

import websockets
import websockets.exceptions
from websockets.protocol import State as _WsState


class AdapterError(Exception):
    """Raised when the adapter returns a JSON-RPC error response.

    Attributes:
        code:    The JSON-RPC error code (e.g. -32001 for WidgetNotFound).
        message: Human-readable description from the adapter.
        data:    Optional extra payload included in the error object.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data

    def __repr__(self) -> str:
        return f"AdapterError(code={self.code!r}, message={self.message!r})"


class EngineDisconnectedError(Exception):
    """Raised when the WebSocket transport fails mid-operation.

    Covers adapter process crashes, network drops, and OS-level socket errors.
    MCP tools catch this and return a structured ``EngineDisconnected`` error
    to the AI so it knows to call ``connect_engine`` again.

    Attributes:
        code: Fixed JSON-RPC error code ``-32099`` (not in the standard table;
              reserved for this adapter-level transport error).
    """

    code: int = -32099

    def __init__(self, message: str = "Engine disconnected. Call connect_engine to reconnect.") -> None:
        super().__init__(message)
        self.message = message

    def __repr__(self) -> str:
        return f"EngineDisconnectedError({self.message!r})"


class WebSocketClient:
    """Asyncio WebSocket client for the AutoAgent wire protocol.

    Not thread-safe — intended for use within a single asyncio event loop.
    ``call()`` is not reentrant; concurrent callers must coordinate externally.
    """

    SUBPROTOCOL = "autoagent.v1"
    PROTOCOL_VERSION = "0.1"

    def __init__(self, host: str = "127.0.0.1", port: int = 27842) -> None:
        self.host = host
        self.port = port
        self._ws: Any = None   # websockets.ClientConnection
        self._next_id: int = 0

    # ------------------------------------------------------------------ state

    @property
    def connected(self) -> bool:
        """True when the WebSocket connection is currently open."""
        return self._ws is not None and self._ws.state is _WsState.OPEN

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> dict[str, Any]:
        """Open the WebSocket and run the version-negotiation handshake.

        Returns the adapter's ``negotiate_version`` result
        (e.g. ``{"server_version": "0.1", "accepted": True}``).

        Raises ``websockets.exceptions.WebSocketException`` on failure.
        """
        self._ws = await websockets.connect(
            self.uri,
            subprotocols=[self.SUBPROTOCOL],
        )
        result = await self.call(
            "negotiate_version", {"client_version": self.PROTOCOL_VERSION}
        )
        return result  # type: ignore[return-value]

    async def disconnect(self) -> None:
        """Close the WebSocket connection gracefully."""
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ RPC

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC 2.0 request and return the ``result`` value.

        Args:
            method: Wire-protocol method name (e.g. ``"dump_tree"``).
            params: Parameters dict (may be empty).

        Returns:
            The parsed ``result`` field from the adapter's response.
            This is ``None`` for methods that succeed with no payload
            (e.g. ``click``), a list for ``dump_tree`` / ``find_widget``,
            and a dict for ``take_screenshot`` / ``negotiate_version``.

        Raises:
            AdapterError: The adapter returned an ``error`` object.
            RuntimeError:  ``connect()`` has not been called.
        """
        if self._ws is None:
            raise RuntimeError(
                "Not connected to engine adapter. Call connect() first."
            )

        self._next_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params,
        }
        try:
            await self._ws.send(json.dumps(request))
            raw = await self._ws.recv()
        except (websockets.exceptions.WebSocketException, OSError, EOFError) as exc:
            raise EngineDisconnectedError(
                f"Adapter connection lost during '{method}': {exc}"
            ) from exc
        response: dict[str, Any] = json.loads(raw)

        if "error" in response:
            err = response["error"]
            raise AdapterError(
                code=err.get("code", -32603),
                message=err.get("message", "unknown error"),
                data=err.get("data"),
            )

        return response.get("result")
