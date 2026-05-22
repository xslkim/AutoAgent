"""TASK-0403: LpipsProcess / compare_lpips tests.

All tests mock ``subprocess.Popen`` so they run without torch or lpips
installed.  The test suite exercises the IPC protocol, error handling,
singleton lifecycle, and threshold semantics.

Coverage:
- Worker startup handshake: "ready" line parsed correctly.
- compare() sends correct JSON request to subprocess stdin.
- compare() parses score from worker response.
- identical=True when score < threshold; False otherwise.
- FileNotFoundError raised before subprocess call for missing images.
- ValueError raised when worker reports "size mismatch".
- RuntimeError raised for generic worker errors.
- RuntimeError raised when worker returns non-JSON.
- LpipsNotAvailable raised when worker never prints "ready".
- LpipsNotAvailable raised when Popen raises FileNotFoundError.
- shutdown() sends {"action": "quit"} and waits.
- Singleton: LpipsProcess.get() returns the same instance.
- compare_lpips() module-level wrapper delegates to singleton.
- LpipsResult is a frozen dataclass with score and identical.
- Auto-restart: a dead process is restarted on next compare().
"""

from __future__ import annotations

import json
import threading
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import autoagent_mcp.vision.lpips_subprocess as _mod
from autoagent_mcp.vision.lpips_subprocess import (
    LpipsNotAvailable,
    LpipsProcess,
    LpipsResult,
    compare_lpips,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(responses: list[str]) -> MagicMock:
    """Return a mock subprocess.Popen whose stdout yields *responses* in order."""
    proc = MagicMock()
    proc.poll.return_value = None  # alive
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.flush = MagicMock()

    # Each readline() call pops the next response from the list.
    _lines = iter(responses)
    proc.stdout.readline = lambda: next(_lines, "")
    return proc


def _ready_then(*responses: str) -> list[str]:
    """Build a response list that starts with the "ready" handshake."""
    return [json.dumps({"ready": True}) + "\n", *responses]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton():
    """Isolate each test from the module-level singleton."""
    old = LpipsProcess._instance
    LpipsProcess._instance = None
    yield
    # Prevent leaked processes from interfering with later tests.
    LpipsProcess._instance = None


@pytest.fixture()
def images(tmp_path):
    """Create two tiny PNG stubs that 'exist' on disk (content doesn't matter)."""
    from skimage import io as skio
    import numpy as np

    def _make(name, color):
        arr = np.full((8, 8, 3), color, dtype=np.uint8)
        p = tmp_path / name
        skio.imsave(str(p), arr, check_contrast=False)
        return str(p)

    return _make("a.png", 100), _make("b.png", 200)


# ---------------------------------------------------------------------------
# LpipsResult
# ---------------------------------------------------------------------------


class TestLpipsResult:
    def test_frozen_dataclass(self):
        r = LpipsResult(score=0.05, identical=True)
        with pytest.raises(Exception):
            r.score = 99.0  # frozen → FrozenInstanceError

    def test_score_and_identical(self):
        r = LpipsResult(score=0.12, identical=False)
        assert r.score == 0.12
        assert r.identical is False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_returns_same_instance(self):
        a = LpipsProcess.get()
        b = LpipsProcess.get()
        assert a is b

    def test_get_creates_new_after_reset(self):
        a = LpipsProcess.get()
        LpipsProcess._instance = None
        b = LpipsProcess.get()
        assert a is not b


# ---------------------------------------------------------------------------
# Worker startup
# ---------------------------------------------------------------------------


class TestStartup:
    def test_ready_handshake_succeeds(self, images):
        pa, pb = images
        proc = _make_proc(
            _ready_then(json.dumps({"ok": True, "score": 0.02}) + "\n")
        )
        with patch("subprocess.Popen", return_value=proc):
            mgr = LpipsProcess()
            result = mgr.compare(pa, pb)
        assert result.score == pytest.approx(0.02)

    def test_no_ready_raises_not_available(self, images):
        pa, pb = images
        proc = _make_proc([""])  # empty → no ready
        proc.terminate = MagicMock()
        with patch("subprocess.Popen", return_value=proc):
            mgr = LpipsProcess()
            with pytest.raises(LpipsNotAvailable):
                mgr.compare(pa, pb)

    def test_bad_json_ready_raises_not_available(self, images):
        pa, pb = images
        proc = _make_proc(["not json\n"])
        proc.terminate = MagicMock()
        with patch("subprocess.Popen", return_value=proc):
            mgr = LpipsProcess()
            with pytest.raises(LpipsNotAvailable):
                mgr.compare(pa, pb)

    def test_popen_failure_raises_not_available(self, images):
        pa, pb = images
        with patch("subprocess.Popen", side_effect=FileNotFoundError("python")):
            mgr = LpipsProcess()
            with pytest.raises(LpipsNotAvailable):
                mgr.compare(pa, pb)


# ---------------------------------------------------------------------------
# compare() — happy path
# ---------------------------------------------------------------------------


class TestCompareHappyPath:
    def test_returns_lpips_result(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.05}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb)
        assert isinstance(result, LpipsResult)

    def test_score_parsed_correctly(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.123}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb)
        assert result.score == pytest.approx(0.123)

    def test_identical_true_below_threshold(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.05}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb, threshold=0.1)
        assert result.identical is True

    def test_identical_false_above_threshold(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.15}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb, threshold=0.1)
        assert result.identical is False

    def test_identical_false_at_threshold(self, images):
        """score == threshold → not identical (strict less-than)."""
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.1}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb, threshold=0.1)
        assert result.identical is False

    def test_request_json_sent_to_stdin(self, images):
        pa, pb = images
        written: list[str] = []
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.0}) + "\n"))
        proc.stdin.write = lambda s: written.append(s)
        with patch("subprocess.Popen", return_value=proc):
            LpipsProcess().compare(pa, pb)
        # First write is the request; last char is "\n"
        req_line = "".join(written)
        req = json.loads(req_line.strip())
        assert req["path_a"] == pa
        assert req["path_b"] == pb

    def test_zero_score_identical(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.0}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb)
        assert result.identical is True

    def test_custom_threshold_respected(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.3}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = LpipsProcess().compare(pa, pb, threshold=0.5)
        assert result.identical is True  # 0.3 < 0.5


