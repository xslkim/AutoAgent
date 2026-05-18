#!/usr/bin/env bash
# TASK-0015 — 防护 0.1 (path whitelist) integration test.
#
# Verifies scripts/ci/check_changed_paths.py rejects path-whitelist violations
# (engine asset edits, secret files, baseline images) and allows legitimate
# adapter source edits.
#
# Per docs/tasks-phase0.md TASK-0015 this is exercised in the sandbox repo via
# a real PR, but the script is self-contained and runs locally:
#   bash scripts/ci/tests/integration/test_path_violation.sh
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
cd "$REPO_ROOT"

CHECK="scripts/ci/check_changed_paths.py"
pass=0
fail=0

# expect_exit <description> <expected-exit-code> <command...>
expect_exit() {
    local desc="$1" expected="$2"
    shift 2
    "$@" >/dev/null 2>&1
    local got=$?
    if [ "$got" -eq "$expected" ]; then
        echo "  [PASS] $desc"
        pass=$((pass + 1))
    else
        echo "  [FAIL] $desc (expected exit $expected, got $got)"
        fail=$((fail + 1))
    fi
}

echo "防护 0.1 — path whitelist integration test"

expect_exit "reject .unity scene edit" 1 \
    python "$CHECK" --path "fixtures/unity-test-project/Assets/Scenes/LoginScene.unity" --quiet
expect_exit "reject .uasset edit" 1 \
    python "$CHECK" --path "fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset" --quiet
expect_exit "reject secret file (.env) edit" 1 \
    python "$CHECK" --path ".env" --quiet
expect_exit "reject baselines/ edit" 1 \
    python "$CHECK" --path "baselines/unity/windows/login_screen.png" --quiet
expect_exit "allow adapter source edit" 0 \
    python "$CHECK" --path "adapters/unity/Runtime/Server/ProtocolHandler.cs" --quiet

echo ""
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
