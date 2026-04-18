"""MCP Server — Model Context Protocol interface for AutoVisionTest.

Exposes 6 tools as specified in product document §10.3:
1. start_test_session    — start a test session
2. get_session_status     — get session status
3. get_session_report     — get session report
4. stop_session          — stop a running session
5. list_recordings       — list all recordings
6. invalidate_recording  — delete a recording

Evidence screenshots are exposed as MCP resources with URIs like:
  autovt://evidence/{session_id}/step_{idx}_after.png
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp_server = FastMCP("AutoVisionTest")

# Module-level scheduler reference
_scheduler: Any = None


def _get_scheduler():
    """Get or lazily initialise the scheduler."""
    global _scheduler
    return _scheduler


def _set_scheduler(scheduler: Any) -> None:
    """Set the scheduler instance."""
    global _scheduler
    _scheduler = scheduler


def run_mcp_server(config_path: str | None = None, http_addr: str | None = None) -> None:
    """Start the MCP server.

    Args:
        config_path: Path to config YAML file.
        http_addr: HTTP address for SSE mode (e.g. ":8090").
            If None, runs in stdio mode.
    """
    # Initialise scheduler
    try:
        from autovisiontest.interfaces.cli_commands import _create_scheduler

        scheduler = _create_scheduler(config_path)
        _set_scheduler(scheduler)
    except Exception:
        logger.exception("scheduler_init_failed")

    if http_addr:
        host, _, port_str = http_addr.partition(":")
        host = host or "0.0.0.0"
        port = int(port_str) if port_str else 8090
        mcp_server.run(transport="sse", host=host, port=port)
    else:
        mcp_server.run(transport="stdio")


# ── Tools ────────────────────────────────────────────────────────────────


@mcp_server.tool()
def start_test_session(
    goal: str,
    app_path: str,
    app_args: str = "",
    timeout_ms: int = 0,
) -> str:
    """Start a new test session.

    Args:
        goal: Natural language goal for the test.
        app_path: Path to the application executable.
        app_args: Space-separated arguments for the application.
        timeout_ms: Maximum session duration in milliseconds (0 = default).

    Returns:
        JSON string with session_id.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return json.dumps({"error": "Scheduler not available"})

    args_list = app_args.split() if app_args else None
    timeout = timeout_ms if timeout_ms > 0 else None

    session_id = scheduler.start_session(
        goal=goal,
        app_path=app_path,
        app_args=args_list,
        timeout_ms=timeout,
    )
    return json.dumps({"session_id": session_id})


@mcp_server.tool()
def get_session_status(session_id: str) -> str:
    """Get the status of a test session.

    Args:
        session_id: The session identifier.

    Returns:
        JSON string with session status details.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return json.dumps({"error": "Scheduler not available"})

    from autovisiontest.scheduler.session_store import SessionStore

    data_dir = Path(scheduler._data_dir)
    store = SessionStore(data_dir=data_dir)
    record = store.load(session_id)
    if record is None:
        return json.dumps({"error": "Session not found"})

    return json.dumps({
        "session_id": record.session_id,
        "status": record.status.value,
        "goal": record.goal,
        "mode": record.mode,
        "termination_reason": record.termination_reason,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    })


@mcp_server.tool()
def get_session_report(session_id: str) -> str:
    """Get the test report for a completed session.

    The report includes evidence screenshots as MCP resources.

    Args:
        session_id: The session identifier.

    Returns:
        JSON string with the full report.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return json.dumps({"error": "Scheduler not available"})

    report = scheduler.get_report(session_id)
    if report is None:
        return json.dumps({"error": "Report not found"})

    # Add resource URIs for screenshots
    report_text = json.dumps(report, indent=2, ensure_ascii=False)
    return report_text


@mcp_server.tool()
def stop_session(session_id: str) -> str:
    """Stop a running test session.

    Args:
        session_id: The session identifier.

    Returns:
        JSON string with stopped status.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return json.dumps({"error": "Scheduler not available"})

    stopped = scheduler.stop(session_id)
    return json.dumps({"stopped": stopped})


@mcp_server.tool()
def list_recordings() -> str:
    """List all recorded test cases.

    Returns:
        JSON string with a list of recordings.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return json.dumps({"error": "Scheduler not available"})

    cases = scheduler._store.list_all()
    recordings = [
        {
            "fingerprint": c.metadata.fingerprint,
            "goal": c.goal,
            "app_path": c.app_config.app_path,
            "steps": len(c.steps),
        }
        for c in cases
    ]
    return json.dumps(recordings, indent=2, ensure_ascii=False)


@mcp_server.tool()
def invalidate_recording(fingerprint: str) -> str:
    """Delete a recorded test case.

    Args:
        fingerprint: The recording fingerprint to delete.

    Returns:
        JSON string with deleted status.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return json.dumps({"error": "Scheduler not available"})

    deleted = scheduler.invalidate_recording(fingerprint)
    return json.dumps({"deleted": deleted})


# ── Resources ───────────────────────────────────────────────────────────


@mcp_server.resource("autovt://evidence/{session_id}/step_{step_idx}_after.png")
def get_evidence_screenshot(session_id: str, step_idx: str) -> str:
    """Get a step's after-action screenshot as base64.

    Args:
        session_id: Session identifier.
        step_idx: Step index.

    Returns:
        Base64-encoded PNG screenshot.
    """
    scheduler = _get_scheduler()
    if scheduler is None:
        return ""

    data_dir = Path(scheduler._data_dir)
    img_path = data_dir / "evidence" / session_id / f"step_{step_idx}_after.png"
    if not img_path.exists():
        return ""

    return base64.b64encode(img_path.read_bytes()).decode("ascii")
