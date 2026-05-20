"""TASK-0123: visual comparison MCP tools tests.

Tests for save_baseline, compare_to_baseline, list_baselines_tool,
and delete_baseline_tool.  All baseline I/O is redirected to a tmp_path
directory via the baseline_dir helper so we never touch ~/.autoagent/baselines.

Also covers the baseline.py storage-layer helpers directly.
"""

from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
from skimage import io as skio

from autoagent_mcp.server import build_server
from autoagent_mcp.vision.baseline import (
    baseline_path,
    delete_baseline,
    list_baselines,
    load_baseline_path,
    save_baseline,
)
from autoagent_mcp.vision.ssim import compare_images


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def solid_png(tmp_path: Path, name: str, color: tuple, size: int = 64) -> Path:
    """Create a solid-color PNG in tmp_path and return its path."""
    arr = np.full((size, size, 3), color, dtype=np.uint8)
    p = tmp_path / name
    skio.imsave(str(p), arr, check_contrast=False)
    return p


def _result(tool_result) -> dict:
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    return tool_result


# ---------------------------------------------------------------------------
# baseline.py storage layer
# ---------------------------------------------------------------------------


class TestBaselineStorage:
    def test_baseline_path_returns_png(self, tmp_path):
        p = baseline_path("login", baseline_dir=tmp_path)
        assert p.suffix == ".png"
        assert p.stem == "login"

    def test_baseline_path_sanitises_slashes(self, tmp_path):
        p = baseline_path("a/b/c", baseline_dir=tmp_path)
        assert "/" not in p.stem

    def test_baseline_path_invalid_name_raises(self, tmp_path):
        with pytest.raises(ValueError):
            baseline_path("", baseline_dir=tmp_path)

    def test_save_baseline_copies_file(self, tmp_path):
        src = solid_png(tmp_path, "src.png", (200, 100, 50))
        dest = save_baseline("test_bl", src, baseline_dir=tmp_path)
        assert dest.exists()

    def test_save_baseline_returns_path(self, tmp_path):
        src = solid_png(tmp_path, "src.png", (0, 0, 0))
        result = save_baseline("foo", src, baseline_dir=tmp_path)
        assert isinstance(result, Path)

    def test_save_baseline_missing_source_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            save_baseline("bl", tmp_path / "no.png", baseline_dir=tmp_path)

    def test_save_baseline_overwrite_true_replaces(self, tmp_path):
        src1 = solid_png(tmp_path, "s1.png", (255, 0, 0))
        src2 = solid_png(tmp_path, "s2.png", (0, 255, 0))
        save_baseline("over", src1, baseline_dir=tmp_path)
        save_baseline("over", src2, baseline_dir=tmp_path, overwrite=True)
        # Should not raise
        assert load_baseline_path("over", baseline_dir=tmp_path).exists()

    def test_save_baseline_overwrite_false_raises(self, tmp_path):
        src = solid_png(tmp_path, "src.png", (0, 0, 255))
        save_baseline("noover", src, baseline_dir=tmp_path)
        with pytest.raises(FileExistsError):
            save_baseline("noover", src, baseline_dir=tmp_path, overwrite=False)

    def test_load_baseline_path_returns_path(self, tmp_path):
        src = solid_png(tmp_path, "src.png", (1, 2, 3))
        save_baseline("ex", src, baseline_dir=tmp_path)
        p = load_baseline_path("ex", baseline_dir=tmp_path)
        assert p.exists()

    def test_load_baseline_path_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="save_baseline"):
            load_baseline_path("nope", baseline_dir=tmp_path)

    def test_list_baselines_empty_dir(self, tmp_path):
        names = list_baselines(baseline_dir=tmp_path / "empty")
        assert names == []

    def test_list_baselines_returns_names(self, tmp_path):
        bl_dir = tmp_path / "baselines"
        for color, name in [((1, 0, 0), "a"), ((0, 1, 0), "b"), ((0, 0, 1), "c")]:
            src = solid_png(tmp_path, f"src_{name}.png", color)
            save_baseline(name, src, baseline_dir=bl_dir)
        names = list_baselines(baseline_dir=bl_dir)
        assert set(names) == {"a", "b", "c"}

    def test_list_baselines_sorted(self, tmp_path):
        bl_dir = tmp_path / "baselines"
        for n in ["z", "a", "m"]:
            src = solid_png(tmp_path, f"src_{n}.png", (0, 0, 0))
            save_baseline(n, src, baseline_dir=bl_dir)
        assert list_baselines(baseline_dir=bl_dir) == ["a", "m", "z"]

    def test_delete_baseline_existing(self, tmp_path):
        src = solid_png(tmp_path, "src.png", (10, 10, 10))
        save_baseline("del_me", src, baseline_dir=tmp_path)
        removed = delete_baseline("del_me", baseline_dir=tmp_path)
        assert removed is True

    def test_delete_baseline_nonexistent(self, tmp_path):
        removed = delete_baseline("ghost", baseline_dir=tmp_path)
        assert removed is False

    def test_delete_baseline_removes_file(self, tmp_path):
        src = solid_png(tmp_path, "src.png", (5, 5, 5))
        save_baseline("gone", src, baseline_dir=tmp_path)
        delete_baseline("gone", baseline_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            load_baseline_path("gone", baseline_dir=tmp_path)


# ---------------------------------------------------------------------------
# MCP tool layer — save_baseline
# ---------------------------------------------------------------------------


class TestSaveBaselineTool:
    @pytest.mark.asyncio
    async def test_save_baseline_success(self, tmp_path, monkeypatch):
        src = solid_png(tmp_path, "shot.png", (100, 200, 50))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        result = _result(await mcp.call_tool("save_baseline", {"name": "home", "path": str(src)}))
        assert result["saved"] is True
        assert result["name"] == "home"
        assert "baseline_path" in result

    @pytest.mark.asyncio
    async def test_save_baseline_missing_source(self, tmp_path, monkeypatch):
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "save_baseline",
            {"name": "x", "path": str(tmp_path / "no.png")},
        ))
        assert result["saved"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_save_baseline_invalid_name(self, tmp_path, monkeypatch):
        src = solid_png(tmp_path, "src.png", (0, 0, 0))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "save_baseline",
            {"name": "", "path": str(src)},
        ))
        assert result["saved"] is False


