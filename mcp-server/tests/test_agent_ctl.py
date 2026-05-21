"""TASK-0129: Tests for autoagent-stop / autoagent-status CLI tools.

All tests redirect the path constants in ``agent_ctl`` and ``agent_cli``
to a tmp_path sandbox so they never touch the real ``~/.autoagent/``.

Coverage:
- agent_ctl.write_stop  — creates STOP file + appends to last_stop.log
- agent_ctl.read_stop   — parses file; graceful on missing / malformed
- agent_ctl.is_stopped  — reflects STOP file presence
- agent_ctl.clear_stop  — removes file; returns True/False
- agent_ctl.list_sessions — scans SESSIONS_DIR, sorted newest-first
- agent_ctl.get_status  — composite dict
- stop_cli()  — success, already-stopped guard, --force, --reason
- status_cli() — human-readable, --json, stopped / running scenarios
"""

from __future__ import annotations

import io
import json
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import autoagent_mcp.agent_ctl as ctl
from autoagent_mcp.agent_cli import status_cli, stop_cli


# ---------------------------------------------------------------------------
# Fixtures: redirect module-level path constants into tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Redirect all path constants to a tmp_path sandbox."""
    aa_dir = tmp_path / ".autoagent"
    aa_dir.mkdir()
    monkeypatch.setattr(ctl, "AUTOAGENT_DIR", aa_dir)
    monkeypatch.setattr(ctl, "STOP_FILE", aa_dir / "STOP")
    monkeypatch.setattr(ctl, "LAST_STOP_LOG", aa_dir / "last_stop.log")
    monkeypatch.setattr(ctl, "SESSIONS_DIR", aa_dir / "sessions")
    return aa_dir


# ---------------------------------------------------------------------------
# agent_ctl.write_stop
# ---------------------------------------------------------------------------


class TestWriteStop:
    def test_creates_stop_file(self, sandbox):
        ctl.write_stop()
        assert ctl.STOP_FILE.is_file()

    def test_stop_file_contains_json(self, sandbox):
        ctl.write_stop("test reason")
        doc = json.loads(ctl.STOP_FILE.read_text(encoding="utf-8"))
        assert doc["reason"] == "test reason"
        assert "stopped_at" in doc
        assert "pid" in doc

    def test_default_reason(self, sandbox):
        ctl.write_stop()
        doc = json.loads(ctl.STOP_FILE.read_text(encoding="utf-8"))
        assert "manual stop" in doc["reason"]

    def test_appends_to_last_stop_log(self, sandbox):
        ctl.write_stop("first stop")
        ctl.write_stop("second stop")
        lines = ctl.LAST_STOP_LOG.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert "first stop" in lines[0]
        assert "second stop" in lines[1]

    def test_returns_record_dict(self, sandbox):
        record = ctl.write_stop("reason")
        assert isinstance(record, dict)
        assert record["reason"] == "reason"

    def test_creates_parent_dir_if_missing(self, tmp_path, monkeypatch):
        new_dir = tmp_path / "new_autoagent"
        monkeypatch.setattr(ctl, "AUTOAGENT_DIR", new_dir)
        monkeypatch.setattr(ctl, "STOP_FILE", new_dir / "STOP")
        monkeypatch.setattr(ctl, "LAST_STOP_LOG", new_dir / "last_stop.log")
        ctl.write_stop()
        assert (new_dir / "STOP").is_file()


# ---------------------------------------------------------------------------
# agent_ctl.read_stop
# ---------------------------------------------------------------------------


class TestReadStop:
    def test_returns_none_when_absent(self, sandbox):
        assert ctl.read_stop() is None

    def test_returns_dict_when_present(self, sandbox):
        ctl.write_stop("check read")
        result = ctl.read_stop()
        assert isinstance(result, dict)
        assert result["reason"] == "check read"

    def test_malformed_file_returns_fallback(self, sandbox):
        ctl.STOP_FILE.write_text("not json", encoding="utf-8")
        result = ctl.read_stop()
        assert result is not None
        assert "unreadable" in result["reason"]

    def test_empty_file_returns_fallback(self, sandbox):
        ctl.STOP_FILE.write_text("", encoding="utf-8")
        result = ctl.read_stop()
        assert result is not None


