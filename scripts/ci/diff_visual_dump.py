"""Dump-time visual diff — 防护 0.3.

Compares two `dump_tree` payloads captured during an e2e run:
  - before.json: fixture loaded, AI code has NOT yet attached components
  - after.json:  AI's Awake / NativeConstruct / _ready has executed

ANY change in a node's `visual` field is a violation. Authoritative source:
docs/06-visual-regression.md §2.3.

Also flags pinned/auto IDs that disappeared between before/after (orphan check).
hash IDs are ignored — they're noise.

`behavior` and `meta` differences are expected and intentional (that's where
AI lives) and are NOT reported.

Usage::

    python scripts/ci/diff_visual_dump.py before.json after.json
    python scripts/ci/diff_visual_dump.py --before b.json --after a.json --quiet

Each input is either a full dump_tree result (`{"nodes": [...], "captured_at": ...}`)
or a raw node array (`[{...}, {...}]`).

Exit codes:
    0 — no visual diffs and no orphan IDs
    1 — at least one visual diff or orphan
    2 — usage / parse error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Visual fields per docs/01-protocol-spec.md §三 — must stay in sync.
VISUAL_FIELDS: tuple[str, ...] = (
    "position",
    "size",
    "anchor",
    "world_bounds",
    "visible",
    "alpha",
    "color",
    "sprite_ref",
    "z_order",
)

REFERENCEABLE_STABLE_SOURCES = frozenset({"pinned", "auto"})


@dataclass(frozen=True)
class VisualDiff:
    node_id: str
    field: str
    before: Any
    after: Any


@dataclass(frozen=True)
class Orphan:
    node_id: str
    stable_id_source: str


def extract_nodes(payload: Any, source: str) -> list[dict]:
    """Accept full dump_tree result envelope or a raw node array."""
    if isinstance(payload, dict) and "nodes" in payload:
        nodes = payload["nodes"]
    elif isinstance(payload, list):
        nodes = payload
    else:
        raise ValueError(
            f"{source}: expected dump_tree result (dict with 'nodes') or node array, "
            f"got {type(payload).__name__}"
        )
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            raise ValueError(f"{source}: nodes[{i}] is not an object")
        if "id" not in n:
            raise ValueError(f"{source}: nodes[{i}] missing required 'id'")
    return nodes


def diff_visual(before_node: dict, after_node: dict) -> list[VisualDiff]:
    b_vis = before_node.get("visual", {}) or {}
    a_vis = after_node.get("visual", {}) or {}
    # Diff over the union of declared visual keys plus the canonical set, so we
    # catch both "field changed value" and "field added/removed".
    fields = set(VISUAL_FIELDS) | set(b_vis) | set(a_vis)
    diffs: list[VisualDiff] = []
    nid = before_node["id"]
    for field in sorted(fields):
        b_val = b_vis.get(field, _MISSING)
        a_val = a_vis.get(field, _MISSING)
        if b_val == a_val:
            continue
        diffs.append(
            VisualDiff(
                node_id=nid,
                field=field,
                before=None if b_val is _MISSING else b_val,
                after=None if a_val is _MISSING else a_val,
            )
        )
    return diffs


_MISSING = object()


def find_orphans(
    before_by_id: dict[str, dict],
    after_ids: set[str],
) -> list[Orphan]:
    orphans: list[Orphan] = []
    for nid, node in before_by_id.items():
        if nid in after_ids:
            continue
        src = node.get("stable_id_source", "hash")
        if src in REFERENCEABLE_STABLE_SOURCES:
            orphans.append(Orphan(node_id=nid, stable_id_source=src))
    return orphans


def run(
    before_payload: Any,
    after_payload: Any,
    check_orphans: bool = True,
) -> tuple[list[VisualDiff], list[Orphan]]:
    before = extract_nodes(before_payload, "before")
    after = extract_nodes(after_payload, "after")

    before_by_id = {n["id"]: n for n in before}
    after_by_id = {n["id"]: n for n in after}

    diffs: list[VisualDiff] = []
    for nid, b_node in before_by_id.items():
        a_node = after_by_id.get(nid)
        if a_node is None:
            continue  # handled by orphan check below
        diffs.extend(diff_visual(b_node, a_node))

    orphans = (
        find_orphans(before_by_id, set(after_by_id))
        if check_orphans
        else []
    )
    return diffs, orphans


def _format_value(v: Any) -> str:
    if v is None:
        return "(missing)"
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(v)


def render(diffs: Iterable[VisualDiff], orphans: Iterable[Orphan]) -> str:
    lines: list[str] = []
    for d in diffs:
        lines.append(
            f"  diff {d.node_id}.{d.field}: before={_format_value(d.before)} "
            f"after={_format_value(d.after)}"
        )
    for o in orphans:
        lines.append(f"  orphan {o.node_id} (stable_id_source={o.stable_id_source})")
    return "\n".join(lines)


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise FileNotFoundError(f"{path}: not found") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: invalid JSON — {e}") from e


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="diff_visual_dump",
        description="Compare visual fields between two dump_tree snapshots (防护 0.3).",
    )
    parser.add_argument(
        "before",
        nargs="?",
        type=Path,
        help="Path to before.json (dump_tree result captured before AI Awake).",
    )
    parser.add_argument(
        "after",
        nargs="?",
        type=Path,
        help="Path to after.json (dump_tree result captured after AI Awake).",
    )
    parser.add_argument("--before", dest="before_flag", type=Path)
    parser.add_argument("--after", dest="after_flag", type=Path)
    parser.add_argument(
        "--no-orphan-check",
        action="store_true",
        help="Skip the pinned/auto ID orphan check.",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print on violation.")
    args = parser.parse_args(argv)

    before_path = args.before_flag or args.before
    after_path = args.after_flag or args.after
    if before_path is None or after_path is None:
        parser.error("both before and after paths are required")

    try:
        before_payload = _load(before_path)
        after_payload = _load(after_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        diffs, orphans = run(
            before_payload,
            after_payload,
            check_orphans=not args.no_orphan_check,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    has_violation = bool(diffs or orphans)

    if has_violation:
        print(
            f"{len(diffs)} visual diff(s), {len(orphans)} orphan ID(s):",
            file=sys.stderr,
        )
        print(render(diffs, orphans), file=sys.stderr)
    elif not args.quiet:
        print("OK — visual dump unchanged, no orphan IDs", file=sys.stderr)

    return 1 if has_violation else 0


if __name__ == "__main__":
    sys.exit(main())
