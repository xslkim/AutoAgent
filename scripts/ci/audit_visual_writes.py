"""Source diff audit — 防护 0.2 (regex 初版).

Scans changed source files for visual-property writes the AI is not allowed
to perform from code. Authoritative rules live in `visual_write_rules.yml`;
spec at docs/06-visual-regression.md §2.2.

File-level exemption: any source file containing the marker
`AUTOAGENT_ALLOW_VISUAL` within its first 30 lines is skipped entirely (still
logged so PR review can verify the exemption is intentional).

Per-line exemption: a rule may declare `allow_if_line_contains`; if any of
those substrings appear on the same line, the violation is suppressed (used
for state_sprites helpers and similar standardized patterns — see §2.5).

Usage::

    # Scan an explicit file list
    python scripts/ci/audit_visual_writes.py --file path/to/foo.cs --file bar.gd

    # Scan changed files between two refs
    python scripts/ci/audit_visual_writes.py --diff origin/main...HEAD

    # Scan paths from stdin (e.g. piped from git diff --name-only)
    git diff --name-only origin/main...HEAD | python scripts/ci/audit_visual_writes.py

Exit codes:
    0 — no violations
    1 — at least one violation
    2 — usage / config error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


DEFAULT_RULES = Path(__file__).resolve().parent / "visual_write_rules.yml"


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    reason: str
    allow_if_line_contains: tuple[str, ...] = ()


@dataclass(frozen=True)
class LanguageConfig:
    name: str
    extensions: tuple[str, ...]
    line_comment: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Violation:
    path: Path
    line_no: int
    rule_name: str
    line_text: str
    reason: str


@dataclass(frozen=True)
class Exemption:
    path: Path
    marker_line_no: int


class Auditor:
    def __init__(self, config: dict) -> None:
        self.exempt_marker: str = config.get("exempt_marker", "AUTOAGENT_ALLOW_VISUAL")
        self.exempt_max_lines: int = int(config.get("exempt_marker_max_lines", 30))

        languages: list[LanguageConfig] = []
        for name, cfg in (config.get("languages") or {}).items():
            rules = tuple(
                Rule(
                    name=r["name"],
                    pattern=re.compile(r["pattern"]),
                    reason=r.get("reason", ""),
                    allow_if_line_contains=tuple(r.get("allow_if_line_contains") or ()),
                )
                for r in cfg.get("rules") or []
            )
            languages.append(
                LanguageConfig(
                    name=name,
                    extensions=tuple(cfg["extensions"]),
                    line_comment=cfg.get("line_comment", "//"),
                    rules=rules,
                )
            )
        self.languages = languages

    def language_for(self, path: Path) -> LanguageConfig | None:
        suffix = path.suffix.lower()
        for lang in self.languages:
            if suffix in lang.extensions:
                return lang
        return None

    def find_exemption(self, lines: list[str]) -> int | None:
        """Return 1-based line number of the marker if found within the head, else None."""
        for idx, line in enumerate(lines[: self.exempt_max_lines], start=1):
            if self.exempt_marker in line:
                return idx
        return None

    @staticmethod
    def _strip_comment(line: str, line_comment: str) -> str:
        # Naive: strip from the first line-comment marker onwards. Doesn't handle
        # markers inside string literals — acceptable for v0.1 regex audit.
        idx = line.find(line_comment)
        return line if idx < 0 else line[:idx]

    def scan_file(
        self, path: Path, content: str
    ) -> tuple[list[Violation], Exemption | None]:
        lang = self.language_for(path)
        if lang is None:
            return [], None

        lines = content.splitlines()
        exempt_at = self.find_exemption(lines)
        if exempt_at is not None:
            return [], Exemption(path=path, marker_line_no=exempt_at)

        violations: list[Violation] = []
        for line_no, raw_line in enumerate(lines, start=1):
            line = self._strip_comment(raw_line, lang.line_comment)
            if not line.strip():
                continue
            for rule in lang.rules:
                if not rule.pattern.search(line):
                    continue
                if any(s in line for s in rule.allow_if_line_contains):
                    continue
                violations.append(
                    Violation(
                        path=path,
                        line_no=line_no,
                        rule_name=rule.name,
                        line_text=raw_line.rstrip(),
                        reason=rule.reason,
                    )
                )
        return violations, None


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"rules file not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def collect_paths(args: argparse.Namespace) -> list[Path]:
    raw: list[str]
    if args.file:
        raw = list(args.file)
    elif args.diff:
        raw = git_diff_names(args.diff)
    elif args.paths_file:
        raw = [
            line.strip()
            for line in Path(args.paths_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        raw = [line.strip() for line in sys.stdin if line.strip()]
    return [Path(p) for p in raw]


def git_diff_names(ref_spec: str) -> list[str]:
    """Run `git diff --name-only <ref_spec>` and return the file list."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", ref_spec],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git diff failed: {e.stderr.strip()}") from e
    return [line.strip() for line in out.splitlines() if line.strip()]


def filter_existing(paths: Iterable[Path]) -> list[Path]:
    """Drop paths that no longer exist (deleted in PR) or are not files."""
    return [p for p in paths if p.is_file()]


def render_violations(violations: list[Violation]) -> str:
    lines = []
    for v in violations:
        lines.append(
            f"  {v.path}:{v.line_no}: [{v.rule_name}] {v.line_text}\n"
            f"      ↳ {v.reason}"
        )
    return "\n".join(lines)


def render_exemptions(exemptions: list[Exemption]) -> str:
    return "\n".join(
        f"  {e.path}  (AUTOAGENT_ALLOW_VISUAL @ line {e.marker_line_no})" for e in exemptions
    )


def run(
    paths: list[Path],
    rules_path: Path,
    repo_root: Path | None = None,
) -> tuple[int, list[Violation], list[Exemption]]:
    config = load_config(rules_path)
    auditor = Auditor(config)

    violations: list[Violation] = []
    exemptions: list[Exemption] = []

    for path in paths:
        abs_path = path if path.is_absolute() else (repo_root / path if repo_root else path)
        if not abs_path.is_file():
            continue
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        v, exempt = auditor.scan_file(path, content)
        violations.extend(v)
        if exempt is not None:
            exemptions.append(exempt)

    return (1 if violations else 0), violations, exemptions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_visual_writes",
        description="Source-diff visual-write audit (防护 0.2).",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
        help=f"Rules YAML (default: {DEFAULT_RULES.name})",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Add a file path to scan (repeatable).",
    )
    parser.add_argument(
        "--paths-file",
        type=Path,
        help="Read paths from a file (one per line). Overrides stdin.",
    )
    parser.add_argument(
        "--diff",
        help="Git ref-spec, e.g. origin/main...HEAD; runs `git diff --name-only <spec>`.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Resolve relative paths against this root (default: cwd).",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print on violation.")
    args = parser.parse_args(argv)

    try:
        paths = collect_paths(args)
    except (OSError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not paths:
        if not args.quiet:
            print("no files to scan", file=sys.stderr)
        return 0

    try:
        exit_code, violations, exemptions = run(paths, args.rules, args.repo_root)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if exemptions and not args.quiet:
        print(f"{len(exemptions)} file(s) exempted via AUTOAGENT_ALLOW_VISUAL:", file=sys.stderr)
        print(render_exemptions(exemptions), file=sys.stderr)

    if violations:
        print(f"{len(violations)} visual-write violation(s) found:", file=sys.stderr)
        print(render_violations(violations), file=sys.stderr)
    elif not args.quiet:
        print("OK — no visual-write violations", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
