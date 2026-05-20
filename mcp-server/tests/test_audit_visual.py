"""TASK-0125: audit_visual_changes tool tests.

All tests mock the engine client and redirect baseline storage to tmp_path.
"""

from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from skimage import io as skio

from autoagent_mcp.connector import WebSocketClient, set_client
from autoagent_mcp.server import build_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def solid_png(path: Path, color: tuple, size: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.full((size, size, 3), color, dtype=np.uint8)
    skio.imsave(str(path), arr, check_contrast=False)
    return path


def _result(tool_result) -> dict:
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    return tool_result


def _patch(monkeypatch, bl_dir: Path) -> None:
    """Redirect all baseline I/O to bl_dir for the duration of the test."""
    import autoagent_mcp.vision.baseline as _bl
    import autoagent_mcp.tools.audit as _au

    monkeypatch.setattr(_bl, "DEFAULT_BASELINE_DIR", bl_dir)
    monkeypatch.setattr(
        _au, "load_baseline_path",
        lambda name: _bl.load_baseline_path(name, baseline_dir=bl_dir),
    )
    monkeypatch.setattr(
        _au, "save_baseline",
        lambda name, src, **kw: _bl.save_baseline(name, src, baseline_dir=bl_dir, **kw),
    )


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=WebSocketClient)
    client.connected = True
    set_client(client)
    yield client
    set_client(None)


def _wire_returns(mock_client, path: Path):
    """Make the mock engine return *path* for take_screenshot calls."""
    async def _call(method, params):
        if method == "take_screenshot":
            return {"path": str(path)}
        return None
    mock_client.call = AsyncMock(side_effect=_call)


# ---------------------------------------------------------------------------
# No-change path
# ---------------------------------------------------------------------------


class TestNoChanges:
    @pytest.mark.asyncio
    async def test_identical_changed_false(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (100, 100, 100))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("home", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "home", "screenshot_path": str(img)},
        ))
        assert result["changed"] is False

    @pytest.mark.asyncio
    async def test_identical_score_near_one(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (128, 200, 50))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img)},
        ))
        assert result["score"] == pytest.approx(1.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_no_change_summary_text(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (50, 50, 50))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img)},
        ))
        assert "No visual changes" in result["summary"]
        assert result["region_count"] == 0

    @pytest.mark.asyncio
    async def test_no_change_baseline_not_updated(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (77, 77, 77))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img), "update_baseline": True},
        ))
        # No change → update_baseline has nothing to do
        assert result["baseline_updated"] is False


# ---------------------------------------------------------------------------
# Change detected
# ---------------------------------------------------------------------------


class TestChangesDetected:
    @pytest.mark.asyncio
    async def test_different_changed_true(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        base = solid_png(tmp_path / "base.png", (0, 0, 0))
        curr = solid_png(tmp_path / "curr.png", (255, 255, 255))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(curr)},
        ))
        assert result["changed"] is True

    @pytest.mark.asyncio
    async def test_change_summary_includes_count_and_score(
        self, tmp_path, mock_client, monkeypatch
    ):
        bl_dir = tmp_path / "bl"
        base = solid_png(tmp_path / "base.png", (0, 0, 0))
        curr = solid_png(tmp_path / "curr.png", (255, 255, 255))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(curr)},
        ))
        assert "region" in result["summary"].lower()
        assert "score" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_region_count_positive(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        base_arr = np.zeros((64, 64, 3), dtype=np.uint8)
        curr_arr = base_arr.copy()
        curr_arr[10:30, 10:30] = 255
        base = tmp_path / "base.png"
        curr = tmp_path / "curr.png"
        skio.imsave(str(base), base_arr, check_contrast=False)
        skio.imsave(str(curr), curr_arr, check_contrast=False)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(curr)},
        ))
        assert result["region_count"] >= 1
        assert len(result["changed_regions"]) == result["region_count"]

    @pytest.mark.asyncio
    async def test_changed_regions_structure(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        base_arr = np.zeros((64, 64, 3), dtype=np.uint8)
        curr_arr = base_arr.copy()
        curr_arr[10:30, 10:30] = 255
        base = tmp_path / "base.png"
        curr = tmp_path / "curr.png"
        skio.imsave(str(base), base_arr, check_contrast=False)
        skio.imsave(str(curr), curr_arr, check_contrast=False)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(curr)},
        ))
        r = result["changed_regions"][0]
        assert {"x", "y", "width", "height"} <= r.keys()
        assert all(isinstance(v, int) for v in r.values())


