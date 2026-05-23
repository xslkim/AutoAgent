"""Pointer-input tools: click, drag, scroll, key_press."""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors

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
    @handle_tool_errors
    async def click(
        id: str,
        button: Literal["left", "right", "middle"] = "left",
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Click a UI widget by its stable id.

        Args:
            id:          Stable node id returned by ``dump_tree`` / ``find_widget``.
            button:      Mouse button to use (default ``"left"``).
            input_layer: ``"engine"`` (default) fires Unity EventSystem events;
                         ``"os"`` injects OS-level SendInput on Windows.
        """
        params: dict[str, Any] = {"id": id}
        if button != "left":
            params["button"] = button
        if input_layer != "engine":
            params["input_layer"] = input_layer
        await get_client().call("click", params)
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    @handle_tool_errors
    async def drag(
        from_id: str,
        to_id: str,
        duration_ms: int = 200,
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Drag from one widget to another over *duration_ms* milliseconds.

        Args:
            from_id:     Stable id of the drag source.
            to_id:       Stable id of the drag target.
            duration_ms: Drag duration in milliseconds (default 200).
            input_layer: ``"engine"`` fires Unity IDragHandler events;
                         ``"os"`` uses Win32 SendInput (Windows only).
        """
        params: dict[str, Any] = {
            "from_id": from_id,
            "to_id": to_id,
            "duration_ms": duration_ms,
        }
        if input_layer != "engine":
            params["input_layer"] = input_layer
        await get_client().call("drag", params)
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    @handle_tool_errors
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
    @handle_tool_errors
    async def key_press(
        id: str,
        key: str,
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Send a key-press event to a specific UI widget.

        Args:
            id:          Stable node id of the target widget.
            key:         Key name. Engine layer supports: ``"Enter"``,
                         ``"Escape"``, ``"Tab"``, ``"Shift+Tab"``.
                         OS layer supports the same set via Win32 SendInput.
            input_layer: ``"engine"`` (default) dispatches Unity EventSystem
                         events; ``"os"`` uses Win32 SendInput (Windows only).
        """
        params: dict[str, Any] = {"id": id, "key": key}
        if input_layer != "engine":
            params["input_layer"] = input_layer
        await get_client().call("key_press", params)
        return {"success": True, "captured_at": time.time()}
