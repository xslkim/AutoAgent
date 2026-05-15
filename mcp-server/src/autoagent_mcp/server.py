"""MCP server entry. stdio transport, 17 tool stubs registered."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from autoagent_mcp import __version__
from autoagent_mcp.tools import register_all


def build_server() -> FastMCP:
    """Build a fresh FastMCP server with all 17 tools registered.

    Separated from `run_stdio` so tests can introspect the tool registry
    without starting the IO loop.
    """
    mcp = FastMCP(
        name="autoagent-mcp",
        instructions=f"AutoAgent MCP server v{__version__}. Wire protocol v0.1.",
    )
    register_all(mcp)
    return mcp


def run_stdio() -> None:
    """Run the MCP server over stdio. Blocks until stdin closes."""
    build_server().run()
