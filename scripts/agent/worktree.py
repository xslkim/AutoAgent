"""git worktree setup / teardown for agent tasks.

Honors the [07 §5.2](docs/07-agent-operations.md) git-operation whitelist:
NO `git reset --hard`, NO `git push --force`, NO `git rebase`. Worktrees are
the only way we get fresh state — see [09 §6.4](docs/09-orchestration.md).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorktreePlan:
    repo_root: Path
    task_id: str
    base_ref: str = "origin/main"

    @property
    def branch(self) -> str:
        return f"agent/{self.task_id}"

    @property
    def path(self) -> Path:
        # Sibling to repo_root: /home/user/AutoAgent.worktrees/<TASK-ID>
        return self.repo_root.parent / f"{self.repo_root.name}.worktrees" / self.task_id


def _git(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    # Force UTF-8: on a zh-CN Windows the default codec is GBK, which raises
    # UnicodeDecodeError when git prints non-ASCII paths/branch names.
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _worktree_exists(repo_root: Path, plan: WorktreePlan) -> bool:
    res = _git(["worktree", "list", "--porcelain"], cwd=repo_root, check=False)
    if res.returncode != 0:
        return False
    target = str(plan.path).replace("\\", "/")
    for line in res.stdout.splitlines():
        if line.startswith("worktree "):
            wt = line[len("worktree "):].replace("\\", "/")
            if wt == target:
                return True
    return False


def _branch_exists(repo_root: Path, branch: str) -> bool:
    res = _git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
               cwd=repo_root, check=False)
    return res.returncode == 0


def setup_worktree(plan: WorktreePlan) -> Path:
    """Create a fresh worktree. If one already exists at the target path,
    destroy and recreate it (per docs/09 §6.4: never `git reset --hard`).
    """
    if _worktree_exists(plan.repo_root, plan):
        _git(["worktree", "remove", "--force", str(plan.path)], cwd=plan.repo_root, check=False)
    if _branch_exists(plan.repo_root, plan.branch):
        _git(["branch", "-D", plan.branch], cwd=plan.repo_root, check=False)

    plan.path.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "-b", plan.branch, str(plan.path), plan.base_ref],
         cwd=plan.repo_root, check=True)
    return plan.path


def remove_worktree(plan: WorktreePlan, *, keep_branch: bool = False) -> None:
    """Destroy a worktree and (optionally) its branch."""
    if _worktree_exists(plan.repo_root, plan):
        _git(["worktree", "remove", "--force", str(plan.path)],
             cwd=plan.repo_root, check=False)
    if not keep_branch and _branch_exists(plan.repo_root, plan.branch):
        _git(["branch", "-D", plan.branch], cwd=plan.repo_root, check=False)
