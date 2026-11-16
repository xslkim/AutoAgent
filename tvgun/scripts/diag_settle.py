#!/usr/bin/env python3
"""急停过冲/收敛诊断（内部开发工具）：量化"快速移动到位后漂移"。
事件 = |ω| 局部峰值 >0.8 rad/s（甩动）；到位时刻 = 峰后 |ω| 首次持续
<0.10 rad/s 达 150ms。到位后 raw 流与真值锚点误差仅 ~5px（已验证），
故直接量 |aim-raw|（= 输出级过冲/收敛尾巴，含预测+滤波）：
  到位 +0/50/100/200/400ms 的中位数。
用法: python scripts/diag_settle.py [--rec name ...] [--decel 0|1]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diag_smooth as ds  # noqa: E402
import guntrack as gt  # noqa: E402

DEFAULT_RECS = ["record_20261002_004842", "record_20260929_223451",
                "record_20260929_223638", "record_wide_20260925_235333"]
OFFSETS_MS = [0, 50, 100, 200, 400]


def find_events(gyro):
    """甩动事件：(t_peak, t_arrive)。到位 = 峰后平滑 |ω| 首次持续 <0.10 达 150ms；
    到位后 0.4s 内再起峰 >0.5 的事件丢弃（连甩，收敛被下一动作污染）。"""
    t = gyro["tsNs"].to_numpy() * 1e-9
    w = np.abs(gyro[["wx", "wy", "wz"]].to_numpy()).max(axis=1)
    ws = np.convolve(w, np.ones(5) / 5, "same")
    dt = float(np.median(np.diff(t)))
    sustain = int(0.15 / dt)
    evs = []
    i = 1
    while i < len(t) - 1:
        if ws[i] > 0.8 and ws[i] >= ws[i - 1] and ws[i] >= ws[i + 1]:
            tp = t[i]
            j = i + 1
            arrive = None
            while j < len(t) and t[j] - tp < 1.5:
                if ws[j] < 0.10:
                    jj = j
                    while jj < len(t) and ws[jj] < 0.10:
                        jj += 1
                    if jj - j >= sustain or jj == len(t):
                        arrive = t[j]
                        break
                    j = jj
                else:
                    j += 1
            if arrive is not None:
                j2 = int(np.searchsorted(t, arrive + 0.4))
                if ws[int(np.searchsorted(t, arrive)):j2].max() <= 0.5:
                    evs.append((tp, arrive))
                i = int(np.searchsorted(t, arrive)) + sustain
            else:
                i += 1
        else:
            i += 1
    return evs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", nargs="*", default=DEFAULT_RECS)
    ap.add_argument("--decel", type=int, default=None)
    ap.add_argument("--td", type=int, default=None, help="v5 在线时间标定开关")
    args = ap.parse_args()
    if args.decel is not None:
        gt.TrackerParams.predict_decel_scale = bool(args.decel)
    if args.td is not None:
        gt.TrackerParams.td_est = bool(args.td)

    for rec in args.rec:
        if not ds.has_frames(rec):
            print(f"== {rec}: 缺 frames，跳过")
            continue
        frames, idx, gyro, detect, meta = ds.load_recording(ROOT / "test_res" / rec)
        p = gt.TrackerParams()
        p.fov_h_deg = float(meta.get("viewAngle", 67.94))
        tr = gt.Tracker(p)
        gts = gyro["tsNs"].to_numpy()
        gw = gyro[["wx", "wy", "wz"]].to_numpy()
        fts = idx["tsNs"].to_numpy()
        gi = 0
        rows = []
        dt_out = 1e9 / 120.0
        next_out = float(fts[0])
        for s in range(len(frames)):
            while next_out <= fts[s]:
                while gi < len(gts) and gts[gi] <= next_out:
                    tr.on_gyro(gts[gi], *gw[gi])
                    gi += 1
                ax, ay, _ = tr.snapshot_ahead(int(next_out), int(90e6))
                x, y, g = tr.snapshot(int(next_out))
                rows.append((next_out, x, y, ax, ay, g))
                next_out += dt_out
            while gi < len(gts) and gts[gi] <= fts[s]:
                tr.on_gyro(gts[gi], *gw[gi])
                gi += 1
            tr.process(frames[s], fts[s])
        import pandas as pd
        out = pd.DataFrame(rows, columns=["t", "rx", "ry", "ax", "ay", "g"])
        ot = out["t"].to_numpy()
        div = np.hypot(out["ax"] - out["rx"], out["ay"] - out["ry"]).to_numpy()
        evs = find_events(gyro)
        print(f"== {rec}: {len(evs)} 甩动事件")
        row = "  |aim-raw| 中位 | "
        for off in OFFSETS_MS:
            vals = []
            for tp, ta in evs:
                tq = ta + off / 1000.0
                i = int(np.searchsorted(ot * 1e-9, tq))
                if i < len(ot) and out["g"].iloc[i] > gt.GRADE_DEAD:
                    vals.append(div[i])
            row += f"+{off:>3d}ms {np.median(vals):6.1f}" if vals else f"+{off:>3d}ms    nan"
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
