#!/usr/bin/env python3
"""失锁帧根因诊断：对指定帧 dump 粗检测内部状态 + 可视化 + 边直线度测量。

用法:
  .venv/Scripts/python.exe scripts/diag_unlock.py --rec test_res/record_wide_20260921_235354 --seqs 70 366 907
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_record_replay import ReplayDet, load_recording  # noqa: E402


def analyze_frame(g640, seq, out_dir, tag=""):
    det = ReplayDet("linefit")
    raw, stage, labels, best, low_thr = det._coarse_parts(g640)
    g = g640[::2, ::2]
    dh, dw = g.shape
    n = dw * dh
    print(f"--- seq {seq} ---")
    print(f"  thr={det.last_thr} low_thr={det.last_low_thr} stage={stage} "
          f"best_count={det.last_best_count} blob_frac={det.last_best_count / n:.4f}")

    # 连通域概览：前 8 大域的面积与种子数
    mask = (g >= low_thr).astype(np.uint8)
    nlab, lab2, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    hi_counts = np.bincount(lab2[g >= det.last_thr].ravel(), minlength=nlab)
    order = np.argsort(-stats[1:, cv2.CC_STAT_AREA])[:8] + 1
    for i in order:
        x, y, w, h, a = stats[i]
        print(f"  blob {i}: area={a} bbox=({x},{y},{w},{h}) seeds={hi_counts[i]}")

    # 可视化：原图 + 掩模 + 最优域 + 粗四角
    vis = cv2.cvtColor(g640, cv2.COLOR_GRAY2BGR)
    if best:
        ov = np.zeros((*g.shape, 3), np.uint8)
        ov[lab2 == best] = (0, 0, 255)
        ov = cv2.resize(ov, (640, 360), interpolation=cv2.INTER_NEAREST)
        vis = cv2.addWeighted(vis, 0.7, ov, 0.5, 0)
    if raw is not None:
        q = (raw.reshape(4, 2) * 2).astype(np.int32)
        cv2.polylines(vis, [q], True, (0, 255, 255), 1)
        for px, py in q:
            cv2.circle(vis, (px, py), 4, (0, 255, 0), -1)
    cv2.putText(vis, f"seq={seq} stage={stage} thr={det.last_thr}/{low_thr}",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    p = out_dir / f"diag_{tag}{seq:06d}.png"
    cv2.imwrite(str(p), vis)

    # 边直线度（畸变评估）：若粗四角合法，沿顶/左边宽带取亮像素测 TLS 残差
    if raw is not None:
        q640 = raw.reshape(4, 2) * 2.0
        for e, nm in ((0, "top"), (3, "left")):
            p0, p1 = q640[e], q640[(e + 1) % 4]
            d = p1 - p0
            L = np.hypot(*d)
            d = d / L
            nv = np.array([-d[1], d[0]])
            c = q640.mean(axis=0)
            if nv @ (p0 - c) < 0:
                nv = -nv
            yy, xx = np.nonzero(mask640 := (g640 >= low_thr))
            perp = (xx - p0[0]) * nv[0] + (yy - p0[1]) * nv[1]
            lon = (xx - p0[0]) * d[0] + (yy - p0[1]) * d[1]
            sel = (np.abs(perp) <= 15) & (lon >= 0) & (lon <= L)
            if sel.sum() < 50:
                print(f"  edge {nm}: too few px ({sel.sum()})")
                continue
            # 外包络点分箱
            bi = (lon[sel] / 3.0).astype(int)
            envx, envp = [], []
            for b in np.unique(bi):
                m = bi == b
                thr95 = np.percentile(perp[sel][m], 95)
                envx.append(lon[sel][m].mean())
                envp.append(perp[sel][m][perp[sel][m] >= thr95].mean())
            envx, envp = np.array(envx), np.array(envp)
            A = np.vstack([envx, np.ones_like(envx)]).T
            k, b0 = np.linalg.lstsq(A, envp, rcond=None)[0]
            res = envp - (k * envx + b0)
            print(f"  edge {nm}: L={L:.0f}px envelope-residual std={res.std():.2f}px "
                  f"max|res|={np.abs(res).max():.2f}px (弯曲/畸变指标)")
    return det


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True)
    ap.add_argument("--seqs", type=int, nargs="+", required=True)
    ap.add_argument("--out", default=str(ROOT / "out" / "diag"))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, idx, gyro, detect, meta = load_recording(Path(args.rec))
    print(f"meta: {meta}")
    tag = Path(args.rec).name[:12] + "_"
    for s in args.seqs:
        analyze_frame(frames[s], s, out_dir, tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
