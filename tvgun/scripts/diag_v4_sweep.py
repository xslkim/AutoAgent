#!/usr/bin/env python3
"""v4 输出平滑变体扫描（内部开发工具）：对每段录制逐个变体回放，
对比 aim 流（真机显示路径）的静止抖动/jerk/感知延迟。
用法: python scripts/diag_v4_sweep.py [--rec name ...] [--variant idx ...]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import guntrack as gt  # noqa: E402
import diag_smooth as ds  # noqa: E402

VARIANTS = [
    ("v3-base",      dict(out_mode="v3", predict_damp_tau=0.0,
                          predict_ema_tau=0.015, predict_decel_scale=False)),
    ("oe1.5-b.08",   dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.08)),
    ("oe1.5-b.02",   dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02)),
    ("oe1.0-b.02",   dict(out_mode="oneuro", oe_min_cutoff=1.0, oe_beta=0.02)),
    ("oe+damp.08",   dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02,
                          predict_damp_tau=0.08)),
    ("offset-.3",    dict(out_mode="offset", off_instant=0.3)),
    ("offset-0",     dict(out_mode="offset", off_instant=0.0)),
    ("oe+damp.06",   dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02,
                          predict_damp_tau=0.06)),
    ("oe1.0+damp.08", dict(out_mode="oneuro", oe_min_cutoff=1.0, oe_beta=0.02,
                          predict_damp_tau=0.08)),
    ("oe+damp.08+e.03", dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02,
                          predict_damp_tau=0.08, predict_ema_tau=0.03)),
    ("oe+damp.10",   dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02,
                          predict_damp_tau=0.10)),
    ("v4-final",     dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02,
                          predict_damp_tau=0.08, predict_ema_tau=0.03)),
    ("v4.1",         dict(out_mode="oneuro", oe_min_cutoff=1.5, oe_beta=0.02,
                          predict_damp_tau=0.08, predict_ema_tau=0.03,
                          predict_decel_scale=True)),
]

DEFAULT_RECS = ["record_20260921_230150", "record_wide_20260921_235354",
                "record_wide_20260925_214838", "record_wide_20260925_235333",
                "record_20260925_235405", "record_20260926_114948",
                "record_20260929_223451", "record_20260929_223525",
                "record_20260929_223638", "record_20261002_004842"]

KEYS = [("avail", "{:.1%}"), ("still_jitter_aim", "{:.2f}"),
        ("jerk_aim_p50", "{:.2f}"), ("jerk_aim_p95", "{:.1f}"),
        ("lag100_aim_med", "{:.1f}"), ("lag100_aim_p95", "{:.0f}")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", nargs="*", default=DEFAULT_RECS)
    ap.add_argument("--variant", nargs="*", type=int, default=None)
    args = ap.parse_args()
    vidx = args.variant if args.variant else range(len(VARIANTS))
    recs = [r for r in args.rec if ds.has_frames(r)]

    table = {}   # (variant, rec) -> metrics
    for vi in vidx:
        name, mod = VARIANTS[vi]
        for k, v in mod.items():
            setattr(gt.TrackerParams, k, v)
        for rec in recs:
            r, df, out = ds.analyze(rec, name, v3=True)
            table[(name, rec)] = r
            print(f"done {name} {rec}", flush=True)

    hdr = f"{'variant':12s} {'rec':28s}" + "".join(f"{k:>14s}" for k, _ in KEYS)
    print(hdr)
    for vi in vidx:
        name = VARIANTS[vi][0]
        for rec in recs:
            r = table[(name, rec)]
            row = f"{name:12s} {rec:28s}"
            for k, fmt in KEYS:
                row += f"{fmt.format(r[k]):>14s}"
            print(row)
        # 段间汇总（中位）
        vals = [table[(name, rec)] for rec in recs]
        row = f"{name:12s} {'-- median --':28s}"
        for k, fmt in KEYS:
            row += f"{fmt.format(float(np.nanmedian([v[k] for v in vals]))):>14s}"
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
