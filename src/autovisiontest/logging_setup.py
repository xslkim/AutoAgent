"""Structured logging setup for AutoVisionTest.

Uses structlog with configurable output format (console or JSON),
context variable binding (session_id, step_idx), and optional
file rotation.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from logging.handlers import RotatingFileHandler


def _add_default_fields(
    logger: logging.Logger, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Add default fields (module) to every log entry."""
    record = event_dict.get("_record")
    if record is not None:
        event_dict.setdefault("module", record.module)
    else:
        event_dict.setdefault("module", "unknown")
    return event_dict


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[Path] = None,
) -> None:
    """Initialize structlog with the given configuration.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output single-line JSON per log entry (for CI/production).
        log_file: Optional path to a log file with rotation (10MB, 5 backups).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib logging as the sink
    handlers: list[logging.Handler] = []

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    handlers.append(console_handler)

    # File handler with rotation
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    # Configure stdlib root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Remove existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()
    for handler in handlers:
        root_logger.addHandler(handler)

    # Configure structlog processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_default_fields,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # JSON output: single line per entry
        renderer = structlog.processors.JSONRenderer()
    else:
        # Console output: human-readable
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Attach structlog formatter to all handlers
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )
    for handler in handlers:
        handler.setFormatter(formatter)
