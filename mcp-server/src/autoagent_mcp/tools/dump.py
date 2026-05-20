"""Tree-query tools: dump_tree, find_widget, get_widget."""

from __future__ import annotations

import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors


def register(mcp: FastMCP) -> None:
    """Register dump_tree, find_widget, and get_widget on *mcp*."""

    @mcp.tool()
    @handle_tool_errors
    async def dump_tree(
        include_invisible: bool = False,
        max_depth: int = -1,
    ) -> dict[str, Any]:
        """Dump the current UI tree from the engine adapter.

        Args:
            include_invisible: When False (default) invisible nodes are excluded.
            max_depth:         Maximum hierarchy depth (-1 = unlimited).

        Returns a dict with ``nodes`` (list of node objects) and
        ``captured_at`` (Unix timestamp).
        """
        nodes: list[dict] = await get_client().call("dump_tree", {}) or []

        if not include_invisible:
            nodes = [
                n for n in nodes
                if n.get("visual", {}).get("visible", True)
            ]

        if max_depth >= 0:
            # Simple depth-limit: keep nodes whose hierarchy path fits.
            # depth = number of ancestor ids in children_ids chains.
            # We use parent_id chain length as a proxy.
            id_depth: dict[str, int] = {}
            trimmed: list[dict] = []
            for n in nodes:
                pid = n.get("parent_id")
                d = (id_depth.get(pid, -1) + 1) if pid else 0
                id_depth[n["id"]] = d
                if d <= max_depth:
                    trimmed.append(n)
            nodes = trimmed

        return {"nodes": nodes, "captured_at": time.time()}

    @mcp.tool()
    @handle_tool_errors
    async def find_widget(
        logical_role: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        """Find widget IDs by logical role and/or text content.

        At least one filter must be provided. Returns ``{"ids": [...]}``
        where each entry is a stable node id. Call ``get_widget`` for
        full node details.
        """
        params: dict[str, Any] = {}
        if logical_role is not None:
            params["logical_role"] = logical_role
        if text is not None:
            params["text"] = text

        ids: list[str] = await get_client().call("find_widget", params) or []
        return {"ids": ids}

    @mcp.tool()
    @handle_tool_errors
    async def get_widget(id: str) -> dict[str, Any]:
        """Get the current state of a single UI node by its stable id."""
        node = await get_client().call("get_widget", {"id": id})
        return {"node": node}
