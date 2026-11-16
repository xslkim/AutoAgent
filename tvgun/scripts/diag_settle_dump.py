#!/usr/bin/env python3
"""停点事件时间线 dump（内部调试用）：围绕每个停点 ±1.2s 输出
t, raw_x/y, aim_x/y, anchor_x/y, grade, |ω|, w_ema| 到 CSV 供细查。
用法: python scripts/diag_settle_dump.py [rec] [event_idx]"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diag_smooth as ds  # noqa: E402
import diag_settle as dse  # noqa: E402
import guntrack as gt  # noqa: E402


def main():
    rec = sys.argv[1] if len(sys.argv) > 1 else "record_20261002_004842"
    ev_pick = int(sys.argv[2]) if len(sys.argv) > 2 else -1

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
            wema = float(np.linalg.norm(tr._w_ema - tr.bias))
            rows.append((next_out, x, y, ax, ay, g, wema))
            next_out += dt_out
        while gi < len(gts) and gts[gi] <= fts[s]:
            tr.on_gyro(gts[gi], *gw[gi])
            gi += 1
        tr.process(frames[s], fts[s])

    import pandas as pd
    out = pd.DataFrame(rows, columns=["t", "rx", "ry", "ax", "ay", "g", "wema"])
    df = pd.DataFrame(dict(ts=fts))
    # 真值锚点重新收集（analyze 里已有，这里简化直接重放时没存 meas——用 analyze 太慢，
    # 改为利用 process 帧循环结束后没存 meas_cross；此处直接标注 grade 即可）
    evs = dse.settle_events(gyro)
    print(f"{len(evs)} events; dumping windows")
    for ei, te in enumerate(evs):
        if ev_pick >= 0 and ei != ev_pick:
            continue
        m = (out["t"] * 1e-9 >= te - 0.8) & (out["t"] * 1e-9 <= te + 1.2)
        sub = out[m].copy()
        sub["t"] = (sub["t"] * 1e-9 - te).round(3)
        fp = str(ROOT / "out" / "settle" / f"settle_{rec}_ev{ei}.csv")
        Path(fp).parent.mkdir(parents=True, exist_ok=True)
        sub.to_csv(fp, index=False)
        print(f"ev{ei} t={te:.2f}s -> {fp} ({len(sub)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
