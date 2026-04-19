"""Unit tests for logging_setup module."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
import structlog

from autovisiontest.logging_setup import setup_logging


class TestSetupLoggingConsole:
    """Verify console (non-JSON) logging output format."""

    def test_console_output_contains_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging(level="DEBUG", json_output=False)

        log = structlog.get_logger("test_module")
        log.info("hello_test", extra_key="extra_val")

        captured = capsys.readouterr()
        # stderr should contain the log message
        assert "hello_test" in captured.err
        assert "info" in captured.err.lower()

    def test_log_level_respected(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging(level="WARNING", json_output=False)

        log = structlog.get_logger("test_module")
        log.debug("should_not_appear")
        log.warning("should_appear")

        captured = capsys.readouterr()
        assert "should_not_appear" not in captured.err
        assert "should_appear" in captured.err


class TestSetupLoggingJson:
    """Verify JSON output mode produces valid, parseable JSON."""

    def test_json_output_is_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging(level="DEBUG", json_output=True)

        log = structlog.get_logger("test_json")
        log.info("json_test_event", key1="value1")

        captured = capsys.readouterr()
        # Find a line that looks like JSON
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert "event" in parsed
                assert parsed["event"] == "json_test_event"
                assert parsed.get("key1") == "value1"
                return

        pytest.fail("No JSON log line found in stderr")

    def test_json_output_contains_timestamp(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging(level="DEBUG", json_output=True)

        log = structlog.get_logger("test_json_ts")
        log.info("ts_test")

        captured = capsys.readouterr()
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert "timestamp" in parsed
                return

        pytest.fail("No JSON log line found in stderr")


class TestContextBinding:
    """Verify contextvars binding propagates to log entries."""

    def test_session_id_binding(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging(level="DEBUG", json_output=True)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(session_id="test-session-42")

        log = structlog.get_logger("test_ctx")
        log.info("context_test_event")

        captured = capsys.readouterr()
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert parsed.get("session_id") == "test-session-42"
                return

        pytest.fail("No JSON log line found in stderr")

    def test_step_idx_binding(self, capsys: pytest.CaptureFixture[str]) -> None:
        setup_logging(level="DEBUG", json_output=True)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(step_idx=7)

        log = structlog.get_logger("test_step")
        log.info("step_test_event")

        captured = capsys.readouterr()
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert parsed.get("step_idx") == 7
                return

        pytest.fail("No JSON log line found in stderr")


class TestLogFileRotation:
    """Verify file logging with rotation."""

    def test_log_file_created(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        setup_logging(level="DEBUG", json_output=False, log_file=log_file)

        log = structlog.get_logger("test_file")
        log.info("file_test_event")

        # Force flush
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "file_test_event" in content
