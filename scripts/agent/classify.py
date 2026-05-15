"""Classify the outcome of a claude CLI invocation.

Inputs: subprocess exit code + stdout text + stderr text.
Output: (status, reason).

Statuses (docs/09-orchestration.md §三 + §九):
    "awaiting_ci"  — claude exited cleanly AND a PR URL was found in stdout
    "success"      — claude exited cleanly but no PR URL (rare; agent may have
                     decided no PR is needed). Not the common path.
    "failed"       — non-zero exit without a recognized policy violation;
                     orchestrator will retry per task.max_retries.
    "needs_human"  — recognized policy violation (path / visual / auth); do
                     not retry, route to needs_human/ per docs/09 §5.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Policy-violation patterns we look for. Order matters: more specific first.
NEEDS_HUMAN_PATTERNS: tuple[tuple[str, str], ...] = (
    # Path whitelist (防护 0.1)
    (r"-32030\b|PathViolation\b", "path violation"),
    (r"path[_\s-]?(whitelist|violation)|路径白名单(违规|违反)", "path violation"),
    # Source-diff visual write audit (防护 0.2)
    (r"-32003\b|VisualPropertyWrite\b", "visual-property write rejected"),
    (r"visual[_\s-]?write[_\s-]?audit|视觉.*违规", "visual-write audit failed"),
    # Auth / config errors that humans must fix
    (r"\b(401|403)\s+(Unauthorized|Forbidden)", "auth failure"),
    (r"ANTHROPIC_API_KEY\s+(not\s+set|invalid|missing)", "missing API key"),
)


# Patterns that should NOT match URLs inside markdown link descriptions etc.
PR_URL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://github\.com/[\w.\-]+/[\w.\-]+/pull/\d+"),
    re.compile(r"gh pr create.*?(https?://\S+/pull/\d+)", re.DOTALL),
)


@dataclass(frozen=True)
class Verdict:
    status: str  # awaiting_ci | success | failed | needs_human
    reason: str
    pr_url: str | None = None


def extract_pr_url(text: str) -> str | None:
    """Return the first PR URL found in `text`, or None."""
    for rx in PR_URL_PATTERNS:
        m = rx.search(text)
        if m is None:
            continue
        return m.group(1) if rx.groups else m.group(0)
    return None


def classify(exit_code: int, stdout: str = "", stderr: str = "") -> Verdict:
    blob = (stdout or "") + "\n" + (stderr or "")

    # 1. Policy violations beat everything — even a "clean" exit 0 with these
    #    strings in stderr should fail to needs_human (defense in depth).
    for pattern, reason in NEEDS_HUMAN_PATTERNS:
        if re.search(pattern, blob, re.IGNORECASE):
            return Verdict("needs_human", reason)

    # 2. Successful exit
    if exit_code == 0:
        pr_url = extract_pr_url(blob)
        if pr_url:
            return Verdict("awaiting_ci", "agent exited cleanly, PR open", pr_url)
        return Verdict("success", "agent exited cleanly, no PR URL detected")

    # 3. Non-zero exit, no policy violation → ordinary failure (retryable)
    short = (stderr or stdout or "").strip().splitlines()[-1:] or [""]
    return Verdict("failed", f"exit {exit_code}: {short[0][:200]}")
