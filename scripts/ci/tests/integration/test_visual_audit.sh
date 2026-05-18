#!/usr/bin/env bash
# TASK-0016 — 防护 0.2 (source-diff visual-write audit) integration test.
#
# Verifies scripts/ci/audit_visual_writes.py rejects visual-property writes
# across the three engine languages (C# / C++ / GDScript) and skips files that
# carry the AUTOAGENT_ALLOW_VISUAL marker.
#
# Per docs/tasks-phase0.md TASK-0016 this is exercised in the sandbox repo via
# a real PR, but the script is self-contained and runs locally:
#   bash scripts/ci/tests/integration/test_visual_audit.sh
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
cd "$REPO_ROOT"

AUDIT="scripts/ci/audit_visual_writes.py"
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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Visual-write violations, one per engine language.
printf 'public class Bad { void M(Image image) { image.color = Color.red; } }\n' \
    > "$WORK/Bad.cs"
printf 'void M(UWidget* W) { W->SetVisibility(ESlateVisibility::Hidden); }\n' \
    > "$WORK/bad.cpp"
printf 'func _f(): node.modulate = Color(1, 0, 0)\n' \
    > "$WORK/bad.gd"
# File-level marker — must be skipped even though it writes a visual property.
printf '// AUTOAGENT_ALLOW_VISUAL: baseline capture only\npublic class Y { void M(Image image) { image.color = Color.red; } }\n' \
    > "$WORK/Allowed.cs"
# Clean file — no visual writes.
printf 'public class Clean { void M() { int x = 1; } }\n' \
    > "$WORK/Clean.cs"

echo "防护 0.2 — visual-write audit integration test"

expect_exit "reject Unity image.color write (C#)" 1 \
    python "$AUDIT" --file "$WORK/Bad.cs" --repo-root "$WORK" --quiet
expect_exit "reject UE SetVisibility (C++)" 1 \
    python "$AUDIT" --file "$WORK/bad.cpp" --repo-root "$WORK" --quiet
expect_exit "reject Godot .modulate write (GDScript)" 1 \
    python "$AUDIT" --file "$WORK/bad.gd" --repo-root "$WORK" --quiet
expect_exit "skip file with AUTOAGENT_ALLOW_VISUAL marker" 0 \
    python "$AUDIT" --file "$WORK/Allowed.cs" --repo-root "$WORK" --quiet
expect_exit "allow clean file" 0 \
    python "$AUDIT" --file "$WORK/Clean.cs" --repo-root "$WORK" --quiet

echo ""
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
