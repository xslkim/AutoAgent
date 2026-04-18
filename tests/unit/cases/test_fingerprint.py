"""Unit tests for cases/fingerprint.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autovisiontest.cases.fingerprint import (
    compute_app_version,
    compute_fingerprint,
    normalize_goal,
)


class TestNormalizeGoal:
    """Tests for normalize_goal."""

    def test_normalize_goal_stable(self) -> None:
        """Same input should produce same output."""
        result1 = normalize_goal("Open the notepad and type hello")
        result2 = normalize_goal("Open the notepad and type hello")
        assert result1 == result2

    def test_normalize_goal_lowercase(self) -> None:
        """Output should be lowercase."""
        result = normalize_goal("Open NOTEPAD")
        assert result == result.lower()

    def test_normalize_goal_removes_stop_words(self) -> None:
        """English stop words should be removed."""
        result = normalize_goal("Open the notepad and type a hello")
        # "the", "and", "a" should be removed
        assert "the" not in result.split()
        assert "and" not in result.split()
        assert "a" not in result.split()
        assert "open" in result
        assert "notepad" in result

    def test_normalize_goal_removes_punctuation(self) -> None:
        """Punctuation should be removed."""
        result = normalize_goal("Open notepad, type hello!")
        assert "," not in result
        assert "!" not in result

    def test_normalize_goal_chinese(self) -> None:
        """Chinese characters should be split per character."""
        result = normalize_goal("打开记事本")
        # Each Chinese character should be a token
        assert "打" in result.split()
        assert "开" in result.split()

    def test_normalize_goal_mixed(self) -> None:
        """Mixed Chinese and English."""
        result = normalize_goal("打开 notepad 输入 hello")
        tokens = result.split()
        assert "notepad" in tokens
        assert "hello" in tokens

    def test_different_input_different_output(self) -> None:
        """Different goals should produce different normalized forms."""
        result1 = normalize_goal("open notepad")
        result2 = normalize_goal("close notepad")
        assert result1 != result2


class TestComputeAppVersion:
    """Tests for compute_app_version."""

    @patch("autovisiontest.cases.fingerprint.subprocess.run")
    def test_pe_version_available(self, mock_run: MagicMock) -> None:
        """Should use PE FileVersion if available."""
        mock_run.return_value = MagicMock(stdout="10.0.19041.1\n")
        result = compute_app_version("C:\\Windows\\notepad.exe")
        assert result == "10.0.19041.1"

    @patch("autovisiontest.cases.fingerprint.subprocess.run")
    def test_pe_version_zero_fallback(self, mock_run: MagicMock) -> None:
        """Should fallback to hash if PE version is 0.0.0.0."""
        mock_run.return_value = MagicMock(stdout="0.0.0.0\n")
        # This will try to hash the actual file, which may not exist
        # So we also mock the file open
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = compute_app_version("nonexistent.exe")
            assert result == "unknown"

    @patch("autovisiontest.cases.fingerprint.subprocess.run")
    def test_pe_version_fails_gracefully(self, mock_run: MagicMock) -> None:
        """Should fallback if PE version extraction fails."""
        mock_run.side_effect = RuntimeError("powershell not found")
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = compute_app_version("nonexistent.exe")
            assert result == "unknown"


class TestComputeFingerprint:
    """Tests for compute_fingerprint."""

    @patch("autovisiontest.cases.fingerprint.compute_app_version", return_value="1.0.0")
    def test_fingerprint_stable_across_calls(self, mock_version: MagicMock) -> None:
        """Same inputs should produce same fingerprint."""
        fp1 = compute_fingerprint("notepad.exe", "open notepad")
        fp2 = compute_fingerprint("notepad.exe", "open notepad")
        assert fp1 == fp2

    @patch("autovisiontest.cases.fingerprint.compute_app_version", return_value="1.0.0")
    def test_fingerprint_changes_on_different_goal(self, mock_version: MagicMock) -> None:
        """Different goals should produce different fingerprints."""
        fp1 = compute_fingerprint("notepad.exe", "open notepad")
        fp2 = compute_fingerprint("notepad.exe", "close notepad")
        assert fp1 != fp2

    @patch("autovisiontest.cases.fingerprint.compute_app_version", return_value="1.0.0")
    def test_fingerprint_is_16_hex_chars(self, mock_version: MagicMock) -> None:
        """Fingerprint should be 16 hex characters."""
        fp = compute_fingerprint("notepad.exe", "open notepad")
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    @patch("autovisiontest.cases.fingerprint.compute_app_version")
    def test_fingerprint_changes_on_different_version(self, mock_version: MagicMock) -> None:
        """Different app versions should produce different fingerprints."""
        mock_version.side_effect = ["1.0.0", "2.0.0"]
        fp1 = compute_fingerprint("notepad.exe", "open notepad")
        fp2 = compute_fingerprint("notepad.exe", "open notepad")
        assert fp1 != fp2
