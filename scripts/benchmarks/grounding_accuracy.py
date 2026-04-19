#!/usr/bin/env python3
"""Grounding accuracy benchmark runner (§T J.5).

Measures the hit rate of a VLM grounding backend against manually-annotated
bounding boxes defined in ``tests/benchmarks/grounding/targets.yaml``.

Usage:
    # Run with ShowUI-2B on default endpoint (localhost:8001)
    python scripts/benchmarks/grounding_accuracy.py

    # Use a custom endpoint
    python scripts/benchmarks/grounding_accuracy.py --endpoint http://gpu-server:8001/v1

    # Use a specific screenshot directory
    python scripts/benchmarks/grounding_accuracy.py --screenshots ./my_screenshots

    # Skip screenshot generation (use existing files)
    python scripts/benchmarks/grounding_accuracy.py --no-generate

Acceptance criterion: overall hit rate >= 85%.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent.parent  # project root
_TARGETS_YAML = _ROOT / "tests" / "benchmarks" / "grounding" / "targets.yaml"
_SCREENSHOTS_DIR = _ROOT / "tests" / "benchmarks" / "grounding"
_RESULTS_MD = _ROOT / "tests" / "benchmarks" / "grounding_accuracy.md"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Target:
    """A single grounding benchmark target."""

    id: str
    query: str
    bbox: tuple[int, int, int, int]  # (x_min, y_min, x_max, y_max)
    category: str


@dataclass
class TargetGroup:
    """A group of targets sharing one screenshot."""

    application: str
    screenshot: str
    description: str
    targets: list[Target] = field(default_factory=list)


@dataclass
class HitResult:
    """Result of a single grounding query."""

    target_id: str
    query: str
    category: str
    expected_bbox: tuple[int, int, int, int]
    predicted_x: int
    predicted_y: int
    confidence: float
    hit: bool
    latency_ms: float
    error: str | None = None


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def load_targets(path: Path) -> list[TargetGroup]:
    """Load target groups from the YAML definition file."""
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    groups: list[TargetGroup] = []
    for doc in docs:
        if doc is None:
            continue
        group = TargetGroup(
            application=doc["application"],
            screenshot=doc["screenshot"],
            description=doc.get("description", ""),
        )
        for t in doc.get("targets", []):
            bbox = tuple(t["bbox"])
            group.targets.append(
                Target(
                    id=t["id"],
                    query=t["query"],
                    bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                    category=t.get("category", "unknown"),
                )
            )
        groups.append(group)
    return groups


# ---------------------------------------------------------------------------
# Placeholder screenshot generation
# ---------------------------------------------------------------------------


def generate_placeholder_screenshots(groups: list[TargetGroup], screenshots_dir: Path) -> None:
    """Generate simple placeholder PNG screenshots if real ones don't exist.

    Each screenshot is a white image with labeled bounding boxes drawn.
    Requires Pillow (PIL).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print(
            "WARNING: Pillow not installed. Cannot generate placeholder screenshots.",
            file=sys.stderr,
        )
        return

    for group in groups:
        screenshot_path = screenshots_dir / group.screenshot
        if screenshot_path.exists():
            continue

        # Determine image size from the largest bbox
        max_x = max(t.bbox[2] for t in group.targets) + 40
        max_y = max(t.bbox[3] for t in group.targets) + 40
        width = max(max_x, 800)
        height = max(max_y, 600)

        img = Image.new("RGB", (width, height), (240, 240, 240))
        draw = ImageDraw.Draw(img)

        # Try to use a basic font
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except (IOError, OSError):
            font = ImageFont.load_default()

        for t in group.targets:
            x0, y0, x1, y1 = t.bbox
            # Draw box outline
            draw.rectangle([x0, y0, x1, y1], outline=(0, 0, 255), width=2)
            # Draw label
            draw.text((x0, y1 + 2), f"{t.id} [{t.category}]", fill=(0, 0, 0), font=font)

        # Draw application title
        draw.text((10, height - 30), f"PLACEHOLDER: {group.application}", fill=(128, 0, 0), font=font)

        img.save(screenshot_path, "PNG")
        print(f"  Generated placeholder: {screenshot_path}")