# ---------------------------------------------------------------------------
# agent_ctl.is_stopped
# ---------------------------------------------------------------------------


class TestIsStopped:
    def test_false_when_no_stop_file(self, sandbox):
        assert ctl.is_stopped() is False

    def test_true_when_stop_file_exists(self, sandbox):
        ctl.write_stop()
        assert ctl.is_stopped() is True

    def test_true_even_if_stop_file_empty(self, sandbox):
        ctl.STOP_FILE.write_text("", encoding="utf-8")
        assert ctl.is_stopped() is True


# ---------------------------------------------------------------------------
# agent_ctl.clear_stop
# ---------------------------------------------------------------------------


class TestClearStop:
    def test_returns_false_when_nothing_to_clear(self, sandbox):
        assert ctl.clear_stop() is False

    def test_returns_true_and_removes_file(self, sandbox):
        ctl.write_stop()
        assert ctl.is_stopped()
        result = ctl.clear_stop()
        assert result is True
        assert not ctl.is_stopped()

    def test_idempotent_second_clear(self, sandbox):
        ctl.write_stop()
        ctl.clear_stop()
        assert ctl.clear_stop() is False


# ---------------------------------------------------------------------------
# agent_ctl.list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_empty_when_dir_missing(self, sandbox):
        # SESSIONS_DIR was not created
        assert ctl.list_sessions() == []

    def test_empty_when_dir_has_no_jsonl(self, sandbox):
        ctl.SESSIONS_DIR.mkdir()
        (ctl.SESSIONS_DIR / "not_a_session.txt").write_text("x")
        assert ctl.list_sessions() == []

    def test_returns_session_metadata(self, sandbox):
        ctl.SESSIONS_DIR.mkdir()
        (ctl.SESSIONS_DIR / "session-abc.jsonl").write_text('{"event": "test"}')
        sessions = ctl.list_sessions()
        assert len(sessions) == 1
        s = sessions[0]
        assert s["session_id"] == "session-abc"
        assert "mtime" in s
        assert "size_bytes" in s
        assert s["size_bytes"] > 0

    def test_sorted_newest_first(self, sandbox):
        ctl.SESSIONS_DIR.mkdir()
        older = ctl.SESSIONS_DIR / "older.jsonl"
        older.write_text("x")
        time.sleep(0.05)
        newer = ctl.SESSIONS_DIR / "newer.jsonl"
        newer.write_text("xx")

        sessions = ctl.list_sessions()
        assert sessions[0]["session_id"] == "newer"
        assert sessions[1]["session_id"] == "older"

    def test_multiple_sessions_all_returned(self, sandbox):
        ctl.SESSIONS_DIR.mkdir()
        for i in range(5):
            (ctl.SESSIONS_DIR / f"session-{i:03d}.jsonl").write_text("x")
        assert len(ctl.list_sessions()) == 5


# ---------------------------------------------------------------------------
# agent_ctl.get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_not_stopped_no_sessions(self, sandbox):
        status = ctl.get_status()
        assert status["stopped"] is False
        assert status["stop_info"] is None
        assert status["session_count"] == 0
        assert status["sessions"] == []

    def test_stopped_reflected(self, sandbox):
        ctl.write_stop("test")
        status = ctl.get_status()
        assert status["stopped"] is True
        assert status["stop_info"]["reason"] == "test"

    def test_sessions_reflected(self, sandbox):
        ctl.SESSIONS_DIR.mkdir()
        (ctl.SESSIONS_DIR / "s1.jsonl").write_text("x")
        status = ctl.get_status()
        assert status["session_count"] == 1


# ---------------------------------------------------------------------------
# stop_cli()
# ---------------------------------------------------------------------------


