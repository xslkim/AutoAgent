"""Phase-4 reflection stubs: invoke_method, get_property, set_property.

These tools expose runtime script introspection and are scheduled for
Phase 4.  They are registered now so that the full 17-tool surface is
available from day 1, but they return stub data and do not make wire calls.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register Phase-4 stub tools on *mcp*."""

    @mcp.tool()
    def invoke_method(
        id: str,
        script: str,
        method_name: str,
        args: list[Any] | None = None,
    ) -> dict[str, Any]:
        """[Phase 4] Invoke a method on a MonoBehaviour attached to a node.

        Not yet wired to the adapter — returns a stub response.
        """
        return {"return_value": None, "_stub": True}

    @mcp.tool()
    def get_property(id: str, script: str, property: str) -> dict[str, Any]:
        """[Phase 4] Read a property from a MonoBehaviour attached to a node.

        Not yet wired to the adapter — returns a stub response.
        """
        return {"value": None, "_stub": True}

    @mcp.tool()
    def set_property(
        id: str,
        script: str,
        property: str,
        value: Any,
        category: Literal["behavior", "meta"],
    ) -> dict[str, Any]:
        """[Phase 4] Write a property on a MonoBehaviour attached to a node.

        Writing visual properties is rejected by the server.
        Not yet wired to the adapter — returns a stub response.
        """
        return {"success": True, "_stub": True}
