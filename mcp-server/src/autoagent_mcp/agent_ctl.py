"""Agent lifecycle control — read / write the STOP sentinel and session metadata.

All path constants are module-level so tests can monkeypatch them easily.

Sentinel protocol (docs/07 §8.1):
- ``~/.autoagent/STOP`` exists → every background agent poll detects it
  and halts at the end of its current iteration (≤ 10 s).
- The file contains a JSON record with ``stopped_at``, ``reason``, and
  ``pid`` fields.
- ``~/.autoagent/last_stop.log`` receives an appended plain-text line for
  each stop event (human-readable audit trail).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path constants — monkeypatched in tests
# ---------------------------------------------------------------------------

AUTOAGENT_DIR: Path = Path.home() / ".autoagent"
STOP_FILE: Path = AUTOAGENT_DIR / "STOP"
LAST_STOP_LOG: Path = AUTOAGENT_DIR / "last_stop.log"
SESSIONS_DIR: Path = AUTOAGENT_DIR / "sessions"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# STOP file API
# ---------------------------------------------------------------------------


def write_stop(reason: str = "manual stop via autoagent-stop") -> dict[str, Any]:
    """Write the STOP sentinel file and append a line to ``last_stop.log``.

    Args:
        reason: Human-readable reason stored in the file and the log.

    Returns:
        The JSON record dict that was written to the STOP file.
    """
    _ensure_dir(AUTOAGENT_DIR)

    record: dict[str, Any] = {
        "stopped_at": datetime.now(tz=timezone.utc).isoformat(),
        "reason": reason,
        "pid": os.getpid(),
    }
    STOP_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")

    # Append to the plain-text audit log
    log_line = (
        f"[{record['stopped_at']}] pid={record['pid']}  {reason}\n"
    )
    with open(LAST_STOP_LOG, "a", encoding="utf-8") as fh:
        fh.write(log_line)

    return record


def read_stop() -> dict[str, Any] | None:
    """Return the parsed STOP file record, or ``None`` if the file is absent.

    Returns a fallback dict (with ``reason="(unreadable)"```) if the file
    exists but cannot be parsed as JSON.
    """
    if not STOP_FILE.is_file():
        return None
    try:
        return json.loads(STOP_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "stopped_at": None,
            "reason": "(unreadable STOP file)",
            "pid": None,
        }


def is_stopped() -> bool:
    """Return ``True`` if the STOP sentinel file exists."""
    return STOP_FILE.is_file()


def clear_stop() -> bool:
    """Remove the STOP sentinel file.

    Returns:
        ``True`` if the file existed and was removed, ``False`` if it was
        already absent.
    """
    if STOP_FILE.is_file():
        STOP_FILE.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------


def list_sessions() -> list[dict[str, Any]]:
    """Scan ``SESSIONS_DIR`` and return metadata for every ``*.jsonl`` file.

    Results are sorted newest-first by modification time.

    Returns:
        A list of dicts, each with keys ``session_id``, ``path``,
        ``mtime`` (ISO-8601 UTC), and ``size_bytes``.  Empty list when the
        directory does not exist or contains no session files.
    """
    if not SESSIONS_DIR.is_dir():
        return []

    sessions: list[dict[str, Any]] = []
    for path in sorted(
        SESSIONS_DIR.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        stat = path.stat()
        sessions.append(
            {
                "session_id": path.stem,
                "path": str(path),
                "mtime": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "size_bytes": stat.st_size,
            }
        )
    return sessions


# ---------------------------------------------------------------------------
# Composite status
# ---------------------------------------------------------------------------


def get_status() -> dict[str, Any]:
    """Return a single structured status dict.

    Schema::

        {
          "stopped": bool,
          "stop_info": {stopped_at, reason, pid} | null,
          "session_count": int,
          "sessions": [
            {"session_id": str, "path": str, "mtime": str, "size_bytes": int},
            ...
          ]
        }
    """
    stop_info = read_stop()
    sessions = list_sessions()
    return {
        "stopped": stop_info is not None,
        "stop_info": stop_info,
        "session_count": len(sessions),
        "sessions": sessions,
    }
