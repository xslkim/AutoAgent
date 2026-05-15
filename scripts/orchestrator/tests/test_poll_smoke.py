"""End-to-end smoke tests for the helper scripts on a temp state/ tree."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.state_io import StateRoot, TASK_BUCKETS

ORCHESTRATOR_DIR = Path(__file__).resolve().parent.parent


def _empty_state(tmp_path: Path) -> Path:
    for b in TASK_BUCKETS + ("logs",):
        (tmp_path / b).mkdir()
    return tmp_path


def _run(script: str, *args, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ORCHESTRATOR_DIR / script), *args],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=cwd,
        encoding="utf-8",
        errors="replace",
    )


def test_status_on_empty_state_does_not_crash(tmp_path):
    state = _empty_state(tmp_path)
    r = _run("status.py", "--state-root", str(state))
    assert r.returncode == 0, r.stderr


def test_poll_dry_run_on_empty_outputs_idle_message(tmp_path):
    """TASK-0019 verification: 输出"无任务可调度"."""
    state = _empty_state(tmp_path)
    r = _run("poll.py", "--state-root", str(state), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "无任务可调度" in r.stdout


def test_poll_moves_no_dep_task_to_ready(tmp_path):
    state = _empty_state(tmp_path)
    root = StateRoot(state)
    (state / "queue" / "TASK-0001.json").write_text(
        json.dumps({"id": "TASK-0001", "depends_on": []}), encoding="utf-8"
    )
    r = _run("poll.py", "--state-root", str(state))
    assert r.returncode == 0, r.stderr
    assert root.find("TASK-0001") == ("ready", root.bucket("ready") / "TASK-0001.json")


def test_poll_blocks_task_when_dep_failed(tmp_path):
    state = _empty_state(tmp_path)
    (state / "failed" / "TASK-0001.json").write_text(
        json.dumps({"id": "TASK-0001", "depends_on": []}), encoding="utf-8"
    )
    (state / "queue" / "TASK-0002.json").write_text(
        json.dumps({"id": "TASK-0002", "depends_on": ["TASK-0001"]}), encoding="utf-8"
    )
    r = _run("poll.py", "--state-root", str(state))
    assert r.returncode == 0, r.stderr
    root = StateRoot(state)
    assert root.find("TASK-0002")[0] == "blocked"


def test_poll_refuses_with_stop_signal(tmp_path):
    state = _empty_state(tmp_path)
    (state / "stop_signal").write_text("manual stop", encoding="utf-8")
    r = _run("poll.py", "--state-root", str(state))
    assert r.returncode == 0, r.stderr
    assert "stop_signal" in r.stdout.lower()


def test_stop_and_resume_round_trip(tmp_path):
    state = _empty_state(tmp_path)
    r1 = _run("stop.py", "--state-root", str(state), "--reason", "test stop")
    assert r1.returncode == 0
    assert (state / "stop_signal").is_file()
    r2 = _run("resume.py", "--state-root", str(state))
    assert r2.returncode == 0
    assert not (state / "stop_signal").is_file()


def test_collect_on_empty_state(tmp_path):
    state = _empty_state(tmp_path)
    r = _run("collect.py", "--state-root", str(state))
    assert r.returncode == 0, r.stderr
    assert "nothing to collect" in r.stdout


def test_spawn_dry_run_on_empty_state(tmp_path):
    state = _empty_state(tmp_path)
    r = _run("spawn.py", "--state-root", str(state), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "无任务可调度" in r.stdout


def test_spawn_dry_run_with_ready_task(tmp_path):
    state = _empty_state(tmp_path)
    (state / "ready" / "TASK-0001.json").write_text(
        json.dumps({"id": "TASK-0001", "depends_on": []}), encoding="utf-8"
    )
    r = _run("spawn.py", "--state-root", str(state), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "TASK-0001" in r.stdout
    # Dry-run must not actually move the task.
    root = StateRoot(state)
    assert root.find("TASK-0001")[0] == "ready"


def test_spawn_refuses_when_in_progress_busy(tmp_path):
    state = _empty_state(tmp_path)
    (state / "in_progress" / "TASK-0001.json").write_text(
        json.dumps({"id": "TASK-0001", "depends_on": []}), encoding="utf-8"
    )
    (state / "ready" / "TASK-0002.json").write_text(
        json.dumps({"id": "TASK-0002", "depends_on": []}), encoding="utf-8"
    )
    r = _run("spawn.py", "--state-root", str(state), "--dry-run")
    assert r.returncode == 0
    assert "serial" in r.stdout.lower() or "in_progress" in r.stdout.lower()


def test_collect_zombie_agent_returns_to_ready(tmp_path):
    state = _empty_state(tmp_path)
    # PID 999999 almost certainly not running. result is missing so collector
    # should detect zombie and bounce back to ready.
    (state / "in_progress" / "TASK-0001.json").write_text(
        json.dumps({"id": "TASK-0001", "depends_on": [], "retries": 0,
                    "spawn": {"pid": 999999}, "result": None}),
        encoding="utf-8",
    )
    r = _run("collect.py", "--state-root", str(state))
    assert r.returncode == 0
    root = StateRoot(state)
    bucket, path = root.find("TASK-0001")
    assert bucket == "ready"
    data = root.load_task(path)
    assert data["retries"] == 1


def test_collect_awaiting_ci_routing(tmp_path):
    state = _empty_state(tmp_path)
    (state / "in_progress" / "TASK-0001.json").write_text(
        json.dumps({
            "id": "TASK-0001",
            "depends_on": [],
            "spawn": {"pid": 0},
            "result": {"status": "awaiting_ci", "pr_url": "https://example/pr/1"},
        }),
        encoding="utf-8",
    )
    r = _run("collect.py", "--state-root", str(state))
    assert r.returncode == 0
    assert StateRoot(state).find("TASK-0001")[0] == "awaiting_ci"


def test_collect_failed_retries_up_to_max(tmp_path):
    state = _empty_state(tmp_path)
    (state / "in_progress" / "TASK-0001.json").write_text(
        json.dumps({
            "id": "TASK-0001",
            "depends_on": [],
            "retries": 4,
            "max_retries": 5,
            "spawn": {"pid": 0},
            "result": {"status": "failed", "error": "boom"},
        }),
        encoding="utf-8",
    )
    r = _run("collect.py", "--state-root", str(state))
    assert r.returncode == 0
    # 4+1 = 5, equals max → goes to failed/
    assert StateRoot(state).find("TASK-0001")[0] == "failed"


def test_collect_failed_below_max_retries(tmp_path):
    state = _empty_state(tmp_path)
    (state / "in_progress" / "TASK-0001.json").write_text(
        json.dumps({
            "id": "TASK-0001",
            "depends_on": [],
            "retries": 1,
            "max_retries": 5,
            "spawn": {"pid": 0},
            "result": {"status": "failed", "error": "boom"},
        }),
        encoding="utf-8",
    )
    r = _run("collect.py", "--state-root", str(state))
    assert r.returncode == 0
    root = StateRoot(state)
    bucket, path = root.find("TASK-0001")
    assert bucket == "ready"
    data = root.load_task(path)
    assert data["retries"] == 2
    assert data["result"] is None  # cleared for retry
    assert len(data["history"]) == 1  # previous attempt recorded
