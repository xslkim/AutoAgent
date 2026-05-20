"""Text-input tool: send_text."""

from __future__ import annotations

import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from autoagent_mcp.connector import get_client
from autoagent_mcp.connector.error_handler import handle_tool_errors


def register(mcp: FastMCP) -> None:
    """Register send_text on *mcp*."""

    @mcp.tool()
    @handle_tool_errors
    async def send_text(
        id: str,
        text: str,
        clear_first: bool = True,
    ) -> dict[str, Any]:
        """Type text into an input widget.

        When *clear_first* is ``True`` (default) any existing content is
        cleared before the new text is inserted.
        """
        await get_client().call(
            "send_text",
            {"id": id, "text": text, "clear_first": clear_first},
        )
        return {"success": True, "captured_at": time.time()}