# ---------------------------------------------------------------------------
# compare() — error cases
# ---------------------------------------------------------------------------


class TestCompareErrors:
    def test_missing_path_a_raises_before_subprocess(self, tmp_path, images):
        _, pb = images
        mgr = LpipsProcess()
        with pytest.raises(FileNotFoundError, match="no_such_a.png"):
            mgr.compare(str(tmp_path / "no_such_a.png"), pb)

    def test_missing_path_b_raises_before_subprocess(self, tmp_path, images):
        pa, _ = images
        mgr = LpipsProcess()
        with pytest.raises(FileNotFoundError, match="no_such_b.png"):
            mgr.compare(pa, str(tmp_path / "no_such_b.png"))

    def test_size_mismatch_raises_value_error(self, images):
        pa, pb = images
        err_resp = json.dumps({
            "ok": False,
            "error": "Image size mismatch: a.png is 8×8 but b.png is 16×16",
        }) + "\n"
        proc = _make_proc(_ready_then(err_resp))
        with patch("subprocess.Popen", return_value=proc):
            with pytest.raises(ValueError, match="size mismatch"):
                LpipsProcess().compare(pa, pb)

    def test_generic_worker_error_raises_runtime(self, images):
        pa, pb = images
        err_resp = json.dumps({"ok": False, "error": "CUDA out of memory"}) + "\n"
        proc = _make_proc(_ready_then(err_resp))
        with patch("subprocess.Popen", return_value=proc):
            with pytest.raises(RuntimeError, match="CUDA out of memory"):
                LpipsProcess().compare(pa, pb)

    def test_non_json_response_raises_runtime(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then("totally not json\n"))
        with patch("subprocess.Popen", return_value=proc):
            with pytest.raises(RuntimeError, match="unexpected output"):
                LpipsProcess().compare(pa, pb)

    def test_empty_response_raises_runtime(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(""))  # EOF after ready
        with patch("subprocess.Popen", return_value=proc):
            with pytest.raises((RuntimeError, json.JSONDecodeError, ValueError)):
                LpipsProcess().compare(pa, pb)


