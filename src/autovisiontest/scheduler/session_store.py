"""Session store — persistent storage for session state.

Each session is stored as a ``status.json`` file under
``{data_dir}/sessions/{session_id}/``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """Status of a test session."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class SessionRecord(BaseModel):
    """Persistent record of a session's state.

    Stored as ``status.json`` in the session directory.
    """

    session_id: str
    goal: str = ""
    app_path: str = ""
    app_args: list[str] = Field(default_factory=list)
    mode: str = "exploratory"  # "exploratory" | "regression"
    status: SessionStatus = SessionStatus.PENDING
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    termination_reason: str | None = None
    report_path: str | None = None
    fingerprint: str | None = None  # for regression sessions


class SessionStore:
    """Persistent store for session state.

    Args:
        data_dir: Root data directory. Sessions are stored under
            ``{data_dir}/sessions/``.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._sessions_dir = data_dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        """Return the directory for a given session."""
        return self._sessions_dir / session_id

    def _status_path(self, session_id: str) -> Path:
        """Return the path to the status.json file."""
        return self._session_dir(session_id) / "status.json"

    def save(self, record: SessionRecord) -> Path:
        """Save or update a session record.

        Args:
            record: The SessionRecord to save.

        Returns:
            Path to the saved JSON file.
        """
        record.updated_at = datetime.now(timezone.utc).isoformat()
        path = self._status_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        logger.debug(
            "session_saved",
            extra={"session_id": record.session_id, "status": record.status.value},
        )
        return path

    def load(self, session_id: str) -> SessionRecord | None:
        """Load a session record by session ID.

        Args:
            session_id: The session identifier.

        Returns:
            SessionRecord if found, None otherwise.
        """
        path = self._status_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionRecord.model_validate(data)
        except Exception:
            logger.exception(
                "session_load_failed", extra={"session_id": session_id}
            )
            return None

    def list_all(self) -> list[SessionRecord]:
        """List all session records.

        Returns:
            List of all SessionRecord objects.
        """
        records: list[SessionRecord] = []
        for status_file in sorted(self._sessions_dir.glob("*/status.json")):
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                records.append(SessionRecord.model_validate(data))
            except Exception:
                logger.warning(
                    "session_skip_invalid", extra={"path": str(status_file)}
                )
        return records

    def delete(self, session_id: str) -> bool:
        """Delete a session record and its directory.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session was deleted, False if not found.
        """
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return False
        import shutil

        shutil.rmtree(session_dir, ignore_errors=True)
        logger.info("session_deleted", extra={"session_id": session_id})
        return True
