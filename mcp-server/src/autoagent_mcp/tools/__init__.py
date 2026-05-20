"""AutoAgent MCP tool registration.

Each sub-module owns a cohesive group of tools and exposes a
``register(mcp: FastMCP) -> None`` function.  ``register_all`` calls them
all in order so ``server.py`` only needs one import.

Tool groups
-----------
dump.py      — dump_tree, find_widget, get_widget
click.py     — click, drag, scroll, key_press
text.py      — send_text
screenshot.py — take_screenshot, wait_for
meta.py      — pin_id, list_orphan_ids
session.py   — ping, get_engine_info   (stubs; real session in TASK-0118)
reflect.py   — invoke_method, get_property, set_property  (Phase-4 stubs)
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.tools import (
    click,
    dump,
    meta,
    reflect,
    screenshot,
    session,
    text,
)


def register_all(mcp: FastMCP) -> None:
    """Register all 17 tools on the given FastMCP instance."""
    dump.register(mcp)
    click.register(mcp)
    text.register(mcp)
    screenshot.register(mcp)
    meta.register(mcp)
    session.register(mcp)
    reflect.register(mcp)


TOOL_NAMES: tuple[str, ...] = (
    # Tree queries
    "dump_tree",
    "find_widget",
    "get_widget",
    # Pointer inputs
    "click",
    "drag",
    "scroll",
    "key_press",
    # Text input
    "send_text",
    # Screenshot & wait
    "take_screenshot",
    "wait_for",
    # ID management
    "pin_id",
    "list_orphan_ids",
    # Session
    "ping",
    "get_engine_info",
    # Phase-4 reflection stubs
    "invoke_method",
    "get_property",
    "set_property",
)
"""Canonical ordered list of the 17 tools registered by :func:`register_all`."""