# ---------------------------------------------------------------------------
# shutdown()
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_shutdown_sends_quit(self, images):
        pa, pb = images
        written: list[str] = []
        proc = _make_proc(
            _ready_then(json.dumps({"ok": True, "score": 0.0}) + "\n")
        )
        proc.stdin.write = lambda s: written.append(s)
        proc.wait = MagicMock()

        with patch("subprocess.Popen", return_value=proc):
            mgr = LpipsProcess()
            mgr.compare(pa, pb)
            mgr.shutdown()

        all_written = "".join(written)
        # The quit command should be among the written lines.
        quit_found = any(
            "quit" in line
            for line in all_written.splitlines()
            if line.strip()
        )
        assert quit_found, f"Expected quit command in: {all_written!r}"

    def test_shutdown_noop_when_not_started(self):
        mgr = LpipsProcess()
        mgr.shutdown()  # must not raise

    def test_shutdown_clears_proc(self, images):
        pa, pb = images
        proc = _make_proc(
            _ready_then(json.dumps({"ok": True, "score": 0.0}) + "\n")
        )
        proc.wait = MagicMock()
        with patch("subprocess.Popen", return_value=proc):
            mgr = LpipsProcess()
            mgr.compare(pa, pb)
            mgr.shutdown()
        assert mgr._proc is None


# ---------------------------------------------------------------------------
# Auto-restart on dead process
# ---------------------------------------------------------------------------


class TestAutoRestart:
    def test_dead_process_restarted(self, images):
        pa, pb = images
        # First proc: dies immediately (poll returns non-None).
        dead_proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.1}) + "\n"))
        live_proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.2}) + "\n"))

        call_count = 0

        def fake_popen(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate the first process dying between the ready handshake
                # and the next compare() call.
                dead_proc.poll.return_value = 1  # dead
                return dead_proc
            return live_proc

        with patch("subprocess.Popen", side_effect=fake_popen):
            mgr = LpipsProcess()
            # First compare — starts dead_proc, succeeds with first ready line.
            # (poll is still None during _ensure_started; we set it to 1 after.)
            dead_proc.poll.return_value = None  # alive during first start
            result1 = mgr.compare(pa, pb)
            assert result1.score == pytest.approx(0.1)

            # Now mark it as dead so next call restarts.
            dead_proc.poll.return_value = 1

            result2 = mgr.compare(pa, pb)
            assert result2.score == pytest.approx(0.2)

        assert call_count == 2  # Popen called twice


# ---------------------------------------------------------------------------
# compare_lpips() convenience wrapper
# ---------------------------------------------------------------------------


class TestCompareLpips:
    def test_delegates_to_singleton(self, images):
        pa, pb = images
        proc = _make_proc(_ready_then(json.dumps({"ok": True, "score": 0.07}) + "\n"))
        with patch("subprocess.Popen", return_value=proc):
            result = compare_lpips(pa, pb, threshold=0.1)
        assert isinstance(result, LpipsResult)
        assert result.score == pytest.approx(0.07)
        assert result.identical is True

    def test_uses_process_level_singleton(self, images):
        pa, pb = images
        proc = _make_proc(
            _ready_then(
                json.dumps({"ok": True, "score": 0.01}) + "\n",
                json.dumps({"ok": True, "score": 0.02}) + "\n",
            )
        )
        with patch("subprocess.Popen", return_value=proc):
            r1 = compare_lpips(pa, pb)
            r2 = compare_lpips(pa, pb)
        # Both calls use the same singleton → Popen called only once.
        assert r1.score == pytest.approx(0.01)
        assert r2.score == pytest.approx(0.02)
