#!/usr/bin/env python3
"""相机↔陀螺时间戳偏移扫描：验证两路时钟是否存在会话级可变固定偏移。

假设背景：手机重启（或相机会话重开）后，camera2 时间戳域与陀螺
SensorEvent.timestamp 域之间可能出现不同的固定偏移，导致视觉校正
与陀螺积分错位，表现为融合飘移。

方法：对连续锁定帧对（未平滑 linefit 四角），把陀螺积分窗口相对帧
时间戳整体平移 δ（默认 -150~+150ms），比较每对的视觉角位移
（四角位移中位 / f）与陀螺积分角 |∫ω dt|；对每个 δ 拟合尺度 k
（吸收焦距误差），取归一化残差最小的 δ。若各录制最优 δ 明显不一致，
说明存在会话级时钟偏移，需要在线时间标定；若都 ≈0，则排除该假设。

用法:
  python scripts/diag_ts_offset.py --rec test_res/record_20261002_004842
  python scripts/diag_ts_offset.py --all test_res/record_*
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_record_replay import load_recording  # noqa: E402
from calib_prop import raw_quads  # noqa: E402


def gyro_angle(gts, gw, t0, t1):
    """[t0,t1] 内陀螺梯形积分角的模（rad）。"""
    m = (gts > t0) & (gts <= t1)
    if m.sum() < 2:
        return np.nan
    ts = np.concatenate([[t0], gts[m], [t1]])
    w = np.vstack([[gw[m][0]], gw[m], [gw[m][-1]]])
    dt = np.diff(ts) * 1e-9
    wmid = (w[:-1] + w[1:]) / 2
    return float(np.linalg.norm((wmid * dt[:, None]).sum(axis=0)))


def scan(rec: Path, d_lo=-0.150, d_hi=0.150, d_step=0.002):
    frames, idx, gyro, detect, meta = load_recording(rec)
    fov = float(meta.get("viewAngle", 67.94))
    f = 320.0 / np.tan(np.radians(fov) / 2)
    quads, locked = raw_quads(frames)
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    fts = idx["tsNs"].to_numpy()

    pairs = []  # (i, vision_angle_rad)
    for i in range(1, len(frames)):
        if not (locked[i] and locked[i - 1]):
            continue
        disp = np.linalg.norm(quads[i].reshape(4, 2) - quads[i - 1].reshape(4, 2), axis=1)
        va = float(np.median(disp)) / f
        if va * f < 1.0:  # <1px 的对被检测噪声主导
            continue
        pairs.append((i, va))
    if len(pairs) < 10:
        print(f"[{rec.name}] moving locked pairs too few: {len(pairs)}")
        return None

    deltas = np.arange(d_lo, d_hi + 1e-9, d_step)
    rows = []
    for d in deltas:
        ag, av = [], []
        for i, va in pairs:
            ga = gyro_angle(gts, gw, fts[i - 1] + d * 1e9, fts[i] + d * 1e9)
            if np.isnan(ga):
                continue
            ag.append(ga)
            av.append(va)
        ag = np.array(ag)
        av = np.array(av)
        # 拟合 av ≈ k*ag（k 吸收焦距/轴映射误差），归一化中位残差
        k = float(ag @ av / (ag @ ag)) if (ag @ ag) > 0 else 1.0
        err = float(np.median(np.abs(av - k * ag)) / np.median(av))
        rows.append((err, d, k))
    rows.sort(key=lambda r: r[0])
    err0 = min(rows, key=lambda r: abs(r[1]))
    best = rows[0]
    print(f"[{rec.name}] pairs={len(pairs)} bestδ={best[1]*1e3:+.0f}ms "
          f"err={best[0]:.3f} k={best[2]:.3f} | δ=0 err={err0[0]:.3f}")
    for e, d, k in rows[1:3]:
        print(f"    next: δ={d*1e3:+.0f}ms err={e:.3f}")
    return best, err0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec")
    ap.add_argument("--all", nargs="+")
    args = ap.parse_args()
    recs = []
    if args.rec:
        recs.append(Path(args.rec))
    for pat in args.all or []:
        recs.extend(sorted(ROOT.glob(pat)) if not Path(pat).is_absolute() else sorted(Path("/").glob(pat.lstrip("/"))))
    results = {}
    for rec in recs:
        r = scan(rec)
        if r:
            results[rec.name] = r
    if len(results) > 1:
        print("\n== 汇总（bestδ 跨会话是否一致）==")
        for name, (best, err0) in results.items():
            print(f"  {name}: bestδ={best[1]*1e3:+.0f}ms err={best[0]:.3f} (δ=0 err={err0[0]:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
