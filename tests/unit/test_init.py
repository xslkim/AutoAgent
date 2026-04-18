"""Tests for T A.1 project initialization."""

import subprocess
import sys


def test_import_autovisiontest():
    """Verify that autovisiontest can be imported and __version__ is correct."""
    import autovisiontest

    assert autovisiontest.__version__ == "0.1.0"


def test_version_from_cli():
    """Verify that `autovisiontest --version` outputs the correct version."""
    result = subprocess.run(
        [sys.executable, "-m", "autovisiontest.cli", "--version"],
        capture_output=True,
        text=True,
    )
    # The click --version option outputs "autovisiontest, version 0.1.0"
    assert "0.1.0" in result.stdout


def test_gitignore_data_dir():
    """Verify that data/ directory would be ignored by git."""
    result = subprocess.run(
        ["git", "check-ignore", "data/"],
        capture_output=True,
        text=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent),
    )
    assert result.returncode == 0, "data/ should be git-ignored"
