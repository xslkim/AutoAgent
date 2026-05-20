"""Heartbeat — periodic liveness check for an active adapter connection.

A :class:`Heartbeat` runs as an asyncio background task.  Every
:attr:`interval_s` seconds it sends a ``negotiate_version`` round-trip to
the adapter.  If the call raises (connection closed, timeout, etc.) it
invokes an *async* ``on_failure`` callback and exits the loop, leaving
reconnect logic entirely to the caller.

Usage::

    hb = Heartbeat(interval_s=30.0)
    hb.start(client, on_failure=session._reconnect)
    # ... later ...
    hb.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class Heartbeat:
    """Asyncio background task that pings the adapter at a fixed interval.

    Attributes:
        interval_s: Seconds between successive liveness pings (default 30).
    """

    DEFAULT_INTERVAL_S = 30.0

    def __init__(self, interval_s: float = DEFAULT_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ state

    @property
    def running(self) -> bool:
        """True while the background task is alive."""
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------ lifecycle

    def start(
        self,
        client: object,
        on_failure: Callable[[], Awaitable[None]],
    ) -> None:
        """Start the heartbeat loop, cancelling any previously running one.

        Args:
            client:     A :class:`~connector.websocket_client.WebSocketClient`
                        whose ``call`` coroutine is used for the ping.
            on_failure: Async callable invoked when a ping fails.  The loop
                        exits immediately after calling it — reconnect logic
                        lives in the callback.
        """
        self.stop()
        self._task = asyncio.create_task(self._loop(client, on_failure))

    def stop(self) -> None:
        """Cancel the background task (no-op if already stopped)."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    # ------------------------------------------------------------------ internal

    async def _loop(
        self,
        client: object,
        on_failure: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval_s)
                try:
                    await client.call(  # type: ignore[attr-defined]
                        "negotiate_version", {"client_version": "0.1"}
                    )
                    logger.debug("Heartbeat OK")
                except Exception as exc:
                    logger.warning("Heartbeat failed: %s — triggering reconnect", exc)
                    await on_failure()
                    return  # reconnect callback takes over
        except asyncio.CancelledError:
            logger.debug("Heartbeat stopped")