# ---------------------------------------------------------------------------
# update_baseline
# ---------------------------------------------------------------------------


class TestUpdateBaseline:
    @pytest.mark.asyncio
    async def test_update_baseline_true_replaces_on_change(
        self, tmp_path, mock_client, monkeypatch
    ):
        bl_dir = tmp_path / "bl"
        base = solid_png(tmp_path / "base.png", (0, 0, 0))
        curr = solid_png(tmp_path / "curr.png", (255, 255, 255))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {
                "baseline_name": "s",
                "screenshot_path": str(curr),
                "update_baseline": True,
            },
        ))
        assert result["changed"] is True
        assert result["baseline_updated"] is True

    @pytest.mark.asyncio
    async def test_update_baseline_false_never_updates(
        self, tmp_path, mock_client, monkeypatch
    ):
        bl_dir = tmp_path / "bl"
        base = solid_png(tmp_path / "base.png", (0, 0, 0))
        curr = solid_png(tmp_path / "curr.png", (255, 255, 255))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {
                "baseline_name": "s",
                "screenshot_path": str(curr),
                "update_baseline": False,
            },
        ))
        assert result["baseline_updated"] is False


# ---------------------------------------------------------------------------
# diff_path
# ---------------------------------------------------------------------------


class TestDiffPath:
    @pytest.mark.asyncio
    async def test_diff_path_written(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        base = solid_png(tmp_path / "base.png", (0, 0, 0))
        curr = solid_png(tmp_path / "curr.png", (255, 255, 255))
        diff = tmp_path / "diff.png"
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", base, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, curr)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {
                "baseline_name": "s",
                "screenshot_path": str(curr),
                "diff_path": str(diff),
            },
        ))
        assert diff.exists()
        assert result["diff_path"] == str(diff)

    @pytest.mark.asyncio
    async def test_no_diff_path_field_is_null(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (128, 128, 128))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img)},
        ))
        assert result["diff_path"] is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    @pytest.mark.asyncio
    async def test_missing_baseline_returns_error(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        _patch(monkeypatch, bl_dir)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "ghost", "screenshot_path": str(tmp_path / "s.png")},
        ))
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_engine_disconnected_returns_structured_error(
        self, tmp_path, monkeypatch
    ):
        """When engine is not connected, handle_tool_errors returns EngineDisconnected."""
        from autoagent_mcp.connector import set_client
        set_client(None)
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (0, 0, 0))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img)},
        ))
        assert result["success"] is False
        assert result["error"]["error_type"] == "EngineDisconnected"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestResponseShape:
    @pytest.mark.asyncio
    async def test_all_top_level_fields_present(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (200, 200, 200))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img)},
        ))
        expected_keys = {
            "changed", "score", "region_count", "changed_regions",
            "summary", "screenshot_path", "baseline_name", "baseline_path",
            "diff_path", "baseline_updated",
        }
        assert expected_keys <= result.keys()

    @pytest.mark.asyncio
    async def test_threshold_controls_changed_flag(
        self, tmp_path, mock_client, monkeypatch
    ):
        """threshold > score → changed=True even for a high-similarity pair."""
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (100, 100, 100))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img), "threshold": 1.1},
        ))
        assert result["changed"] is True

    @pytest.mark.asyncio
    async def test_score_is_float(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "bl"
        img = solid_png(tmp_path / "img.png", (0, 0, 0))
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("s", img, baseline_dir=bl_dir)
        _patch(monkeypatch, bl_dir)
        _wire_returns(mock_client, img)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "audit_visual_changes",
            {"baseline_name": "s", "screenshot_path": str(img)},
        ))
        assert isinstance(result["score"], float)
        assert isinstance(result["changed"], bool)
        assert isinstance(result["region_count"], int)