# ---------------------------------------------------------------------------
# MCP tool layer — compare_to_baseline
# ---------------------------------------------------------------------------


class TestCompareToBaselineTool:
    @pytest.mark.asyncio
    async def test_identical_images_score_one(self, tmp_path, monkeypatch):
        img = solid_png(tmp_path, "img.png", (128, 128, 128))
        _patch_baseline_dir(monkeypatch, tmp_path)
        # Save baseline
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "same", "path": str(img)})
        # Compare against itself
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "same", "current_path": str(img)},
        ))
        assert result["score"] == pytest.approx(1.0, abs=1e-4)
        assert result["identical"] is True
        assert result["changed_regions"] == []

    @pytest.mark.asyncio
    async def test_different_images_not_identical(self, tmp_path, monkeypatch):
        baseline_img = solid_png(tmp_path, "base.png", (0, 0, 0))
        current_img = solid_png(tmp_path, "curr.png", (255, 255, 255))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "diff", "path": str(baseline_img)})
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "diff", "current_path": str(current_img)},
        ))
        assert result["score"] < 0.5
        assert result["identical"] is False

    @pytest.mark.asyncio
    async def test_missing_baseline_returns_error(self, tmp_path, monkeypatch):
        img = solid_png(tmp_path, "img.png", (0, 0, 0))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "nonexistent", "current_path": str(img)},
        ))
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_current_returns_error(self, tmp_path, monkeypatch):
        img = solid_png(tmp_path, "base.png", (50, 50, 50))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "bl", "path": str(img)})
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "bl", "current_path": str(tmp_path / "no.png")},
        ))
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_save_diff_path_written(self, tmp_path, monkeypatch):
        a = solid_png(tmp_path, "a.png", (0, 0, 0))
        b = solid_png(tmp_path, "b.png", (255, 255, 255))
        diff_path = tmp_path / "diff.png"
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "dd", "path": str(a)})
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "dd", "current_path": str(b), "save_diff": str(diff_path)},
        ))
        assert diff_path.exists()
        assert result["diff_path"] == str(diff_path)

    @pytest.mark.asyncio
    async def test_result_contains_paths(self, tmp_path, monkeypatch):
        img = solid_png(tmp_path, "img.png", (80, 80, 80))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "paths", "path": str(img)})
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "paths", "current_path": str(img)},
        ))
        assert "baseline_path" in result
        assert "current_path" in result

    @pytest.mark.asyncio
    async def test_threshold_parameter_respected(self, tmp_path, monkeypatch):
        """threshold=0.0 → always identical; threshold=1.1 → never identical."""
        img = solid_png(tmp_path, "img.png", (100, 100, 100))
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "thr", "path": str(img)})
        r_low = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "thr", "current_path": str(img), "threshold": 0.0},
        ))
        r_high = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "thr", "current_path": str(img), "threshold": 1.1},
        ))
        assert r_low["identical"] is True
        assert r_high["identical"] is False

    @pytest.mark.asyncio
    async def test_changed_regions_list_of_dicts(self, tmp_path, monkeypatch):
        base = np.zeros((64, 64, 3), dtype=np.uint8)
        curr = base.copy()
        curr[10:30, 10:30] = 255
        bp = tmp_path / "base.png"
        cp = tmp_path / "curr.png"
        skio.imsave(str(bp), base, check_contrast=False)
        skio.imsave(str(cp), curr, check_contrast=False)
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "chg", "path": str(bp)})
        result = _result(await mcp.call_tool(
            "compare_to_baseline",
            {"name": "chg", "current_path": str(cp)},
        ))
        assert isinstance(result["changed_regions"], list)
        assert len(result["changed_regions"]) >= 1
        r = result["changed_regions"][0]
        assert {"x", "y", "width", "height"} <= r.keys()


