"""events.py: append + iter on events.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from lib.events import append_event, iter_events


def test_append_creates_parent_dir(tmp_path):
    p = tmp_path / "subdir" / "events.jsonl"
    append_event(p, "polling_tick", in_progress=0, ready=0)
    assert p.is_file()


def test_append_and_iter_round_trip(tmp_path):
    p = tmp_path / "events.jsonl"
    append_event(p, "task_spawned", task_id="TASK-0001", pid=123)
    append_event(p, "task_done", task_id="TASK-0001", duration_s=42)
    events = list(iter_events(p))
    assert len(events) == 2
    assert events[0]["type"] == "task_spawned"
    assert events[0]["task_id"] == "TASK-0001"
    assert events[1]["type"] == "task_done"
    assert "ts" in events[0]


def test_iter_missing_file_yields_nothing(tmp_path):
    assert list(iter_events(tmp_path / "nope.jsonl")) == []


def test_iter_skips_blank_lines(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text(
        '{"ts": "2026-01-01T00:00:00Z", "type": "a"}\n'
        '\n'
        '{"ts": "2026-01-01T00:00:01Z", "type": "b"}\n',
        encoding="utf-8",
    )
    events = list(iter_events(p))
    assert [e["type"] for e in events] == ["a", "b"]


def test_iter_tolerates_corrupted_line(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text(
        '{"ts": "2026-01-01T00:00:00Z", "type": "a"}\n'
        '{ this is not valid json\n'
        '{"ts": "2026-01-01T00:00:01Z", "type": "b"}\n',
        encoding="utf-8",
    )
    events = list(iter_events(p))
    # Corrupted middle line is silently skipped.
    assert [e["type"] for e in events] == ["a", "b"]


def test_append_includes_arbitrary_fields(tmp_path):
    p = tmp_path / "events.jsonl"
    append_event(p, "decision_parsed", original_text="approve 11", parsed={"action": "approve_retry"})
    line = p.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["original_text"] == "approve 11"
    assert record["parsed"]["action"] == "approve_retry"
