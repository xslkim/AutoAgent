"""TASK-0407: In-process TreeCache stress test (no engine required).

Generates synthetic node trees of varying sizes and measures store/diff
latency.  Runs on GitHub-hosted runners.
"""

from __future__ import annotations

import random
import time

import pytest

from autoagent_mcp.tree_cache import TreeCache, reset_tree_cache


def _make_node(nid: str) -> dict:
    return {
        "id": nid,
        "type": "Button",
        "engine_type": "UnityEngine.UI.Button",
        "parent_id": None,
        "children_ids": [],
        "stable_id_source": "hash",
        "visual": {
            "position": [random.randint(0, 1920), random.randint(0, 1080)],
            "size": [100, 40],
            "anchor": [0.5, 0.5],
            "visible": True,
            "alpha": 1.0,
            "color": "#FFFFFFFF",
        },
        "behavior": {
            "interactable": True,
            "raycast_target": True,
            "event_handlers": ["onClick"],
        },
    }


def _make_tree(count: int) -> list[dict]:
    return [_make_node(f"node_{i:04d}") for i in range(count)]


class TestTreeCacheStress:
    """Performance benchmarks for TreeCache at scale."""

    @pytest.mark.parametrize("count", [10, 100, 500, 1000])
    def test_store_latency(self, count: int):
        reset_tree_cache()
        cache = TreeCache()
        nodes = _make_tree(count)

        t0 = time.perf_counter()
        snap_id = cache.store(nodes)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert len(snap_id) == 8
        assert elapsed_ms < 100, f"store({count}) took {elapsed_ms:.1f} ms (limit: 100 ms)"

    @pytest.mark.parametrize("count", [10, 100, 500, 1000])
    def test_diff_latency_identical(self, count: int):
        reset_tree_cache()
        cache = TreeCache()
        nodes = _make_tree(count)
        snap_id = cache.store(nodes)

        t0 = time.perf_counter()
        result = cache.diff(snap_id, nodes)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert not result.full_snapshot
        assert result.changed == []
        assert result.unchanged_count == count
        assert elapsed_ms < 100, f"diff({count}) took {elapsed_ms:.1f} ms (limit: 100 ms)"

    @pytest.mark.parametrize("count", [10, 100, 500, 1000])
    def test_diff_latency_half_changed(self, count: int):
        reset_tree_cache()
        cache = TreeCache()
        nodes = _make_tree(count)
        snap_id = cache.store(nodes)

        # Modify half the nodes.
        modified = list(nodes)
        for i in range(0, count, 2):
            m = dict(modified[i])
            m["visual"] = dict(m["visual"])
            m["visual"]["position"] = [999, 999]
            modified[i] = m

        t0 = time.perf_counter()
        result = cache.diff(snap_id, modified)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert not result.full_snapshot
        assert len(result.changed) == count // 2
        assert elapsed_ms < 100, f"diff({count}/half) took {elapsed_ms:.1f} ms (limit: 100 ms)"

    def test_snapshot_chain_1000(self):
        """Simulate 100 sequential dump_tree_delta calls on a 1000-node tree."""
        reset_tree_cache()
        cache = TreeCache()
        nodes = _make_tree(1000)
        snap_id: str | None = None
        latencies: list[float] = []

        for i in range(100):
            # Randomly tweak a few nodes each round.
            tweaked = list(nodes)
            for _ in range(random.randint(1, 5)):
                idx = random.randint(0, 999)
                m = dict(tweaked[idx])
                m["visual"] = dict(m["visual"])
                m["visual"]["alpha"] = random.random()
                tweaked[idx] = m

            t0 = time.perf_counter()
            if snap_id is None:
                snap_id = cache.store(tweaked)
            else:
                result = cache.diff(snap_id, tweaked)
                snap_id = result.snapshot_id
            latencies.append((time.perf_counter() - t0) * 1000)

        p50 = sorted(latencies)[len(latencies) // 2]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p50 < 50, f"snapshot chain p50={p50:.1f} ms (limit: 50 ms)"
        assert p95 < 100, f"snapshot chain p95={p95:.1f} ms (limit: 100 ms)"