# ---------------------------------------------------------------------------
# MCP tool layer — list_baselines_tool
# ---------------------------------------------------------------------------


class TestListBaselinesTool:
    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self, tmp_path, monkeypatch):
        _patch_baseline_dir(monkeypatch, tmp_path / "empty")
        mcp = build_server()
        result = _result(await mcp.call_tool("list_baselines_tool", {}))
        assert result["baselines"] == []

    @pytest.mark.asyncio
    async def test_saved_baselines_appear(self, tmp_path, monkeypatch):
        bl_dir = tmp_path / "baselines"
        _patch_baseline_dir(monkeypatch, bl_dir)
        mcp = build_server()
        for name in ["alpha", "beta"]:
            src = solid_png(tmp_path, f"src_{name}.png", (0, 0, 0))
            await mcp.call_tool("save_baseline", {"name": name, "path": str(src)})
        result = _result(await mcp.call_tool("list_baselines_tool", {}))
        assert set(result["baselines"]) == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# MCP tool layer — delete_baseline_tool
# ---------------------------------------------------------------------------


class TestDeleteBaselineTool:
    @pytest.mark.asyncio
    async def test_delete_existing(self, tmp_path, monkeypatch):
        _patch_baseline_dir(monkeypatch, tmp_path)
        src = solid_png(tmp_path, "src.png", (9, 9, 9))
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "rm", "path": str(src)})
        result = _result(await mcp.call_tool("delete_baseline_tool", {"name": "rm"}))
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_path, monkeypatch):
        _patch_baseline_dir(monkeypatch, tmp_path)
        mcp = build_server()
        result = _result(await mcp.call_tool("delete_baseline_tool", {"name": "ghost"}))
        assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, tmp_path, monkeypatch):
        _patch_baseline_dir(monkeypatch, tmp_path)
        src = solid_png(tmp_path, "src.png", (3, 3, 3))
        mcp = build_server()
        await mcp.call_tool("save_baseline", {"name": "gone", "path": str(src)})
        await mcp.call_tool("delete_baseline_tool", {"name": "gone"})
        result = _result(await mcp.call_tool("list_baselines_tool", {}))
        assert "gone" not in result["baselines"]


# ---------------------------------------------------------------------------
# Helper: monkeypatch DEFAULT_BASELINE_DIR in both modules
# ---------------------------------------------------------------------------


def _patch_baseline_dir(monkeypatch, dir_: Path) -> None:
    """Redirect all baseline storage to *dir_* for the duration of the test."""
    import autoagent_mcp.vision.baseline as _bl_mod
    import autoagent_mcp.tools.visual as _vt_mod

    monkeypatch.setattr(_bl_mod, "DEFAULT_BASELINE_DIR", dir_)
    # The tool module imports helpers from baseline, so we patch the references
    # those imports captured:
    monkeypatch.setattr(_vt_mod, "list_baselines", lambda: _bl_mod.list_baselines(baseline_dir=dir_))
    monkeypatch.setattr(_vt_mod, "delete_baseline", lambda name: _bl_mod.delete_baseline(name, baseline_dir=dir_))
    monkeypatch.setattr(
        _vt_mod,
        "load_baseline_path",
        lambda name: _bl_mod.load_baseline_path(name, baseline_dir=dir_),
    )
    monkeypatch.setattr(
        _vt_mod,
        "_save_baseline",
        lambda name, path, **kw: _bl_mod.save_baseline(name, path, baseline_dir=dir_, **kw),
    )