# ---------------------------------------------------------------------------
# Grounding backend creation
# ---------------------------------------------------------------------------


def create_backend(
    backend_type: str = "showui",
    model: str = "showlab/ShowUI-2B",
    endpoint: str = "http://localhost:8001/v1",
    confidence_threshold: float = 0.5,
):
    """Create a grounding backend instance."""
    if backend_type == "showui":
        from autovisiontest.backends.showui import ShowUIGroundingBackend

        return ShowUIGroundingBackend(
            model=model,
            endpoint=endpoint,
            confidence_threshold=confidence_threshold,
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def check_hit(px: int, py: int, bbox: tuple[int, int, int, int]) -> bool:
    """Check if predicted point falls within the ground-truth bbox (inclusive)."""
    x_min, y_min, x_max, y_max = bbox
    return x_min <= px <= x_max and y_min <= py <= y_max


def run_benchmark(
    groups: list[TargetGroup],
    backend,
    screenshots_dir: Path,
) -> list[HitResult]:
    """Run grounding queries for all targets and collect results."""
    results: list[HitResult] = []

    for group in groups:
        screenshot_path = screenshots_dir / group.screenshot
        if not screenshot_path.exists():
            print(f"  SKIP {group.application}: screenshot not found ({screenshot_path})")
            for t in group.targets:
                results.append(
                    HitResult(
                        target_id=t.id,
                        query=t.query,
                        category=t.category,
                        expected_bbox=t.bbox,
                        predicted_x=0,
                        predicted_y=0,
                        confidence=0.0,
                        hit=False,
                        latency_ms=0.0,
                        error="screenshot_not_found",
                    )
                )
            continue

        image_bytes = screenshot_path.read_bytes()
        print(f"\n  [{group.application}] ({len(group.targets)} targets)")

        for t in group.targets:
            t_start = time.perf_counter()
            try:
                resp = backend.ground(image_bytes, t.query)
                latency_ms = (time.perf_counter() - t_start) * 1000.0
                hit = check_hit(resp.x, resp.y, t.bbox)
                result = HitResult(
                    target_id=t.id,
                    query=t.query,
                    category=t.category,
                    expected_bbox=t.bbox,
                    predicted_x=resp.x,
                    predicted_y=resp.y,
                    confidence=resp.confidence,
                    hit=hit,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                latency_ms = (time.perf_counter() - t_start) * 1000.0
                result = HitResult(
                    target_id=t.id,
                    query=t.query,
                    category=t.category,
                    expected_bbox=t.bbox,
                    predicted_x=0,
                    predicted_y=0,
                    confidence=0.0,
                    hit=False,
                    latency_ms=latency_ms,
                    error=str(exc),
                )

            status = "HIT" if result.hit else "MISS"
            print(
                f"    {status}  {t.id:30s}  "
                f"pred=({result.predicted_x}, {result.predicted_y})  "
                f"bbox={t.bbox}  "
                f"conf={result.confidence:.2f}  "
                f"{result.latency_ms:.0f}ms"
            )
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def compute_metrics(results: list[HitResult]) -> dict:
    """Compute aggregate metrics from results."""
    total = len(results)
    if total == 0:
        return {"total": 0, "hits": 0, "hit_rate": 0.0}

    hits = sum(1 for r in results if r.hit)
    errors = sum(1 for r in results if r.error is not None)
    latencies = [r.latency_ms for r in results if r.error is None]

    metrics = {
        "total": total,
        "hits": hits,
        "misses": total - hits,
        "errors": errors,
        "hit_rate": hits / total,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "min_latency_ms": min(latencies) if latencies else 0,
    }

    # Per-category breakdown
    categories: dict[str, dict] = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"total": 0, "hits": 0}
        categories[cat]["total"] += 1
        if r.hit:
            categories[cat]["hits"] += 1
    metrics["per_category"] = {
        cat: {**v, "hit_rate": v["hits"] / v["total"] if v["total"] else 0}
        for cat, v in categories.items()
    }

    # Per-application breakdown
    apps: dict[str, dict] = {}
    # Map target IDs to applications (via prefix)
    for r in results:
        app = "unknown"
        if r.target_id.startswith("notepad-"):
            app = "notepad"
        elif r.target_id.startswith("calc-"):
            app = "calculator"
        if app not in apps:
            apps[app] = {"total": 0, "hits": 0}
        apps[app]["total"] += 1
        if r.hit:
            apps[app]["hits"] += 1
    metrics["per_application"] = {
        app: {**v, "hit_rate": v["hits"] / v["total"] if v["total"] else 0}
        for app, v in apps.items()
    }

    return metrics


def print_report(results: list[HitResult], metrics: dict) -> None:
    """Print a summary report to stdout."""
    hr = metrics["hit_rate"]
    status = "PASS" if hr >= 0.85 else "FAIL"

    print("\n" + "=" * 70)
    print(f"  Grounding Accuracy Benchmark — {status}")
    print("=" * 70)
    print(f"  Total queries:   {metrics['total']}")
    print(f"  Hits:            {metrics['hits']}")
    print(f"  Misses:          {metrics['misses']}")
    print(f"  Errors:          {metrics['errors']}")
    print(f"  Hit rate:        {hr:.1%}  (threshold: 85%)")
    print(f"  Avg latency:     {metrics['avg_latency_ms']:.0f} ms")
    print(f"  Max latency:     {metrics['max_latency_ms']:.0f} ms")
    print()

    # Per-application
    print("  Per-application:")
    for app, v in metrics.get("per_application", {}).items():
        print(f"    {app:20s}  {v['hit_rate']:.1%}  ({v['hits']}/{v['total']})")
    print()

    # Per-category
    print("  Per-category:")
    for cat, v in metrics.get("per_category", {}).items():
        print(f"    {cat:20s}  {v['hit_rate']:.1%}  ({v['hits']}/{v['total']})")
    print()

    # Miss details
    misses = [r for r in results if not r.hit]
    if misses:
        print("  Miss details:")
        for r in misses:
            detail = f"    {r.target_id:30s}  pred=({r.predicted_x}, {r.predicted_y})"
            if r.error:
                detail += f"  ERROR: {r.error}"
            else:
                detail += f"  bbox={r.expected_bbox}"
            print(detail)

    print("=" * 70)


def write_results_md(
    results: list[HitResult],
    metrics: dict,
    backend_info: dict,
    output_path: Path,
) -> None:
    """Write results to a Markdown file."""
    hr = metrics["hit_rate"]
    status = "PASS" if hr >= 0.85 else "FAIL"

    lines: list[str] = [
        "# Grounding Accuracy Benchmark Results (§T J.5)",
        "",
        f"**Status**: {status}",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Hit rate**: {hr:.1%} ({metrics['hits']}/{metrics['total']})",
        f"**Threshold**: 85%",
        "",
        "## Backend Configuration",
        "",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| Backend   | {backend_info.get('type', 'N/A')} |",
        f"| Model     | {backend_info.get('model', 'N/A')} |",
        f"| Endpoint  | {backend_info.get('endpoint', 'N/A')} |",
        "",
        "## Overall Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total queries | {metrics['total']} |",
        f"| Hits | {metrics['hits']} |",
        f"| Misses | {metrics['misses']} |",
        f"| Errors | {metrics['errors']} |",
        f"| Hit rate | {hr:.1%} |",
        f"| Avg latency | {metrics['avg_latency_ms']:.0f} ms |",
        f"| Max latency | {metrics['max_latency_ms']:.0f} ms |",
        "",
        "## Per-Application Breakdown",
        "",
        "| Application | Hit Rate | Hits / Total |",
        "|-------------|----------|-------------|",
    ]

    for app, v in metrics.get("per_application", {}).items():
        lines.append(f"| {app} | {v['hit_rate']:.1%} | {v['hits']} / {v['total']} |")

    lines.extend([
        "",
        "## Per-Category Breakdown",
        "",
        "| Category | Hit Rate | Hits / Total |",
        "|----------|----------|-------------|",
    ])

    for cat, v in metrics.get("per_category", {}).items():
        lines.append(f"| {cat} | {v['hit_rate']:.1%} | {v['hits']} / {v['total']} |")

    lines.extend([
        "",
        "## Detailed Results",
        "",
        "| Target ID | Query | Predicted | Expected bbox | Hit | Confidence | Latency |",
        "|-----------|-------|-----------|--------------|-----|------------|---------|",
    ])

    for r in results:
        pred = f"({r.predicted_x}, {r.predicted_y})" if not r.error else "ERROR"
        bbox_str = f"({r.expected_bbox[0]}, {r.expected_bbox[1]}, {r.expected_bbox[2]}, {r.expected_bbox[3]})"
        hit_str = "YES" if r.hit else ("ERR" if r.error else "NO")
        error_suffix = f" ({r.error})" if r.error else ""
        lines.append(
            f"| {r.target_id} | {r.query} | {pred} | {bbox_str} | {hit_str} | "
            f"{r.confidence:.2f} | {r.latency_ms:.0f} ms{error_suffix} |"
        )

    lines.extend(["", "---", f"*Generated by grounding_accuracy.py*"])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grounding accuracy benchmark runner (§T J.5)",
    )
    parser.add_argument(
        "--targets",
        type=Path,
        default=_TARGETS_YAML,
        help="Path to targets.yaml (default: tests/benchmarks/grounding/targets.yaml)",
    )
    parser.add_argument(
        "--screenshots",
        type=Path,
        default=_SCREENSHOTS_DIR,
        help="Directory containing screenshot PNG files",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://localhost:8001/v1",
        help="Grounding model endpoint URL",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="showlab/ShowUI-2B",
        help="Model name for the grounding backend",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="showui",
        choices=["showui"],
        help="Grounding backend type",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.5,
        help="Minimum confidence threshold",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_RESULTS_MD,
        help="Path to write results Markdown file",
    )
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Skip placeholder screenshot generation",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also output results as JSON to stdout",
    )

    args = parser.parse_args()

    # 1. Load targets
    print(f"Loading targets from: {args.targets}")
    groups = load_targets(args.targets)
    total_targets = sum(len(g.targets) for g in groups)
    print(f"  {len(groups)} applications, {total_targets} targets")

    # 2. Generate placeholder screenshots if needed
    if not args.no_generate:
        print("\nChecking screenshots...")
        generate_placeholder_screenshots(groups, args.screenshots)
    else:
        print("\nSkipping screenshot generation (--no-generate)")

    # 3. Create grounding backend
    print(f"\nCreating grounding backend: {args.backend}")
    print(f"  Model: {args.model}")
    print(f"  Endpoint: {args.endpoint}")

    try:
        backend = create_backend(
            backend_type=args.backend,
            model=args.model,
            endpoint=args.endpoint,
            confidence_threshold=args.confidence_threshold,
        )
    except Exception as exc:
        print(f"ERROR: Failed to create backend: {exc}", file=sys.stderr)
        print("Hint: Make sure the grounding model service is running.", file=sys.stderr)
        return 1

    # 4. Run benchmark
    print("\nRunning benchmark...")
    results = run_benchmark(groups, backend, args.screenshots)

    # 5. Compute metrics and report
    metrics = compute_metrics(results)
    print_report(results, metrics)

    # 6. Write results MD
    backend_info = {
        "type": args.backend,
        "model": args.model,
        "endpoint": args.endpoint,
    }
    write_results_md(results, metrics, backend_info, args.output)

    # 7. Optional JSON output
    if args.json:
        json_output = {
            "metrics": {
                k: v for k, v in metrics.items()
                if k not in ("per_category", "per_application")
            },
            "per_category": metrics.get("per_category", {}),
            "per_application": metrics.get("per_application", {}),
            "results": [
                {
                    "target_id": r.target_id,
                    "query": r.query,
                    "category": r.category,
                    "expected_bbox": list(r.expected_bbox),
                    "predicted_x": r.predicted_x,
                    "predicted_y": r.predicted_y,
                    "confidence": r.confidence,
                    "hit": r.hit,
                    "latency_ms": round(r.latency_ms, 1),
                    "error": r.error,
                }
                for r in results
            ],
        }
        print("\n--- JSON OUTPUT ---")
        print(json.dumps(json_output, indent=2))

    # Exit code: 0 if pass, 1 if fail
    return 0 if metrics["hit_rate"] >= 0.85 else 1


if __name__ == "__main__":
    sys.exit(main())
