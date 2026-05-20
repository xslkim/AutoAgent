"""ID-management tools: pin_id, list_orphan_ids."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client


def register(mcp: FastMCP) -> None:
    """Register pin_id and list_orphan_ids on *mcp*."""

    @mcp.tool()
    async def pin_id(current_id: str, new_id: str) -> dict[str, Any]:
        """Attach a stable, human-chosen id to a widget.

        After pinning, every subsequent ``dump_ui_tree`` call will identify
        the widget with ``new_id`` and report ``stable_id_source = "pinned"``,
        so the id survives UI restructuring that would otherwise shift the
        hash-derived id.

        Raises ``AdapterError(-32001)`` if *current_id* cannot be found.
        """
        await get_client().call("pin_id", {"id": current_id, "pinned_id": new_id})
        return {"success": True, "pinned_id": new_id}

    @mcp.tool()
    async def list_orphan_ids() -> dict[str, Any]:
        """Return ids that were present in the last dump but are now missing.

        Useful for detecting deleted or renamed widgets between test runs.
        Returns ``{"orphans": ["id1", "id2", ...]}``.
        """
        orphans: list[str] = await get_client().call("list_orphan_ids", {}) or []
        return {"orphans": orphans}
