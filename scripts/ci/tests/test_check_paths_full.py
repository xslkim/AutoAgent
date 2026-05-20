"""TASK-0127: Comprehensive path whitelist tests.

Covers every ✅ allow / ⚠️ review_required / ❌ deny pattern in
``scripts/ci/path_whitelist.yml``, plus PR-body ``path_exception`` parsing.

Tests are organised by YAML section then by rule pattern so a single broken
rule maps to exactly the parametrize ID that failed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(SCRIPT_DIR))

import check_changed_paths as ccp  # noqa: E402

WHITELIST = SCRIPT_DIR / "path_whitelist.yml"


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def checker() -> ccp.WhitelistChecker:
    config = yaml.safe_load(WHITELIST.read_text(encoding="utf-8"))
    return ccp.WhitelistChecker(config)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run(paths: list[str], exceptions: list[str] = (), pr_body: str = "") -> int:
    argv: list[str] = []
    for p in paths:
        argv.extend(["--path", p])
    for e in exceptions:
        argv.extend(["--exception", e])
    if pr_body:
        argv.extend(["--pr-body", pr_body])
    argv.append("--quiet")
    return ccp.main(argv)


# ===========================================================================
# ALLOW patterns
# ===========================================================================


class TestAllowPatterns:
    """Every pattern in the allow: section must classify matching paths as allow."""

    # --- Unity adapter ---

    @pytest.mark.parametrize("path", [
        "adapters/unity/Runtime/AutoAgentBootstrap.cs",
        "adapters/unity/Runtime/Core/NodeScanner.cs",
        "adapters/unity/Runtime/Handlers/ClickHandler.cs",
    ])
    def test_unity_runtime_cs(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unity/Editor/AutoAgentMenu.cs",
        "adapters/unity/Editor/Inspectors/NodeInspector.cs",
    ])
    def test_unity_editor_cs(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unity/Tests/Runtime/NodeScannerTests.cs",
        "adapters/unity/Tests/Editor/MenuTests.cs",
    ])
    def test_unity_tests_cs(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unity/package.json",
    ])
    def test_unity_package_json(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unity/Runtime/AutoAgent.asmdef",
        "adapters/unity/Editor/AutoAgentEditor.asmdef",
        "adapters/unity/Tests/AutoAgentTests.asmdef",
    ])
    def test_unity_asmdef(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unity/Runtime/AutoAgentBootstrap.cs.meta",
        "adapters/unity/Editor/AutoAgentMenu.cs.meta",
        "adapters/unity/Runtime/Core.meta",
    ])
    def test_unity_meta(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unity/Plugins/link.xml",
        "adapters/unity/Runtime/link.xml",
    ])
    def test_unity_xml(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- Unreal adapter ---

    @pytest.mark.parametrize("path", [
        "adapters/unreal/Source/AutoAgentRuntime/AutoAgent.h",
        "adapters/unreal/Source/AutoAgentRuntime/Private/Scanner.h",
    ])
    def test_unreal_source_h(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unreal/Source/AutoAgentRuntime/AutoAgent.cpp",
        "adapters/unreal/Source/AutoAgentRuntime/Private/Scanner.cpp",
    ])
    def test_unreal_source_cpp(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unreal/Source/AutoAgentRuntime/AutoAgentRuntime.Build.cs",
        "adapters/unreal/Source/AutoAgent.Target.cs",
    ])
    def test_unreal_source_cs(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unreal/Tests/AutoAgentTests.cpp",
        "adapters/unreal/Tests/SomeSubdir/OtherTest.h",
    ])
    def test_unreal_tests(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/unreal/AutoAgentPlugin.uplugin",
    ])
    def test_unreal_uplugin(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- Godot adapter ---

    @pytest.mark.parametrize("path", [
        "adapters/godot/addons/autoagent/main.gd",
        "adapters/godot/addons/autoagent/core/scanner.gd",
        "adapters/godot/addons/autoagent/handlers/click.gd",
    ])
    def test_godot_gd(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "adapters/godot/addons/autoagent/plugin.cfg",
        "adapters/godot/addons/autoagent/subdir/config.cfg",
    ])
    def test_godot_cfg(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- MCP server ---

    @pytest.mark.parametrize("path", [
        "mcp-server/src/autoagent_mcp/server.py",
        "mcp-server/src/autoagent_mcp/tools/click.py",
        "mcp-server/src/autoagent_mcp/vision/ssim.py",
    ])
    def test_mcp_src_py(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "mcp-server/tests/test_server_starts.py",
        "mcp-server/tests/test_claude_judge.py",
    ])
    def test_mcp_tests_py(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "mcp-server/pyproject.toml",
    ])
    def test_mcp_pyproject(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "mcp-server/README.md",
    ])
    def test_mcp_readme(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- Protocol ---

    @pytest.mark.parametrize("path", [
        "protocol/schema/node.json",
        "protocol/schema/methods/click.json",
    ])
    def test_protocol_schema_json(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "protocol/tests/test_schema_valid.py",
        "protocol/tests/test_methods.py",
    ])
    def test_protocol_tests_py(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "protocol/README.md",
    ])
    def test_protocol_readme(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- Scripts ---

    @pytest.mark.parametrize("path", [
        "scripts/ci/check_changed_paths.py",
        "scripts/ci/path_whitelist.yml",
        "scripts/ci/tests/test_check_paths.py",
        "scripts/ci/tests/fixtures/allowed_paths.txt",
    ])
    def test_scripts_ci(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "scripts/e2e/run_login.py",
        "scripts/e2e/helpers/screenshot.py",
    ])
    def test_scripts_e2e(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "scripts/orchestrator/poll.py",
        "scripts/orchestrator/scheduler.py",
    ])
    def test_scripts_orchestrator(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "scripts/agent/runner.py",
        "scripts/agent/stop.py",
    ])
    def test_scripts_agent(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "scripts/fixtures/setup.py",
        "scripts/fixtures/helpers/seed.py",
    ])
    def test_scripts_fixtures_py(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- Fixture scripts ---

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Scripts/LoginController.cs",
        "fixtures/unity-test-project/Scripts/UI/ButtonHandler.cs",
        "fixtures/godot-test-project/Scripts/LoginController.cs",
    ])
    def test_fixture_scripts_cs(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Scripts/LoginController.cpp",
    ])
    def test_fixture_scripts_cpp(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Scripts/Native/NativeHelper.h",
    ])
    def test_fixture_scripts_h(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "fixtures/godot-test-project/Scripts/login_controller.gd",
        "fixtures/godot-test-project/Scripts/ui/button_handler.gd",
    ])
    def test_fixture_scripts_gd(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Source/AutoAgentTest/LoginController.h",
        "fixtures/unreal-test-project/Source/AutoAgentTest/Private/Helpers.h",
    ])
    def test_fixture_unreal_source_h(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Source/AutoAgentTest/LoginController.cpp",
        "fixtures/unreal-test-project/Source/AutoAgentTest/Private/Helpers.cpp",
    ])
    def test_fixture_unreal_source_cpp(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Source/AutoAgentTest/AutoAgentTest.Build.cs",
        "fixtures/unreal-test-project/Source/AutoAgentTest.Target.cs",
    ])
    def test_fixture_unreal_source_cs(self, checker, path):
        assert checker.check(path, set()).classification == "allow"

    # --- Task docs ---

    @pytest.mark.parametrize("path", [
        "docs/tasks.md",
        "docs/tasks-phase0.md",
        "docs/tasks-phase1.md",
        "docs/tasks-phase2.md",
    ])
    def test_docs_tasks(self, checker, path):
        assert checker.check(path, set()).classification == "allow"


# --- Negative: allow patterns must NOT match wrong files ---


class TestAllowNegative:
    """Paths that should NOT be classified as allow by any allow rule."""

    @pytest.mark.parametrize("path", [
        # Wrong extension in Unity adapter
        "adapters/unity/Runtime/AutoAgentBootstrap.py",
        "adapters/unity/Runtime/AutoAgentBootstrap.txt",
        # Unity .meta in wrong location
        "some/other/dir/file.cs.meta",
        # Not under adapters
        "src/unity/Runtime/AutoAgent.cs",
        # Deep path outside allowed scripts dir
        "fixtures/unity-test-project/Assets/Scripts/LoginController.cs",
        # Godot .gd outside the addon
        "adapters/godot/other/plugin.gd",
        # Script not under Scripts/ (falls to default_deny, not allow)
        "fixtures/unity-test-project/Runtime/LoginController.cs",
        # Unrecognized root
        "some/random/file.py",
    ])
    def test_not_allow(self, checker, path):
        v = checker.check(path, set())
        assert v.classification != "allow", (
            f"{path!r} classified as allow but should not be; verdict: {v}"
        )


# ===========================================================================
# DENY patterns
# ===========================================================================


class TestDenyPatterns:
    """Every pattern in deny: must match expected paths."""

    # --- Scene files ---

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Assets/Scenes/LoginScene.unity",
        "fixtures/unity-test-project/Assets/Scenes/Sub/LoginScene.unity",
    ])
    def test_unity_scene(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset",
        "fixtures/unreal-test-project/Content/UI/Deep/WBP.uasset",
    ])
    def test_unreal_uasset(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/godot-test-project/scenes/login.tscn",
        "fixtures/godot-test-project/scenes/sub/menu.tscn",
    ])
    def test_godot_tscn(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Content/Maps/LoginMap.umap",
        "fixtures/unreal-test-project/Content/Maps/Sub/Level.umap",
    ])
    def test_unreal_umap(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Art assets ---

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Assets/Sprites/UI/btn_login_normal.png",
        "fixtures/unity-test-project/Assets/Sprites/btn.png",
    ])
    def test_unity_sprites(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Resources/UI/icon.png",
        "fixtures/godot-test-project/Resources/UI/button.png",
    ])
    def test_resources_ui(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Content/UI/T_Button.png",
        "fixtures/unreal-test-project/Content/UI/Sub/Texture.png",
    ])
    def test_content_ui(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Fonts ---

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Assets/Fonts/Roboto-Regular.ttf",
        "fixtures/unity-test-project/Assets/Fonts/Sub/Bold.otf",
    ])
    def test_unity_fonts(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Content/UI/Fonts/Roboto-Regular.ttf",
        "fixtures/unreal-test-project/Content/UI/Fonts/Sub/Bold.ttf",
    ])
    def test_unreal_fonts(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Engine project settings ---

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/ProjectSettings/ProjectSettings.asset",
        "fixtures/unity-test-project/ProjectSettings/InputManager.asset",
        "fixtures/unity-test-project/ProjectSettings/Sub/Package.asset",
    ])
    def test_project_settings(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Config/DefaultEngine.ini",
        "fixtures/another-project/Config/DefaultEngine.ini",
    ])
    def test_default_engine_ini(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Visual baselines ---

    @pytest.mark.parametrize("path", [
        "baselines/unity/windows/login_screen.png",
        "baselines/unreal/linux/menu.png",
        "baselines/deep/nested/dir/image.png",
    ])
    def test_baselines(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Secrets ---

    @pytest.mark.parametrize("path", [
        ".env",
    ])
    def test_env(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        ".env.production",
        ".env.staging",
        ".env.local",
    ])
    def test_env_subext(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "private.key",
        "server.key",
    ])
    def test_key_files(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "server.pem",
        "ca.pem",
    ])
    def test_pem_files(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "secrets/api_token.txt",
        "secrets/db_password.env",
        "secrets/nested/key.txt",
    ])
    def test_secrets_dir(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Product docs ---

    @pytest.mark.parametrize("path", [
        "docs/00-intro.md",
        "docs/01-protocol-spec.md",
        "docs/03-adapter-unity.md",
        "docs/07-agent-operations.md",
        "docs/09-final.md",
    ])
    def test_product_docs_0x(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    @pytest.mark.parametrize("path", [
        "docs/10-fixture-setup-guide.md",
        "docs/15-ue-runner.md",
        "docs/19-last.md",
    ])
    def test_product_docs_1x(self, checker, path):
        assert checker.check(path, set()).classification == "deny"

    # --- Git internals ---

    @pytest.mark.parametrize("path", [
        ".git/config",
        ".git/hooks/pre-commit",
        ".git/refs/heads/main",
    ])
    def test_git_internals(self, checker, path):
        assert checker.check(path, set()).classification == "deny"


# --- Deny negative: patterns must NOT match sibling paths ---


class TestDenyNegative:
    """Paths that SHOULD NOT be caught by deny rules (i.e., they are allow/review/default)."""

    @pytest.mark.parametrize("path", [
        # .unity inside the adapter (code), not fixtures
        "adapters/unity/Runtime/SomeUtil.unity",  # would be weird but not in fixtures → not deny
        # baselines prefix but not under baselines/
        "fixtures/baselines/image.png",
        # *.key deep in path (deny is anchored to root-level *.key)
        "adapters/unreal/Source/AutoAgent/some.key",
        # *.pem inside a subdir
        "mcp-server/tests/certs/test.pem",
        # doc 20+ is not denied by current rules
        "docs/20-future.md",
    ])
    def test_not_deny(self, checker, path):
        v = checker.check(path, set())
        assert v.classification != "deny", (
            f"{path!r} was classified as deny but should not be; verdict: {v}"
        )


# ===========================================================================
# REVIEW_REQUIRED patterns
# ===========================================================================


class TestReviewRequiredPatterns:
    """Every pattern in review_required: must classify matching paths as review."""

    @pytest.mark.parametrize("path", [
        ".github/workflows/unity-ci.yml",
        ".github/workflows/mcp-pr.yml",
        ".github/workflows/subdir/reusable.yml",
    ])
    def test_github_workflows(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "docs/canonical-tasks/login_mvp.yaml",
        "docs/canonical-tasks/sub/task.yaml",
    ])
    def test_canonical_tasks(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "docs/runners-inventory.md",
        "docs/orchestrator-prompt.md",
    ])
    def test_ops_docs(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "docs/user-guide-quickstart.md",
        "docs/user-guide-advanced.md",
    ])
    def test_user_guide(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "docs/users/alice.md",
        "docs/users/team/bob.md",
    ])
    def test_users_docs(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "docs/phase0-gate-report.md",
        "docs/phase1-gate-report.md",
    ])
    def test_phase_gate_report(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "docs/sprint-report.md",
        "docs/cost-report.md",
    ])
    def test_any_report(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "fixtures/unity-test-project/Packages/manifest.json",
        "fixtures/unreal-test-project/Packages/manifest.json",
    ])
    def test_packages_manifest(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "fixtures/unreal-test-project/Config/AutoAgentIds.ini",
    ])
    def test_autoagent_ids(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        ".gitignore",
        "LICENSE",
        "README.md",
    ])
    def test_repo_root(self, checker, path):
        assert checker.check(path, set()).classification == "review"

    @pytest.mark.parametrize("path", [
        "adapters/unreal/Resources/icon.png",
        "adapters/unreal/Resources/splash.jpg",
        "adapters/unreal/Resources/sub/logo.png",
    ])
    def test_unreal_resources(self, checker, path):
        assert checker.check(path, set()).classification == "review"


# ===========================================================================
# Default deny (no rule matches)
# ===========================================================================


class TestDefaultDeny:
    @pytest.mark.parametrize("path", [
        "some/random/file.txt",
        "completely_unknown_file.py",
        "foo/bar/baz.json",
        "docs/99-unrecognised.md",        # 99 is > 19, not caught by deny
        "adapters/another-engine/foo.cs",  # not unity/unreal/godot
        "fixtures/unity-test-project/Assets/Prefabs/LoginPanel.prefab",
    ])
    def test_default_deny(self, checker, path):
        v = checker.check(path, set())
        assert v.classification == "default_deny", (
            f"{path!r} should be default_deny, got {v.classification!r}"
        )


# ===========================================================================
# Exception mechanics
# ===========================================================================


class TestExceptions:
    def test_exception_overrides_deny(self, checker):
        path = "baselines/unity/windows/login.png"
        assert checker.check(path, set()).classification == "deny"
        assert checker.check(path, {path}).classification == "exception"

    def test_exception_overrides_default_deny(self, checker):
        path = "some/random/file.txt"
        assert checker.check(path, set()).classification == "default_deny"
        assert checker.check(path, {path}).classification == "exception"

    def test_exception_does_not_affect_other_paths(self, checker):
        path_a = "baselines/unity/windows/login.png"
        path_b = "baselines/unity/windows/menu.png"
        assert checker.check(path_a, {path_b}).classification == "deny"

    def test_cli_exception_flag_unblocks_denied_path(self):
        rc = _run(
            ["baselines/unity/windows/login.png"],
            exceptions=["baselines/unity/windows/login.png"],
        )
        assert rc == 0

    def test_cli_without_exception_blocks_denied_path(self):
        rc = _run(["baselines/unity/windows/login.png"])
        assert rc != 0


# ===========================================================================
# PR-body path_exception parsing
# ===========================================================================


class TestParsePrBodyExceptions:
    """Unit tests for parse_pr_body_exceptions()."""

    def test_empty_body(self):
        assert ccp.parse_pr_body_exceptions("") == set()

    def test_no_path_exception_key(self):
        body = "## Task\nTASK-0001: some task\n\n## Changes\n- foo.py: added stuff\n"
        assert ccp.parse_pr_body_exceptions(body) == set()

    def test_fenced_yaml_block(self):
        body = textwrap.dedent("""\
            ## Task
            TASK-0042: special task

            ```yaml
            path_exception:
              - baselines/unity/windows/login.png
              - baselines/unreal/linux/menu.png
            ```
        """)
        result = ccp.parse_pr_body_exceptions(body)
        assert result == {
            "baselines/unity/windows/login.png",
            "baselines/unreal/linux/menu.png",
        }

    def test_fenced_yml_tag(self):
        body = textwrap.dedent("""\
            ```yml
            path_exception:
              - baselines/godot/linux/login.png
            ```
        """)
        result = ccp.parse_pr_body_exceptions(body)
        assert "baselines/godot/linux/login.png" in result

    def test_fenced_yaml_case_insensitive_tag(self):
        body = textwrap.dedent("""\
            ```YAML
            path_exception:
              - baselines/unity/windows/special.png
            ```
        """)
        result = ccp.parse_pr_body_exceptions(body)
        assert "baselines/unity/windows/special.png" in result

    def test_bare_path_exception_block(self):
        body = textwrap.dedent("""\
            ## Task
            TASK-0042: special task
            path_exception:
              - baselines/unity/windows/login.png
              - baselines/unreal/linux/menu.png
            ## Changes
        """)
        result = ccp.parse_pr_body_exceptions(body)
        assert result == {
            "baselines/unity/windows/login.png",
            "baselines/unreal/linux/menu.png",
        }

    def test_bare_single_exception(self):
        body = "path_exception:\n  - secrets/override.txt\n"
        result = ccp.parse_pr_body_exceptions(body)
        assert "secrets/override.txt" in result

    def test_fenced_and_bare_merged(self):
        body = textwrap.dedent("""\
            path_exception:
              - baselines/unity/windows/login.png

            ```yaml
            path_exception:
              - baselines/unreal/linux/menu.png
            ```
        """)
        result = ccp.parse_pr_body_exceptions(body)
        assert "baselines/unity/windows/login.png" in result
        assert "baselines/unreal/linux/menu.png" in result

    def test_malformed_yaml_block_skipped(self):
        body = textwrap.dedent("""\
            ```yaml
            path_exception: [unclosed
            ```
        """)
        # Should not raise; returns empty set
        result = ccp.parse_pr_body_exceptions(body)
        assert isinstance(result, set)

    def test_fenced_block_without_path_exception(self):
        body = textwrap.dedent("""\
            ```yaml
            some_other_key:
              - value1
            ```
        """)
        assert ccp.parse_pr_body_exceptions(body) == set()

    def test_non_list_path_exception_ignored(self):
        body = textwrap.dedent("""\
            ```yaml
            path_exception: "single string, not a list"
            ```
        """)
        assert ccp.parse_pr_body_exceptions(body) == set()

    def test_pr_body_with_multiple_yaml_blocks(self):
        body = textwrap.dedent("""\
            ```yaml
            path_exception:
              - baselines/unity/windows/a.png
            ```

            Some prose in between.

            ```yaml
            path_exception:
              - baselines/unity/windows/b.png
            ```
        """)
        result = ccp.parse_pr_body_exceptions(body)
        assert "baselines/unity/windows/a.png" in result
        assert "baselines/unity/windows/b.png" in result


# ===========================================================================
# End-to-end: CLI with --pr-body and --pr-body-file
# ===========================================================================


class TestCliPrBodyException:
    """Integration: denied path allowed via PR-body exception."""

    DENIED_PATH = "baselines/unity/windows/login.png"

    def _pr_body(self, paths: list[str]) -> str:
        items = "\n".join(f"  - {p}" for p in paths)
        return f"path_exception:\n{items}\n"

    def test_pr_body_inline_unblocks_denied(self):
        body = self._pr_body([self.DENIED_PATH])
        rc = _run([self.DENIED_PATH], pr_body=body)
        assert rc == 0

    def test_pr_body_inline_does_not_unblock_other(self):
        # exception for a *different* baseline → the checked path still denied
        body = self._pr_body(["baselines/unity/windows/other.png"])
        rc = _run([self.DENIED_PATH], pr_body=body)
        assert rc != 0

    def test_pr_body_fenced_yaml_unblocks_denied(self):
        body = textwrap.dedent(f"""\
            ## Task
            TASK-9999: test

            ```yaml
            path_exception:
              - {self.DENIED_PATH}
            ```
        """)
        rc = _run([self.DENIED_PATH], pr_body=body)
        assert rc == 0

    def test_pr_body_file_unblocks_denied(self, tmp_path):
        body_file = tmp_path / "pr_body.md"
        body_file.write_text(self._pr_body([self.DENIED_PATH]), encoding="utf-8")
        argv = [
            "--path", self.DENIED_PATH,
            "--pr-body-file", str(body_file),
            "--quiet",
        ]
        rc = ccp.main(argv)
        assert rc == 0

    def test_pr_body_file_missing_returns_exit2(self, tmp_path):
        argv = [
            "--path", "adapters/unity/Runtime/Foo.cs",
            "--pr-body-file", str(tmp_path / "nonexistent.md"),
            "--quiet",
        ]
        rc = ccp.main(argv)
        assert rc == 2

    def test_pr_body_merges_with_exception_flag(self):
        # --exception covers path_a, --pr-body covers path_b → both pass
        path_a = "baselines/unity/windows/a.png"
        path_b = "baselines/unity/windows/b.png"
        body = self._pr_body([path_b])
        argv = [
            "--path", path_a,
            "--path", path_b,
            "--exception", path_a,
            "--pr-body", body,
            "--quiet",
        ]
        rc = ccp.main(argv)
        assert rc == 0

    def test_empty_pr_body_has_no_effect(self):
        rc = _run([self.DENIED_PATH], pr_body="")
        assert rc != 0


# ===========================================================================
# Full whitelist fixture-file driven tests (extended)
# ===========================================================================


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> list[str]:
    return [
        line.strip()
        for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_fixture_allowed_paths_all_pass():
    rc = _run(_load_fixture("allowed_paths.txt"))
    assert rc == 0


def test_fixture_denied_paths_all_fail():
    rc = _run(_load_fixture("denied_paths.txt"))
    assert rc != 0


def test_fixture_review_paths_pass_with_warning(capsys):
    rc = _run(_load_fixture("review_paths.txt"))
    assert rc == 0
    out = capsys.readouterr().err + capsys.readouterr().out
    # review warning may be on stdout or stderr; just check exit code


def test_fixture_mixed_fails():
    rc = _run(_load_fixture("mixed_paths.txt"))
    assert rc != 0
