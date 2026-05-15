"""Phase 0 dummy stubs for the 17 wire methods exposed as MCP tools.

Stubs accept the params shape declared in docs/01-protocol-spec.md §四 and return
mock data that satisfies protocol/schema/methods.json. Phase 1 replaces these
with real WebSocket calls into engine adapters.

`negotiate_version` is wire-internal handshake (docs/01 §七) and is NOT exposed
as an MCP tool — Claude only sees the 17 callable methods.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    """Register all 17 tool stubs on the given FastMCP instance."""

    # ---- 4.1 Tree queries ----

    @mcp.tool()
    def dump_tree(
        root_id: str | None = None,
        include_invisible: bool = False,
        max_depth: int = -1,
        fields: list[Literal["visual", "behavior", "meta", "engine_extras"]] | None = None,
    ) -> dict[str, Any]:
        """Dump UI tree (whole tree or subtree).

        Phase 0 stub: returns an empty tree. Phase 1 connects to engine adapter.
        """
        return {"nodes": [], "captured_at": time.time()}

    @mcp.tool()
    def find_widget(
        by: Literal["id", "logical_role", "role", "type", "text"],
        value: str,
        first_only: bool = True,
    ) -> dict[str, Any]:
        """Find widgets by id / logical_role / role / type / text."""
        return {"nodes": []}

    @mcp.tool()
    def get_widget(id: str) -> dict[str, Any]:
        """Get the current state of a single node by id."""
        return {
            "node": {
                "id": id,
                "type": "Unknown",
                "engine_type": "Unknown",
                "parent_id": None,
                "children_ids": [],
                "stable_id_source": "hash",
                "visual": {"position": [0.0, 0.0], "size": [0.0, 0.0], "visible": False},
            }
        }

    # ---- 4.2 Inputs ----

    @mcp.tool()
    def click(
        id: str,
        button: Literal["left", "right", "middle"] = "left",
        modifiers: list[Literal["ctrl", "shift", "alt", "meta"]] | None = None,
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Click a widget. Target must already have the appropriate interactive
        component attached (e.g., Button) — see docs/01 §4.2 preconditions.
        """
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    def send_text(id: str, text: str, clear_first: bool = True) -> dict[str, Any]:
        """Send text to an input widget."""
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    def drag(
        from_id: str,
        to_id: str,
        duration_ms: int = 200,
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Drag from one widget to another."""
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    def scroll(
        id: str,
        direction: Literal["up", "down", "left", "right"],
        amount: float = 100.0,
    ) -> dict[str, Any]:
        """Scroll a scroll container."""
        return {"success": True, "captured_at": time.time()}

    @mcp.tool()
    def key_press(
        keys: list[str],
        input_layer: Literal["engine", "os"] = "engine",
    ) -> dict[str, Any]:
        """Press one or more keys (e.g., ['Enter'] or ['Ctrl', 'A'])."""
        return {"success": True, "captured_at": time.time()}

    # ---- 4.3 Screenshot & wait ----

    @mcp.tool()
    def take_screenshot(
        scope: Literal["fullscreen", "node", "rect"] = "fullscreen",
        node_id: str | None = None,
        rect: list[float] | None = None,
        format: Literal["png", "jpg"] = "png",
        save_path: str | None = None,
    ) -> dict[str, Any]:
        """Take a screenshot (full screen / node bounds / arbitrary rect)."""
        return {"saved_path": save_path, "base64": None, "size": [0, 0]}

    @mcp.tool()
    def wait_for(
        condition: Literal["widget_appeared", "widget_disappeared", "widget_visible", "text_changed"],
        id: str,
        expected_value: str | None = None,
        timeout_ms: int = 5000,
        poll_interval_ms: int = 100,
    ) -> dict[str, Any]:
        """Block until a condition is met or timeout."""
        return {"success": True, "elapsed_ms": 0}

    # ---- 4.4 Reflection ----

    @mcp.tool()
    def invoke_method(
        id: str,
        script: str,
        method_name: str,
        args: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke a method on a script attached to a node."""
        return {"return_value": None}

    @mcp.tool()
    def get_property(id: str, script: str, property: str) -> dict[str, Any]:
        """Read a behavior/meta property from a script field."""
        return {"value": None}

    @mcp.tool()
    def set_property(
        id: str,
        script: str,
        property: str,
        value: Any,
        category: Literal["behavior", "meta"],
    ) -> dict[str, Any]:
        """Write a behavior/meta property on a script field. Writing visual is rejected server-side."""
        return {"success": True}

    # ---- 4.5 ID management ----

    @mcp.tool()
    def pin_id(current_id: str, new_id: str) -> dict[str, Any]:
        """Pin a stable id to a node (persisted to engine metadata)."""
        return {"success": True}

    @mcp.tool()
    def list_orphan_ids() -> dict[str, Any]:
        """List previously-seen ids that can no longer be located."""
        return {"orphans": []}

    # ---- 4.6 Session ----

    @mcp.tool()
    def ping() -> dict[str, Any]:
        """Liveness check. Pairs with adapter pong."""
        return {"pong": True}

    @mcp.tool()
    def get_engine_info() -> dict[str, Any]:
        """Engine / adapter / protocol version info."""
        return {
            "engine": "Unity",
            "engine_version": "0.0.0-stub",
            "adapter_version": "0.0.0-stub",
            "protocol_version": "0.1",
            "platform": "Windows",
            "build_type": "Editor",
        }


TOOL_NAMES: tuple[str, ...] = (
    "dump_tree",
    "find_widget",
    "get_widget",
    "click",
    "send_text",
    "drag",
    "scroll",
    "key_press",
    "take_screenshot",
    "wait_for",
    "invoke_method",
    "get_property",
    "set_property",
    "pin_id",
    "list_orphan_ids",
    "ping",
    "get_engine_info",
)
"""Canonical ordered list of the 17 tools registered by register_all()."""
