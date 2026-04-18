"""Additional edge-case tests for T A.3 logging setup (Test Agent supplement)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import structlog

from autovisiontest.logging_setup import setup_logging


class TestSetupLoggingEdgeCases:
    """Edge cases for logging_setup module."""

    def test_setup_logging_idempotent(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Calling setup_logging twice should not produce duplicate log entries."""
        setup_logging(level="DEBUG", json_output=True)
        setup_logging(level="DEBUG", json_output=True)

        log = structlog.get_logger("test_idempotent")
        log.info("idempotent_test")

        captured = capsys.readouterr()
        json_lines = [
            line.strip()
            for line in captured.err.strip().splitlines()
            if line.strip().startswith("{")
        ]
        # Should produce exactly one log entry, not duplicates
        assert len(json_lines) == 1

    def test_case_insensitive_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Log level should be case-insensitive (e.g., 'debug' == 'DEBUG')."""
        setup_logging(level="debug", json_output=True)

        log = structlog.get_logger("test_case")
        log.debug("case_test")

        captured = capsys.readouterr()
        assert "case_test" in captured.err

    def test_invalid_level_defaults_to_info(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid level string should default to INFO without crashing."""
        setup_logging(level="INVALID_LEVEL", json_output=True)

        log = structlog.get_logger("test_invalid")
        log.info("invalid_level_test")

        captured = capsys.readouterr()
        assert "invalid_level_test" in captured.err

    def test_json_output_includes_level_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output must include a 'level' field."""
        setup_logging(level="DEBUG", json_output=True)

        log = structlog.get_logger("test_level_field")
        log.info("level_field_test")

        captured = capsys.readouterr()
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert "level" in parsed
                return

        pytest.fail("No JSON log line found")

    def test_json_output_includes_module_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        """JSON output must include a 'module' field (per task requirement)."""
        setup_logging(level="DEBUG", json_output=True)

        log = structlog.get_logger("test_module_field")
        log.info("module_field_test")

        captured = capsys.readouterr()
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert "module" in parsed
                return

        pytest.fail("No JSON log line found")

    def test_file_rotation_params(self, tmp_path: Path) -> None:
        """Verify RotatingFileHandler is configured with correct rotation params."""
        log_file = tmp_path / "rotation_test.log"
        setup_logging(level="DEBUG", json_output=False, log_file=log_file)

        # Find the file handler
        root_logger = logging.getLogger()
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        fh = file_handlers[0]
        assert fh.maxBytes == 10 * 1024 * 1024  # 10 MB
        assert fh.backupCount == 5

    def test_log_file_parent_dir_created(self, tmp_path: Path) -> None:
        """If log_file's parent dir doesn't exist, it should be created."""
        log_file = tmp_path / "subdir" / "nested" / "test.log"
        setup_logging(level="DEBUG", json_output=False, log_file=log_file)

        log = structlog.get_logger("test_nested")
        log.info("nested_dir_test")

        for handler in logging.getLogger().handlers:
            handler.flush()

        assert log_file.exists()

    def test_clear_contextvars_does_not_leak(self, capsys: pytest.CaptureFixture[str]) -> None:
        """After clear_contextvars, session_id should not appear in subsequent logs."""
        setup_logging(level="DEBUG", json_output=True)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(session_id="should-be-cleared")
        structlog.contextvars.clear_contextvars()

        log = structlog.get_logger("test_clear")
        log.info("after_clear_test")

        captured = capsys.readouterr()
        for line in captured.err.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                assert parsed.get("session_id") is None
                return

        pytest.fail("No JSON log line found")
