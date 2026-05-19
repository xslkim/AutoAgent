"""Capture a visual baseline screenshot from a running engine adapter.

Drives the AutoAgent wire protocol's take_screenshot against a running engine
(Unity / Godot / Unreal) and saves the PNG plus a .meta.json sidecar under
baselines/<engine>/<platform>/<scene>.{png,meta.json}.

Prerequisites
-------------
1. Run the engine adapter so it serves on ws://127.0.0.1:27842, with the
   target scene loaded (e.g. Unity LoginScene playing).
2. pip install websockets

Usage
-----
    python scripts/e2e/capture_baseline.py --engine unity --scene login_screen
    python scripts/e2e/capture_baseline.py --engine godot --scene poc_playground

Capture all six Phase-0 baselines by running this once per engine+scene
(switching the loaded scene in the editor between runs).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

WS_URL = "ws://127.0.0.1:27842"
SUBPROTOCOL = "autoagent.v1"

ENGINES = ("unity", "godot", "unreal")
SCENES = ("login_screen", "poc_playground")


class CaptureError(Exception):
    """A capture step failed."""


def rpc(ws, method: str, params: dict | None, req_id: int):
    """Send one JSON-RPC request, return the result, raise on error."""
    request = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        request["params"] = params
    ws.send(json.dumps(request))
    response = json.loads(ws.recv())
    if "error" in response:
        raise CaptureError(f"{method}: server error {response['error']}")
    if "result" not in response:
        raise CaptureError(f"{method}: response has no result")
    return response["result"]


def png_resolution(path: pathlib.Path) -> list[int] | None:
    """Read [width, height] from a PNG's IHDR chunk — no image library needed."""
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return [width, height]


def capture(engine: str, scene: str, platform: str) -> int:
    try:
        from websockets.sync.client import connect
    except ImportError:
        raise CaptureError("websockets not installed — run: pip install websockets")

    out_dir = REPO_ROOT / "baselines" / engine / platform
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{scene}.png"
    meta_path = out_dir / f"{scene}.meta.json"

    # Remove any stale image so we can detect the fresh write.
    if png_path.exists():
        png_path.unlink()

    print(f"capturing {engine}/{platform}/{scene} -> {png_path}")

    try:
        ws = connect(WS_URL, subprotocols=[SUBPROTOCOL], open_timeout=5)
    except (ConnectionRefusedError, OSError) as exc:
        raise CaptureError(
            f"cannot reach {WS_URL} ({exc}). Is the {engine} adapter running "
            f"with the {scene} scene loaded?"
        )

    with ws:
        if ws.subprotocol != SUBPROTOCOL:
            raise CaptureError(f"subprotocol not negotiated (got {ws.subprotocol!r})")
        rpc(ws, "negotiate_version", {"client_version": "0.1"}, 1)
        rpc(ws, "take_screenshot", {"path": str(png_path)}, 2)

    # take_screenshot is fire-and-forget on Unity/Unreal — wait for the file.
    deadline = time.time() + 15
    while time.time() < deadline:
        if png_path.exists() and png_path.stat().st_size > 0:
            break
        time.sleep(0.3)
    else:
        raise CaptureError(
            f"no screenshot appeared at {png_path} within 15s — "
            f"check the engine console for errors"
        )

    resolution = png_resolution(png_path)
    meta = {
        "engine": engine,
        "scene": scene,
        "platform": platform,
        "image": png_path.name,
        "resolution": resolution,
        "size_bytes": png_path.stat().st_size,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "wire_protocol": SUBPROTOCOL,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"  PNG  {png_path}  ({meta['size_bytes']} bytes, resolution {resolution})")
    print(f"  meta {meta_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="capture_baseline",
        description="Capture a visual baseline screenshot from a running engine adapter.",
    )
    parser.add_argument("--engine", required=True, choices=ENGINES)
    parser.add_argument("--scene", required=True, choices=SCENES)
    parser.add_argument("--platform", default="windows",
                        help="Baseline platform folder (default: windows).")
    args = parser.parse_args(argv)

    try:
        return capture(args.engine, args.scene, args.platform)
    except CaptureError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
