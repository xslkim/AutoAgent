"""Unit tests for cases/store.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autovisiontest.cases.schema import AppConfig, CaseMetadata, Step, TestCase
from autovisiontest.cases.store import RecordingStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(
    goal: str = "test goal",
    app_path: str = "notepad.exe",
    fingerprint: str = "abc123def4567890",
) -> TestCase:
    return TestCase(
        goal=goal,
        app_config=AppConfig(app_path=app_path),
        metadata=CaseMetadata(fingerprint=fingerprint, step_count=0),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecordingStore:
    """Tests for RecordingStore."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save a recording and load it back."""
        store = RecordingStore(data_dir=tmp_path)
        case = _make_case()

        path = store.save(case)
        assert path.exists()

        loaded = store.load("abc123def4567890")
        assert loaded is not None
        assert loaded.goal == "test goal"
        assert loaded.app_config.app_path == "notepad.exe"

    def test_load_not_found(self, tmp_path: Path) -> None:
        """Loading a non-existent fingerprint returns None."""
        store = RecordingStore(data_dir=tmp_path)
        result = store.load("nonexistent")
        assert result is None

    def test_list_all(self, tmp_path: Path) -> None:
        """list_all returns all saved recordings."""
        store = RecordingStore(data_dir=tmp_path)
        store.save(_make_case(fingerprint="fp1"))
        store.save(_make_case(goal="goal 2", fingerprint="fp2"))

        cases = store.list_all()
        assert len(cases) == 2

    def test_list_all_empty(self, tmp_path: Path) -> None:
        """list_all on empty store returns empty list."""
        store = RecordingStore(data_dir=tmp_path)
        cases = store.list_all()
        assert cases == []

    def test_delete(self, tmp_path: Path) -> None:
        """Delete removes a recording."""
        store = RecordingStore(data_dir=tmp_path)
        store.save(_make_case(fingerprint="fp1"))

        assert store.delete("fp1") is True
        assert store.load("fp1") is None

    def test_delete_not_found(self, tmp_path: Path) -> None:
        """Delete of non-existent returns False."""
        store = RecordingStore(data_dir=tmp_path)
        assert store.delete("nonexistent") is False

    def test_find_for_goal_matches(self, tmp_path: Path) -> None:
        """find_for_goal finds a recording by app_path and goal."""
        store = RecordingStore(data_dir=tmp_path)
        case = _make_case(goal="open notepad", app_path="notepad.exe", fingerprint="fp1")
        store.save(case)

        # Mock compute_fingerprint to return the same fingerprint
        from unittest.mock import patch
        with patch("autovisiontest.cases.store.compute_fingerprint", return_value="fp1"):
            found = store.find_for_goal("notepad.exe", "open notepad")
        assert found is not None
        assert found.goal == "open notepad"

    def test_find_for_goal_no_match(self, tmp_path: Path) -> None:
        """find_for_goal returns None when no match."""
        store = RecordingStore(data_dir=tmp_path)
        from unittest.mock import patch
        with patch("autovisiontest.cases.store.compute_fingerprint", return_value="no_match"):
            found = store.find_for_goal("notepad.exe", "open notepad")
        assert found is None

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Save should create the recordings directory if it doesn't exist."""
        data_dir = tmp_path / "nested" / "data"
        store = RecordingStore(data_dir=data_dir)
        path = store.save(_make_case(fingerprint="fp1"))
        assert path.exists()
