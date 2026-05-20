"""Structured JSON logging with rotating file handler.

Call :func:`setup_logging` once at process startup (the CLI does this
automatically).  All modules in the package should use the standard
``logging.getLogger(__name__)`` idiom; this module wires up the
handlers and formatter globally.

Log-line format (one JSON object per line, no trailing whitespace)::

    {"time": "2026-05-20T12:34:56.789Z", "level": "INFO",
     "logger": "autoagent_mcp.tools.click", "msg": "clicked btn_ok"}

Extra keyword arguments passed via ``extra={"key": val}`` appear under
an ``"extra"`` key::

    {"time": "...", "level": "DEBUG", "logger": "...", "msg": "...",
     "extra": {"method": "click", "id": "btn_ok"}}

Usage::

    from autoagent_mcp.logging import get_logger
    log = get_logger(__name__)
    log.info("clicked widget", extra={"id": widget_id})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_LOG_DIR: Path = Path.home() / ".autoagent" / "logs"
DEFAULT_LOG_FILE: Path = DEFAULT_LOG_DIR / "mcp-server.log"
DEFAULT_LEVEL: str = "INFO"
DEFAULT_MAX_BYTES: int = 10 * 1024 * 1024   # 10 MB
DEFAULT_BACKUP_COUNT: int = 5

# Idempotency sentinel — set to True after the first successful setup_logging()
_configured: bool = False

# Fields that are part of the standard LogRecord and should NOT appear in "extra"
_BUILTIN_RECORD_ATTRS: frozenset[str] = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
})


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Format each :class:`logging.LogRecord` as a single-line JSON object.

    Fields always present:

    * ``time``    — ISO 8601 UTC timestamp with milliseconds, e.g.
                    ``"2026-05-20T12:34:56.789Z"``
    * ``level``   — log level name (``"DEBUG"``, ``"INFO"``, …)
    * ``logger``  — logger name (usually the module's ``__name__``)
    * ``msg``     — rendered message string

    Optional fields:

    * ``exc_info`` — formatted exception traceback (if an exception was
                     logged)
    * ``extra``   — dict of caller-supplied extra fields; omitted when
                    empty
    """

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        # Build timestamp manually so we control the exact format.
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        time_str = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z"

        doc: dict[str, Any] = {
            "time": time_str,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            doc["exc_info"] = self.formatException(record.exc_info)

        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _BUILTIN_RECORD_ATTRS
        }
        if extra:
            doc["extra"] = extra

        return json.dumps(doc, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def setup_logging(
    log_file: str | os.PathLike | None = None,
    level: str = DEFAULT_LEVEL,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    *,
    stderr: bool = True,
    _force: bool = False,
) -> None:
    """Configure the root logger for structured JSON output.

    Safe to call multiple times — subsequent calls are no-ops unless
    *_force* is ``True`` (intended for tests that need a clean slate).

    Args:
        log_file:     Path for the rotating log file.  Defaults to
                      ``~/.autoagent/logs/mcp-server.log``.  Pass
                      ``False`` or an empty string to disable the file
                      handler (useful for unit tests that only want
                      the in-memory / stderr handler).
        level:        Minimum log level name (``"DEBUG"``, ``"INFO"``,
                      ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``).
                      Case-insensitive.
        max_bytes:    Rotate after this many bytes (default 10 MB).
        backup_count: Number of rotated backup files to keep (default 5).
        stderr:       When ``True`` (default) also attach a handler that
                      writes to ``sys.stderr``.
        _force:       Bypass the idempotency guard and reconfigure even
                      if :func:`setup_logging` was called before.
                      **Use only in tests.**
    """
    global _configured
    if _configured and not _force:
        return
    _configured = True

    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    formatter = JsonFormatter()

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Remove any handlers installed by a previous _force=True call so tests
    # don't accumulate duplicates.
    root.handlers.clear()

    # --- Rotating file handler ---
    if log_file is not False and log_file != "":
        log_path = Path(log_file) if log_file else DEFAULT_LOG_FILE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,   # don't create the file until the first record
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)

    # --- stderr handler ---
    if stderr:
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (convenience wrapper around :func:`logging.getLogger`).

    Allows callers to avoid a separate ``import logging``::

        from autoagent_mcp.logging import get_logger
        log = get_logger(__name__)
    """
    return logging.getLogger(name)
