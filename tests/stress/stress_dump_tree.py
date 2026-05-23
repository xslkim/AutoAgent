"""TASK-0407: Stress-test harness for dump_tree / dump_tree_delta.

Connects to a running Unity adapter via WebSocket and repeatedly calls
dump_tree, measuring latency.  Designed to be run on a self-hosted CI
runner with Unity in Play Mode.

Usage:
    python tests/stress/stress_dump_tree.py --iterations 100 --threshold-ms 100
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time

# Allow running from the repo root without installing.
sys.path.insert(0, "mcp-server/src")

from autoagent_mcp.connector import WebSocketClient


async def benchmark(host: str, port: int, iterations: int, threshold_ms: float) -> int:
    """Run *iterations* dump_tree calls and report stats.

    Returns 0 if the median latency is ≤ *threshold_ms*, 1 otherwise.
    """
    client = WebSocketClient(host=host, port=port)
    await client.connect()
    caps = client.capabilities
    has_delta = caps.get("dump_tree_delta", False)
    print(f"Connected. Capabilities: {caps}")
    print(f"Running {iterations} iterations (threshold: {threshold_ms} ms)...")

    latencies: list[float] = []
    last_snap: str | None = None

    for i in range(iterations):
        t0 = time.perf_counter()

        if has_delta and last_snap is not None:
            result = await client.call("dump_tree_delta", {
                "since": last_snap,
                "include_invisible": False,
                "max_depth": -1,
            })
            if isinstance(result, dict):
                node_count = len(result.get("changed", []))
                full = result.get("full_snapshot", False)
                last_snap = result.get("snapshot_id", "")
            else:
                node_count = len(result) if isinstance(result, list) else 0
                full = True
        else:
            result = await client.call("dump_tree", {})
            node_count = len(result) if isinstance(result, list) else 0
            full = True

        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        if i % 10 == 0 or i == iterations - 1:
            mode = "full" if full else "delta"
            p50 = statistics.median(latencies) * 1000 if latencies else 0
            print(f"  [{i+1:4d}/{iterations}] {elapsed_ms:6.1f} ms  "
                  f"nodes={node_count:4d}  {mode:5s}  "
                  f"p50={p50/1000:6.1f} ms")

    await client.disconnect()

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]

    print()
    print(f"Results ({iterations} iterations):")
    print(f"  p50: {p50:6.1f} ms")
    print(f"  p95: {p95:6.1f} ms")
    print(f"  p99: {p99:6.1f} ms")
    print(f"  min: {latencies[0]:6.1f} ms")
    print(f"  max: {latencies[-1]:6.1f} ms")

    if p50 <= threshold_ms:
        print(f"  PASS: median {p50:.1f} ms ≤ threshold {threshold_ms} ms")
        return 0
    else:
        print(f"  FAIL: median {p50:.1f} ms > threshold {threshold_ms} ms")
        return 1


def main() -> int:
    p = argparse.ArgumentParser(description="dump_tree stress test")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=27842)
    p.add_argument("--iterations", type=int, default=100)
    p.add_argument("--threshold-ms", type=float, default=100.0,
                   help="Fail if median latency exceeds this (default: 100 ms)")
    args = p.parse_args()
    return asyncio.run(benchmark(
        args.host, args.port, args.iterations, args.threshold_ms))


if __name__ == "__main__":
    raise SystemExit(main())
