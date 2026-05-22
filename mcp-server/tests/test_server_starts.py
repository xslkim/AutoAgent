"""TASK-0002 verification.

- Server builds without error.
- All 17 wire methods are registered as tools.
- CLI --help prints help.
- CLI --list-tools prints 17 names.
"""

from __future__ import annotations

import io
import subprocess
import sys
from contextlib import redirect_stdout
from unittest.mock import AsyncMock

import pytest

from autoagent_mcp.connector import WebSocketClient, set_client
from autoagent_mcp.server import build_server
from autoagent_mcp.tools import TOOL_NAMES
from autoagent_mcp.cli import cli


@pytest.fixture(autouse=False)
def mock_connected_client():
    """Set a mock WebSocketClient as the active client for tool-invocation tests."""
    client = AsyncMock(spec=WebSocketClient)
    client.connected = True
    client.call = AsyncMock(return_value=None)
    set_client(client)
    yield client
    set_client(None)


EXPECTED_COUNT = 26  # 25 + compare_lpips_to_baseline (TASK-0403)


def test_tool_names_count():
    assert len(TOOL_NAMES) == EXPECTED_COUNT


def test_tool_names_no_negotiate_version():
    """negotiate_version is wire-internal handshake (docs/01 §七), not an MCP tool."""
    assert "negotiate_version" not in TOOL_NAMES


def test_build_server_does_not_crash():
    mcp = build_server()
    assert mcp is not None


@pytest.mark.asyncio
async def test_all_17_tools_registered():
    mcp = build_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    missing = set(TOOL_NAMES) - names
    extra = names - set(TOOL_NAMES)
    assert not missing, f"missing tools: {missing}"
    assert not extra, f"unexpected tools: {extra}"
    assert len(names) == EXPECTED_COUNT


@pytest.mark.asyncio
async def test_tool_has_description():
    """Each tool should have a non-empty description (from docstring)."""
    mcp = build_server()
    tools = await mcp.list_tools()
    for tool in tools:
        assert tool.description, f"tool {tool.name} has no description"


@pytest.mark.asyncio
async def test_dump_tree_returns_protocol_shape(mock_connected_client):
    mock_connected_client.call.return_value = []
    mcp = build_server()
    result = await mcp.call_tool("dump_tree", {})
    # FastMCP wraps the return value; just verify the call doesn't raise.
    assert result is not None
    mock_connected_client.call.assert_called_once_with("dump_tree", {})


@pytest.mark.asyncio
async def test_click_accepts_minimal_params(mock_connected_client):
    mock_connected_client.call.return_value = None
    mcp = build_server()
    result = await mcp.call_tool("click", {"id": "some_button"})
    assert result is not None
    mock_connected_client.call.assert_called_once_with("click", {"id": "some_button"})


def test_cli_list_tools(capsys):
    rc = cli(["--list-tools"])
    assert rc == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == EXPECTED_COUNT
    assert set(lines) == set(TOOL_NAMES)


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "autoagent-mcp" in captured.out


def test_cli_help_subprocess():
    """Subprocess invocation to catch argparse / import errors at the entry boundary."""
    import os
    from pathlib import Path

    src_dir = Path(__file__).resolve().parent.parent / "src"
    env = {**os.environ, "PYTHONPATH": str(src_dir)}
    result = subprocess.run(
        [sys.executable, "-m", "autoagent_mcp.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "autoagent-mcp" in result.stdout
    assert "--list-tools" in result.stdout
