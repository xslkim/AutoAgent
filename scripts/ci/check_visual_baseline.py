#!/usr/bin/env python3
"""scripts/ci/check_visual_baseline.py — 防护 0.3 visual regression check.

Compare a candidate screenshot against a stored baseline PNG using SSIM
(Structural Similarity Index Measure).

Exit codes
----------
0  SSIM >= threshold  → images are visually identical (CI green)
1  SSIM <  threshold  → visual change detected (CI fail)
2  Usage / file error

A diff PNG is written to --save-diff (if provided) whenever the images fail
the threshold, highlighting the changed regions.

Usage
-----
  python scripts/ci/check_visual_baseline.py \\
      --baseline baselines/unity/windows/welcome_screen.png \\
      --current  /tmp/live_shot.png \\
      --threshold 0.95 \\
      --save-diff /tmp/diff.png

  # Batch mode — compare every *.png in a directory against its baseline:
  python scripts/ci/check_visual_baseline.py \\
      --baseline-dir baselines/unity/windows \\
      --current-dir  /tmp/shots/unity/windows \\
      --save-diff-dir /tmp/diffs/unity/windows

Integration with CI (source-audit.yml or unity-pr.yml)
-------------------------------------------------------
After the Unity test runner captures a screenshot via take_screenshot, pass
the resulting PNG as --current.  The script exits non-zero so GitHub Actions
marks the step as failed if the visual changed unexpectedly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# SSIM implementation (inline — avoids mcp-server import path dependency)
# ---------------------------------------------------------------------------

def _compare(path_a: Path, path_b: Path,
             threshold: float, save_diff: Path | None) -> tuple[float, bool]:
    """
    Return (ssim_score, passed).
    If save_diff is set and the images differ, write a diff PNG.
    Raises FileNotFoundError / ValueError on bad inputs.
    """
    try:
        import numpy as np
        from skimage import io as skio
        from skimage.color import rgb2gray
        from skimage.metrics import structural_similarity
    except ImportError as exc:
        print(f"ERROR: required package not installed — {exc}", file=sys.stderr)
        print("       pip install scikit-image", file=sys.stderr)
        sys.exit(2)

    def load_rgb(p: Path) -> "np.ndarray":
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {p}")
        img = skio.imread(str(p))
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]           # RGBA → RGB
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=2)   # grey → RGB
        if img.dtype != np.uint8:
            img = (np.clip(img.astype(float), 0.0, 1.0) * 255).astype(np.uint8)
        return img

    img_a = load_rgb(path_a)
    img_b = load_rgb(path_b)

    if img_a.shape != img_b.shape:
        raise ValueError(
            f"Size mismatch: {path_a.name} {img_a.shape[1]}×{img_a.shape[0]} "
            f"vs {path_b.name} {img_b.shape[1]}×{img_b.shape[0]}"
        )

    from skimage.color import rgb2gray as _rgb2gray

    def to_gray(img):
        return _rgb2gray(img.astype(np.float64) / 255.0)

    gray_a = to_gray(img_a)
    gray_b = to_gray(img_b)

    h, w = gray_a.shape
    win = min(7, h, w)
    if win % 2 == 0:
        win -= 1
    win = max(win, 3)

    score, ssim_map = structural_similarity(
        gray_a, gray_b, data_range=1.0, full=True, win_size=win,
    )
    score = float(score)
    passed = score >= threshold

    if save_diff is not None and not passed:
        diff = np.clip(1.0 - ssim_map, 0.0, 1.0)
        # Amplify diff for visibility: overlay on a red tint
        diff_u8 = (diff * 255).astype(np.uint8)
        red_overlay = np.zeros((*diff_u8.shape, 3), dtype=np.uint8)
        red_overlay[:, :, 0] = diff_u8   # red channel = diff intensity
        # Blend diff onto greyed-out base image
        grey_base = (img_a.astype(float) * 0.5).astype(np.uint8)
        composite = np.clip(
            grey_base.astype(int) + red_overlay.astype(int), 0, 255
        ).astype(np.uint8)
        save_diff.parent.mkdir(parents=True, exist_ok=True)
        skio.imsave(str(save_diff), composite, check_contrast=False)

    return score, passed


# ---------------------------------------------------------------------------
# Single-pair comparison
# ---------------------------------------------------------------------------

def compare_pair(baseline: Path, current: Path, threshold: float,
                 save_diff: Path | None, quiet: bool) -> bool:
    """
    Compare one pair. Returns True if passed.
    """
    try:
        score, passed = _compare(baseline, current, threshold, save_diff)
    except (FileNotFoundError, ValueError) as exc:
        print(f"  ERROR  {exc}", file=sys.stderr)
        return False

    status = "PASS" if passed else "FAIL"
    diff_note = ""
    if not passed and save_diff:
        diff_note = f"  diff → {save_diff}"

    if not quiet or not passed:
        print(f"  {status}  SSIM={score:.4f}  (threshold={threshold:.2f})"
              f"  {current.name}{diff_note}")

    return passed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_visual_baseline",
        description="SSIM visual regression check (防护 0.3).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ---- single-pair mode ----
    single = p.add_argument_group("Single-pair mode")
    single.add_argument("--baseline", type=Path,
                        help="Reference (baseline) PNG path.")
    single.add_argument("--current",  type=Path,
                        help="Candidate (current) PNG path.")
    single.add_argument("--save-diff", type=Path, metavar="PATH",
                        help="Where to write the diff PNG on failure.")

    # ---- batch mode ----
    batch = p.add_argument_group("Batch mode (compare every *.png in a directory)")
    batch.add_argument("--baseline-dir", type=Path,
                       help="Directory containing baseline PNGs.")
    batch.add_argument("--current-dir",  type=Path,
                       help="Directory containing current PNGs (same filenames).")
    batch.add_argument("--save-diff-dir", type=Path, metavar="DIR",
                       help="Directory for diff PNGs on failure.")

    # ---- engine convenience mode ----
    # Allows CI scripts to specify engine / platform / name instead of full paths:
    #   python check_visual_baseline.py \
    #       --engine ue --platform windows --name login_screen \
    #       --current /path/to/Saved/Automation/Comparisons/login_screen.png
    #
    # Engine → baselines subdirectory mapping:
    #   unity  → baselines/unity/{platform}/{name}.png
    #   ue     → baselines/unreal/{platform}/{name}.png
    #   godot  → baselines/godot/{platform}/{name}.png
    engine_grp = p.add_argument_group(
        "Engine convenience mode (resolves --baseline from engine/platform/name)"
    )
    engine_grp.add_argument(
        "--engine",
        choices=["unity", "ue", "godot"],
        help="Engine identifier — resolves the baseline directory automatically.",
    )
    engine_grp.add_argument(
        "--platform",
        choices=["windows", "linux", "mac"],
        default="windows",
        help="Target platform for baseline isolation (default: windows).",
    )
    engine_grp.add_argument(
        "--name",
        metavar="NAME",
        help="Screenshot stem (without .png). Required with --engine.",
    )
    engine_grp.add_argument(
        "--baselines-root",
        type=Path,
        default=Path("baselines"),
        metavar="DIR",
        help="Root directory for baseline trees (default: baselines/).",
    )

    # ---- common ----
    p.add_argument("--threshold", type=float, default=0.95,
                   help="SSIM pass threshold (default: 0.95).")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-file output for passing images.")

    return p


# ---------------------------------------------------------------------------
# Engine / platform path resolution
# ---------------------------------------------------------------------------

_ENGINE_DIR: dict[str, str] = {
    "unity": "unity",
    "ue":    "unreal",
    "godot": "godot",
}


def resolve_engine_paths(args: argparse.Namespace) -> int:
    """
    Populate ``args.baseline`` and (optionally) ``args.baseline_dir`` from
    ``--engine`` / ``--platform`` / ``--name`` when those convenience flags
    are provided.

    Returns 0 on success, 2 on usage error.
    """
    if not args.engine:
        return 0

    if not args.name:
        print("ERROR: --name is required when --engine is specified.", file=sys.stderr)
        print(
            "  Example: --engine ue --platform windows --name login_screen"
            " --current /path/to/login_screen.png",
            file=sys.stderr,
        )
        return 2

    engine_subdir = _ENGINE_DIR[args.engine]
    baseline_dir = args.baselines_root / engine_subdir / args.platform

    # Single-name mode → resolve to a single baseline PNG.
    args.baseline = baseline_dir / f"{args.name}.png"

    # Ensure --current is supplied (engine mode always needs one).
    if not getattr(args, "current", None):
        print(
            "ERROR: --current must be supplied together with --engine / --name.",
            file=sys.stderr,
        )
        return 2

    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # ---- engine convenience resolution (may set args.baseline) ----
    rc = resolve_engine_paths(args)
    if rc != 0:
        return rc

    threshold = args.threshold
    failed = 0
    compared = 0

    # ---- single-pair ----
    if args.baseline or args.current:
        if not args.baseline or not args.current:
            print("ERROR: --baseline and --current must both be supplied together.",
                  file=sys.stderr)
            return 2

        print(f"Comparing {args.baseline.name} vs {args.current.name} "
              f"(threshold={threshold:.2f})")
        passed = compare_pair(
            args.baseline, args.current, threshold,
            args.save_diff, args.quiet,
        )
        compared = 1
        if not passed:
            failed = 1

    # ---- batch ----
    elif args.baseline_dir or args.current_dir:
        if not args.baseline_dir or not args.current_dir:
            print("ERROR: --baseline-dir and --current-dir must both be supplied.",
                  file=sys.stderr)
            return 2

        baseline_pngs = sorted(args.baseline_dir.glob("*.png"))
        if not baseline_pngs:
            print(f"WARNING: no *.png files found in {args.baseline_dir}")
            return 0

        print(f"Batch comparing {len(baseline_pngs)} baseline(s) "
              f"from {args.baseline_dir}  (threshold={threshold:.2f})")

        for bpng in baseline_pngs:
            cpng = args.current_dir / bpng.name
            save_diff = (args.save_diff_dir / bpng.name) if args.save_diff_dir else None
            passed = compare_pair(bpng, cpng, threshold, save_diff, args.quiet)
            compared += 1
            if not passed:
                failed += 1

    else:
        print("ERROR: supply either (--baseline + --current) or "
              "(--baseline-dir + --current-dir).", file=sys.stderr)
        return 2

    # ---- summary ----
    print()
    print(f"Visual regression summary: {compared - failed}/{compared} passed")
    if failed:
        print(f"FAILED: {failed} image(s) changed beyond SSIM threshold {threshold:.2f}")
        return 1

    print(f"PASSED: all images within SSIM threshold {threshold:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
