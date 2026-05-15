"""Build the prompt sent to claude CLI for a single task.

Template per docs/09-orchestration.md §9.1. The prompt is small on purpose —
claude pulls task details from the linked docs at task execution time.
"""

from __future__ import annotations

from pathlib import Path


PROMPT_TEMPLATE = """You are an AutoAgent task execution agent.

# Current task: {task_id}

**Title**: {title}
**Phase**: {phase}
**Engine**: {engine}
**Risk**: {risk}

Full spec: see `{spec_path}` (read it before you start).

## Goal

{goal}

## Verification

{verification}

## Worktree

You are working in git worktree `{worktree_path}` on branch `{branch}`.
Treat this as an isolated checkout — do **not** edit anything outside it.

## Hard constraints

1. Path whitelist (防护 0.1): you may only modify paths matched by
   `scripts/ci/path_whitelist.yml`. The CI step `scripts/ci/check_changed_paths.py`
   will run on your PR and reject violations with exit code 1.
2. Visual write audit (防护 0.2): you may not assign to `visual` fields in
   source code. Use `AUTOAGENT_ALLOW_VISUAL` file-level marker only when truly
   needed and reviewed.
3. No destructive git ops: no `git reset --hard`, no `git push --force`, no
   `git rebase`. See docs/07 §5.2.
4. One commit per task, message format: `[{task_id}] <title under 70 chars>`.

## Required closing steps

1. `git add <your files>`
2. `git commit -m "[{task_id}] <title>"`
3. `git push -u origin {branch}`
4. `gh pr create --title "[{task_id}] <title>" --body "..."`
5. Exit normally — do **not** wait for CI; that's the orchestrator's job.

If anything goes wrong, exit with a non-zero code and leave the worktree as-is.
Do not delete files or try to undo your work.
"""


def build_prompt(task: dict, *, worktree_path: Path, branch: str) -> str:
    return PROMPT_TEMPLATE.format(
        task_id=task.get("id", "TASK-UNKNOWN"),
        title=task.get("title", "(no title)"),
        phase=task.get("phase", "?"),
        engine=task.get("engine", "none"),
        risk=task.get("risk", "?"),
        spec_path=task.get("spec_path", "docs/tasks.md"),
        goal=task.get("goal", "(no goal specified)"),
        verification="\n".join(f"- {v}" for v in (task.get("verification") or []))
        or "(none)",
        worktree_path=str(worktree_path),
        branch=branch,
    )
