"""Tests for EvidenceCleaner — retention-based cleanup."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from autovisiontest.report.cleaner import CleanupStats, EvidenceCleaner


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory."""
    return tmp_path


def _create_session(
    evidence_dir: Path,
    session_id: str,
    status: str = "COMPLETED",
    age_days: float = 0,
) -> Path:
    """Create a fake session directory with status.json."""
    session_dir = evidence_dir / "evidence" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write status.json
    status_data = {
        "session_id": session_id,
        "status": status,
    }
    (session_dir / "status.json").write_text(
        json.dumps(status_data), encoding="utf-8"
    )

    # Write a dummy file
    (session_dir / "screenshot.png").write_bytes(b"fake_png_data")

    # Adjust mtime if needed
    if age_days > 0:
        mtime = time.time() - (age_days * 86400)
        import os
        os.utime(session_dir, (mtime, mtime))

    return session_dir


class TestEvidenceCleaner:
    """Tests for EvidenceCleaner."""

    def test_cleanup_by_count(self, tmp_data_dir: Path) -> None:
        """Cleanup removes oldest sessions beyond keep_recent_sessions."""
        cleaner = EvidenceCleaner(
            data_dir=tmp_data_dir,
            keep_recent_sessions=3,
            keep_days=-1,  # Expire everything by time, rely on count only
            keep_failed_days=-1,
        )

        # Create 5 sessions with distinct ages to ensure deterministic ordering.
        # session-4 is newest (age=0), session-0 is oldest (age=4 days).
        for i in range(5):
            _create_session(tmp_data_dir, f"session-{i}", age_days=4 - i)

        stats = cleaner.cleanup()

        assert stats.scanned == 5
        assert stats.deleted == 2  # 5 - 3 keep_recent
        # Verify newest 3 remain (session-2, session-3, session-4)
        assert (tmp_data_dir / "evidence" / "session-4").exists()
        assert (tmp_data_dir / "evidence" / "session-3").exists()
        assert (tmp_data_dir / "evidence" / "session-2").exists()
        # Oldest 2 deleted
        assert not (tmp_data_dir / "evidence" / "session-0").exists()
        assert not (tmp_data_dir / "evidence" / "session-1").exists()

    def test_cleanup_preserves_recent(self, tmp_data_dir: Path) -> None:
        """Recent sessions are preserved by time window even if beyond count."""
        cleaner = EvidenceCleaner(
            data_dir=tmp_data_dir,
            keep_recent_sessions=0,  # No count-based retention
            keep_days=7,
            keep_failed_days=30,
        )

        # Create old session (10 days old) — beyond 7-day window
        _create_session(tmp_data_dir, "old-session", age_days=10)

        # Create recent session (1 day old) — within 7-day window
        _create_session(tmp_data_dir, "recent-session", age_days=1)

        stats = cleaner.cleanup()

        assert stats.scanned == 2
        assert stats.deleted == 1
        assert (tmp_data_dir / "evidence" / "recent-session").exists()
        assert not (tmp_data_dir / "evidence" / "old-session").exists()

    def test_cleanup_preserves_failed_longer(self, tmp_data_dir: Path) -> None:
        """Failed sessions are kept for keep_failed_days."""
        cleaner = EvidenceCleaner(
            data_dir=tmp_data_dir,
            keep_recent_sessions=0,  # No count-based retention
            keep_days=7,
            keep_failed_days=30,
        )

        # Create failed session (15 days old) — beyond 7-day but within 30-day
        _create_session(
            tmp_data_dir, "failed-old", status="FAILED", age_days=15
        )

        # Create normal session (15 days old) — beyond 7-day window
        _create_session(tmp_data_dir, "normal-old", age_days=15)

        stats = cleaner.cleanup()

        assert stats.scanned == 2
        assert stats.deleted == 1
        # Failed preserved (within 30-day window)
        assert (tmp_data_dir / "evidence" / "failed-old").exists()
        # Normal deleted (outside 7-day window)
        assert not (tmp_data_dir / "evidence" / "normal-old").exists()

    def test_recordings_never_deleted(self, tmp_data_dir: Path) -> None:
        """recordings/ directory is never touched by cleanup."""
        # Create recordings
        recordings_dir = tmp_data_dir / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        (recordings_dir / "abc123.json").write_text("{}", encoding="utf-8")

        # Create an old evidence session that would be cleaned
        _create_session(tmp_data_dir, "old-session", age_days=100)

        cleaner = EvidenceCleaner(
            data_dir=tmp_data_dir,
            keep_recent_sessions=0,  # Clean everything
            keep_days=0,
            keep_failed_days=0,
        )
        cleaner.cleanup()

        # Recordings untouched
        assert (recordings_dir / "abc123.json").exists()

    def test_cleanup_empty_dir(self, tmp_data_dir: Path) -> None:
        """Cleanup handles empty evidence directory."""
        cleaner = EvidenceCleaner(data_dir=tmp_data_dir)
        stats = cleaner.cleanup()
        assert stats.scanned == 0
        assert stats.deleted == 0

    def test_cleanup_no_evidence_dir(self, tmp_data_dir: Path) -> None:
        """Cleanup handles missing evidence directory."""
        cleaner = EvidenceCleaner(data_dir=tmp_data_dir / "nonexistent")
        stats = cleaner.cleanup()
        assert stats.scanned == 0

    def test_cleanup_stats_freed_bytes(self, tmp_data_dir: Path) -> None:
        """Cleanup stats include freed bytes count."""
        cleaner = EvidenceCleaner(
            data_dir=tmp_data_dir,
            keep_recent_sessions=0,
            keep_days=-1,  # Expire everything
            keep_failed_days=-1,
        )

        _create_session(tmp_data_dir, "to-delete")
        stats = cleaner.cleanup()

        assert stats.deleted == 1
        assert stats.freed_bytes > 0

    def test_start_stop_background(self, tmp_data_dir: Path) -> None:
        """Background thread starts and stops cleanly."""
        cleaner = EvidenceCleaner(data_dir=tmp_data_dir)

        thread = cleaner.start_background(interval_s=1)
        assert thread.is_alive()

        cleaner.stop_background()
        thread.join(timeout=3)
        assert not thread.is_alive()
