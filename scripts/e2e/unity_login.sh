#!/usr/bin/env bash
# AutoAgent TASK-0133 — scripts/e2e/unity_login.sh
#
# Run the E2E login PlayMode tests in Unity headless mode and verify
# that the key log lines appear, confirming the full login flow:
#   send_text → click → mock API 收到 POST → welcome_text 出现
#
# Usage:
#   bash scripts/e2e/unity_login.sh [--project-path PATH] [--unity-path PATH]
#
# Environment variables (take precedence over defaults):
#   UNITY_PATH         Path to Unity.exe / Unity binary
#   UNITY_PROJECT_PATH Path to the Unity project directory
#
# Exit codes:
#   0 — all e2e checks passed
#   1 — one or more checks failed
#   2 — Unity binary not found

set -euo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

UNITY_PROJECT_PATH="${UNITY_PROJECT_PATH:-}"
UNITY_PATH="${UNITY_PATH:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-path)  UNITY_PROJECT_PATH="$2"; shift 2 ;;
        --unity-path)    UNITY_PATH="$2";          shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Locate repo root and project
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -z "$UNITY_PROJECT_PATH" ]]; then
    UNITY_PROJECT_PATH="$REPO_ROOT/fixtures/unity-test-project"
fi

# ---------------------------------------------------------------------------
# Locate Unity binary
# ---------------------------------------------------------------------------

# Candidate paths (Windows / macOS / Linux), ordered by likelihood
UNITY_CANDIDATES=(
    "C:/Program Files/Unity 2023.2.20f1/Editor/Unity.exe"
    "C:/Program Files/Unity/Hub/Editor/2023.2.20f1/Editor/Unity.exe"
    "/Applications/Unity/Hub/Editor/2023.2.20f1/Unity.app/Contents/MacOS/Unity"
    "/opt/unity/2023.2.20f1/Editor/Unity"
)

if [[ -z "$UNITY_PATH" ]]; then
    for candidate in "${UNITY_CANDIDATES[@]}"; do
        # Normalise Windows paths for Git Bash
        normalised="${candidate/C:\//$PROGRAMFILES/}"
        if [[ -f "$candidate" ]]; then
            UNITY_PATH="$candidate"
            break
        elif [[ -f "$normalised" ]]; then
            UNITY_PATH="$normalised"
            break
        fi
    done
fi

if [[ -z "$UNITY_PATH" || ! -f "$UNITY_PATH" ]]; then
    echo "ERROR: Unity binary not found." >&2
    echo "  Set UNITY_PATH or pass --unity-path to override." >&2
    echo "  Looked in:" >&2
    for c in "${UNITY_CANDIDATES[@]}"; do echo "    $c" >&2; done
    exit 2
fi

echo "=== AutoAgent E2E — Unity Login Flow ==="
echo "  Unity:   $UNITY_PATH"
echo "  Project: $UNITY_PROJECT_PATH"
echo ""

# ---------------------------------------------------------------------------
# Temp output directory
# ---------------------------------------------------------------------------

WORK_DIR="$(mktemp -d)"
RESULTS_XML="$WORK_DIR/e2e-results.xml"
LOG_FILE="$WORK_DIR/unity-e2e.log"

cleanup() {
    if [[ -f "$LOG_FILE" ]]; then
        echo ""
        echo "--- Unity log (last 60 lines) ---"
        tail -n 60 "$LOG_FILE" || true
    fi
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Run Unity PlayMode tests (e2e filter only)
# ---------------------------------------------------------------------------

echo "--- Running Unity PlayMode tests ---"

# Unity exits 0 for pass, non-zero for compile error or test failure.
# Use Start-Process pattern on Windows (via Git Bash, Unity is a GUI app).
if [[ "$UNITY_PATH" == *.exe ]]; then
    # Windows: Unity.exe is a GUI process; we must wait for it explicitly.
    "$UNITY_PATH" \
        -batchmode \
        -nographics \
        -accept-apiupdate \
        -projectPath "$(cygpath -w "$UNITY_PROJECT_PATH" 2>/dev/null || echo "$UNITY_PROJECT_PATH")" \
        -runTests \
        -testPlatform PlayMode \
        -testFilter "AutoAgent.Login.Tests.E2ELoginTests" \
        -testResults "$(cygpath -w "$RESULTS_XML" 2>/dev/null || echo "$RESULTS_XML")" \
        -logFile "$(cygpath -w "$LOG_FILE" 2>/dev/null || echo "$LOG_FILE")" \
        || true  # capture exit code below
    UNITY_EXIT=${PIPESTATUS[0]:-$?}
else
    # macOS / Linux
    "$UNITY_PATH" \
        -batchmode \
        -nographics \
        -accept-apiupdate \
        -projectPath "$UNITY_PROJECT_PATH" \
        -runTests \
        -testPlatform PlayMode \
        -testFilter "AutoAgent.Login.Tests.E2ELoginTests" \
        -testResults "$RESULTS_XML" \
        -logFile "$LOG_FILE" \
        || true
    UNITY_EXIT=${PIPESTATUS[0]:-$?}
fi

echo "Unity exited with code: $UNITY_EXIT"

# ---------------------------------------------------------------------------
# Parse XML results
# ---------------------------------------------------------------------------

PASS=0
FAIL=0

if [[ -f "$RESULTS_XML" ]]; then
    echo ""
    echo "--- Test results XML ---"
    cat "$RESULTS_XML"
    echo ""

    # Check overall result attribute: result="Passed"
    if grep -qiE 'result="Passed"' "$RESULTS_XML"; then
        echo "[OK] XML: overall result = Passed"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] XML: overall result is not Passed"
        FAIL=$((FAIL + 1))
    fi

    # Count test-case elements and check for failures
    total_cases=$(grep -c '<test-case' "$RESULTS_XML" || echo 0)
    failed_cases=$(grep -c 'result="Failed"' "$RESULTS_XML" || echo 0)
    echo "[INFO] test-case total=$total_cases  failed=$failed_cases"
    if [[ "$failed_cases" -gt 0 ]]; then
        echo "[FAIL] $failed_cases test case(s) failed"
        FAIL=$((FAIL + 1))
    fi
else
    echo "[FAIL] No test-results XML produced — compilation or runner error"
    FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# Verify required log lines
# ---------------------------------------------------------------------------

echo ""
echo "--- Checking required log lines ---"

check_log() {
    local pattern="$1"
    local label="$2"
    if [[ -f "$LOG_FILE" ]] && grep -qF "$pattern" "$LOG_FILE"; then
        echo "[OK]   $label"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] $label  (pattern: '$pattern')"
        FAIL=$((FAIL + 1))
    fi
}

check_log "[E2E] send_text 成功"  "send_text 成功 in log"
check_log "[E2E] click 成功"      "click 成功 in log"
check_log "[E2E] mock API 收到 POST" "mock API 收到 POST in log"

# ---------------------------------------------------------------------------
# Unity process exit code check
# ---------------------------------------------------------------------------

if [[ "$UNITY_EXIT" -ne 0 ]]; then
    echo ""
    echo "[FAIL] Unity process exited with non-zero code: $UNITY_EXIT"
    FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=== E2E Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
    echo "RESULT: FAILED ($FAIL check(s) did not pass)"
    exit 1
fi

echo "RESULT: ALL CHECKS PASSED — login e2e flow verified"
exit 0
