"""Evidence cleaner — background task for cleaning old evidence data.

Cleanup rules (per §11.4):
- Default: keep last 50 sessions OR last 7 days (whichever comes first)
- FAILED/ABORTED sessions: keep for 30 days regardless
- ``recordings/`` directory: **never** deleted
- Runs periodically in a background thread (default: every 1 hour)
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    """Statistics from a cleanup run."""

    scanned: int = 0
    deleted: int = 0
    kept_failed: int = 0
    kept_recent: int = 0
    freed_bytes: int = 0


class EvidenceCleaner:
    """Clean up old evidence directories based on retention policy.

    Args:
        data_dir: Root data directory containing ``evidence/`` and ``recordings/``.
        keep_recent_sessions: Maximum number of recent sessions to keep.
        keep_days: Maximum age in days for normal sessions.
        keep_failed_days: Maximum age in days for failed/aborted sessions.
    """

    def __init__(
        self,
        data_dir: Path,
        keep_recent_sessions: int = 50,
        keep_days: int = 7,
        keep_failed_days: int = 30,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._evidence_dir = data_dir / "evidence"
        self._recordings_dir = data_dir / "recordings"
        self._keep_recent = keep_recent_sessions
        self._keep_days = keep_days
        self._keep_failed_days = keep_failed_days
        self._stop_event = threading.Event()

    def cleanup(self) -> CleanupStats:
        """Run a single cleanup pass.

        Scans all session directories under ``evidence/`` and removes
        those that exceed retention limits.  The ``recordings/`` directory
        is **never** touched.

        Returns:
            CleanupStats with counts of scanned/deleted/kept items.
        """
        stats = CleanupStats()

        if not self._evidence_dir.exists():
            return stats

        # Collect all session directories with their metadata
        sessions: list[dict] = []
        for session_dir in sorted(self._evidence_dir.iterdir()):
            if not session_dir.is_dir():
                continue

            # Check if this looks like a failed session
            is_failed = self._is_failed_session(session_dir)
            mtime = session_dir.stat().st_mtime

            sessions.append({
                "path": session_dir,
                "mtime": mtime,
                "is_failed": is_failed,
            })

        stats.scanned = len(sessions)

        # Sort by modification time (newest first)
        sessions.sort(key=lambda s: s["mtime"], reverse=True)

        now = time.time()
        cutoff_normal = now - (self._keep_days * 86400)
        cutoff_failed = now - (self._keep_failed_days * 86400)

        # Sessions to keep
        to_delete: list[dict] = []
        keep_count = 0
        for session in sessions:
            # Within recent count → always keep
            if keep_count < self._keep_recent:
                keep_count += 1
                if session["is_failed"]:
                    stats.kept_failed += 1
                else:
                    stats.kept_recent += 1
                continue

            # Beyond recent count — check time-based retention
            if session["is_failed"] and session["mtime"] >= cutoff_failed:
                stats.kept_failed += 1
                continue

            if not session["is_failed"] and session["mtime"] >= cutoff_normal:
                stats.kept_recent += 1
                continue

            # Neither count nor time qualifies → delete
            to_delete.append(session)

        for session in to_delete:
            size = self._dir_size(session["path"])
            try:
                shutil.rmtree(session["path"], ignore_errors=True)
                stats.deleted += 1
                stats.freed_bytes += size
                logger.info(
                    "evidence_cleaned",
                    extra={
                        "path": str(session["path"]),
                        "size_bytes": size,
                    },
                )
            except Exception:
                logger.exception(
                    "evidence_clean_failed",
                    extra={"path": str(session["path"])},
                )

        logger.info(
            "evidence_cleanup_complete",
            extra={
                "scanned": stats.scanned,
                "deleted": stats.deleted,
                "freed_bytes": stats.freed_bytes,
            },
        )

        return stats

    def start_background(self, interval_s: int = 3600) -> threading.Thread:
        """Start the cleanup in a background thread.

        Args:
            interval_s: Interval between cleanup runs in seconds.

        Returns:
            The background thread (daemon).
        """
        self._stop_event.clear()

        def _run() -> None:
            while not self._stop_event.is_set():
                try:
                    self.cleanup()
                except Exception:
                    logger.exception("background_cleanup_error")
                self._stop_event.wait(timeout=interval_s)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        logger.info(
            "cleanup_thread_started", extra={"interval_s": interval_s}
        )
        return thread

    def stop_background(self) -> None:
        """Signal the background thread to stop."""
        self._stop_event.set()

    def _is_failed_session(self, session_dir: Path) -> bool:
        """Check if a session directory represents a failed/aborted session.

        Looks for a ``status.json`` file and checks the status field.
        """
        status_file = session_dir / "status.json"
        if not status_file.exists():
            # No status file — check for report.json with FAIL status
            report_file = session_dir / "report.json"
            if report_file.exists():
                try:
                    import json
                    data = json.loads(report_file.read_text(encoding="utf-8"))
                    result = data.get("result", {})
                    status = result.get("status", "")
                    return status in ("FAIL", "ABORT")
                except Exception:
                    pass
            # No status info — treat as normal
            return False

        try:
            import json
            data = json.loads(status_file.read_text(encoding="utf-8"))
            status = data.get("status", "")
            return status in ("FAILED", "ABORTED")
        except Exception:
            return False

    def _dir_size(self, path: Path) -> int:
        """Calculate total size of a directory in bytes."""
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except Exception:
            pass
        return total
