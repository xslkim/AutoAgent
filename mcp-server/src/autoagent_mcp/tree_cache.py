"""In-memory snapshot cache for UI tree delta comparisons (TASK-0405C).

:class:`TreeCache` stores numbered snapshots of ``dump_tree`` results and
computes diffs between them so :func:`dump_tree_delta` can return only the
nodes that changed since a previous call.

Why not store raw engine output?
    The cache operates on the *filtered* node list that the agent already
    sees (after ``include_invisible`` / ``max_depth`` are applied), so the
    delta is always meaningful from the agent's perspective.

Snapshot IDs
    8-character hex strings (4 bytes of randomness).  They are opaque — the
    agent passes them back as-is.  If a snapshot has been evicted (the cache
    holds at most *max_snapshots* entries, oldest evicted first), the delta
    call falls back to returning the full tree.

Thread safety
    All mutations are protected by a :class:`threading.Lock`.

Usage::

    from autoagent_mcp.tree_cache import get_tree_cache, reset_tree_cache

    cache = get_tree_cache()
    snap_id = cache.store(nodes)           # returns "a1b2c3d4"
    delta   = cache.diff(snap_id, nodes2)  # DeltaResult or None
"""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass, field

# Maximum number of snapshots kept in memory.  Oldest entry is evicted when
# the limit is exceeded.
_DEFAULT_MAX_SNAPSHOTS: int = 20


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class DeltaResult:
    """Result of :meth:`TreeCache.diff`.

    Attributes:
        snapshot_id:     ID of the *new* snapshot (use for the next delta call).
        changed:         Nodes that were **added or modified** since the baseline
                         (full node data, same schema as ``dump_tree`` nodes).
        removed_ids:     IDs that were present in the baseline but are gone now.
        unchanged_count: Number of nodes that did not change (informational).
        full_snapshot:   ``True`` when the baseline snapshot was not found and
                         the result contains the complete tree instead of a diff.
    """

    snapshot_id: str
    changed: list[dict] = field(default_factory=list)
    removed_ids: list[str] = field(default_factory=list)
    unchanged_count: int = 0
    full_snapshot: bool = False


# ---------------------------------------------------------------------------
# Cache implementation
# ---------------------------------------------------------------------------


class TreeCache:
    """Snapshot store with LRU eviction.

    Args:
        max_snapshots: Maximum number of snapshots to keep (default 20).
    """

    def __init__(self, max_snapshots: int = _DEFAULT_MAX_SNAPSHOTS) -> None:
        self._max = max_snapshots
        self._lock = threading.Lock()
        # snapshot_id → {node_id: canonical_json}
        self._snapshots: dict[str, dict[str, str]] = {}
        self._order: list[str] = []  # insertion order for eviction

    # ---- public API -------------------------------------------------------

    def store(self, nodes: list[dict]) -> str:
        """Persist *nodes* as a new snapshot and return its ID."""
        snap_id = secrets.token_hex(4)  # 8 hex chars, e.g. "a1b2c3d4"
        mapping = {n["id"]: _canonical(n) for n in nodes if "id" in n}
        with self._lock:
            self._snapshots[snap_id] = mapping
            self._order.append(snap_id)
            self._evict()
        return snap_id

    def diff(self, since_id: str, new_nodes: list[dict]) -> DeltaResult:
        """Compute the delta from snapshot *since_id* to *new_nodes*.

        If *since_id* is unknown (expired or invalid), the result is treated
        as a fresh full snapshot (``full_snapshot=True``).

        Always stores *new_nodes* as a new snapshot and returns its ID.
        """
        with self._lock:
            baseline: dict[str, str] | None = self._snapshots.get(since_id)

        if baseline is None:
            # Baseline expired or never existed — return the full tree.
            new_snap_id = self.store(new_nodes)
            return DeltaResult(
                snapshot_id=new_snap_id,
                changed=list(new_nodes),
                removed_ids=[],
                unchanged_count=0,
                full_snapshot=True,
            )

        # Build new mapping for comparison.
        new_map: dict[str, tuple[dict, str]] = {
            n["id"]: (n, _canonical(n)) for n in new_nodes if "id" in n
        }

        changed: list[dict] = []
        unchanged_count: int = 0
        for node_id, (node, canon) in new_map.items():
            if node_id not in baseline or baseline[node_id] != canon:
                changed.append(node)
            else:
                unchanged_count += 1

        removed_ids = [nid for nid in baseline if nid not in new_map]

        new_snap_id = self.store(new_nodes)
        return DeltaResult(
            snapshot_id=new_snap_id,
            changed=changed,
            removed_ids=removed_ids,
            unchanged_count=unchanged_count,
            full_snapshot=False,
        )

    def clear(self) -> None:
        """Remove all snapshots."""
        with self._lock:
            self._snapshots.clear()
            self._order.clear()

    def snapshot_count(self) -> int:
        """Return the number of snapshots currently stored."""
        with self._lock:
            return len(self._snapshots)

    # ---- private ----------------------------------------------------------

    def _evict(self) -> None:
        """Evict oldest entries until at or below *_max*. Caller holds lock."""
        while len(self._order) > self._max:
            old_id = self._order.pop(0)
            self._snapshots.pop(old_id, None)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _canonical(node: dict) -> str:
    """Return a stable, compact JSON string for node equality comparison."""
    return json.dumps(node, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache = TreeCache()


def get_tree_cache() -> TreeCache:
    """Return the process-level :class:`TreeCache` singleton."""
    return _cache


def reset_tree_cache() -> None:
    """Clear all snapshots (e.g. on engine reconnect or test teardown)."""
    _cache.clear()
