"""state_io.py: atomic moves, bucket listing, stop_signal helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.state_io import StateRoot, TASK_BUCKETS, load_all_tasks


@pytest.fixture
def state(tmp_path: Path) -> StateRoot:
    for b in TASK_BUCKETS + ("logs",):
        (tmp_path / b).mkdir()
    return StateRoot(tmp_path)


def _write(root: StateRoot, bucket: str, task_id: str, **extra) -> Path:
    data = {"id": task_id, "title": f"Task {task_id}", "depends_on": []}
    data.update(extra)
    path = root.bucket(bucket) / f"{task_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_bucket_paths(state):
    assert state.bucket("queue").name == "queue"
    with pytest.raises(ValueError):
        state.bucket("not_a_bucket")


def test_list_task_files_sorted(state):
    _write(state, "queue", "TASK-0003")
    _write(state, "queue", "TASK-0001")
    _write(state, "queue", "TASK-0002")
    ids = state.list_task_ids("queue")
    assert ids == ["TASK-0001", "TASK-0002", "TASK-0003"]


def test_list_ignores_non_task_files(state):
    _write(state, "queue", "TASK-0001")
    (state.bucket("queue") / "README.md").write_text("noise")
    (state.bucket("queue") / ".gitkeep").touch()
    assert state.list_task_ids("queue") == ["TASK-0001"]


def test_find_returns_first_matching_bucket(state):
    _write(state, "ready", "TASK-0001")
    bucket, path = state.find("TASK-0001")
    assert bucket == "ready"
    assert path.parent.name == "ready"


def test_find_missing_returns_none(state):
    assert state.find("TASK-9999") is None


def test_move_task_changes_bucket(state):
    _write(state, "queue", "TASK-0001")
    new_path = state.move_task("TASK-0001", "ready")
    assert new_path.parent.name == "ready"
    assert state.find("TASK-0001") == ("ready", new_path)
    # source bucket emptied
    assert state.list_task_ids("queue") == []


def test_move_task_missing_raises(state):
    with pytest.raises(FileNotFoundError):
        state.move_task("TASK-9999", "ready")


def test_atomic_write_replaces_existing(state):
    p = state.bucket("queue") / "TASK-0001.json"
    state.write_task(p, {"id": "TASK-0001", "v": 1})
    state.write_task(p, {"id": "TASK-0001", "v": 2})
    assert state.load_task(p)["v"] == 2
    # tmp file must not linger
    assert not (p.parent / "TASK-0001.json.tmp").exists()


def test_stop_signal_lifecycle(state):
    assert not state.is_stopped()
    state.touch_stop_signal("manual test")
    assert state.is_stopped()
    assert state.stop_signal_path.read_text(encoding="utf-8") == "manual test"
    state.clear_stop_signal()
    assert not state.is_stopped()
    # Second clear is a no-op (idempotent)
    state.clear_stop_signal()


def test_load_all_tasks_collects_across_buckets(state):
    _write(state, "queue", "TASK-0001")
    _write(state, "ready", "TASK-0002")
    _write(state, "done", "TASK-0003")
    all_tasks = load_all_tasks(state)
    assert set(all_tasks) == {"TASK-0001", "TASK-0002", "TASK-0003"}
    assert all_tasks["TASK-0002"][0] == "ready"
