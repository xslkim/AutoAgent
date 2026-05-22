"""TASK-0405C: TreeCache and dump_tree_delta tests.

All tests are pure Python — no engine connection required.
The MCP tool tests mock get_client() to return preset node lists.

Coverage:
TreeCache.store()
  - returns an 8-char hex snapshot_id
  - successive stores return different IDs
  - evicts oldest when max_snapshots exceeded
  - nodes without 'id' are silently skipped

TreeCache.diff()
  - unknown since_id → full_snapshot=True, all nodes in changed
  - expired snapshot → full_snapshot=True
  - identical nodes → changed=[], removed_ids=[], unchanged_count=N
  - added node → appears in changed
  - modified node → appears in changed
  - removed node → appears in removed_ids
  - unchanged nodes counted correctly
  - diff stores new snapshot (returned snapshot_id is usable for next diff)

DeltaResult fields
  - correct types and defaults

reset_tree_cache()
  - clears all snapshots

dump_tree_delta MCP tool
  - since=None → full_snapshot=True, all nodes returned
  - since=<id> → delta nodes only
  - snapshot_id in response is usable for a second delta call
  - include_invisible=False filters invisible nodes
  - full_snapshot=True when since_id not found
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoagent_mcp.tree_cache import (
    DeltaResult,
    TreeCache,
    get_tree_cache,
    reset_tree_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(nid: str, text: str = "x", visible: bool = True) -> dict:
    return {
        "id": nid,
        "type": "Button",
        "visual": {"visible": visible, "position": [0, 0]},
        "text": text,
    }


def _nodes(*ids: str) -> list[dict]:
    return [_node(nid) for nid in ids]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset():
    """Ensure module-level cache is clean before each test."""
    reset_tree_cache()
    yield
    reset_tree_cache()


@pytest.fixture()
def cache():
    return TreeCache(max_snapshots=5)


# ---------------------------------------------------------------------------
# TreeCache.store()
# ---------------------------------------------------------------------------


class TestStore:
    def test_returns_8_char_hex(self, cache):
        sid = cache.store(_nodes("a", "b"))
        assert len(sid) == 8
        assert all(c in "0123456789abcdef" for c in sid)

    def test_successive_ids_differ(self, cache):
        ids = {cache.store(_nodes("a")) for _ in range(10)}
        assert len(ids) > 1  # extremely unlikely to collide with 4-byte entropy

    def test_snapshot_count_increments(self, cache):
        assert cache.snapshot_count() == 0
        cache.store(_nodes("a"))
        assert cache.snapshot_count() == 1
        cache.store(_nodes("b"))
        assert cache.snapshot_count() == 2

    def test_evicts_oldest_on_overflow(self):
        cache = TreeCache(max_snapshots=3)
        ids = [cache.store(_nodes(f"n{i}")) for i in range(4)]
        # Only the 3 newest should survive
        assert cache.snapshot_count() == 3
        # The first ID is evicted → diff returns full_snapshot
        delta = cache.diff(ids[0], _nodes("x"))
        assert delta.full_snapshot is True

    def test_nodes_without_id_skipped(self, cache):
        nodes = [{"type": "Button"}, _node("has_id")]  # first has no 'id'
        sid = cache.store(nodes)
        # Should not raise; the node without 'id' is silently ignored
        assert len(sid) == 8

    def test_empty_node_list(self, cache):
        sid = cache.store([])
        assert len(sid) == 8


# ---------------------------------------------------------------------------
# TreeCache.diff() — unknown / expired baseline
# ---------------------------------------------------------------------------


class TestDiffUnknownBaseline:
    def test_unknown_id_full_snapshot(self, cache):
        nodes = _nodes("a", "b")
        delta = cache.diff("deadbeef", nodes)
        assert delta.full_snapshot is True

    def test_unknown_id_all_nodes_in_changed(self, cache):
        nodes = _nodes("a", "b", "c")
        delta = cache.diff("deadbeef", nodes)
        assert len(delta.changed) == len(nodes)

    def test_unknown_id_removed_ids_empty(self, cache):
        delta = cache.diff("deadbeef", _nodes("a"))
        assert delta.removed_ids == []

    def test_unknown_id_stores_new_snapshot(self, cache):
        delta = cache.diff("deadbeef", _nodes("a"))
        # New snapshot should be usable for a subsequent diff
        delta2 = cache.diff(delta.snapshot_id, _nodes("a"))
        assert delta2.full_snapshot is False


# ---------------------------------------------------------------------------
# TreeCache.diff() — happy path
# ---------------------------------------------------------------------------


class TestDiffDelta:
    def test_identical_nodes_no_changes(self, cache):
        nodes = _nodes("a", "b", "c")
        sid = cache.store(nodes)
        delta = cache.diff(sid, nodes)
        assert delta.changed == []
        assert delta.removed_ids == []
        assert delta.unchanged_count == 3
        assert delta.full_snapshot is False

    def test_added_node_appears_in_changed(self, cache):
        sid = cache.store(_nodes("a", "b"))
        delta = cache.diff(sid, _nodes("a", "b", "c"))
        ids = [n["id"] for n in delta.changed]
        assert "c" in ids
        assert len(delta.changed) == 1

    def test_removed_node_appears_in_removed_ids(self, cache):
        sid = cache.store(_nodes("a", "b", "c"))
        delta = cache.diff(sid, _nodes("a", "b"))
        assert "c" in delta.removed_ids
        assert len(delta.removed_ids) == 1

    def test_modified_node_appears_in_changed(self, cache):
        sid = cache.store([_node("a", text="before")])
        delta = cache.diff(sid, [_node("a", text="after")])
        assert len(delta.changed) == 1
        assert delta.changed[0]["id"] == "a"
        assert delta.removed_ids == []

    def test_unchanged_count_correct(self, cache):
        nodes = _nodes("a", "b", "c", "d")
        sid = cache.store(nodes)
        new_nodes = [*_nodes("a", "b", "c"), _node("d", text="changed")]
        delta = cache.diff(sid, new_nodes)
        assert delta.unchanged_count == 3
        assert len(delta.changed) == 1

    def test_full_snapshot_false_on_valid_baseline(self, cache):
        sid = cache.store(_nodes("a"))
        delta = cache.diff(sid, _nodes("a"))
        assert delta.full_snapshot is False

    def test_new_snapshot_id_different_from_baseline(self, cache):
        sid = cache.store(_nodes("a"))
        delta = cache.diff(sid, _nodes("a"))
        assert delta.snapshot_id != sid

    def test_chained_diffs(self, cache):
        """Three consecutive diffs each track changes correctly."""
        sid1 = cache.store(_nodes("a", "b"))
        delta1 = cache.diff(sid1, _nodes("a", "b", "c"))  # added c
        assert any(n["id"] == "c" for n in delta1.changed)

        delta2 = cache.diff(delta1.snapshot_id, _nodes("a", "c"))  # removed b
        assert "b" in delta2.removed_ids
        assert delta2.changed == []

    def test_add_remove_same_call(self, cache):
        sid = cache.store(_nodes("a", "b"))
        delta = cache.diff(sid, _nodes("a", "c"))  # removed b, added c
        assert "b" in delta.removed_ids
        assert any(n["id"] == "c" for n in delta.changed)
        assert delta.unchanged_count == 1  # "a" unchanged


# ---------------------------------------------------------------------------
# DeltaResult
# ---------------------------------------------------------------------------


class TestDeltaResult:
    def test_default_fields(self):
        dr = DeltaResult(snapshot_id="abc")
        assert dr.changed == []
        assert dr.removed_ids == []
        assert dr.unchanged_count == 0
        assert dr.full_snapshot is False

    def test_explicit_fields(self):
        dr = DeltaResult(
            snapshot_id="x",
            changed=[{"id": "a"}],
            removed_ids=["b"],
            unchanged_count=5,
            full_snapshot=True,
        )
        assert dr.snapshot_id == "x"
        assert len(dr.changed) == 1
        assert dr.removed_ids == ["b"]
        assert dr.unchanged_count == 5
        assert dr.full_snapshot is True


# ---------------------------------------------------------------------------
# reset_tree_cache()
# ---------------------------------------------------------------------------


class TestResetTreeCache:
    def test_clears_all_snapshots(self):
        cache = get_tree_cache()
        cache.store(_nodes("a", "b"))
        cache.store(_nodes("c"))
        assert cache.snapshot_count() == 2
        reset_tree_cache()
        assert cache.snapshot_count() == 0

    def test_after_reset_since_id_unknown(self):
        cache = get_tree_cache()
        sid = cache.store(_nodes("a"))
        reset_tree_cache()
        delta = cache.diff(sid, _nodes("a"))
        assert delta.full_snapshot is True


# ---------------------------------------------------------------------------
# dump_tree_delta MCP tool
# ---------------------------------------------------------------------------


def _make_client(nodes: list[dict]) -> MagicMock:
    client = MagicMock()
    client.call = AsyncMock(return_value=nodes)
    return client


class TestDumpTreeDeltaTool:
    @pytest.mark.asyncio
    async def test_first_call_full_snapshot(self):
        from autoagent_mcp.server import build_server

        nodes = _nodes("btn1", "btn2", "txt1")
        with patch("autoagent_mcp.tools.dump.get_client", return_value=_make_client(nodes)):
            mcp = build_server()
            result = await mcp.call_tool("dump_tree_delta", {})

        data = result[1] if isinstance(result, tuple) else result
        assert data["full_snapshot"] is True
        assert len(data["nodes"]) == 3
        assert len(data["snapshot_id"]) == 8
        assert data["removed_ids"] == []
        assert data["unchanged_count"] == 0

    @pytest.mark.asyncio
    async def test_delta_returns_only_changed(self):
        from autoagent_mcp.server import build_server

        base_nodes  = _nodes("a", "b", "c")
        delta_nodes = [*_nodes("a", "c"), _node("d")]  # removed b, added d

        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(base_nodes)):
            mcp = build_server()
            r1 = await mcp.call_tool("dump_tree_delta", {})

        d1 = r1[1] if isinstance(r1, tuple) else r1
        snap_id = d1["snapshot_id"]

        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(delta_nodes)):
            r2 = await mcp.call_tool("dump_tree_delta", {"since": snap_id})

        d2 = r2[1] if isinstance(r2, tuple) else r2
        assert d2["full_snapshot"] is False
        changed_ids = {n["id"] for n in d2["nodes"]}
        assert "d" in changed_ids       # newly added
        assert "a" not in changed_ids   # unchanged
        assert "c" not in changed_ids   # unchanged
        assert "b" in d2["removed_ids"]
        assert d2["unchanged_count"] == 2

    @pytest.mark.asyncio
    async def test_expired_snapshot_falls_back_to_full(self):
        from autoagent_mcp.server import build_server

        nodes = _nodes("x")
        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(nodes)):
            mcp = build_server()
            result = await mcp.call_tool(
                "dump_tree_delta", {"since": "00000000"}  # unknown id
            )

        data = result[1] if isinstance(result, tuple) else result
        assert data["full_snapshot"] is True
        assert len(data["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_include_invisible_false_filters(self):
        from autoagent_mcp.server import build_server

        nodes = [_node("vis"), _node("invis", visible=False)]
        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(nodes)):
            mcp = build_server()
            result = await mcp.call_tool(
                "dump_tree_delta", {"include_invisible": False}
            )

        data = result[1] if isinstance(result, tuple) else result
        ids = [n["id"] for n in data["nodes"]]
        assert "vis" in ids
        assert "invis" not in ids

    @pytest.mark.asyncio
    async def test_snapshot_id_usable_for_next_call(self):
        """snapshot_id from response can be passed as `since` on the next call."""
        from autoagent_mcp.server import build_server

        nodes = _nodes("a", "b")
        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(nodes)):
            mcp = build_server()
            r1 = await mcp.call_tool("dump_tree_delta", {})
            d1 = r1[1] if isinstance(r1, tuple) else r1

        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(nodes)):
            r2 = await mcp.call_tool(
                "dump_tree_delta", {"since": d1["snapshot_id"]}
            )
            d2 = r2[1] if isinstance(r2, tuple) else r2

        assert d2["full_snapshot"] is False
        assert d2["nodes"] == []          # nothing changed
        assert d2["unchanged_count"] == 2

    @pytest.mark.asyncio
    async def test_captured_at_is_float(self):
        from autoagent_mcp.server import build_server

        with patch("autoagent_mcp.tools.dump.get_client",
                   return_value=_make_client(_nodes("a"))):
            mcp = build_server()
            result = await mcp.call_tool("dump_tree_delta", {})

        data = result[1] if isinstance(result, tuple) else result
        assert isinstance(data["captured_at"], float)
