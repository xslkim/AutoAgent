"""LPIPS perceptual distance worker — runs as a subprocess.

Protocol (stdin/stdout, newline-delimited JSON):

  Startup:  worker prints ``{"ready": true}`` once PyTorch + LPIPS are loaded.
  Request:  ``{"path_a": "<path>", "path_b": "<path>"}``
  Response: ``{"ok": true, "score": <float>}``
          | ``{"ok": false, "error": "<message>"}``
  Shutdown: send ``{"action": "quit"}`` or close stdin (EOF).

The model (AlexNet backbone) is loaded once at startup.  All subsequent
requests share it, avoiding the 0.5–2 s cold-start overhead per comparison.

Usage (from a subprocess manager — not called directly)::

    python -m autoagent_mcp.vision.lpips_worker
    # or
    python /path/to/lpips_worker.py
"""

from __future__ import annotations

import json
import sys


def _load_image(path: str):
    """Load *path* as a (1, 3, H, W) float32 tensor in [-1, 1]."""
    import numpy as np
    import torch
    from PIL import Image

    img = Image.open(path).convert("RGB")
    arr = np.array(img, dtype=np.float32) / 127.5 - 1.0  # [0,255] → [-1, 1]
    # (H, W, 3) → (1, 3, H, W)
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
    return tensor


def _compute(model, path_a: str, path_b: str) -> float:
    """Return the LPIPS perceptual distance between two images."""
    import torch
    from pathlib import Path

    if not Path(path_a).exists():
        raise FileNotFoundError(f"Image not found: {path_a}")
    if not Path(path_b).exists():
        raise FileNotFoundError(f"Image not found: {path_b}")

    ta = _load_image(path_a)
    tb = _load_image(path_b)

    if ta.shape != tb.shape:
        h_a, w_a = ta.shape[2], ta.shape[3]
        h_b, w_b = tb.shape[2], tb.shape[3]
        raise ValueError(
            f"Image size mismatch: {Path(path_a).name} is {w_a}×{h_a} "
            f"but {Path(path_b).name} is {w_b}×{h_b}"
        )

    with torch.no_grad():
        dist = model(ta, tb)
    return float(dist.item())


def main() -> None:
    """Entry point: load model, then serve requests from stdin."""
    try:
        import lpips as lpips_lib  # type: ignore[import]
    except ImportError:
        sys.stderr.write(
            "lpips not installed. Run: pip install autoagent-mcp[lpips]\n"
        )
        sys.exit(1)

    model = lpips_lib.LPIPS(net="alex", verbose=False)
    model.eval()

    # Signal to the parent process that we are ready.
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(
                json.dumps({"ok": False, "error": f"bad JSON: {exc}"}) + "\n"
            )
            sys.stdout.flush()
            continue

        if req.get("action") == "quit":
            break

        try:
            score = _compute(model, req["path_a"], req["path_b"])
            sys.stdout.write(json.dumps({"ok": True, "score": score}) + "\n")
        except Exception as exc:
            sys.stdout.write(
                json.dumps({"ok": False, "error": str(exc)}) + "\n"
            )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
