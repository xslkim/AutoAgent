from __future__ import annotations

from pathlib import Path

from prompt_template import build_prompt


def test_prompt_includes_task_id_and_title(tmp_path):
    task = {
        "id": "TASK-0007",
        "title": "Unity adapter PoC",
        "phase": 0,
        "engine": "unity",
        "risk": "medium",
        "goal": "Implement minimal Unity adapter",
        "verification": ["pytest passes", "wscat handshake works"],
    }
    p = build_prompt(task, worktree_path=tmp_path / "wt", branch="agent/TASK-0007")
    assert "TASK-0007" in p
    assert "Unity adapter PoC" in p
    assert "agent/TASK-0007" in p
    assert "pytest passes" in p
    assert "wscat handshake works" in p


def test_prompt_handles_missing_optional_fields(tmp_path):
    task = {"id": "TASK-0001"}
    p = build_prompt(task, worktree_path=tmp_path / "wt", branch="agent/TASK-0001")
    # No crash; placeholders fall back to (no title) etc.
    assert "TASK-0001" in p
    assert "(no title)" in p


def test_prompt_includes_required_constraints(tmp_path):
    """The hard constraints (path whitelist, visual audit, no force-push) must
    always appear so the agent always sees them, regardless of task content.
    """
    p = build_prompt({"id": "TASK-X"}, worktree_path=tmp_path, branch="agent/TASK-X")
    assert "path_whitelist" in p.lower() or "防护 0.1" in p
    assert "visual" in p.lower()
    assert "git push --force" in p or "force" in p.lower()
    assert "gh pr create" in p
