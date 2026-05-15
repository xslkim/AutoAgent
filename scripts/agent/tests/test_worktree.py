"""worktree.py: create and destroy git worktrees in a real (temp) git repo.

These tests run actual git commands. They're fast (~1s each on a fresh repo)
and validate the real plumbing the agent will use.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from worktree import WorktreePlan, setup_worktree, remove_worktree


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny git repo with a single commit on 'main'."""
    repo = tmp_path / "AutoAgent"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("hi", encoding="utf-8")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-q", "-m", "init"], cwd=repo)
    return repo


def test_setup_worktree_creates_branch_and_dir(repo):
    plan = WorktreePlan(repo_root=repo, task_id="TASK-0007", base_ref="main")
    wt_path = setup_worktree(plan)
    assert wt_path.is_dir()
    assert (wt_path / "README.md").is_file()
    # Branch exists
    r = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/agent/TASK-0007"],
        cwd=str(repo),
    )
    assert r.returncode == 0


def test_setup_worktree_idempotent_destroys_and_recreates(repo):
    plan = WorktreePlan(repo_root=repo, task_id="TASK-0007", base_ref="main")
    setup_worktree(plan)
    # Modify the worktree to simulate dirty state
    (plan.path / "dirty.txt").write_text("X", encoding="utf-8")
    # Second setup should wipe and recreate cleanly
    setup_worktree(plan)
    assert not (plan.path / "dirty.txt").exists()


def test_remove_worktree_clears_dir_and_branch(repo):
    plan = WorktreePlan(repo_root=repo, task_id="TASK-0008", base_ref="main")
    setup_worktree(plan)
    remove_worktree(plan)
    assert not plan.path.exists()
    r = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/agent/TASK-0008"],
        cwd=str(repo),
    )
    assert r.returncode != 0


def test_plan_branch_and_path_naming(tmp_path):
    plan = WorktreePlan(repo_root=tmp_path / "AutoAgent", task_id="TASK-0042")
    assert plan.branch == "agent/TASK-0042"
    assert plan.path == tmp_path / "AutoAgent.worktrees" / "TASK-0042"
