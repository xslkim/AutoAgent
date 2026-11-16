#!/usr/bin/env python3
"""追踪器 v2（guntrack.Tracker）录制回放评测 —— 闭环开发主入口。

指标：
  - 可用率：grade!=DEAD 帧占比（总体 / 分等级统计）
  - 静止抖动：seq5-55 段准星 std（去 MA5 趋势），目标 ≤0.4 规范 px
  - 精度：相对 linefit 参考（旧算法锁定帧）的偏差 median/P95（分等级）
  - 再锁定误差：GYRO->视觉 转换帧的校正量（= 陀螺累积漂移）
  - 伪失锁 Monte Carlo：状态快照+恢复，随机挖窗 0.2~3s，窗末 |输出-参考| 误差
  - 耗时：ms/帧（Python 参考值，Java 约同量级）

用法:
  .venv/Scripts/python.exe scripts/run_track_replay.py --rec test_res/record_20260921_230150
  .venv/Scripts/python.exe scripts/run_track_replay.py --rec test_res/record_wide_20260921_235354
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import guntrack as gt  # noqa: E402
from guntrack import (GRADE_DEAD, GRADE_GYRO, GRADE_EDGE, GRADE_PARTIAL,  # noqa: E402
                      GRADE_FULL, GRADE_NAMES, Tracker, TrackerParams)
from run_record_replay import load_recording  # noqa: E402


def run_tracker(frames, idx, gyro, fov_h, suppress_mask=None, v3=True, bias_dyn=True):
    """全程回放。suppress_mask[i]=True 时第 i 帧抑制视觉（仅陀螺传播）。
    返回 (DataFrame, tracker)。"""
    p = TrackerParams()
    p.fov_h_deg = fov_h
    p.v3 = v3
    p.bias_dyn = bias_dyn
    tr = Tracker(p)
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy().astype(np.float32)  # 与 Java float 一致
    fts = idx["tsNs"].to_numpy()
    gi = 0
    rows = []
    for s in range(len(frames)):
        # 前瞻喂入 +150ms（真机管道延迟，与 diag_smooth.replay 一致；
        # 否则 δ̂>0 时每帧漏积 δ̂ 的旋转）
        while gi < len(gts) and gts[gi] <= fts[s] + 150_000_000:
            tr.on_gyro(gts[gi], *gw[gi])
            gi += 1
        if suppress_mask is not None and suppress_mask[s]:
            # 抑制视觉：传播后跳过测量/采集（手动内联 process 的传播段）
            _propagate_only(tr, fts[s])
        else:
            tr.process(frames[s], fts[s])
        rows.append({"seq": s, "grade": tr.grade, "n_edges": tr.n_edges,
                     "cross_x": tr.cross[0], "cross_y": tr.cross[1],
                     "innov": tr.innov, "acq_cand": tr.acq_candidate,
                     "bias_x": tr.bias[0], "bias_y": tr.bias[1], "bias_z": tr.bias[2]})
    return pd.DataFrame(rows), tr


def _propagate_only(tr: Tracker, ts_ns):
    """process() 的无视觉变体：惰性传播到 ts_ns + 等级衰减与输出。
    （v5：与 process 一致加 δ̂ 对齐陀螺时钟）"""
    tr._propagate_to(ts_ns + int(round(tr.td_ns)))
    tr.t = ts_ns * 1e-9
    tr.edges_meas = []
    tr.innov = np.nan
    tr.n_edges = 0
    if tr.H is None:
        tr.grade = GRADE_DEAD
        tr.cross[:] = np.nan
        return
    if tr.t - tr.last_vision_t > tr.P.t_gyro_max:
        tr.grade = GRADE_DEAD
        tr.H = None
        tr.cross[:] = np.nan
        return
    tr.grade = GRADE_GYRO
    c = tr.H @ np.array([640.0 / 2, 360.0 / 2, 1.0])
    tr.cross = c[:2] / c[2]


def snapshot(tr: Tracker):
    return (tr.H.copy() if tr.H is not None else None, tr.grade,
            tr.bias.copy(), tr.last_vision_t, tr.cross.copy(), tr.n_edges)


def restore(tr: Tracker, snap):
    tr.H = snap[0].copy() if snap[0] is not None else None
    tr.grade = snap[1]
    tr.bias = snap[2].copy()
    tr.last_vision_t = snap[3]
    tr.cross = snap[4].copy()
    tr.n_edges = snap[5]


def jitter_std(x, y):
    if len(x) < 10:
        return float("nan")
    k = np.ones(5) / 5
    rx = (x - np.convolve(x, k, "same"))[2:-2]
    ry = (y - np.convolve(y, k, "same"))[2:-2]
    return float(np.hypot(rx, ry).std())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--mc", type=int, default=25, help="每档窗长的 MC 窗数")
    ap.add_argument("--v2", action="store_true", help="关闭 v3 融合核（基线对照）")
    ap.add_argument("--bias-dyn", type=int, default=1, help="v3 连续零偏估计开关")
    args = ap.parse_args(argv)
    rec = Path(args.rec)
    out_dir = Path(args.out) if args.out else ROOT / "out" / f"track_{rec.name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames, idx, gyro, detect, meta = load_recording(rec)
    fov = float(meta.get("viewAngle", 67.94))
    n = len(frames)
    print(f"recording: {rec.name} {n} frames, fov={fov}")

    t0 = time.monotonic()
    df, tr = run_tracker(frames, idx, gyro, fov, v3=not args.v2, bias_dyn=bool(args.bias_dyn))
    dt_ms = (time.monotonic() - t0) * 1000 / n
    df.to_csv(out_dir / "track_replay.csv", index=False)
    print(f"[track] {dt_ms:.1f} ms/frame")

    # ---- 可用率
    grades = df["grade"].value_counts().to_dict()
    valid = float((df["grade"] > GRADE_DEAD).mean())
    ghist = {GRADE_NAMES[k]: int(grades.get(k, 0)) for k in range(5)}
    print(f"[metric] availability: {valid:.1%} valid; grades {ghist}")

    # ---- 参考（旧 linefit 回放，仅老录制存在且帧数匹配时用）
    ref_path = ROOT / "out" / ("replay_main" if "wide" not in rec.name else "replay_wide")
    ref = None
    if (ref_path / "linefit_replay.csv").exists():
        _ref = pd.read_csv(ref_path / "linefit_replay.csv")
        if len(_ref) == n:
            ref = _ref

    # ---- 静止段抖动（tracker 输出 + 参考）
    s0, s1 = 5, 55
    seg = df.iloc[s0:s1]
    jit = jitter_std(seg["cross_x"].to_numpy(), seg["cross_y"].to_numpy()) \
        if (seg["grade"] > GRADE_DEAD).all() else float("nan")
    print(f"[metric] still jitter (seq5-55): {jit:.3f} norm px")

    # ---- 精度 vs linefit 参考（过滤参考的错锁帧：准星超出合理范围的帧不可信，
    # 实测 linefit 会把灯具/桌面错锁成 (-5785,-642) 之类的值）
    acc = {}
    if ref is not None:
        plausible = ref["locked"].to_numpy() \
            & ref["cross_x"].between(-300, 2220).to_numpy() \
            & ref["cross_y"].between(-300, 1380).to_numpy()
        m = plausible & (df["grade"] > GRADE_DEAD).to_numpy()
        dx = df.loc[m, "cross_x"].to_numpy() - ref.loc[m, "cross_x"].to_numpy()
        dy = df.loc[m, "cross_y"].to_numpy() - ref.loc[m, "cross_y"].to_numpy()
        dd = np.hypot(dx, dy)
        acc["vs_linefit_median"] = float(np.median(dd))
        acc["vs_linefit_p95"] = float(np.percentile(dd, 95))
        acc["vs_linefit_note"] = "参考错锁帧已剔除（|cross| 超界）；剩余偏差含参考自身噪声"
        print(f"[metric] vs linefit ref (plausible only): median {np.median(dd):.2f} "
              f"P95 {np.percentile(dd, 95):.2f} (n={m.sum()})")
        # 分等级
        for gd, nm in ((GRADE_FULL, "FULL"), (GRADE_PARTIAL, "PARTIAL"),
                       (GRADE_EDGE, "EDGE"), (GRADE_GYRO, "GYRO")):
            mm = m & (df["grade"] == gd).to_numpy()
            if mm.sum() > 5:
                d2 = np.hypot(df.loc[mm, "cross_x"] - ref.loc[mm, "cross_x"],
                              df.loc[mm, "cross_y"] - ref.loc[mm, "cross_y"])
                acc[f"vs_linefit_{nm}"] = float(np.median(d2))
                print(f"    {nm:8s}: n={mm.sum():4d} median {np.median(d2):6.2f} "
                      f"P95 {np.percentile(d2, 95):6.2f}")

    # ---- 再锁定误差（GYRO -> 视觉 的转换帧 innov）
    g = df["grade"].to_numpy()
    relock = (g[1:] >= GRADE_EDGE) & (g[:-1] == GRADE_GYRO)
    relock_idx = np.flatnonzero(relock) + 1
    rin = df["innov"].to_numpy()[relock_idx]
    rin = rin[np.isfinite(rin)]
    if len(rin):
        print(f"[metric] relock corrections: n={len(rin)} median {np.median(rin):.1f} "
              f"P95 {np.percentile(rin, 95):.1f} norm px (slew 限幅前)")

    # ---- 伪失锁 MC：窗末误差（顺序扫描+定点快照）
    mc_df = mc_pass(frames, idx, gyro, fov, df, args.mc, durs=[0.2, 0.5, 1.0, 2.0, 3.0],
                    v3=not args.v2, bias_dyn=bool(args.bias_dyn))
    if len(mc_df):
        mc_df.to_csv(out_dir / "dropout_mc.csv", index=False)
        tab = mc_df.groupby("dur")["err"].agg(["median", lambda v: np.percentile(v, 95), "count"])
        print("[metric] dropout MC window-end err (norm px):")
        print(tab.round(1).to_string())

    # ---- 图
    fts = idx["tsNs"].to_numpy()
    fig, axes = plt.subplots(3, 1, figsize=(15, 9), sharex=True,
                             gridspec_kw={"height_ratios": [0.8, 1.4, 1.4]})
    t = (fts - fts[0]) * 1e-9
    colors = {GRADE_FULL: 4, GRADE_PARTIAL: 3, GRADE_EDGE: 2, GRADE_GYRO: 1, GRADE_DEAD: 0}
    axes[0].fill_between(t, 0, df["grade"].map(colors), step="post", color="g", alpha=0.5)
    axes[0].set_yticks([0, 1, 2, 3, 4])
    axes[0].set_yticklabels(["DEAD", "GYRO", "EDGE", "PART", "FULL"], fontsize=7)
    axes[0].set_title(f"{rec.name} tracker grade")
    for ax, col, refcol in ((axes[1], "cross_x", "cross_x"), (axes[2], "cross_y", "cross_y")):
        if ref is not None:
            rv = np.where(ref["locked"] & ref["cross_valid"], ref[refcol], np.nan)
            ax.plot(t, rv, ".", ms=1.5, color="0.7", label="linefit ref")
        vv = np.where(df["grade"] > GRADE_DEAD, df[col], np.nan)
        ax.plot(t, vv, "g-", lw=0.8, label="tracker")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    axes[2].set_xlabel("t (s)")
    fig.tight_layout()
    fig.savefig(out_dir / "track_timeline.png", dpi=110)
    plt.close(fig)

    metrics = {"frames": n, "ms_per_frame": dt_ms, "availability": valid,
               "grades": ghist, "still_jitter": jit, "accuracy": acc,
               "relock_median": float(np.median(rin)) if len(rin) else None,
               "relock_p95": float(np.percentile(rin, 95)) if len(rin) else None}
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"summary -> {out_dir}/summary.json")
    return 0


def mc_pass(frames, idx, gyro, fov, df_ref, n_per, durs, v3=True, bias_dyn=True):
    """顺序扫描 + 定点快照的伪失锁 MC：
    先随机选窗（起点 grade>=EDGE，末帧参考 grade>=EDGE），再单次回放，
    途经每个窗起点时存快照、支线跑到窗末（视觉抑制）、比较后恢复继续。"""
    n = len(frames)
    fts = idx["tsNs"].to_numpy()
    rng = np.random.default_rng(11)
    windows = []  # (f0, f1, dur)
    per_dur = {d: 0 for d in durs}
    attempts = 0
    while attempts < 4000 and any(per_dur[d] < n_per for d in durs):
        attempts += 1
        d = durs[int(rng.integers(0, len(durs)))]
        if per_dur[d] >= n_per:
            continue
        f0 = int(rng.integers(2, n - 5))
        f1 = int(np.searchsorted(fts, fts[f0] + d * 1e9))
        if f1 >= n or f1 <= f0:
            continue
        if df_ref["grade"][f0] < GRADE_EDGE or df_ref["grade"][f1] < GRADE_EDGE:
            continue
        windows.append((f0, f1, d))
        per_dur[d] += 1
    windows.sort()
    start_map = {}
    for f0, f1, d in windows:
        start_map.setdefault(f0, []).append((f1, d))

    p = TrackerParams()
    p.fov_h_deg = fov
    p.v3 = v3
    p.bias_dyn = bias_dyn
    tr = Tracker(p)
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy().astype(np.float32)  # 与 Java float 一致
    gi = 0
    rows = []
    for s in range(n):
        while gi < len(gts) and gts[gi] <= fts[s]:
            tr.on_gyro(gts[gi], *gw[gi])
            gi += 1
        tr.process(frames[s], fts[s])
        if s in start_map:
            for f1, d in start_map[s]:
                snap = snapshot(tr)
                gi2 = gi
                for ss in range(s + 1, f1 + 1):
                    while gi2 < len(gts) and gts[gi2] <= fts[ss]:
                        tr.on_gyro(gts[gi2], *gw[gi2])
                        gi2 += 1
                    _propagate_only(tr, fts[ss])
                if tr.grade > GRADE_DEAD and np.isfinite(tr.cross[0]):
                    err = float(np.hypot(tr.cross[0] - df_ref["cross_x"][f1],
                                         tr.cross[1] - df_ref["cross_y"][f1]))
                else:
                    err = float("nan")
                rows.append({"f0": s, "f1": f1, "dur": d, "err": err,
                             "dead": int(tr.grade == GRADE_DEAD)})
                restore(tr, snap)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    sys.exit(main())
