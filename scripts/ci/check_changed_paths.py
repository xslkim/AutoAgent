"""Path whitelist enforcement (防护 0.1).

Reads a list of changed file paths and classifies each against path_whitelist.yml.
Exits 0 only if every path is either explicitly allowed or covered by an exception.

Authoritative source for what AI may modify. See docs/07-agent-operations.md §3.2.

Usage::

    # From stdin (one path per line)
    git diff --name-only origin/main...HEAD | python scripts/ci/check_changed_paths.py

    # From a file
    python scripts/ci/check_changed_paths.py --paths-file changed.txt

    # Explicit paths
    python scripts/ci/check_changed_paths.py --path fixtures/foo.unity --path mcp-server/src/foo.py

    # With task-declared exceptions (overrides deny)
    python scripts/ci/check_changed_paths.py --exception baselines/unity/windows/login.png < paths.txt

Exit codes:
    0 — all paths allowed (possibly some need human review; logged but not blocking)
    1 — at least one path violation
    2 — usage / config error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


DEFAULT_WHITELIST = Path(__file__).resolve().parent / "path_whitelist.yml"


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a gitignore-style glob to a full-path-anchored regex.

    Semantics:
      *      → any chars except /
      **     → any chars including / (zero or more path segments)
      ?      → single char except /
      [...]  → char class (passed through to regex)
      others → literal (regex special chars escaped)
    """
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # ** — match across path segments. `**/` consumes one or more dirs (or zero).
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:[^/]+/)*")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c == "[":
            # Pass char class through. Find matching ].
            j = i + 1
            if j < n and pattern[j] == "!":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j < n:
                out.append(pattern[i : j + 1])
                i = j + 1
                continue
            # No closing bracket — treat as literal.
            out.append(r"\[")
            i += 1
            continue
        if c in ".+(){}|^$\\":
            out.append("\\" + c)
            i += 1
            continue
        # / and ordinary chars are literal.
        out.append(c)
        i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass
class Verdict:
    path: str
    classification: str  # exception | allow | review | deny | default_deny
    matched_pattern: str | None = None


class WhitelistChecker:
    def __init__(self, config: dict) -> None:
        self.allow = [(p, glob_to_regex(p)) for p in config.get("allow", []) or []]
        self.review = [(p, glob_to_regex(p)) for p in config.get("review_required", []) or []]
        self.deny = [(p, glob_to_regex(p)) for p in config.get("deny", []) or []]

    @staticmethod
    def _first_match(path: str, patterns: list[tuple[str, re.Pattern[str]]]) -> str | None:
        for pat, rx in patterns:
            if rx.match(path):
                return pat
        return None

    def check(self, path: str, exceptions: set[str]) -> Verdict:
        if path in exceptions:
            return Verdict(path, "exception", path)
        if (pat := self._first_match(path, self.deny)) is not None:
            return Verdict(path, "deny", pat)
        if (pat := self._first_match(path, self.review)) is not None:
            return Verdict(path, "review", pat)
        if (pat := self._first_match(path, self.allow)) is not None:
            return Verdict(path, "allow", pat)
        return Verdict(path, "default_deny", None)


def load_whitelist(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"whitelist not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def collect_paths(args: argparse.Namespace) -> list[str]:
    if args.path:
        return [p.strip() for p in args.path if p.strip()]
    if args.paths_file:
        return [
            line.strip()
            for line in Path(args.paths_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    # default: read from stdin
    return [line.strip() for line in sys.stdin if line.strip()]


PREFIX = {
    "exception": "EXCEPT",
    "allow": "ALLOW ",
    "review": "REVIEW",
    "deny": "DENY  ",
    "default_deny": "DENY  ",
}


def render(verdicts: Iterable[Verdict]) -> str:
    lines = []
    for v in verdicts:
        suffix = "" if v.matched_pattern is None else f"  [matched: {v.matched_pattern}]"
        if v.classification == "default_deny":
            suffix = "  [no whitelist rule]"
        lines.append(f"  {PREFIX[v.classification]}  {v.path}{suffix}")
    return "\n".join(lines)


def run(
    paths: list[str],
    exceptions: set[str],
    whitelist_path: Path,
) -> tuple[int, list[Verdict]]:
    config = load_whitelist(whitelist_path)
    checker = WhitelistChecker(config)
    verdicts = [checker.check(p, exceptions) for p in paths]

    violations = [v for v in verdicts if v.classification in ("deny", "default_deny")]
    return (1 if violations else 0), verdicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_changed_paths",
        description="Path whitelist enforcement (防护 0.1).",
    )
    parser.add_argument(
        "--whitelist",
        type=Path,
        default=DEFAULT_WHITELIST,
        help=f"Whitelist YAML (default: {DEFAULT_WHITELIST.name})",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Add a path to check (repeatable). Overrides stdin / --paths-file.",
    )
    parser.add_argument(
        "--paths-file",
        type=Path,
        help="Read paths from a file (one per line). Overrides stdin.",
    )
    parser.add_argument(
        "--exception",
        action="append",
        default=[],
        help="A path explicitly allowed by task path_exception (repeatable).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print on violation.",
    )
    args = parser.parse_args(argv)

    try:
        paths = collect_paths(args)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not paths:
        print("no paths to check", file=sys.stderr)
        return 0

    try:
        exit_code, verdicts = run(paths, set(args.exception), args.whitelist)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    violations = [v for v in verdicts if v.classification in ("deny", "default_deny")]
    review = [v for v in verdicts if v.classification == "review"]

    if not args.quiet or violations:
        print(render(verdicts))

    if violations:
        print(
            f"\n{len(violations)} path violation(s) — see DENY lines above.",
            file=sys.stderr,
        )
    if review:
        print(
            f"{len(review)} path(s) need human review (label: needs-human-review).",
            file=sys.stderr,
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
