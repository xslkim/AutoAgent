"""End-to-end tests for run_task.py using a mock claude CLI.

Strategy: the mock is `python -c <script>`. We pass it via --claude-cmd
(python.exe path) + --claude-arg (the rest of argv), bypassing shlex so
Windows backslash paths don't get mangled. Real worktree setup is bypassed
via --no-worktree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.state_io import StateRoot, TASK_BUCKETS
from run_task import _prompt_via_arg

AGENT_DIR = Path(__file__).resolve().parent.parent
RUN_TASK = AGENT_DIR / "run_task.py"


def _empty_state(tmp_path: Path) -> Path:
    for b in TASK_BUCKETS + ("logs",):
        (tmp_path / b).mkdir()
    return tmp_path


def _queue_task(state_root: Path, task_id: str, **fields) -> Path:
    data = {
        "id": task_id,
        "title": fields.pop("title", "Mock task"),
        "phase": 0,
        "engine": "none",
        "risk": "low",
        "depends_on": [],
        "spec_path": "docs/tasks.md",
        "goal": "test goal",
        "verification": ["test verification"],
        "retries": 0,
        "max_retries": 5,
    }
    data.update(fields)
    p = state_root / "in_progress" / f"{task_id}.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _run_agent(
    state_root: Path,
    task_id: str,
    *,
    mock_script: str = "import sys; sys.stdin.read(); sys.exit(0)",
    timeout_seconds: int | None = None,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    # argparse rejects "-c" / "--version" as values for --claude-arg because they
    # look like flags. Use --claude-arg=<value> to force them through.
    cmd = [
        sys.executable,
        str(RUN_TASK),
        task_id,
        "--state-root", str(state_root),
        "--no-worktree",
        "--claude-cmd", sys.executable,
        "--claude-arg=-c",
        f"--claude-arg={mock_script}",
    ]
    if timeout_seconds is not None:
        cmd.extend(["--timeout-seconds", str(timeout_seconds)])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


# --- TASK-0020 verification: clean exit -----------------------------------

def test_mock_claude_clean_exit_writes_result(tmp_path):
    """`echo + exit 0` → task.result populated, status=awaiting_ci if PR URL emitted."""
    state = _empty_state(tmp_path)
    task_path = _queue_task(state, "TASK-MOCK-1")

    mock_script = (
        "import sys; sys.stdin.read(); "
        "print('Done. PR: https://github.com/test/repo/pull/1'); "
        "sys.exit(0)"
    )
    r = _run_agent(state, "TASK-MOCK-1", mock_script=mock_script)
    assert r.returncode == 0, r.stderr

    data = json.loads(task_path.read_text(encoding="utf-8"))
    assert data["result"] is not None
    assert data["result"]["status"] == "awaiting_ci"
    assert "pull/1" in data["result"]["pr_url"]


# --- TASK-0020 verification: path violation -------------------------------

def test_mock_claude_path_violation_routes_to_needs_human(tmp_path):
    """exit 1 + 路径违规 stderr → result.status = needs_human."""
    state = _empty_state(tmp_path)
    task_path = _queue_task(state, "TASK-MOCK-2")

    mock_script = (
        "import sys; sys.stdin.read(); "
        "sys.stderr.write('MCP error -32030 PathViolation: tried to write .unity'); "
        "sys.exit(1)"
    )
    r = _run_agent(state, "TASK-MOCK-2", mock_script=mock_script)
    assert r.returncode == 0, r.stderr

    data = json.loads(task_path.read_text(encoding="utf-8"))
    assert data["result"]["status"] == "needs_human"
    assert "path" in data["result"]["needs_human_reason"].lower()


# --- Plain non-zero exit ---------------------------------------------------

def test_mock_claude_generic_failure_marks_failed(tmp_path):
    state = _empty_state(tmp_path)
    task_path = _queue_task(state, "TASK-MOCK-3")

    mock_script = (
        "import sys; sys.stdin.read(); "
        "sys.stderr.write('compile error: missing semicolon'); "
        "sys.exit(2)"
    )
    r = _run_agent(state, "TASK-MOCK-3", mock_script=mock_script)
    assert r.returncode == 0

    data = json.loads(task_path.read_text(encoding="utf-8"))
    assert data["result"]["status"] == "failed"
    assert data["result"]["exit_code"] == 2


# --- Timeout enforcement ---------------------------------------------------

def test_mock_claude_timeout_marks_failed(tmp_path):
    state = _empty_state(tmp_path)
    task_path = _queue_task(state, "TASK-MOCK-4")

    mock_script = "import sys, time; sys.stdin.read(); time.sleep(10)"
    r = _run_agent(state, "TASK-MOCK-4", mock_script=mock_script, timeout_seconds=1)
    assert r.returncode == 0, r.stderr

    data = json.loads(task_path.read_text(encoding="utf-8"))
    assert data["result"]["status"] == "failed"
    assert data["result"]["timed_out"] is True


# --- Log scrubbing (verification: "log 不包含明文 secret") ----------------

def test_log_scrubs_secret_env(tmp_path):
    """A secret-looking env var must not appear verbatim in the log file."""
    state = _empty_state(tmp_path)
    _queue_task(state, "TASK-MOCK-5")

    secret = "sk-ant-superduperLONGFakeKey1234567890abcdef"
    env = dict(os.environ)
    env["ANTHROPIC_API_KEY"] = secret

    # Mock claude echoes its env value (simulating an accidental leak).
    mock_script = (
        "import os, sys; sys.stdin.read(); "
        "print('debug echo: ' + os.environ.get('ANTHROPIC_API_KEY', '(unset)'))"
    )
    r = _run_agent(state, "TASK-MOCK-5", mock_script=mock_script, env=env)
    assert r.returncode == 0, r.stderr

    # By default the agent does NOT forward ANTHROPIC_API_KEY to the child env
    # (see isolated_env). So the mock prints '(unset)'. But even if it did
    # leak, the scrubber must replace it.
    log_files = list((state / "logs" / "TASK-MOCK-5").glob("*.log"))
    assert log_files, "no log file written"
    text = log_files[0].read_text(encoding="utf-8")
    assert secret not in text, "secret leaked into log file!"


def test_task_not_found_returns_error(tmp_path):
    state = _empty_state(tmp_path)
    cmd = [
        sys.executable, str(RUN_TASK), "TASK-NOWHERE",
        "--state-root", str(state),
        "--no-worktree",
        "--claude-cmd", sys.executable,
        "--claude-arg=--version",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace")
    assert r.returncode != 0
    assert "not found" in (r.stdout + r.stderr).lower()


def test_spawn_metadata_filled(tmp_path):
    state = _empty_state(tmp_path)
    task_path = _queue_task(state, "TASK-MOCK-6")
    _run_agent(state, "TASK-MOCK-6")

    data = json.loads(task_path.read_text(encoding="utf-8"))
    assert data["spawn"]["pid"] is not None
    assert data["spawn"]["branch"] == "agent/TASK-MOCK-6"
    assert data["spawn"]["log_path"]
    assert Path(data["spawn"]["log_path"]).is_file()
    assert data["started_at"]
    assert data["finished_at"]


# --- opencode vs claude prompt-delivery detection ------------------------

def test_prompt_via_arg_detects_opencode():
    """opencode receives the prompt as a positional arg; claude reads stdin."""
    # opencode → arg mode
    assert _prompt_via_arg(["opencode", "run"]) is True
    assert _prompt_via_arg(["opencode"]) is True
    assert _prompt_via_arg([r"C:\tools\opencode.cmd", "run"]) is True
    assert _prompt_via_arg(["/usr/local/bin/opencode.exe"]) is True
    # claude / other commands → stdin mode
    assert _prompt_via_arg(["claude", "-p"]) is False
    assert _prompt_via_arg([r"C:\Python\python.exe", "-c", "pass"]) is False
    assert _prompt_via_arg([]) is False


def test_spawn_error_when_executable_missing(tmp_path):
    """If the claude executable can't be spawned, agent still writes a result."""
    state = _empty_state(tmp_path)
    task_path = _queue_task(state, "TASK-MOCK-7")

    cmd = [
        sys.executable, str(RUN_TASK), "TASK-MOCK-7",
        "--state-root", str(state),
        "--no-worktree",
        "--claude-cmd", "/definitely/not/a/real/path/claude",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr

    data = json.loads(task_path.read_text(encoding="utf-8"))
    assert data["result"]["status"] == "failed"
    assert data["result"]["spawn_error"]
    assert data["result"]["exit_code"] == 127
