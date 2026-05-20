"""TASK-0124: take_screenshot baseline-integration tests.

Verifies the two new optional parameters added to take_screenshot:
- save_as_baseline  → saves the captured file as a named baseline
- compare_baseline  → runs SSIM comparison, embeds result in response

All tests mock the engine client (no real WebSocket) and redirect baseline
storage to a tmp_path subdirectory.
"""

from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from skimage import io as skio

from autoagent_mcp.connector import WebSocketClient, set_client
from autoagent_mcp.server import build_server
from autoagent_mcp.vision.baseline import load_baseline_path, save_baseline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def solid_png(path: Path, color: tuple, size: int = 64) -> Path:
    arr = np.full((size, size, 3), color, dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    skio.imsave(str(path), arr, check_contrast=False)
    return path


def _result(tool_result) -> dict:
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    return tool_result


def _patch_baseline_dir(monkeypatch, bl_dir: Path) -> None:
    import autoagent_mcp.vision.baseline as _bl
    import autoagent_mcp.tools.screenshot as _sc

    monkeypatch.setattr(_bl, "DEFAULT_BASELINE_DIR", bl_dir)
    monkeypatch.setattr(
        _sc, "save_baseline",
        lambda name, src, **kw: _bl.save_baseline(name, src, baseline_dir=bl_dir, **kw),
    )
    monkeypatch.setattr(
        _sc, "load_baseline_path",
        lambda name: _bl.load_baseline_path(name, baseline_dir=bl_dir),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client(tmp_path):
    """Mock engine client whose take_screenshot returns the requested save_path."""
    client = AsyncMock(spec=WebSocketClient)
    client.connected = True

    async def _call(method, params):
        if method == "take_screenshot":
            return {"path": params["path"]}
        return None

    client.call = AsyncMock(side_effect=_call)
    set_client(client)
    yield client
    set_client(None)


# ---------------------------------------------------------------------------
# Backward compatibility — no new params
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_basic_screenshot_still_works(self, tmp_path, mock_client):
        save_path = str(tmp_path / "shot.png")
        solid_png(tmp_path / "shot.png", (128, 128, 128))
        mcp = build_server()
        result = _result(await mcp.call_tool("take_screenshot", {"save_path": save_path}))
        assert result["saved_path"] == save_path
        assert result["scope"] == "fullscreen"
        assert "baseline_comparison" not in result
        assert "baseline_saved" not in result

    @pytest.mark.asyncio
    async def test_scope_node_still_works(self, tmp_path, mock_client):
        save_path = str(tmp_path / "node.png")
        solid_png(tmp_path / "node.png", (0, 0, 0))
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": save_path, "scope": "node", "node_id": "btn"},
        ))
        assert result["saved_path"] == save_path
        mock_client.call.assert_called_once_with(
            "take_screenshot", {"path": save_path, "mode": "node", "id": "btn"}
        )


# ---------------------------------------------------------------------------
# save_as_baseline
# ---------------------------------------------------------------------------


class TestSaveAsBaseline:
    @pytest.mark.asyncio
    async def test_save_as_baseline_creates_baseline(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        shot = tmp_path / "shot.png"
        solid_png(shot, (200, 100, 50))
        _patch_baseline_dir(monkeypatch, bl_dir)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(shot), "save_as_baseline": "home_screen"},
        ))
        assert result["baseline_saved"] is True
        assert result["baseline_name"] == "home_screen"
        assert "baseline_path" in result
        # File actually exists on disk
        import autoagent_mcp.vision.baseline as _bl
        assert load_baseline_path("home_screen", baseline_dir=bl_dir).exists()

    @pytest.mark.asyncio
    async def test_save_as_baseline_response_fields(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        shot = tmp_path / "s.png"
        solid_png(shot, (0, 0, 0))
        _patch_baseline_dir(monkeypatch, bl_dir)
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(shot), "save_as_baseline": "my_bl"},
        ))
        assert "saved_path" in result
        assert "baseline_saved" in result
        assert "baseline_name" in result
        assert "baseline_path" in result

    @pytest.mark.asyncio
    async def test_save_as_baseline_missing_source_sets_error(
        self, tmp_path, mock_client, monkeypatch
    ):
        """If the adapter returns a path that doesn't exist, baseline_saved=False."""
        bl_dir = tmp_path / "baselines"
        _patch_baseline_dir(monkeypatch, bl_dir)

        async def _call(method, params):
            return {"path": str(tmp_path / "nonexistent.png")}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {
                "save_path": str(tmp_path / "nonexistent.png"),
                "save_as_baseline": "bad",
            },
        ))
        assert result["baseline_saved"] is False
        assert "baseline_error" in result

    @pytest.mark.asyncio
    async def test_save_as_baseline_overwrites_existing(
        self, tmp_path, mock_client, monkeypatch
    ):
        bl_dir = tmp_path / "baselines"
        shot1 = tmp_path / "s1.png"
        shot2 = tmp_path / "s2.png"
        solid_png(shot1, (255, 0, 0))
        solid_png(shot2, (0, 255, 0))
        _patch_baseline_dir(monkeypatch, bl_dir)

        async def _call1(m, p):
            return {"path": str(shot1)}

        async def _call2(m, p):
            return {"path": str(shot2)}

        mcp = build_server()
        mock_client.call.side_effect = _call1
        await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(shot1), "save_as_baseline": "bl"},
        )
        mock_client.call.side_effect = _call2
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(shot2), "save_as_baseline": "bl"},
        ))
        assert result["baseline_saved"] is True


# ---------------------------------------------------------------------------
# compare_baseline
# ---------------------------------------------------------------------------


