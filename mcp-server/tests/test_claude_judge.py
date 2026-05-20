"""TASK-0126: Claude Vision judge tests.

All API calls are mocked — no real ANTHROPIC_API_KEY is needed.
Tests cover:
- judge_diff() parses valid JSON from Claude correctly.
- Malformed / non-JSON response → graceful fallback JudgeResult.
- Missing image file → FileNotFoundError.
- All four severity levels accepted.
- diff_path included as third image when provided.
- _parse_response handles edge-cases (missing keys, bad severity).
- MCP tool judge_visual_diff returns correct shape on success.
- MCP tool returns {"success": false} on FileNotFoundError and API error.
- model / max_tokens forwarded to client.
"""

from __future__ import annotations

import json
import numpy as np
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from skimage import io as skio

from autoagent_mcp.server import build_server
from autoagent_mcp.vision.claude_judge import (
    DEFAULT_MODEL,
    JudgeResult,
    _parse_response,
    judge_diff,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def solid_png(path: Path, color: tuple = (128, 128, 128), size: int = 32) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.full((size, size, 3), color, dtype=np.uint8)
    skio.imsave(str(path), arr, check_contrast=False)
    return path


def _make_mock_client(json_payload: dict | None = None, raw_text: str | None = None):
    """Return a mock Anthropic client whose .messages.create() returns a preset response."""
    if raw_text is None:
        raw_text = json.dumps(json_payload or {
            "changed": False,
            "severity": "none",
            "description": "No changes detected.",
            "details": [],
        })
    mock_msg = SimpleNamespace(content=[SimpleNamespace(text=raw_text)])
    client = MagicMock()
    client.messages.create.return_value = mock_msg
    return client


def _result(tool_result) -> dict:
    if isinstance(tool_result, tuple) and len(tool_result) == 2:
        return tool_result[1]
    return tool_result


# ---------------------------------------------------------------------------
# _parse_response unit tests
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_valid_json_parsed(self):
        raw = json.dumps({
            "changed": True,
            "severity": "minor",
            "description": "Button moved slightly.",
            "details": ["Submit button shifted 2px right"],
        })
        result = _parse_response(raw, model=DEFAULT_MODEL)
        assert result.changed is True
        assert result.severity == "minor"
        assert result.description == "Button moved slightly."
        assert result.details == ["Submit button shifted 2px right"]

    def test_all_severities_accepted(self):
        for sev in ("none", "minor", "moderate", "major"):
            raw = json.dumps({"changed": False, "severity": sev, "description": "x", "details": []})
            result = _parse_response(raw, model=DEFAULT_MODEL)
            assert result.severity == sev

    def test_unknown_severity_falls_back_to_moderate(self):
        raw = json.dumps({"changed": True, "severity": "catastrophic", "description": "x", "details": []})
        result = _parse_response(raw, model=DEFAULT_MODEL)
        assert result.severity == "moderate"

    def test_non_json_response_fallback(self):
        result = _parse_response("I cannot process this request.", model=DEFAULT_MODEL)
        assert isinstance(result.description, str)
        assert len(result.description) > 0
        assert result.severity == "moderate"

    def test_empty_response_fallback(self):
        result = _parse_response("", model=DEFAULT_MODEL)
        assert isinstance(result, JudgeResult)

    def test_markdown_fenced_json_stripped(self):
        raw = "```json\n" + json.dumps({
            "changed": False, "severity": "none",
            "description": "Nothing changed.", "details": [],
        }) + "\n```"
        result = _parse_response(raw, model=DEFAULT_MODEL)
        assert result.severity == "none"

    def test_changed_false_when_severity_none(self):
        raw = json.dumps({"changed": False, "severity": "none", "description": "same", "details": []})
        result = _parse_response(raw, model=DEFAULT_MODEL)
        assert result.changed is False

    def test_missing_details_defaults_to_empty(self):
        raw = json.dumps({"changed": True, "severity": "major", "description": "x"})
        result = _parse_response(raw, model=DEFAULT_MODEL)
        assert result.details == []

    def test_model_field_preserved(self):
        raw = json.dumps({"changed": False, "severity": "none", "description": "x", "details": []})
        result = _parse_response(raw, model="custom-model")
        assert result.model == "custom-model"

    def test_raw_response_stored(self):
        raw = '{"changed": false, "severity": "none", "description": "x", "details": []}'
        result = _parse_response(raw, model=DEFAULT_MODEL)
        assert result.raw_response == raw


# ---------------------------------------------------------------------------
# judge_diff() with mock client
# ---------------------------------------------------------------------------


class TestJudgeDiff:
    def test_returns_judge_result(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png", (200, 200, 200))
        client = _make_mock_client({"changed": False, "severity": "none",
                                    "description": "Same", "details": []})
        result = judge_diff(a, b, _client=client)
        assert isinstance(result, JudgeResult)

    def test_changed_field_from_payload(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png", (0, 0, 0))
        client = _make_mock_client({"changed": True, "severity": "major",
                                    "description": "Layout broken", "details": ["x"]})
        result = judge_diff(a, b, _client=client)
        assert result.changed is True
        assert result.severity == "major"

    def test_two_images_sent_without_diff(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client()
        judge_diff(a, b, _client=client)
        call_kwargs = client.messages.create.call_args
        content = call_kwargs.kwargs["messages"][0]["content"]
        image_blocks = [c for c in content if c.get("type") == "image"]
        assert len(image_blocks) == 2

    def test_three_images_sent_with_diff(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        d = solid_png(tmp_path / "d.png", (50, 50, 50))
        client = _make_mock_client()
        judge_diff(a, b, diff_path=d, _client=client)
        call_kwargs = client.messages.create.call_args
        content = call_kwargs.kwargs["messages"][0]["content"]
        image_blocks = [c for c in content if c.get("type") == "image"]
        assert len(image_blocks) == 3

    def test_model_forwarded(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client()
        judge_diff(a, b, model="claude-3-5-sonnet-20241022", _client=client)
        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-3-5-sonnet-20241022"

    def test_max_tokens_forwarded(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client()
        judge_diff(a, b, max_tokens=256, _client=client)
        call_kwargs = client.messages.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 256

    def test_missing_baseline_raises(self, tmp_path):
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client()
        with pytest.raises(FileNotFoundError):
            judge_diff(tmp_path / "no.png", b, _client=client)

    def test_missing_current_raises(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        client = _make_mock_client()
        with pytest.raises(FileNotFoundError):
            judge_diff(a, tmp_path / "no.png", _client=client)

    def test_image_data_is_base64(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client()
        judge_diff(a, b, _client=client)
        call_kwargs = client.messages.create.call_args
        content = call_kwargs.kwargs["messages"][0]["content"]
        img = next(c for c in content if c.get("type") == "image")
        import base64
        # Should not raise
        base64.standard_b64decode(img["source"]["data"])

    def test_png_media_type(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client()
        judge_diff(a, b, _client=client)
        call_kwargs = client.messages.create.call_args
        content = call_kwargs.kwargs["messages"][0]["content"]
        img = next(c for c in content if c.get("type") == "image")
        assert img["source"]["media_type"] == "image/png"

    def test_malformed_api_response_graceful(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        client = _make_mock_client(raw_text="Sorry, I cannot do that.")
        result = judge_diff(a, b, _client=client)
        assert isinstance(result, JudgeResult)
        assert result.severity == "moderate"


# ---------------------------------------------------------------------------
# MCP tool judge_visual_diff
# ---------------------------------------------------------------------------


class TestJudgeVisualDiffTool:
    @pytest.mark.asyncio
    async def test_success_response_shape(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png", (200, 200, 200))
        import autoagent_mcp.tools.judge as _jt
        original = _jt.judge_diff

        def _stub(*args, **kwargs):
            return JudgeResult(
                changed=False, description="No change.", severity="none",
                details=[], model=DEFAULT_MODEL,
            )

        _jt.judge_diff = _stub
        try:
            mcp = build_server()
            result = _result(await mcp.call_tool(
                "judge_visual_diff",
                {"baseline_path": str(a), "current_path": str(b)},
            ))
            assert result["changed"] is False
            assert result["severity"] == "none"
            assert result["description"] == "No change."
            assert "details" in result
            assert "model" in result
        finally:
            _jt.judge_diff = original

    @pytest.mark.asyncio
    async def test_missing_baseline_returns_error(self, tmp_path):
        b = solid_png(tmp_path / "b.png")
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "judge_visual_diff",
            {"baseline_path": str(tmp_path / "no.png"), "current_path": str(b)},
        ))
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_current_returns_error(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        mcp = build_server()
        result = _result(await mcp.call_tool(
            "judge_visual_diff",
            {"baseline_path": str(a), "current_path": str(tmp_path / "no.png")},
        ))
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_api_error_returns_error(self, tmp_path):
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        failing_client = MagicMock()
        failing_client.messages.create.side_effect = RuntimeError("API timeout")
        mcp = build_server()

        # Inject via _client parameter by patching judge_diff in tools.judge
        import autoagent_mcp.tools.judge as _jt
        original = _jt.judge_diff

        def _failing(*args, **kwargs):
            raise RuntimeError("API timeout")

        _jt.judge_diff = _failing
        try:
            result = _result(await mcp.call_tool(
                "judge_visual_diff",
                {"baseline_path": str(a), "current_path": str(b)},
            ))
            assert result["success"] is False
            assert "error" in result
        finally:
            _jt.judge_diff = original

    @pytest.mark.asyncio
    async def test_tool_passes_model_and_max_tokens(self, tmp_path):
        """Tool parameters are forwarded (tested via direct judge_diff mock)."""
        a = solid_png(tmp_path / "a.png")
        b = solid_png(tmp_path / "b.png")
        captured: dict = {}

        import autoagent_mcp.tools.judge as _jt
        original = _jt.judge_diff

        def _capture(*args, **kwargs):
            captured.update(kwargs)
            return JudgeResult(
                changed=False, description="ok", severity="none",
                details=[], model=kwargs.get("model", DEFAULT_MODEL),
            )

        _jt.judge_diff = _capture
        try:
            mcp = build_server()
            await mcp.call_tool(
                "judge_visual_diff",
                {
                    "baseline_path": str(a),
                    "current_path": str(b),
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 128,
                },
            )
            assert captured.get("model") == "claude-3-haiku-20240307"
            assert captured.get("max_tokens") == 128
        finally:
            _jt.judge_diff = original


# ---------------------------------------------------------------------------
# JudgeResult dataclass
# ---------------------------------------------------------------------------


class TestJudgeResult:
    def test_fields(self):
        r = JudgeResult(
            changed=True,
            description="Something changed",
            severity="major",
            details=["item"],
            model="m",
        )
        assert r.changed is True
        assert r.severity == "major"
        assert r.details == ["item"]

    def test_defaults(self):
        r = JudgeResult(changed=False, description="x", severity="none")
        assert r.details == []
        assert r.model == DEFAULT_MODEL
        assert r.raw_response == ""
