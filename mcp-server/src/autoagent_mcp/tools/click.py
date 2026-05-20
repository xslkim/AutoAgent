"""Pointer-input tools: click, drag, scroll, key_press."""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client

# Scroll direction → (delta_x, delta_y) multipliers
_SCROLL_DELTA: dict[str, tuple[float, float]] = {
    "up":    (0.0,  1.0),
    "down":  (0.0, -1.0),
    "left":  (-1.0, 0.0),
    "right": (1.0,  0.0),
}


def register(mcp: FastMCP) -> None:
    """Register click, drag, scroll, and key_press on *mcp*."""

    @mcp.tool()
    async def click(
        id: str,
        button: Literal["left", "right", "middle"] = "left",
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Click a UI widget by its stable id.

        ``button`` and ``input_layer`` are accepted for schema compatibility
        but the current adapter always performs an engine-layer left-click.
        """
        await get_client().call("click", {"id": id})
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    async def drag(
        from_id: str,
        to_id: str,
        duration_ms: int = 200,
    ) -> dict[str, Any]:
        """Drag from one widget to another over *duration_ms* milliseconds."""
        await get_client().call(
            "drag",
            {"from_id": from_id, "to_id": to_id, "duration_ms": duration_ms},
        )
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    async def scroll(
        id: str,
        direction: Literal["up", "down", "left", "right"] = "down",
        amount: float = 100.0,
    ) -> dict[str, Any]:
        """Scroll a scroll container by *amount* pixels in *direction*.

        Positive *amount* always scrolls in the named direction regardless
        of coordinate-system conventions in the underlying engine.
        """
        mx, my = _SCROLL_DELTA[direction]
        await get_client().call(
            "scroll",
            {"id": id, "delta_x": mx * amount, "delta_y": my * amount},
        )
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    async def key_press(
        id: str,
        key: str,
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Send a key-press event to a specific UI widget.

        ``key`` must be a Unity KeyCode name (e.g. ``"Return"``, ``"Tab"``,
        ``"Escape"``, ``"A"``).  ``input_layer`` is accepted for schema
        compatibility but the adapter currently only supports engine-layer input.
        """
        await get_client().call("key_press", {"id": id, "key": key})
        return {"success": True, "captured_at": time.time()}