class TestStopCli:
    def test_writes_stop_file(self, sandbox):
        rc = stop_cli([])
        assert rc == 0
        assert ctl.is_stopped()

    def test_exit_0_on_success(self, sandbox):
        assert stop_cli([]) == 0

    def test_custom_reason_stored(self, sandbox):
        stop_cli(["--reason", "maintenance window"])
        doc = ctl.read_stop()
        assert doc["reason"] == "maintenance window"

    def test_already_stopped_returns_1_without_force(self, sandbox):
        ctl.write_stop()
        rc = stop_cli([])
        assert rc == 1

    def test_already_stopped_with_force_returns_0(self, sandbox):
        ctl.write_stop("first")
        rc = stop_cli(["--force", "--reason", "second"])
        assert rc == 0
        doc = ctl.read_stop()
        assert doc["reason"] == "second"

    def test_force_on_fresh_state_also_works(self, sandbox):
        rc = stop_cli(["--force"])
        assert rc == 0
        assert ctl.is_stopped()

    def test_prints_stop_file_path(self, sandbox, capsys):
        stop_cli([])
        out = capsys.readouterr().out
        assert "STOP" in out

    def test_prints_reason(self, sandbox, capsys):
        stop_cli(["--reason", "ci-threshold-exceeded"])
        out = capsys.readouterr().out
        assert "ci-threshold-exceeded" in out


# ---------------------------------------------------------------------------
# status_cli()
# ---------------------------------------------------------------------------


class TestStatusCli:
    def test_exit_0_always(self, sandbox):
        assert status_cli([]) == 0

    def test_exit_0_when_stopped(self, sandbox):
        ctl.write_stop()
        assert status_cli([]) == 0

    def test_running_state_in_output(self, sandbox, capsys):
        status_cli([])
        out = capsys.readouterr().out
        assert "RUNNING" in out

    def test_stopped_state_in_output(self, sandbox, capsys):
        ctl.write_stop("maintenance")
        status_cli([])
        out = capsys.readouterr().out
        assert "STOPPED" in out
        assert "maintenance" in out

    def test_no_sessions_message(self, sandbox, capsys):
        status_cli([])
        out = capsys.readouterr().out
        assert "none" in out.lower() or "no session" in out.lower() or "0" in out

    def test_sessions_shown_in_output(self, sandbox, capsys):
        ctl.SESSIONS_DIR.mkdir()
        (ctl.SESSIONS_DIR / "session-xyz.jsonl").write_text("x" * 1024)
        status_cli([])
        out = capsys.readouterr().out
        assert "session-xyz" in out

    def test_json_output_flag(self, sandbox, capsys):
        status_cli(["--json"])
        out = capsys.readouterr().out
        doc = json.loads(out)
        assert "stopped" in doc
        assert "sessions" in doc
        assert "session_count" in doc

    def test_json_stopped_state(self, sandbox, capsys):
        ctl.write_stop("json-test")
        status_cli(["--json"])
        out = capsys.readouterr().out
        doc = json.loads(out)
        assert doc["stopped"] is True
        assert doc["stop_info"]["reason"] == "json-test"

    def test_json_running_state(self, sandbox, capsys):
        status_cli(["--json"])
        out = capsys.readouterr().out
        doc = json.loads(out)
        assert doc["stopped"] is False
        assert doc["stop_info"] is None

    def test_json_sessions_listed(self, sandbox, capsys):
        ctl.SESSIONS_DIR.mkdir()
        (ctl.SESSIONS_DIR / "ses-001.jsonl").write_text("x")
        (ctl.SESSIONS_DIR / "ses-002.jsonl").write_text("xx")
        status_cli(["--json"])
        out = capsys.readouterr().out
        doc = json.loads(out)
        assert doc["session_count"] == 2
        ids = [s["session_id"] for s in doc["sessions"]]
        assert "ses-001" in ids
        assert "ses-002" in ids

    def test_header_present(self, sandbox, capsys):
        status_cli([])
        out = capsys.readouterr().out
        assert "AutoAgent Status" in out
