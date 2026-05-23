"""TASK-0003 verification.

Tests for scripts/ci/check_changed_paths.py and path_whitelist.yml.

Per docs/tasks-phase0.md TASK-0003:
- 模拟改 .unity 文件 → exit code 非 0
- 模拟改 adapters/unity/Assets/AutoAgent/Runtime/*.cs → exit code 0
- 模拟改 .env → exit code 非 0
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Make sibling module importable without packaging.
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_changed_paths as ccp  # noqa: E402

WHITELIST = SCRIPT_DIR / "path_whitelist.yml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --- glob_to_regex unit tests ---------------------------------------------

@pytest.mark.parametrize("pattern,path,expected", [
    # Star matches single segment
    ("foo/*.py", "foo/bar.py", True),
    ("foo/*.py", "foo/baz/bar.py", False),

    # ** matches across segments
    ("foo/**/*.py", "foo/bar.py", True),
    ("foo/**/*.py", "foo/a/b/c.py", True),
    ("foo/**/*.py", "foo/a.cpp", False),

    # **.unity catches scenes anywhere under prefix
    ("fixtures/*/**.unity", "fixtures/unity-test-project/Assets/Scenes/LoginScene.unity", True),
    ("fixtures/*/**.unity", "fixtures/godot-test-project/scenes/login.tscn", False),

    # Char class
    ("docs/0[0-9]-*.md", "docs/03-adapter-unity.md", True),
    ("docs/0[0-9]-*.md", "docs/04a-adapter-unreal.md", False),
    ("docs/0[0-9]-*.md", "docs/tasks.md", False),

    # Exact match
    (".env", ".env", True),
    (".env", ".env.production", False),

    # Extension wildcard
    (".env.*", ".env.production", True),
    (".env.*", ".env", False),

    # ** at end
    ("baselines/**", "baselines/unity/windows/login.png", True),
    ("baselines/**", "fixtures/baselines/foo.png", False),

    # Secret patterns
    ("*.key", "private.key", True),
    ("*.key", "foo/private.key", False),
    ("*.pem", "server.pem", True),
])
def test_glob_to_regex(pattern, path, expected):
    rx = ccp.glob_to_regex(pattern)
    assert bool(rx.match(path)) is expected


# --- WhitelistChecker.check ----------------------------------------------

@pytest.fixture(scope="module")
def checker():
    config = yaml.safe_load(WHITELIST.read_text(encoding="utf-8"))
    return ccp.WhitelistChecker(config)


@pytest.mark.parametrize("path", [
    "adapters/unity/Assets/AutoAgent/Runtime/AutoAgentBootstrap.cs",
    "mcp-server/src/autoagent_mcp/server.py",
    "protocol/schema/node.json",
    "scripts/ci/check_changed_paths.py",
    "fixtures/unity-test-project/Scripts/LoginController.cs",
    "fixtures/unreal-test-project/Source/AutoAgentTest/Login.cpp",
    "docs/tasks.md",
])
def test_allowed_paths(checker, path):
    v = checker.check(path, exceptions=set())
    assert v.classification == "allow", f"{path}: {v}"


@pytest.mark.parametrize("path", [
    # Scenes / WBP
    "fixtures/unity-test-project/Assets/Scenes/LoginScene.unity",
    "fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset",
    "fixtures/unreal-test-project/Content/Maps/LoginMap.umap",
    # Art / fonts
    "fixtures/unity-test-project/Assets/Sprites/UI/btn_login_normal.png",
    "fixtures/unity-test-project/Assets/Fonts/Roboto-Regular.ttf",
    # Settings
    "fixtures/unity-test-project/ProjectSettings/ProjectSettings.asset",
    "fixtures/unreal-test-project/Config/DefaultEngine.ini",
    # Baselines
    "baselines/unity/windows/login_screen.png",
    # Secrets
    ".env",
    ".env.production",
    "private.key",
    "server.pem",
    "secrets/api_token.txt",
    # Product docs
    "docs/01-protocol-spec.md",
    "docs/10-fixture-setup-guide.md",
])
def test_denied_paths(checker, path):
    v = checker.check(path, exceptions=set())
    assert v.classification == "deny", f"{path}: {v}"


@pytest.mark.parametrize("path", [
    ".github/workflows/unity-ci.yml",
    "docs/canonical-tasks/login_mvp.yaml",
    "docs/runners-inventory.md",
    "fixtures/unity-test-project/Packages/manifest.json",
    ".gitignore",
    "LICENSE",
    "README.md",
    "adapters/unreal/Resources/icon.png",
])
def test_review_required_paths(checker, path):
    v = checker.check(path, exceptions=set())
    assert v.classification == "review", f"{path}: {v}"


def test_unrecognized_path_default_deny(checker):
    v = checker.check("some/random/file.txt", exceptions=set())
    assert v.classification == "default_deny"


def test_exception_overrides_deny(checker):
    deny_path = "fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"
    # without exception → deny
    assert checker.check(deny_path, exceptions=set()).classification == "deny"
    # with exception → allow
    v = checker.check(deny_path, exceptions={deny_path})
    assert v.classification == "exception"


# --- End-to-end exit-code tests (verification per task spec) -------------

def _run(paths: list[str], exceptions: list[str] = (), quiet=True) -> int:
    """Invoke main() with explicit --path args (no stdin needed)."""
    argv = []
    for p in paths:
        argv.extend(["--path", p])
    for e in exceptions:
        argv.extend(["--exception", e])
    if quiet:
        argv.append("--quiet")
    return ccp.main(argv)


def test_unity_scene_change_fails():
    """模拟改 .unity 文件 → exit code 非 0."""
    rc = _run(["fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"])
    assert rc != 0


def test_unity_adapter_runtime_cs_passes():
    """模拟改 adapters/unity/Assets/AutoAgent/Runtime/*.cs → exit code 0."""
    rc = _run(["adapters/unity/Assets/AutoAgent/Runtime/AutoAgentBootstrap.cs"])
    assert rc == 0


def test_env_file_change_fails():
    """模拟改 .env → exit code 非 0."""
    rc = _run([".env"])
    assert rc != 0


def test_env_subextension_fails():
    rc = _run([".env.production"])
    assert rc != 0


def test_secret_key_fails():
    rc = _run(["secrets/api_token.txt", "private.key", "server.pem"])
    assert rc != 0


def test_multiple_allowed_passes():
    rc = _run([
        "adapters/unity/Assets/AutoAgent/Runtime/AutoAgentBootstrap.cs",
        "mcp-server/src/autoagent_mcp/server.py",
        "protocol/schema/node.json",
    ])
    assert rc == 0


def test_one_denied_among_many_fails():
    rc = _run([
        "adapters/unity/Assets/AutoAgent/Runtime/AutoAgentBootstrap.cs",
        "fixtures/unity-test-project/Assets/Scenes/LoginScene.unity",
        "mcp-server/src/autoagent_mcp/server.py",
    ])
    assert rc != 0


def test_exception_unblocks_otherwise_denied_path():
    rc = _run(
        ["fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"],
        exceptions=["fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"],
    )
    assert rc == 0


def test_review_only_paths_pass_but_warn(capsys):
    rc = _run([".github/workflows/unity-ci.yml"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "review" in (captured.err + captured.out).lower()


def test_empty_input_passes(capsys, monkeypatch):
    # Empty stdin → "no paths to check" → exit 0
    monkeypatch.setattr("sys.stdin", iter([]))
    rc = ccp.main([])
    assert rc == 0


# --- Fixture-file driven cases -------------------------------------------

def test_fixture_allowed_paths_all_pass():
    rc = _run(_load_fixture("allowed_paths.txt"))
    assert rc == 0


def test_fixture_denied_paths_all_fail():
    rc = _run(_load_fixture("denied_paths.txt"))
    assert rc != 0


def test_fixture_review_paths_pass():
    rc = _run(_load_fixture("review_paths.txt"))
    assert rc == 0


def test_fixture_mixed_fails():
    rc = _run(_load_fixture("mixed_paths.txt"))
    assert rc != 0


def _load_fixture(name: str) -> list[str]:
    return [
        line.strip()
        for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --- Subprocess invocation (catch import / entry-point regressions) ------

def test_subprocess_stdin_denied():
    """Pipe paths via stdin like a real CI run."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_changed_paths.py"), "--quiet"],
        input=".env\nadapters/unity/Assets/AutoAgent/Runtime/Foo.cs\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert ".env" in result.stdout + result.stderr


def test_subprocess_stdin_all_allowed():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_changed_paths.py"), "--quiet"],
        input="adapters/unity/Assets/AutoAgent/Runtime/Foo.cs\nmcp-server/src/autoagent_mcp/server.py\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
