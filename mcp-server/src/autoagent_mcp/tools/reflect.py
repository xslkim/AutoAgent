"""Reflection tools: invoke_method, get_property, set_property.

Expose runtime script introspection via the wire protocol.
The adapter enforces the visual-write guard (-32003); the MCP layer
forwards the call and surfaces any wire error as a Python exception.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors


def register(mcp: FastMCP) -> None:
    """Register invoke_method, get_property, set_property on *mcp*."""

    @mcp.tool()
    @handle_tool_errors
    async def invoke_method(
        id: str,
        script: str,
        method_name: str,
        args: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke a public method on a MonoBehaviour attached to the node.

        Args:
            id:          Stable ID of the target node.
            script:      MonoBehaviour type name (e.g. ``"LoginController"``).
            method_name: Name of the method to call.
            args:        Positional arguments (strings, numbers, bools, nulls).

        Returns:
            ``{"return_value": <serialized result or null>}``
        """
        result = await get_client().call(
            "invoke_method",
            {"id": id, "script": script, "method_name": method_name,
             "args": args or []},
        )
        return result

    @mcp.tool()
    @handle_tool_errors
    async def get_property(id: str, script: str, property: str) -> dict[str, Any]:
        """Read a field or property from a MonoBehaviour on the node.

        Args:
            id:       Stable ID of the target node.
            script:   MonoBehaviour type name.
            property: Field or property name.

        Returns:
            ``{"value": <serialized value>}``
        """
        result = await get_client().call(
            "get_property",
            {"id": id, "script": script, "property": property},
        )
        return result

    @mcp.tool()
    @handle_tool_errors
    async def set_property(
        id: str,
        script: str,
        property: str,
        value: Any,
        category: Literal["behavior", "meta"],
    ) -> dict[str, Any]:
        """Write a field or property on a MonoBehaviour on the node.

        The adapter rejects ``category="visual"`` with error -32003
        VisualPropertyWrite.  Only ``"behavior"`` and ``"meta"`` categories
        are accepted here and forwarded to the adapter.

        Args:
            id:       Stable ID of the target node.
            script:   MonoBehaviour type name.
            property: Field or property name.
            value:    New value (any JSON-serializable primitive).
            category: Must be ``"behavior"`` or ``"meta"``.

        Returns:
            ``{"success": true}``
        """
        result = await get_client().call(
            "set_property",
            {"id": id, "script": script, "property": property,
             "value": value, "category": category},
        )
        return result