class TestCompareBaseline:
    @pytest.mark.asyncio
    async def test_compare_identical_images(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        img = tmp_path / "img.png"
        solid_png(img, (128, 128, 128))
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("home", img, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(img), "compare_baseline": "home"},
        ))
        cmp = result["baseline_comparison"]
        assert cmp["score"] == pytest.approx(1.0, abs=1e-4)
        assert cmp["identical"] is True
        assert cmp["changed_regions"] == []

    @pytest.mark.asyncio
    async def test_compare_different_images(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        baseline_img = tmp_path / "base.png"
        current_img = tmp_path / "curr.png"
        solid_png(baseline_img, (0, 0, 0))
        solid_png(current_img, (255, 255, 255))
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("dark", baseline_img, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(current_img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(current_img), "compare_baseline": "dark"},
        ))
        cmp = result["baseline_comparison"]
        assert cmp["score"] < 0.5
        assert cmp["identical"] is False

    @pytest.mark.asyncio
    async def test_compare_missing_baseline_embeds_error(
        self, tmp_path, mock_client, monkeypatch
    ):
        bl_dir = tmp_path / "baselines"
        img = tmp_path / "img.png"
        solid_png(img, (0, 0, 0))
        _patch_baseline_dir(monkeypatch, bl_dir)

        async def _call(m, p):
            return {"path": str(img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(img), "compare_baseline": "nonexistent"},
        ))
        # Tool should NOT fail — error is embedded inside baseline_comparison
        assert "baseline_comparison" in result
        assert "error" in result["baseline_comparison"]

    @pytest.mark.asyncio
    async def test_compare_result_fields(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        img = tmp_path / "img.png"
        solid_png(img, (50, 50, 50))
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("fields", img, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(img), "compare_baseline": "fields"},
        ))
        cmp = result["baseline_comparison"]
        assert "score" in cmp
        assert "identical" in cmp
        assert "changed_regions" in cmp
        assert "diff_path" in cmp
        assert "baseline_name" in cmp
        assert "baseline_path" in cmp

    @pytest.mark.asyncio
    async def test_compare_threshold_respected(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        img = tmp_path / "img.png"
        solid_png(img, (100, 100, 100))
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("thr", img, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        # threshold > 1.0 → identical=False even for a perfect score
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(img), "compare_baseline": "thr", "baseline_threshold": 1.1},
        ))
        assert result["baseline_comparison"]["identical"] is False

    @pytest.mark.asyncio
    async def test_compare_diff_path_written(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        baseline_img = tmp_path / "base.png"
        current_img = tmp_path / "curr.png"
        diff = tmp_path / "diff.png"
        solid_png(baseline_img, (0, 0, 0))
        solid_png(current_img, (255, 255, 255))
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("dif", baseline_img, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(current_img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {
                "save_path": str(current_img),
                "compare_baseline": "dif",
                "diff_path": str(diff),
            },
        ))
        assert diff.exists()
        assert result["baseline_comparison"]["diff_path"] == str(diff)

    @pytest.mark.asyncio
    async def test_changed_regions_structure(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        base = np.zeros((64, 64, 3), dtype=np.uint8)
        curr = base.copy()
        curr[10:30, 10:30] = 255
        base_p = tmp_path / "base.png"
        curr_p = tmp_path / "curr.png"
        skio.imsave(str(base_p), base, check_contrast=False)
        skio.imsave(str(curr_p), curr, check_contrast=False)
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("region", base_p, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(curr_p)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {"save_path": str(curr_p), "compare_baseline": "region"},
        ))
        regions = result["baseline_comparison"]["changed_regions"]
        assert len(regions) >= 1
        r = regions[0]
        assert all(k in r for k in ("x", "y", "width", "height"))


# ---------------------------------------------------------------------------
# Combined: save_as_baseline AND compare_baseline in same call
# ---------------------------------------------------------------------------


class TestCombined:
    @pytest.mark.asyncio
    async def test_save_and_compare_independent(self, tmp_path, mock_client, monkeypatch):
        """save_as_baseline and compare_baseline can refer to different names."""
        bl_dir = tmp_path / "baselines"
        existing_bl = tmp_path / "existing.png"
        new_shot = tmp_path / "new.png"
        solid_png(existing_bl, (255, 0, 0))
        solid_png(new_shot, (255, 0, 0))  # same colour so comparison passes
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("old_bl", existing_bl, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(new_shot)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {
                "save_path": str(new_shot),
                "save_as_baseline": "new_bl",
                "compare_baseline": "old_bl",
            },
        ))
        assert result["baseline_saved"] is True
        assert result["baseline_name"] == "new_bl"
        assert "baseline_comparison" in result
        assert result["baseline_comparison"]["identical"] is True

    @pytest.mark.asyncio
    async def test_response_contains_all_groups(self, tmp_path, mock_client, monkeypatch):
        bl_dir = tmp_path / "baselines"
        img = tmp_path / "img.png"
        solid_png(img, (77, 77, 77))
        _patch_baseline_dir(monkeypatch, bl_dir)
        import autoagent_mcp.vision.baseline as _bl
        _bl.save_baseline("ref", img, baseline_dir=bl_dir)

        async def _call(m, p):
            return {"path": str(img)}

        mock_client.call.side_effect = _call
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "take_screenshot",
            {
                "save_path": str(img),
                "save_as_baseline": "snap",
                "compare_baseline": "ref",
            },
        ))
        # Base fields
        assert "saved_path" in result
        assert "scope" in result
        # save_as_baseline fields
        assert result["baseline_saved"] is True
        # compare_baseline fields
        assert "baseline_comparison" in result
