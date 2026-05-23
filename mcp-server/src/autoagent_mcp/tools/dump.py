"""Tree-query tools: dump_tree, dump_tree_delta, find_widget, get_widget."""

from __future__ import annotations

import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors
from autoagent_mcp.tree_cache import get_tree_cache


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
    async def dump_tree_delta(
        since: str | None = None,
        include_invisible: bool = False,
        max_depth: int = -1,
    ) -> dict[str, Any]:
        """Fetch the UI tree and return only nodes that changed since a snapshot.

        On the **first call** (``since=null``): returns the complete tree and a
        ``snapshot_id`` to pass on the next call.

        On **subsequent calls** (``since="<snapshot_id>"``): returns only nodes
        that were **added or modified** plus a ``removed_ids`` list.  Unchanged
        nodes are omitted, significantly reducing the token count when the UI
        is mostly stable.

        If the snapshot has expired (cache holds the last 20 snapshots) the
        response falls back to the full tree and sets ``full_snapshot=true``.

        Args:
            since:             Snapshot ID from a previous ``dump_tree_delta``
                               call.  Omit or pass ``null`` for a full snapshot.
            include_invisible: Include invisible nodes (default ``false``).
            max_depth:         Maximum hierarchy depth (``-1`` = unlimited).

        Returns::

            {
              "snapshot_id": "a1b2c3d4",
              "nodes": [...],          // added / modified nodes only (or all on full)
              "removed_ids": ["id1"],  // IDs no longer in the scene
              "unchanged_count": 42,  // nodes skipped because they didn't change
              "full_snapshot": false,  // true when `since` was absent or expired
              "captured_at": 1716000000.0
            }

        Typical workflow::

            # First call — establish baseline
            r1 = dump_tree_delta()
            snap = r1["snapshot_id"]

            # ... agent interacts with the UI ...

            # Second call — only changed nodes
            r2 = dump_tree_delta(since=snap)
            snap = r2["snapshot_id"]   # update for next call
        """
        client = get_client()
        caps = client.capabilities if hasattr(client, "capabilities") else {}

        if caps.get("dump_tree_delta"):
            params: dict[str, Any] = {
                "include_invisible": include_invisible,
                "max_depth": max_depth,
            }
            if since:
                params["since"] = since
            result: dict = await client.call("dump_tree_delta", params) or {}
            return {
                "snapshot_id": result.get("snapshot_id", ""),
                "nodes": result.get("changed", []),
                "removed_ids": result.get("removed_ids", []),
                "unchanged_count": result.get("unchanged_count", 0),
                "full_snapshot": result.get("full_snapshot", False),
                "captured_at": time.time(),
            }

        # Fallback to full dump + Python-side delta.
        raw_nodes: list[dict] = await client.call("dump_tree", {}) or []

        # Apply the same filters as dump_tree so the diff reflects what the
        # agent actually sees.
        nodes = raw_nodes
        if not include_invisible:
            nodes = [n for n in nodes if n.get("visual", {}).get("visible", True)]

        if max_depth >= 0:
            id_depth: dict[str, int] = {}
            trimmed: list[dict] = []
            for n in nodes:
                pid = n.get("parent_id")
                d = (id_depth.get(pid, -1) + 1) if pid else 0
                id_depth[n["id"]] = d
                if d <= max_depth:
                    trimmed.append(n)
            nodes = trimmed

        cache = get_tree_cache()

        if since is None:
            # Full snapshot — store and return everything.
            snap_id = cache.store(nodes)
            return {
                "snapshot_id": snap_id,
                "nodes": nodes,
                "removed_ids": [],
                "unchanged_count": 0,
                "full_snapshot": True,
                "captured_at": time.time(),
            }

        # Delta — compare with the stored snapshot.
        delta = cache.diff(since, nodes)
        return {
            "snapshot_id": delta.snapshot_id,
            "nodes": delta.changed,
            "removed_ids": delta.removed_ids,
            "unchanged_count": delta.unchanged_count,
            "full_snapshot": delta.full_snapshot,
            "captured_at": time.time(),
        }

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
