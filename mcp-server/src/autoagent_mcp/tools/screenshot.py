"""Screenshot and wait tools: take_screenshot, wait_for."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors


def register(mcp: FastMCP) -> None:
    """Register take_screenshot and wait_for on *mcp*."""

    @mcp.tool()
    @handle_tool_errors
    async def take_screenshot(
        save_path: str,
        scope: Literal["fullscreen", "node", "rect"] = "fullscreen",
        node_id: str | None = None,
        rect: list[float] | None = None,
    ) -> dict[str, Any]:
        """Capture a screenshot and write it to *save_path*.

        ``scope`` controls the capture region:

        * ``"fullscreen"`` — entire game window (default).
        * ``"node"`` — bounding rect of the widget identified by *node_id*.
        * ``"rect"`` — explicit ``[x, y, w, h]`` region supplied in *rect*.

        The file format is inferred from *save_path*'s extension (``.png``
        or ``.jpg``).  Returns ``{"saved_path": "..."}`` on success.
        """
        params: dict[str, Any] = {"path": save_path, "mode": scope}

        if scope == "node":
            if not node_id:
                raise ValueError("node_id is required when scope='node'")
            params["id"] = node_id

        elif scope == "rect":
            if not rect or len(rect) < 4:
                raise ValueError("rect must be [x, y, w, h] when scope='rect'")
            params["x"] = int(rect[0])
            params["y"] = int(rect[1])
            params["w"] = int(rect[2])
            params["h"] = int(rect[3])

        result = await get_client().call("take_screenshot", params)
        path = (result or {}).get("path", save_path)
        return {"saved_path": path}

    @mcp.tool()
    @handle_tool_errors
    async def wait_for(
        condition: Literal[
            "widget_appeared",
            "widget_disappeared",
            "widget_visible",
            "text_changed",
        ],
        id: str,
        expected_value: str | None = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Block until a UI condition is met or the timeout expires.

        Conditions:

        * ``widget_appeared``    — the widget exists in the active scene.
        * ``widget_disappeared`` — the widget is absent from the active scene.
        * ``widget_visible``     — the widget is present **and** visible.
        * ``text_changed``       — the widget's text equals *expected_value*.

        Returns ``{"success": True, "elapsed_ms": N}`` on success; raises
        ``AdapterError(-32005)`` on timeout.
        """
        params: dict[str, Any] = {
            "condition": condition,
            "id": id,
            "timeout_ms": timeout_ms,
        }
        if expected_value is not None:
            params["expected_value"] = expected_value

        result = await get_client().call("wait_for", params)
        return result or {"success": True, "elapsed_ms": 0}
