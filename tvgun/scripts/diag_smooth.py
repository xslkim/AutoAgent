#!/usr/bin/env python3
"""流畅度/手感诊断 —— v3 融合核的量化基线与闭环验证器。

真值锚点法：FULL 帧 DLT 的未平滑测量准星 meas_cross 是"真实指向"的最好
观测（仅测量噪声，无平滑滞后）。锚点间线性插值得到任意时刻真实指向 a(t)。
  - 感知延迟误差：|o(t) - a(t+L)|（当前，o=120Hz 输出）vs
    |pred(t,L) - a(t+L)|（陀螺外推预测），L 扫描 66/100/133ms；
  - 跟踪器内禀滞后 τ：argmin_s median |o(t+s) - a(t)|；
  - 视觉测量噪声 σ_meas：静止段锚点抖动；
  - 静止抖动（帧率/120Hz）、FULL innov（30Hz 阶跃）、jerk、陀螺统计；
  - 零偏注入模式（--inject）：验证动态零偏估计的收敛方向与量级。

用法:
  .venv/Scripts/python.exe scripts/diag_smooth.py [--rec name] [--v3 0|1]
      [--tag baseline] [--save out/diag_x.json]
      [--inject 0.012,-0.008,0.006 --no-still-bias]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import guntrack as gt  # noqa: E402
from guntrack import (GRADE_DEAD, GRADE_FULL, GRADE_NAMES, Tracker, TrackerParams)  # noqa: E402
from run_record_replay import load_recording  # noqa: E402

RECS = ["record_20260921_230150", "record_wide_20260921_235354",
        "record_wide_20260925_214838", "record_wide_20260925_235333",
        "record_20260925_235405", "record_20260926_114948"]

SAMPLE_HZ = 120.0
LAG_MS = (66, 100, 133)
AIM_AHEAD_MS = 90.0      # 与真机 predictMs 默认值一致（显示/射击路径）
FEED_SLACK_NS = int(150e6)   # process 前的前瞻喂入（真机管道延迟）


def has_frames(rec):
    f = ROOT / "test_res" / rec / "frames.bin"
    if not f.exists():
        return False
    idx = pd.read_csv(ROOT / "test_res" / rec / "frames_idx.csv")
    return f.stat().st_size == len(idx) * 360 * 640


def replay(rec, v3=True, sample_hz=SAMPLE_HZ, inject=None, still_bias=True,
           gyro_shift_ns=0):
    """全程回放 + 帧间隔内 120Hz snapshot。aim 采样保持因果（只用 ≤ 采样
    时刻的陀螺）；process 前按真机管道延迟前瞻喂入（+150ms，与传感器
    回调实时喂入的真机等价——否则 δ̂>0 时每帧漏积 δ̂ 的旋转，td-on 被
    系统性冤枉）。snapshot_ahead 内部已按 ≤tgt 的最后 tick 算外推余量，
    前瞻样本不污染 aim 流。gyro_shift_ns：td 注入测试用时间戳平移。
    返回 (帧级 df, 高频输出 df{含 pred}, tracker, gyro df)。"""
    frames, idx, gyro, detect, meta = load_recording(ROOT / "test_res" / rec)
    fov = float(meta.get("viewAngle", 67.94))
    p = TrackerParams()
    p.fov_h_deg = fov
    p.v3 = v3
    if not still_bias:
        p.bias_alpha = 0.0
    tr = Tracker(p)
    gts = gyro["tsNs"].to_numpy() + int(gyro_shift_ns)
    gw = gyro[["wx", "wy", "wz"]].to_numpy().astype(np.float32)  # 与 Java float 一致
    if inject is not None:
        gw = gw + np.asarray(inject, dtype=float)
    fts = idx["tsNs"].to_numpy()
    gi = 0
    rows = []
    o_t, o_x, o_y, o_g = [], [], [], []
    o_aim_x, o_aim_y = [], []
    o_pred = {L: [] for L in LAG_MS}
    dt_out = 1e9 / sample_hz
    next_out = float(fts[0])
    for s in range(len(frames)):
        while next_out <= fts[s]:
            while gi < len(gts) and gts[gi] <= next_out:
                tr.on_gyro(gts[gi], *gw[gi])
                gi += 1
            # aim 流 = 真机显示/射击路径（snapshot_ahead + out_mode 平滑），先采样
            ax, ay, _ = tr.snapshot_ahead(int(next_out), int(AIM_AHEAD_MS * 1e6))
            o_aim_x.append(ax)
            o_aim_y.append(ay)
            x, y, g = tr.snapshot(int(next_out))
            o_t.append(next_out)
            o_x.append(x)
            o_y.append(y)
            o_g.append(g)
            for L in LAG_MS:
                o_pred[L].append(tr.snapshot_ahead(int(next_out), int(L * 1e6))
                                 if g > GRADE_DEAD else (np.nan, np.nan, g))
            next_out += dt_out
        while gi < len(gts) and gts[gi] <= fts[s] + FEED_SLACK_NS:
            tr.on_gyro(gts[gi], *gw[gi])
            gi += 1
        tr.process(frames[s], fts[s])
        rows.append(dict(seq=s, ts=fts[s], grade=tr.grade,
                         x=tr.cross[0], y=tr.cross[1],
                         meas_x=tr.meas_cross[0], meas_y=tr.meas_cross[1],
                         innov=tr.innov, innov_pre=tr.innov_pre,
                         g_eff=tr._g_eff_last, n_edges=tr.n_edges,
                         bx=tr.bias[0], by=tr.bias[1], bz=tr.bias[2],
                         td_ms=tr.td_ns * 1e-6))
    out = pd.DataFrame(dict(t=o_t, x=o_x, y=o_y, g=o_g,
                            aim_x=o_aim_x, aim_y=o_aim_y))
    for L in LAG_MS:
        arr = np.array([(p[0], p[1]) for p in o_pred[L]])
        out[f"pred{L}_x"] = arr[:, 0]
        out[f"pred{L}_y"] = arr[:, 1]
    return pd.DataFrame(rows), out, tr, gyro


def detrended_jitter(x, y, k=5):
    if len(x) < k * 3:
        return float("nan")
    ker = np.ones(k) / k
    rx = (x - np.convolve(x, ker, "same"))[k:-k]
    ry = (y - np.convolve(y, ker, "same"))[k:-k]
    return float(np.hypot(rx, ry).std())


def still_segments(gyro, min_dur=0.8, rate_thr=0.06):
    t = gyro["tsNs"].to_numpy() * 1e-9
    w = np.abs(gyro[["wx", "wy", "wz"]].to_numpy()).max(axis=1)
    still = w < rate_thr
    segs = []
    i = 0
    while i < len(t):
        if still[i]:
            j = i
            while j + 1 < len(t) and still[j + 1]:
                j += 1
            if t[j] - t[i] >= min_dur:
                segs.append((t[i], t[j]))
            i = j + 1
        else:
            i += 1
    return segs


class Anchors:
    """FULL 帧 meas_cross 锚点 + 线性插值（bracket gap ≤0.4s 才有效）。"""

    def __init__(self, df, max_gap=0.4e9):
        m = (df["grade"] == GRADE_FULL).to_numpy() \
            & np.isfinite(df["meas_x"].to_numpy())
        self.ta = df["ts"].to_numpy()[m]
        self.xa = df["meas_x"].to_numpy()[m]
        self.ya = df["meas_y"].to_numpy()[m]
        self.max_gap = max_gap

    def at(self, t_ns):
        i = int(np.searchsorted(self.ta, t_ns))
        if i == 0 or i >= len(self.ta):
            return None
        t0, t1 = self.ta[i - 1], self.ta[i]
        if t1 - t0 > self.max_gap:
            return None
        f = (t_ns - t0) / (t1 - t0)
        return np.array([self.xa[i - 1] + f * (self.xa[i] - self.xa[i - 1]),
                         self.ya[i - 1] + f * (self.ya[i] - self.ya[i - 1])])


def analyze(rec, tag, v3=True, inject=None, still_bias=True):
    df, out, tr, gyro = replay(rec, v3=v3, inject=inject, still_bias=still_bias)
    r = {"rec": rec, "tag": tag, "v3": v3, "frames": len(df)}
    valid = df["grade"] > GRADE_DEAD
    r["avail"] = float(valid.mean())
    r["grades"] = {GRADE_NAMES[k]: int((df["grade"] == k).sum()) for k in range(5)}

    fts = df["ts"].to_numpy()
    segs = still_segments(gyro)
    r["n_still_segs"] = len(segs)
    anc = Anchors(df)
    r["n_anchors"] = len(anc.ta)

    # 静止段：帧率抖动 / 120Hz 抖动 / σ_meas（锚点抖动）
    # （FULL-only 变体：GYRO 段的抖动受视角透视放大影响，随反馈路径混沌，
    #  跨版本不可比；公平对比只看 FULL 段）
    sj, sj120, smeas, sjf = [], [], [], []
    for a, b in segs:
        m = (fts * 1e-9 >= a) & (fts * 1e-9 <= b) & valid.to_numpy()
        if m.sum() >= 8:
            sj.append(detrended_jitter(df["x"].to_numpy()[m], df["y"].to_numpy()[m]))
        mf = m & (df["grade"] == GRADE_FULL).to_numpy()
        if mf.sum() >= 8:
            sjf.append(detrended_jitter(df["x"].to_numpy()[mf], df["y"].to_numpy()[mf]))
        mo = (out["t"].to_numpy() * 1e-9 >= a) & (out["t"].to_numpy() * 1e-9 <= b) \
            & (out["g"].to_numpy() > GRADE_DEAD)
        if mo.sum() >= 30:
            sj120.append(detrended_jitter(out["x"].to_numpy()[mo], out["y"].to_numpy()[mo]))
        ma = (anc.ta * 1e-9 >= a) & (anc.ta * 1e-9 <= b)
        if ma.sum() >= 8:
            smeas.append(detrended_jitter(anc.xa[ma], anc.ya[ma]))
    r["still_jitter_frame"] = float(np.nanmedian(sj)) if sj else float("nan")
    r["still_jitter_full"] = float(np.nanmedian(sjf)) if sjf else float("nan")
    r["still_jitter_120hz"] = float(np.nanmedian(sj120)) if sj120 else float("nan")
    r["sigma_meas"] = float(np.nanmedian(smeas)) if smeas else float("nan")

    # 平滑运动段（0.1<|ω|<0.8 rad/s）FULL 帧 MA7 去趋势抖动 —— 运动中稳定性
    gspd = np.abs(gyro[["wx", "wy", "wz"]].to_numpy()).max(axis=1)
    gtt = gyro["tsNs"].to_numpy()
    mvj = []
    spd_f = np.interp(fts, gtt, gspd)
    mm = (spd_f > 0.1) & (spd_f < 0.8) & (df["grade"] == GRADE_FULL).to_numpy()
    # 连续 FULL 子段
    idxs = np.flatnonzero(mm)
    if len(idxs):
        splits = np.split(idxs, np.flatnonzero(np.diff(idxs) > 1) + 1)
        for sub in splits:
            if len(sub) >= 12:
                mvj.append(detrended_jitter(df["x"].to_numpy()[sub],
                                            df["y"].to_numpy()[sub], k=7))
    r["move_jitter_full"] = float(np.nanmedian(mvj)) if mvj else float("nan")

    # FULL innov（30Hz 可见阶跃；innov_pre = 满增益创新量）
    for col, nm in (("innov", "full_innov"), ("innov_pre", "full_innov_pre")):
        iv = df[col].to_numpy()[(df["grade"] == GRADE_FULL).to_numpy()]
        iv = iv[np.isfinite(iv)]
        r[nm + "_med"] = float(np.median(iv)) if len(iv) else float("nan")
        r[nm + "_p95"] = float(np.percentile(iv, 95)) if len(iv) else float("nan")

    # 120Hz 输出 jerk（二阶差分）
    ov = (out["g"] > GRADE_DEAD).to_numpy()
    x = out["x"].to_numpy()
    y = out["y"].to_numpy()
    d2 = np.hypot(np.abs(np.diff(x, 2)), np.abs(np.diff(y, 2)))
    mv = ov[2:] & ov[1:-1] & ov[:-2]
    jerk = d2[mv]
    r["jerk_p50"] = float(np.percentile(jerk, 50)) if len(jerk) else float("nan")
    r["jerk_p95"] = float(np.percentile(jerk, 95)) if len(jerk) else float("nan")

    # aim 流（真机显示/射击路径 = snapshot_ahead(90ms) + out_mode 平滑）：
    # 静止抖动 / jerk / 感知延迟——用户实际看到摸到的量
    axs = out["aim_x"].to_numpy()
    ays = out["aim_y"].to_numpy()
    saj = []
    for a, b in segs:
        mo = (out["t"].to_numpy() * 1e-9 >= a) & (out["t"].to_numpy() * 1e-9 <= b) \
            & (out["g"].to_numpy() > GRADE_DEAD)
        if mo.sum() >= 30:
            saj.append(detrended_jitter(axs[mo], ays[mo]))
    r["still_jitter_aim"] = float(np.nanmedian(saj)) if saj else float("nan")
    d2a = np.hypot(np.abs(np.diff(axs, 2)), np.abs(np.diff(ays, 2)))
    ja = d2a[mv]
    r["jerk_aim_p50"] = float(np.percentile(ja, 50)) if len(ja) else float("nan")
    r["jerk_aim_p95"] = float(np.percentile(ja, 95)) if len(ja) else float("nan")
    la = []
    tt_a = out["t"].to_numpy()
    og_a = out["g"].to_numpy()
    for i in range(0, len(tt_a), 2):
        if og_a[i] <= GRADE_DEAD:
            continue
        a = anc.at(tt_a[i] + int(100e6))
        if a is None:
            continue
        la.append(float(np.hypot(axs[i] - a[0], ays[i] - a[1])))
    r["lag100_aim_med"] = float(np.median(la)) if la else float("nan")
    r["lag100_aim_p95"] = float(np.percentile(la, 95)) if la else float("nan")

    # 感知延迟误差（真值锚点法）：cur=|o(t)-a(t+L)|  pred=|pred(t,L)-a(t+L)|
    tt = out["t"].to_numpy()
    og = out["g"].to_numpy()
    ox = out["x"].to_numpy()
    oy = out["y"].to_numpy()
    for L in LAG_MS:
        cur, prd = [], []
        px = out[f"pred{L}_x"].to_numpy()
        py = out[f"pred{L}_y"].to_numpy()
        for i in range(0, len(tt), 2):
            if og[i] <= GRADE_DEAD:
                continue
            a = anc.at(tt[i] + int(L * 1e6))
            if a is None:
                continue
            cur.append(float(np.hypot(ox[i] - a[0], oy[i] - a[1])))
            if np.isfinite(px[i]):
                prd.append(float(np.hypot(px[i] - a[0], py[i] - a[1])))
        r[f"lag{L}_cur_med"] = float(np.median(cur)) if cur else float("nan")
        r[f"lag{L}_cur_p95"] = float(np.percentile(cur, 95)) if cur else float("nan")
        r[f"lag{L}_pred_med"] = float(np.median(prd)) if prd else float("nan")
        r[f"lag{L}_pred_p95"] = float(np.percentile(prd, 95)) if prd else float("nan")

    # 跟踪器内禀滞后 τ：argmin_s median |o(t+s) - a(t)|
    shifts = np.arange(0.0, 0.26, 1.0 / 120.0)
    err_s = []
    step_ns = 1e9 / SAMPLE_HZ
    for s in shifts:
        off = int(round(s * SAMPLE_HZ))
        es = []
        for i in range(0, len(tt) - off, 3):
            j = i + off
            if og[j] <= GRADE_DEAD:
                continue
            a = anc.at(tt[i])
            if a is None:
                continue
            es.append(float(np.hypot(ox[j] - a[0], oy[j] - a[1])))
        err_s.append(float(np.median(es)) if es else np.nan)
    err_s = np.array(err_s)
    if np.isfinite(err_s).any():
        k = int(np.nanargmin(err_s))
        r["tau_ms"] = float(shifts[k] * 1000)
        r["tau_err0"] = float(err_s[0])
        r["tau_errmin"] = float(err_s[k])
    else:
        r["tau_ms"] = r["tau_err0"] = r["tau_errmin"] = float("nan")

    # 陀螺统计
    gdt = np.diff(gyro["tsNs"].to_numpy()) * 1e-9
    r["gyro_hz"] = float(1.0 / np.median(gdt)) if len(gdt) else float("nan")
    wn = []
    for a, b in segs:
        m = (gyro["tsNs"].to_numpy() * 1e-9 >= a) & (gyro["tsNs"].to_numpy() * 1e-9 <= b)
        if m.sum() > 50:
            wn.append(gyro[["wx", "wy", "wz"]].to_numpy()[m].std(axis=0))
    if wn:
        r["gyro_noise"] = [float(v) for v in np.mean(wn, axis=0)]
    if len(df) > 10:
        r["bias_start"] = [float(df["bx"].iloc[10]), float(df["by"].iloc[10]),
                           float(df["bz"].iloc[10])]
        r["bias_end"] = [float(df["bx"].iloc[-1]), float(df["by"].iloc[-1]),
                         float(df["bz"].iloc[-1])]
    return r, df, out


def print_rec(r):
    print(f"== {r['rec']} [{r['tag']}] v3={r['v3']}")
    print(f"   avail={r['avail']:.1%} grades={r['grades']} anchors={r['n_anchors']}")
    print(f"   still: segs={r['n_still_segs']} jit_frame={r['still_jitter_frame']:.2f} "
          f"jit_full={r['still_jitter_full']:.2f} jit_120hz={r['still_jitter_120hz']:.2f} "
          f"σ_meas={r['sigma_meas']:.2f}px move_jit_full={r['move_jitter_full']:.2f}px")
    print(f"   FULL innov med={r['full_innov_med']:.2f} p95={r['full_innov_p95']:.2f} | "
          f"innov_pre med={r['full_innov_pre_med']:.2f} p95={r['full_innov_pre_p95']:.2f}px")
    print(f"   jerk p50={r['jerk_p50']:.3f} p95={r['jerk_p95']:.3f}px | "
          f"τ={r['tau_ms']:.0f}ms (err0={r['tau_err0']:.1f} -> errmin={r['tau_errmin']:.1f}px)")
    print(f"   aim流(显示路径): still_jit={r['still_jitter_aim']:.2f} "
          f"jerk p50={r['jerk_aim_p50']:.3f} p95={r['jerk_aim_p95']:.3f}px | "
          f"lag100 med={r['lag100_aim_med']:.1f} p95={r['lag100_aim_p95']:.1f}px")
    for L in LAG_MS:
        print(f"   lag{L}ms: cur med={r[f'lag{L}_cur_med']:.1f} p95={r[f'lag{L}_cur_p95']:.1f} | "
              f"pred med={r[f'lag{L}_pred_med']:.1f} p95={r[f'lag{L}_pred_p95']:.1f} px")
    print(f"   gyro {r['gyro_hz']:.0f}Hz noise={np.round(r.get('gyro_noise', [np.nan] * 3), 5)} "
          f"bias {np.round(r['bias_start'], 4) if r.get('bias_start') else None} -> "
          f"{np.round(r['bias_end'], 4) if r.get('bias_end') else None}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", default=None)
    ap.add_argument("--v3", type=int, default=1)
    ap.add_argument("--tag", default="diag")
    ap.add_argument("--save", default=None)
    ap.add_argument("--inject", default=None, help="bx,by,bz rad/s 注入陀螺")
    ap.add_argument("--no-still-bias", action="store_true")
    args = ap.parse_args()
    inject = [float(v) for v in args.inject.split(",")] if args.inject else None
    recs = [args.rec] if args.rec else RECS
    results = []
    for rec in recs:
        if not has_frames(rec):
            print(f"== {rec}: frames.bin 缺失或为 LFS 指针，跳过")
            continue
        r, df, out = analyze(rec, args.tag, v3=bool(args.v3), inject=inject,
                             still_bias=not args.no_still_bias)
        results.append(r)
        print_rec(r)
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"saved -> {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
