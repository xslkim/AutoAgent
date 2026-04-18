"""Additional edge-case tests for T A.1 project initialization (Test Agent supplement)."""

import subprocess
import sys

import autovisiontest


def test_version_is_string():
    """Verify __version__ is a string (not accidentally int/float)."""
    assert isinstance(autovisiontest.__version__, str)


def test_version_format_semver():
    """Verify __version__ follows basic semver pattern (X.Y.Z)."""
    parts = autovisiontest.__version__.split(".")
    assert len(parts) == 3, f"Version should have 3 dot-separated parts, got: {autovisiontest.__version__}"
    for part in parts:
        assert part.isdigit(), f"Each version part should be numeric, got: {part}"


def test_module_docstring_exists():
    """Verify the package has a module-level docstring."""
    assert autovisiontest.__doc__ is not None
    assert len(autovisiontest.__doc__.strip()) > 0


def test_cli_help_option():
    """Verify `autovisiontest --help` exits with code 0."""
    result = subprocess.run(
        [sys.executable, "-m", "autovisiontest.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_gitignore_secrets():
    """Verify that .env files and .autovt/ are git-ignored (dev_workflow §16.8)."""
    project_root = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
    for pattern in [".env", "secrets.env", ".autovt/"]:
        result = subprocess.run(
            ["git", "check-ignore", pattern],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        assert result.returncode == 0, f"'{pattern}' should be git-ignored"


def test_gitignore_agent_locks():
    """Verify that .agent/locks/ is git-ignored (dev_workflow §16.8)."""
    project_root = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        ["git", "check-ignore", ".agent/locks/"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, "'.agent/locks/' should be git-ignored"


def test_gitignore_pycache():
    """Verify that __pycache__/ is git-ignored."""
    project_root = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        ["git", "check-ignore", "__pycache__/"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, "'__pycache__/' should be git-ignored"


def test_gitignore_egg_info():
    """Verify that *.egg-info is git-ignored."""
    project_root = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        ["git", "check-ignore", "autovisiontest.egg-info/"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, "'*.egg-info/' should be git-ignored"
