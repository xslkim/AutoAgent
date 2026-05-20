"""MCP tool error handler — structured error responses for the AI.

Every MCP tool that communicates with the engine adapter is decorated with
:func:`handle_tool_errors`.  The decorator intercepts three failure modes and
converts them into structured return dicts instead of letting raw exceptions
propagate to FastMCP (which would produce opaque error strings for the AI):

* **AdapterError** (JSON-RPC error from the adapter, e.g. -32001 WidgetNotFound)
  → ``{"success": False, "error": {"code": -32001, "message": "...", "error_type": "WidgetNotFound"}}``

* **EngineDisconnectedError** (WebSocket transport failure / adapter crash)
  → ``{"success": False, "error": {"code": -32099, "error_type": "EngineDisconnected", ...}}``

* **RuntimeError("No engine connected …")** — ``get_client()`` raised before
  ``connect_engine`` was called
  → ``{"success": False, "error": {"code": -32099, "error_type": "EngineDisconnected", ...}}``

All other exceptions propagate normally so genuine programming bugs are visible.

Usage::

    @mcp.tool()
    @handle_tool_errors
    async def click(id: str) -> dict:
        await get_client().call("click", {"id": id})
        return {"success": True}
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from autoagent_mcp.connector.websocket_client import AdapterError, EngineDisconnectedError

# ---------------------------------------------------------------------------
# Wire-error-code → human-readable type name
# ---------------------------------------------------------------------------

_CODE_TO_TYPE: dict[int, str] = {
    -32700: "ParseError",
    -32600: "InvalidRequest",
    -32601: "MethodNotFound",
    -32602: "InvalidParams",
    -32603: "InternalError",
    -32001: "WidgetNotFound",
    -32002: "WidgetNotInteractable",
    -32003: "VisualPropertyWrite",
    -32004: "StructuralChange",
    -32005: "TimeoutError",
    -32006: "InputInjectionFailed",
    -32007: "EngineThreadViolation",
    -32008: "ScreenshotFailed",
    -32010: "VersionMismatch",
    -32011: "NegotiationTimeout",
    -32012: "SubprotocolMismatch",
    -32013: "NotNegotiated",
    -32030: "PathViolation",
    EngineDisconnectedError.code: "EngineDisconnected",
}

_NO_ENGINE_MSG = "No engine connected. Call connect_engine first."


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def error_result(code: int, message: str, error_type: str | None = None) -> dict[str, Any]:
    """Build the canonical error-response dict returned by a tool on failure.

    Args:
        code:       JSON-RPC error code.
        message:    Human-readable explanation.
        error_type: Snake-case type name (inferred from *code* if omitted).

    Returns:
        ``{"success": False, "error": {"code": ..., "message": ..., "error_type": ...}}``
    """
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "error_type": error_type or _CODE_TO_TYPE.get(code, "UnknownError"),
        },
    }


def handle_tool_errors(fn: Callable) -> Callable:
    """Decorator that converts adapter/transport exceptions to structured dicts.

    Apply *inside* ``@mcp.tool()`` so FastMCP still sees the original function
    signature for schema generation::

        @mcp.tool()
        @handle_tool_errors
        async def click(id: str) -> dict:
            ...

    Three exception types are handled; everything else propagates:

    * :class:`AdapterError` — JSON-RPC error from the adapter.
    * :class:`EngineDisconnectedError` — WebSocket transport failure.
    * ``RuntimeError`` whose message starts with ``"No engine connected"``
      — raised by :func:`~connector.get_client` when no session exists.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)

        except AdapterError as exc:
            return error_result(exc.code, exc.message)

        except EngineDisconnectedError as exc:
            return error_result(
                EngineDisconnectedError.code,
                exc.message,
                "EngineDisconnected",
            )

        except RuntimeError as exc:
            msg = str(exc)
            if msg.startswith("No engine connected") or "connect_engine" in msg:
                return error_result(
                    EngineDisconnectedError.code,
                    _NO_ENGINE_MSG,
                    "EngineDisconnected",
                )
            raise  # genuine programming error — let it propagate

    return wrapper
