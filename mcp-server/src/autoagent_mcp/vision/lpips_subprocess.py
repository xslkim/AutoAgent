"""LPIPS subprocess manager.

Manages a single long-lived worker subprocess (:mod:`lpips_worker`) that
loads PyTorch + LPIPS once and serves perceptual-distance requests over a
newline-delimited JSON pipe (stdin/stdout).

Why a subprocess?
    PyTorch allocates several hundred MB of GPU/CPU memory on first import.
    Running it in-process would bloat the MCP server for all users, even those
    who never call an LPIPS tool.  The subprocess is lazily started and kept
    alive so the cold-start cost is paid only once per server session.

Usage::

    from autoagent_mcp.vision.lpips_subprocess import compare_lpips

    result = compare_lpips("baseline.png", "current.png")
    print(result.score)      # LPIPS distance; 0.0 = identical
    print(result.identical)  # True when score < threshold (default 0.1)

The singleton worker is shut down automatically via ``atexit``.

Thread safety: one request at a time, protected by :class:`threading.Lock`.
"""

from __future__ import annotations

import atexit
import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class LpipsNotAvailable(RuntimeError):
    """Raised when the ``[lpips]`` optional extras are not installed.

    Install with::

        pip install "autoagent-mcp[lpips]"
    """


@dataclass(frozen=True)
class LpipsResult:
    """Result of a perceptual distance comparison.

    Attributes:
        score:     LPIPS distance in ``[0, ∞)``.  ``0.0`` means the images are
                   perceptually identical; larger values indicate more difference.
                   Typical UI screenshots that look identical to the human eye
                   have a score below ``0.05``.
        identical: ``True`` when *score* is below the *threshold* passed to
                   :func:`compare_lpips` (default ``0.1``).
    """

    score: float
    identical: bool


# ---------------------------------------------------------------------------
# Internal: subprocess manager
# ---------------------------------------------------------------------------

_WORKER_MODULE = "autoagent_mcp.vision.lpips_worker"


class LpipsProcess:
    """Manages a single LPIPS worker subprocess (process-level singleton).

    Call :meth:`get` to retrieve the shared instance.  Use :meth:`compare`
    to run a comparison.  Call :meth:`shutdown` (or rely on ``atexit``) to
    terminate the worker.
    """

    _class_lock: threading.Lock = threading.Lock()
    _instance: "LpipsProcess | None" = None

    def __init__(self) -> None:
        self._proc_lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        atexit.register(self.shutdown)

    # ---- class-level singleton --------------------------------------------

    @classmethod
    def get(cls) -> "LpipsProcess":
        """Return the process-level singleton, creating it if necessary."""
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ---- subprocess lifecycle ---------------------------------------------

    def _ensure_started(self) -> None:
        """Start the worker subprocess if it is not currently running."""
        if self._proc is not None and self._proc.poll() is None:
            return  # already alive

        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-m", _WORKER_MODULE],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,  # line-buffered
            )
        except FileNotFoundError as exc:
            raise LpipsNotAvailable(
                "Could not locate Python interpreter to spawn the LPIPS worker. "
                "Install optional dependencies: pip install 'autoagent-mcp[lpips]'"
            ) from exc

        # Read the "ready" handshake (or an empty string on immediate crash).
        ready_line = self._proc.stdout.readline()
        try:
            msg: dict = json.loads(ready_line)
        except (json.JSONDecodeError, ValueError):
            msg = {}

        if not msg.get("ready"):
            # Worker crashed before printing ready — most likely torch/lpips missing.
            self._proc.terminate()
            self._proc = None
            raise LpipsNotAvailable(
                "LPIPS worker failed to start.  "
                "Make sure torch and lpips are installed: "
                "pip install 'autoagent-mcp[lpips]'"
            )

    def compare(
        self,
        path_a: str,
        path_b: str,
        *,
        threshold: float = 0.1,
    ) -> LpipsResult:
        """Compute the LPIPS perceptual distance between two images.

        Args:
            path_a:    Reference (baseline) image path.
            path_b:    Candidate (current) image path.
            threshold: Distance below which the images are considered identical
                       (default ``0.1``).  Note: LPIPS is a *distance* — lower
                       means more similar, the opposite of SSIM.

        Returns:
            :class:`LpipsResult`.

        Raises:
            LpipsNotAvailable: torch or lpips is not installed.
            FileNotFoundError: An image path does not exist.
            ValueError:        The images have different spatial dimensions.
            RuntimeError:      The worker returned an unexpected error.
        """
        # Check file existence in the parent process — gives a clean error
        # immediately without a round-trip to the worker.
        for p in (path_a, path_b):
            if not Path(p).exists():
                raise FileNotFoundError(f"Image not found: {p}")

        with self._proc_lock:
            self._ensure_started()

            # Send request.
            req = json.dumps({"path_a": str(path_a), "path_b": str(path_b)})
            self._proc.stdin.write(req + "\n")
            self._proc.stdin.flush()

            # Read response.
            line = self._proc.stdout.readline()

        try:
            resp: dict = json.loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(
                f"LPIPS worker returned unexpected output: {line!r}"
            ) from exc

        if not resp.get("ok"):
            err = resp.get("error", "unknown error")
            # Surface size-mismatch as ValueError for API parity with ssim.compare_images.
            if "size mismatch" in err.lower():
                raise ValueError(err)
            raise RuntimeError(f"LPIPS worker error: {err}")

        score = float(resp["score"])
        return LpipsResult(score=score, identical=score < threshold)

    def shutdown(self) -> None:
        """Terminate the worker subprocess gracefully."""
        with self._proc_lock:
            if self._proc is None:
                return
            try:
                self._proc.stdin.write(json.dumps({"action": "quit"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            finally:
                self._proc = None


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def compare_lpips(
    path_a: str | Path,
    path_b: str | Path,
    *,
    threshold: float = 0.1,
) -> LpipsResult:
    """Compute the LPIPS perceptual distance between two images.

    Convenience wrapper around :class:`LpipsProcess`.  The worker subprocess
    is started on the first call and reused for all subsequent calls.

    Args:
        path_a:    Reference (baseline) image path.
        path_b:    Candidate (current) image path.
        threshold: Identical-threshold (default ``0.1``).

    Returns:
        :class:`LpipsResult`.

    Raises:
        LpipsNotAvailable: torch or lpips not installed.
        FileNotFoundError: An image path does not exist.
        ValueError:        Image size mismatch.
    """
    return LpipsProcess.get().compare(str(path_a), str(path_b), threshold=threshold)
