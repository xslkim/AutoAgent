"""Session — lifecycle manager for a single engine-adapter connection.

Responsibilities:

* **Connect**: open the WebSocket, negotiate version, start heartbeat.
* **Disconnect**: stop heartbeat, close socket, clear the singleton client.
* **Auto-reconnect**: on heartbeat failure, retry up to
  :attr:`Session.MAX_ATTEMPTS` times with exponential back-off
  (default ``[1, 2, 4, 8, 16]`` seconds).

Public API::

    from autoagent_mcp.connector.session import connect, disconnect

    result = await connect("127.0.0.1", 27842)
    # ... do work ...
    await disconnect()

These are thin wrappers around the module-level :data:`_session` singleton.
Tests inject their own :class:`Session` instance to avoid touching global state.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from autoagent_mcp.connector import set_client
from autoagent_mcp.connector.heartbeat import Heartbeat
from autoagent_mcp.connector.websocket_client import WebSocketClient

logger = logging.getLogger(__name__)


class Session:
    """Manages the lifecycle of a single WebSocket connection.

    Args:
        heartbeat:        Custom :class:`Heartbeat` (default: 30 s interval).
        client_factory:   Callable ``(host, port) -> WebSocketClient``.
                          Injected in tests to supply mock clients.
        reconnect_delays: Sequence of back-off delays in seconds.
                          Length determines max reconnect attempts (default 5).
    """

    MAX_ATTEMPTS: int = 5
    RECONNECT_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)

    def __init__(
        self,
        heartbeat: Heartbeat | None = None,
        client_factory: Callable[[str, int], WebSocketClient] | None = None,
        reconnect_delays: tuple[float, ...] | None = None,
    ) -> None:
        self._heartbeat = heartbeat or Heartbeat()
        self._client_factory = client_factory or WebSocketClient
        self._reconnect_delays = reconnect_delays or self.RECONNECT_DELAYS

        self._client: WebSocketClient | None = None
        self._host: str = "127.0.0.1"
        self._port: int = 27842

    # ------------------------------------------------------------------ public

    async def connect(self, host: str, port: int) -> dict[str, Any]:
        """Open a new connection, replacing any existing one.

        Starts the heartbeat after a successful connection.

        Returns:
            The adapter's ``negotiate_version`` result
            (e.g. ``{"server_version": "0.1", "accepted": True}``).

        Raises:
            Any exception from :meth:`WebSocketClient.connect` on failure.
        """
        # Teardown existing connection first.
        if self._client is not None:
            await self.disconnect()

        self._host = host
        self._port = port

        client = self._client_factory(host, port)
        result = await client.connect()

        self._client = client
        set_client(client)
        self._heartbeat.start(client, self._reconnect)

        logger.info("Connected to adapter at %s:%d", host, port)
        return result

    async def disconnect(self) -> None:
        """Stop the heartbeat and close the WebSocket gracefully."""
        self._heartbeat.stop()
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
        set_client(None)
        logger.info("Disconnected from adapter")

    # ------------------------------------------------------------------ reconnect

    async def _reconnect(self) -> None:
        """Attempt to re-establish the connection with exponential back-off.

        Called by the :class:`Heartbeat` when a liveness ping fails.
        Tries each delay in :attr:`_reconnect_delays` in order.  On success
        the new client replaces the singleton and a fresh heartbeat starts.
        On total failure the singleton is cleared.
        """
        logger.warning(
            "Connection lost — attempting reconnect (%d attempts)",
            len(self._reconnect_delays),
        )
        for attempt, delay in enumerate(self._reconnect_delays, start=1):
            await asyncio.sleep(delay)
            try:
                client = self._client_factory(self._host, self._port)
                await client.connect()
                self._client = client
                set_client(client)
                self._heartbeat.start(client, self._reconnect)
                logger.info("Reconnected on attempt %d", attempt)
                return
            except Exception as exc:
                logger.warning(
                    "Reconnect attempt %d/%d failed: %s",
                    attempt,
                    len(self._reconnect_delays),
                    exc,
                )

        # All attempts exhausted.
        logger.error("All reconnect attempts failed — adapter unreachable")
        self._client = None
        set_client(None)


# ---------------------------------------------------------------------------
# Module-level singleton and convenience helpers
# ---------------------------------------------------------------------------

_session: Session = Session()


async def connect(host: str = "127.0.0.1", port: int = 27842) -> dict[str, Any]:
    """Connect the global session to an engine adapter."""
    return await _session.connect(host, port)


async def disconnect() -> None:
    """Disconnect the global session."""
    await _session.disconnect()
