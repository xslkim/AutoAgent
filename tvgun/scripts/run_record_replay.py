#!/usr/bin/env python3
"""真机录制回放调试：手机光枪检测算法升级（直线拟合角点）+ IMU 融合回放。

数据：out/record_20260919_104442/
  frames.bin    1120 帧 640x360 uint8 灰度（已从 NV21 stride-2 抽样并旋转到显示坐标）
  frames_idx.csv seq,tsNs（30fps 单调时钟）
  gyro.csv      tsNs,wx,wy,wz（~417Hz，同一单调时钟，rad/s）
  detect.csv    机载当前算法逐帧输出（基线）
  meta.txt      S=1619.31（规范px/rad）、viewAngle=67.94°、detRotation=0

模式：
  --baseline   只跑机载算法复刻（320x180 双阈值连通域 + 极值角点），对照 detect.csv
  --fuse       在新检测输出上做 Fusion.java 同规格融合回放 + 调参
  --annotate N 出 N 张标注帧（四角+网格+准星），外加失败根因示例帧
  默认：baseline 复刻验证 + 新算法（直线拟合角点）+ 指标对比 + 图

新算法（直线拟合角点）：
  1. 粗定位与机载一致：320x180 双阈值滞后连通（低阈值连通 + 高亮种子）取最大域，
     极值点 + 质心细化得粗四角；
  2. 在 640x360 全分辨率上，对每条边取粗边线 ±EDGE_BAND px 带内、且 det 标签属于
     最大域的低阈值掩模像素，TLS（PCA 主轴）直线拟合 + 2 轮 2σ 残差剔除；
  3. 四条边两两求交得亚像素角点；任一边失败（点 <MIN_EDGE_PTS 或残差 σ 超限）
     本帧失败（fail=6）走既有 3 帧迟滞；
  4. 几何校验（对边角差/宽高比）与平滑迟滞不变，α 可调（默认 0.5，噪声小了放大）。

fail 编号（与 Detector.java 一致 + 新增 6）：
  0=ok 1=blob<0.8% 2=无极值 3=四边形非法(面积/边长) 4=单应失败 5=几何校验拒绝
  6=边线拟合失败
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NORM_W, NORM_H = 1920.0, 1080.0

# ---- Detector.java 常量（baseline 完全等价机载） ----
TARGET_W = 320
ALPHA_BASE = 0.3
MIN_AREA_FRAC = 0.02
MIN_BLOB_FRAC = 0.008
MIN_EDGE = 20.0
MAX_MISSES = 3
LOW_THR_RATIO = 0.75
LOW_THR_MIN = 150
MIN_SEED_HI = 30
MAX_OPP_EDGE_ANG = np.deg2rad(10)
MIN_ASPECT, MAX_ASPECT = 1.2, 2.6

# ---- 直线拟合角点参数 ----
ALPHA_FIT = 0.5          # 角点平滑（新算法噪声小，放大 α 降滞后）
EDGE_BAND = 6.0          # 粗边线 ±带（640x360 全分辨率 px）
EDGE_EXTEND = 0.05       # 边带纵向外延比例
MIN_EDGE_BINS = 12       # 边线拟合最少有效纵向 bin 数
EDGE_BIN_W = 3.0         # 纵向分箱宽度（全分辨率 px）
MIN_SUPPORT = 0.5        # 有支撑 bin 占比下限（低于则看 span 规则）
MIN_SPAN = 0.8           # 支撑 bin 首尾覆盖边长比例下限（两端在则直线仍被约束）
MAX_EDGE_SIGMA = 2.0     # 外包络点残差 σ 上限（px）
TRIM_ROUNDS = 2          # 2σ 剔除轮数
MAX_TRACK_SHIFT = 15.0   # 跟踪回退：拟合四角相对参考四边形的最大位移（det px）
# 新算法的几何校验包络：实测近距侧拍真实梯形汇聚可达 ~20°（10° 会误杀，见报告）
MAX_OPP_EDGE_ANG_FIT = np.deg2rad(15)
MIN_ASPECT_FIT, MAX_ASPECT_FIT = 1.1, 3.0


# ================================================================ 数据加载

def load_recording(rec_dir: Path):
    idx = pd.read_csv(rec_dir / "frames_idx.csv")
    n = len(idx)
    frames = np.fromfile(rec_dir / "frames.bin", np.uint8).reshape(n, 360, 640)
    gyro = pd.read_csv(rec_dir / "gyro.csv")
    detect = pd.read_csv(rec_dir / "detect.csv")
    meta = {}
    for line in (rec_dir / "meta.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return frames, idx, gyro, detect, meta


# ================================================================ 检测器

class ReplayDet:
    """Detector.java 等价实现（640x360 灰度输入，stride-2 = 机载 stride-4@720p）。

    mode="extrema"：机载基线（掩模极值角点）；
    mode="linefit"：直线拟合角点升级（粗四角与基线相同，仅角点精化不同）。
    """

    def __init__(self, mode="extrema", alpha=None):
        self.mode = mode
        self.alpha = ALPHA_BASE if alpha is None else alpha
        self.smooth = None
        self.miss_count = 0
        self.locked = False
        self.last_fail = 0
        self.last_thr = 0
        self.last_low_thr = 0
        self.last_best_count = 0
        self.corners = np.zeros(8)   # TL,TR,BR,BL，检测图(320x180)坐标
        self.cross = np.zeros(2)
        self.cross_valid = False
        self.H = None
        self.edge_info = None        # linefit 调试：每边 (bins, support, σ)
        self.tracked = False         # 本帧是否由跟踪回退锁定
        self.track_ref = None        # 最近锁定的平滑四边形（跟踪回退参考，det 坐标）
        self.track_age = 0           # 距上次锁定的帧数

    def _miss(self, stage):
        self.last_fail = stage
        self.miss_count += 1
        self.track_age += 1
        if self.smooth is None or self.miss_count >= MAX_MISSES:
            self.locked = False
            self.cross_valid = False
            self.smooth = None
            self.miss_count = 0

    # ---- 粗定位：双阈值连通域（与 Detector.java 相同语义） ----
    def _coarse_parts(self, g640):
        """返回 (raw|None, fail_stage, labels, best, low_thr)；不触发 miss 状态机。"""
        g = g640[::2, ::2]           # stride-2 -> 320x180，等价机载 stride-4@720p
        dh, dw = g.shape
        n = dw * dh
        hist = np.bincount(g.ravel(), minlength=256)
        need = int(n * 0.02) + 1
        acc, thr = 0, 255
        for v in range(255, -1, -1):
            acc += int(hist[v])
            if acc >= need:
                thr = v
                break
        thr = min(max(thr, 190), 254)
        low_thr = max(LOW_THR_MIN, int(thr * LOW_THR_RATIO))
        self.last_thr, self.last_low_thr = thr, low_thr

        mask = (g >= low_thr).astype(np.uint8)
        nlab, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        if nlab > 1:
            hi_counts = np.bincount(labels[g >= thr].ravel(), minlength=nlab)
            cand = [i for i in range(1, nlab) if hi_counts[i] >= MIN_SEED_HI]
            if cand:
                best = max(cand, key=lambda i: stats[i, cv2.CC_STAT_AREA])
                best_count = int(stats[best, cv2.CC_STAT_AREA])
            else:
                best, best_count = 0, 0
        else:
            best, best_count = 0, 0
        self.last_best_count = best_count
        if best_count < int(MIN_BLOB_FRAC * n):
            return None, 1, labels, 0, low_thr
        ys, xs = np.nonzero(labels == best)
        if len(xs) == 0:
            return None, 2, labels, best, low_thr
        s = xs + ys
        d = xs - ys
        pts = {"tl": (xs[np.argmin(s)], ys[np.argmin(s)]),
               "br": (xs[np.argmax(s)], ys[np.argmax(s)]),
               "tr": (xs[np.argmax(d)], ys[np.argmax(d)]),
               "bl": (xs[np.argmin(d)], ys[np.argmin(d)])}

        def refine(cx, cy):
            j0, j1 = max(0, cy - 2), min(dh - 1, cy + 2)
            i0, i1 = max(0, cx - 2), min(dw - 1, cx + 2)
            win = labels[j0:j1 + 1, i0:i1 + 1]
            wy, wx = np.nonzero(win == best)
            if len(wx) == 0:
                return float(cx), float(cy)
            return float(wx.mean() + i0), float(wy.mean() + j0)

        raw = np.array([*refine(*pts["tl"]), *refine(*pts["tr"]),
                        *refine(*pts["br"]), *refine(*pts["bl"])])
        if not self._valid(raw, dw, dh):
            return None, 3, labels, best, low_thr
        return raw, 0, labels, best, low_thr

    def _coarse(self, g640):
        """baseline 兼容入口（内部走 miss 状态机）。"""
        raw, stage, labels, best, low_thr = self._coarse_parts(g640)
        if stage != 0:
            self._miss(stage)
            return None
        return raw, labels, best, low_thr

    def _accept(self, raw):
        """平滑 + 单应 + 锁定（baseline/linefit 共用）。"""
        self.miss_count = 0
        self.last_fail = 0
        if self.smooth is None:
            self.smooth = raw.copy()
        else:
            self.smooth += self.alpha * (raw - self.smooth)
        self.corners = self.smooth.copy()
        self.track_ref = self.corners.copy()
        self.track_age = 0
        dst = np.array([[0, 0], [NORM_W, 0], [NORM_W, NORM_H], [0, NORM_H]], np.float32)
        H = cv2.getPerspectiveTransform(self.corners.reshape(4, 2).astype(np.float32),
                                        dst).astype(np.float64)
        if H is None:
            self._miss(4)
            return
        self.H = H
        self.locked = True
        pt = H @ np.array([160.0, 90.0, 1.0])   # 帧中心（det 320x180）
        pt /= pt[2]
        self.cross = pt[:2]
        self.cross_valid = bool(0 <= self.cross[0] <= NORM_W
                                and 0 <= self.cross[1] <= NORM_H)

    # ---- 机载几何校验（面积/边长 + 对边角差/宽高比） ----
    @staticmethod
    def _valid(c, dw, dh):
        pts = c.reshape(4, 2)
        area = 0.0
        for i in range(4):
            j = (i + 1) % 4
            area += pts[i, 0] * pts[j, 1] - pts[j, 0] * pts[i, 1]
        if abs(area) / 2 < MIN_AREA_FRAC * dw * dh:
            return False
        for i in range(4):
            j = (i + 1) % 4
            if np.hypot(*(pts[j] - pts[i])) < MIN_EDGE:
                return False
        return True

    @staticmethod
    def _geo_valid(c):
        tl, tr, br, bl = c.reshape(4, 2)

        def ang(p, q):
            return np.arctan2(q[1] - p[1], q[0] - p[0])

        def ang_diff(a, b):
            dd = (a - b) % np.pi
            return dd - np.pi if dd > np.pi / 2 else (dd + np.pi if dd < -np.pi / 2 else dd)

        if abs(ang_diff(ang(tl, tr), ang(bl, br))) > MAX_OPP_EDGE_ANG:
            return False
        if abs(ang_diff(ang(tl, bl), ang(tr, br))) > MAX_OPP_EDGE_ANG:
            return False
        w_avg = (np.hypot(*(tr - tl)) + np.hypot(*(br - bl))) / 2
        h_avg = (np.hypot(*(bl - tl)) + np.hypot(*(br - tr))) / 2
        if w_avg <= 0 or h_avg <= 0:
            return False
        aspect = max(w_avg, h_avg) / min(w_avg, h_avg)
        return MIN_ASPECT <= aspect <= MAX_ASPECT

    # ---- 直线拟合角点（640x360 全分辨率）：外包络点 + TLS + 2σ 剔除 ----
    def _fit_edges(self, g640, raw_det, low_thr):
        """每条边：粗边线 ±EDGE_BAND 带内、属于最大域的低阈值掩模像素，
        按纵向 EDGE_BIN_W 分箱取外侧（远离四边形中心）包络点（bin 内 perp 95 分位），
        对包络点做 TLS 直线拟合 + 2 轮 2σ 剔除；支撑率/残差不过则边失败。"""
        mask640 = (g640 >= low_thr)
        # 不加 det 标签过滤：碎环时边框段分属不同连通域，过滤会误杀支撑点；
        # 干扰由 ±6px 窄带 + 外侧包络 + 2σ 剔除 + 几何校验联合抑制
        corners640 = raw_det.reshape(4, 2) * 2.0
        centroid = corners640.mean(axis=0)
        lines = []
        info = []
        for e in range(4):
            p0 = corners640[e]
            p1 = corners640[(e + 1) % 4]
            d = p1 - p0
            L = np.hypot(*d)
            if L < 1:
                return None, None
            d = d / L
            nv = np.array([-d[1], d[0]])
            if nv @ (p0 - centroid) < 0:
                nv = -nv                  # nv 指向四边形外侧
            x0 = max(int(min(p0[0], p1[0]) - EDGE_BAND - 2), 0)
            x1 = min(int(max(p0[0], p1[0]) + EDGE_BAND + 2), 640)
            y0 = max(int(min(p0[1], p1[1]) - EDGE_BAND - 2), 0)
            y1 = min(int(max(p0[1], p1[1]) + EDGE_BAND + 2), 360)
            sub_mask = mask640[y0:y1, x0:x1]
            if not sub_mask.any():
                return None, None
            yy, xx = np.nonzero(sub_mask)
            xx = xx + x0
            yy = yy + y0
            perp = (xx - p0[0]) * nv[0] + (yy - p0[1]) * nv[1]
            lon = (xx - p0[0]) * d[0] + (yy - p0[1]) * d[1]
            sel = (np.abs(perp) <= EDGE_BAND) & (lon >= 0) & (lon <= L)
            xx, yy, perp, lon = xx[sel], yy[sel], perp[sel], lon[sel]
            n_bins = int(L / EDGE_BIN_W)
            if n_bins < MIN_EDGE_BINS:
                return None, None
            # 纵向分箱取外包络点（bin 内 perp >= 95 分位的像素均值）
            bi = np.minimum((lon / EDGE_BIN_W).astype(int), n_bins - 1)
            env = []
            env_bins = []
            for b in range(n_bins):
                m = bi == b
                if not m.any():
                    continue
                thr95 = np.percentile(perp[m], 95)
                top = m & (perp >= thr95 - 1e-9)
                env.append((xx[top].mean(), yy[top].mean()))
                env_bins.append(b)
            support = len(env) / n_bins
            # 支撑 bin 覆盖边长比例：中段被画面边界裁掉时两端仍在，
            # 直线仍被良好约束（span 规则），允许拟合并外推交点。
            # 但两端残桩（如 L 角标残臂）也会满足 span——要求跨度规则下
            # 支撑率至少 15%，防止两条残桩决定整条边。
            span = (env_bins[-1] - env_bins[0] + 1) / n_bins if env_bins else 0.0
            ok = len(env) >= MIN_EDGE_BINS and \
                (support >= MIN_SUPPORT or (span >= MIN_SPAN and support >= 0.15))
            if not ok:
                info.append((len(env), support, float("nan")))
                return None, info
            pts = np.array(env)
            sigma = float("inf")
            normal = None
            ctr = None
            for _ in range(TRIM_ROUNDS + 1):
                ctr = pts.mean(axis=0)
                cov = np.cov((pts - ctr).T)
                eigval, eigvec = np.linalg.eigh(cov)
                normal = eigvec[:, 0]
                res = (pts - ctr) @ normal
                sigma = float(res.std())
                if sigma < 1e-9:
                    break
                inl = np.abs(res - res.mean()) <= 2 * sigma
                if inl.all():
                    break
                pts = pts[inl]
                if len(pts) < MIN_EDGE_BINS:
                    info.append((len(pts), support, sigma))
                    return None, info
            if sigma > MAX_EDGE_SIGMA:
                info.append((len(pts), support, sigma))
                return None, info
            info.append((len(pts), support, sigma))
            lines.append(np.array([normal[0], normal[1], -normal @ ctr]))
        # 相邻边求交：角点 i = 边 i-1 ∩ 边 i（顺序 TL,TR,BR,BL）
        corners = []
        for i in range(4):
            p = np.cross(lines[(i - 1) % 4], lines[i])
            if abs(p[2]) < 1e-9:
                return None, info
            corners.append(p[:2] / p[2])
        return np.array(corners).reshape(8) / 2.0, info   # 回到 det 坐标

    # 新算法几何校验：包络放宽（近距侧拍真实梯形汇聚实测可达 ~20°）
    @staticmethod
    def _geo_valid_fit(c):
        tl, tr, br, bl = c.reshape(4, 2)

        def ang(p, q):
            return np.arctan2(q[1] - p[1], q[0] - p[0])

        def ang_diff(a, b):
            dd = (a - b) % np.pi
            return dd - np.pi if dd > np.pi / 2 else (dd + np.pi if dd < -np.pi / 2 else dd)

        if abs(ang_diff(ang(tl, tr), ang(bl, br))) > MAX_OPP_EDGE_ANG_FIT:
            return False
        if abs(ang_diff(ang(tl, bl), ang(tr, br))) > MAX_OPP_EDGE_ANG_FIT:
            return False
        w_avg = (np.hypot(*(tr - tl)) + np.hypot(*(br - bl))) / 2
        h_avg = (np.hypot(*(bl - tl)) + np.hypot(*(br - tr))) / 2
        if w_avg <= 0 or h_avg <= 0:
            return False
        aspect = max(w_avg, h_avg) / min(w_avg, h_avg)
        return MIN_ASPECT_FIT <= aspect <= MAX_ASPECT_FIT

    # ---- 主入口 ----
    def process(self, g640):
        raw, stage, labels, best, low_thr = self._coarse_parts(g640)
        self.tracked = False
        if self.mode == "extrema":
            # baseline：与机载逐语句等价（无跟踪回退）
            if stage != 0:
                self._miss(stage)
                return
            if not self._geo_valid(raw):
                self._miss(5)
                return
            self._accept(raw)
            return

        # linefit：粗四角 -> 全分辨率边线拟合
        self.edge_info = None
        fit_stage = stage
        if stage == 0:
            fitted, info = self._fit_edges(g640, raw, low_thr)
            self.edge_info = info
            if fitted is not None and self._geo_valid_fit(fitted):
                self._accept(fitted)
                return
            fit_stage = 5 if fitted is not None else 6
        # 跟踪回退：以最近锁定四边形为参考拟合（覆盖碎环/极值退化/瞬时遮挡），
        # 参考最多保留 30 帧（≈1s，与融合预测窗一致），
        # 拟合四角相对参考位移不超过 MAX_TRACK_SHIFT 防止跳锁
        if self.track_ref is not None and self.track_age <= 30:
            fitted2, info2 = self._fit_edges(g640, self.track_ref, low_thr)
            if fitted2 is not None and self._geo_valid_fit(fitted2) \
                    and np.abs(fitted2 - self.track_ref).max() <= MAX_TRACK_SHIFT:
                self.edge_info = info2
                self.tracked = True
                self._accept(fitted2)
                return
        self._miss(fit_stage)


# ================================================================ 融合（Fusion.java 同规格）

def run_fusion(frame_ts, locked, cx, cy, gyro, S, gain=0.3, predict_ns=1_000_000_000,
               axis_h=("wy", +1), axis_v=("wx", +1)):
    """Fusion.java 逐语句等价回放（轴向/符号可配）。

    机载 Fusion.java rot=0 映射为 dx=+wy·dt·S, dy=+wx·dt·S；
    本录制数据回归显示实际应为 dx=−wx, dy=+wy（见 axis_calibration），
    即 axis_h=("wx",-1), axis_v=("wy",+1)。
    返回每帧 snapshot。"""
    MAX_DT_S = 0.1
    ah, sh = axis_h
    av, sv = axis_v
    Sh, Sv = S if isinstance(S, (tuple, list)) else (S, S)
    gi = 0
    gts = gyro["tsNs"].to_numpy()
    gw = {k: gyro[k].to_numpy() for k in ("wx", "wy", "wz")}
    n_g = len(gyro)
    initialized = False
    lock = False
    x = y = 0.0
    last_gyro_ns = -1
    last_lock_ns = -1
    out = []
    for i in range(len(frame_ts)):
        fts = frame_ts[i]
        # 播放该帧之前的所有陀螺 tick
        while gi < n_g and gts[gi] <= fts:
            if last_gyro_ns >= 0:
                dt = (gts[gi] - last_gyro_ns) * 1e-9
                if 0 < dt <= MAX_DT_S and initialized \
                        and not (not lock and gts[gi] - last_lock_ns > predict_ns):
                    x += sh * gw[ah][gi] * dt * Sh
                    y += sv * gw[av][gi] * dt * Sv
            last_gyro_ns = gts[gi]
            gi += 1
        # 相机事件
        if locked[i] and np.isfinite(cx[i]):
            if not initialized:
                x, y = cx[i], cy[i]
                initialized = True
            else:
                x = (1 - gain) * x + gain * cx[i]
                y = (1 - gain) * y + gain * cy[i]
            lock = True
            last_lock_ns = fts
        else:
            lock = False
        # snapshot
        within = initialized and (lock or (fts - last_lock_ns) <= predict_ns)
        out.append({"fused_x": x if initialized else np.nan,
                    "fused_y": y if initialized else np.nan,
                    "valid": within,
                    "predicted": (not lock) and within,
                    "lock": lock})
    return pd.DataFrame(out)


# ================================================================ 主流程

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rec", default=str(ROOT / "out" / "record_20260919_104442"))
    ap.add_argument("--out", default=str(ROOT / "out" / "record_replay"))
    ap.add_argument("--baseline", action="store_true", help="只跑机载算法复刻对照")
    ap.add_argument("--fuse", action="store_true", help="融合回放 + 调参")
    ap.add_argument("--annotate", type=int, default=0, metavar="N", help="出 N 张标注帧")
    ap.add_argument("--clip-test", action="store_true",
                    help="合成裁剪实验：量化 baseline 在屏幕缺边时的静默误差")
    args = ap.parse_args(argv)

    rec_dir = Path(args.rec)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames, idx, gyro, detect, meta = load_recording(rec_dir)
    S = float(meta.get("S", 1619.31))
    n = len(frames)
    print(f"recording: {n} frames 640x360, gyro {len(gyro)} samples, S={S}")

    if args.clip_test:
        clip_test(frames, out_dir)
        return 0

    def run_detector(mode, alpha=None):
        det = ReplayDet(mode, alpha)
        rows = []
        for s in range(n):
            det.process(frames[s])
            c = det.corners
            rows.append({"seq": s, "locked": det.locked, "fail": det.last_fail,
                         "tracked": getattr(det, "tracked", False),
                         "thr": det.last_thr, "low_thr": det.last_low_thr,
                         "cross_x": det.cross[0], "cross_y": det.cross[1],
                         "cross_valid": det.cross_valid,
                         "c0x": c[0], "c0y": c[1], "c1x": c[2], "c1y": c[3],
                         "c2x": c[4], "c2y": c[5], "c3x": c[6], "c3y": c[7]})
        return pd.DataFrame(rows)

    # ---- 基线复刻验证
    base = run_detector("extrema")
    base_lock = float(base["locked"].mean())
    dev_lock = float(detect["locked"].mean())
    base_fail = base["fail"].value_counts().to_dict()
    dev_fail = detect["failStage"].value_counts().to_dict()
    print(f"[baseline] replay lock {base_lock:.1%} vs device {dev_lock:.1%} "
          f"(diff {abs(base_lock - dev_lock):.1%})")
    print(f"[baseline] replay fail {base_fail} vs device {dev_fail}")
    # 角点一致性（共同锁定帧）
    both = base["locked"] & detect["locked"].astype(bool)
    if both.sum() > 10:
        dc = np.hypot(base.loc[both, "cross_x"] - detect.loc[both, "detCrossX"],
                      base.loc[both, "cross_y"] - detect.loc[both, "detCrossY"])
        print(f"[baseline] cross diff vs device: median {dc.median():.2f} "
              f"P95 {dc.quantile(.95):.2f} norm px (n={int(both.sum())})")
    base.to_csv(out_dir / "baseline_replay.csv", index=False)
    if args.baseline:
        return 0

    # ---- 新算法
    t0 = time.monotonic()
    new = run_detector("linefit", alpha=ALPHA_FIT)
    print(f"[linefit] {time.monotonic() - t0:.1f}s, lock {new['locked'].mean():.1%}, "
          f"fail {new['fail'].value_counts().to_dict()}")
    new.to_csv(out_dir / "linefit_replay.csv", index=False)

    # ---- 指标
    # 静止段：录制协议首段为"瞄准静止"，实测 seq 5..55 全锁定、速度中位 45 规范px/s、
    # x 峰谷仅 22（gyro 全程 |ω|>0.2 rad/s 因持续手震/调整，不能用作静止判据）
    s0, s1 = 5, 55
    print(f"[metric] still segment: seq {s0}..{s1} (固定选取，速度剖面验证)")

    def jitter(dfx, cx_col, cy_col, seg):
        m = dfx["locked"].to_numpy().copy()
        m[:seg[0]] = False
        m[seg[1]:] = False
        x = dfx[cx_col].to_numpy()[m]
        y = dfx[cy_col].to_numpy()[m]
        if len(x) < 10:
            return float("nan")
        k = np.ones(5) / 5
        rx = (x - np.convolve(x, k, "same"))[2:-2]   # 去掉 MA 边缘效应
        ry = (y - np.convolve(y, k, "same"))[2:-2]
        return float(np.hypot(rx, ry).std())

    jit_base = jitter(base, "cross_x", "cross_y", (s0, s1))
    jit_new = jitter(new, "cross_x", "cross_y", (s0, s1))
    # 设备基线抖动（detect.csv detCross）
    dev_d = detect.copy()
    dev_d["locked"] = dev_d["locked"].astype(bool)
    jit_dev = jitter(dev_d.rename(columns={"detCrossX": "cross_x", "detCrossY": "cross_y"}),
                     "cross_x", "cross_y", (s0, s1))

    def unlock_runs(dfx):
        unl = ~dfx["locked"].to_numpy()
        runs, st = [], None
        for i, u in enumerate(unl):
            if u and st is None:
                st = i
            if not u and st is not None:
                runs.append((st, i - 1))
                st = None
        if st is not None:
            runs.append((st, len(unl) - 1))
        return runs

    runs_base = unlock_runs(base)
    runs_new = unlock_runs(new)

    metrics = {
        "frames": n,
        "still_segment": [int(s0), int(s1)],
        "device_baseline": {"lock_rate": dev_lock, "fail": dev_fail,
                            "still_jitter_std": jit_dev},
        "replay_baseline": {"lock_rate": base_lock,
                            "report_rate": float((base["locked"] & base["cross_valid"]).mean()),
                            "fail": base_fail,
                            "still_jitter_std": jit_base,
                            "unlock_runs": len(runs_base),
                            "max_unlock_run": max((b - a + 1) for a, b in runs_base)},
        "linefit": {"lock_rate": float(new["locked"].mean()),
                    "report_rate": float((new["locked"] & new["cross_valid"]).mean()),
                    "fail": {int(k): int(v) for k, v in
                             new["fail"].value_counts().items()},
                    "still_jitter_std": jit_new,
                    "unlock_runs": len(runs_new),
                    "max_unlock_run": max((b - a + 1) for a, b in runs_new),
                    "alpha": ALPHA_FIT},
    }

    # 参考真值 = linefit 输出（经标注帧人工确认）；精度在静止段比较
    # （运动段两算法 α 滞后不同会混入系统性差异，不代表精度）
    still_b = base["locked"].copy()
    still_b[:] = False
    still_b[s0:s1] = base["locked"][s0:s1]
    still_n = new["locked"].copy()
    still_n[:] = False
    still_n[s0:s1] = new["locked"][s0:s1]
    both_b = still_b & still_n
    dev_b = np.hypot(base.loc[both_b, "cross_x"] - new.loc[both_b, "cross_x"],
                     base.loc[both_b, "cross_y"] - new.loc[both_b, "cross_y"])
    metrics["accuracy_vs_truth"] = {
        "truth": "linefit replay (manually verified annotated frames)",
        "note": "静止段(seq5-55)中位偏差；运动段差异受 α 滞后影响不代表精度",
        "replay_baseline_median": float(dev_b.median()) if len(dev_b) else None,
        "replay_baseline_p95": float(dev_b.quantile(.95)) if len(dev_b) else None,
    }
    both_d = detect["locked"].astype(bool) & new["locked"]
    dev_d2 = np.hypot(detect.loc[both_d, "detCrossX"] - new.loc[both_d, "cross_x"],
                      detect.loc[both_d, "detCrossY"] - new.loc[both_d, "cross_y"])
    metrics["accuracy_vs_truth"]["device_baseline_median_all"] = float(dev_d2.median())
    metrics["accuracy_vs_truth"]["device_baseline_p95_all"] = float(dev_d2.quantile(.95))

    # ---- 可见性 oracle：对每个失锁 run，用前后锁定四边形线性插值出参考四边形，
    # 在 run 中点帧上做宽带边线拟合（±15px），判断屏幕是否完整入镜。
    # 结论写入 metrics["excluded_runs"]，用于"剔除故意遮挡段后的锁定率"。
    oracle = visibility_oracle(frames, new, idx)
    metrics["visibility_oracle"] = oracle["runs"]
    cs = contact_sheet(frames, new, out_dir)
    metrics["contact_sheet"] = str(cs)
    vis_frames = np.ones(n, bool)
    for r in oracle["runs"]:
        if not r["visible"]:
            vis_frames[r["start"]:r["end"] + 1] = False
    adj_lock = float(new["locked"].to_numpy()[vis_frames].mean())
    metrics["linefit"]["lock_rate_excluding_occluded"] = adj_lock
    metrics["linefit"]["excluded_frames_frac"] = float(1 - vis_frames.mean())
    print(f"[metric] linefit lock excl. occluded: {adj_lock:.1%} "
          f"(excluded {int((~vis_frames).sum())} frames in "
          f"{sum(1 for r in oracle['runs'] if not r['visible'])} runs)")

    print(f"[metric] still jitter std: device {jit_dev:.2f} | replay-baseline {jit_base:.2f} "
          f"| linefit {jit_new:.2f} norm px (target <4)")
    print(f"[metric] unlock runs: baseline {len(runs_base)} (max {metrics['replay_baseline']['max_unlock_run']}) "
          f"-> linefit {len(runs_new)} (max {metrics['linefit']['max_unlock_run']})")
    print(f"[metric] cross dev vs truth: replay-baseline median {dev_b.median():.2f}, "
          f"device median {dev_d2.median():.2f} norm px")

    # ---- 图：锁定时间线 + 静止段抖动
    fig, axes = plt.subplots(3, 1, figsize=(15, 9), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1.4, 1.4]})
    t = np.arange(n) / 30
    axes[0].fill_between(t, 0, detect["locked"], alpha=0.4, step="post",
                         label="device baseline")
    axes[0].fill_between(t, 0, -base["locked"], alpha=0.4, step="post",
                         label="replay baseline")
    axes[0].fill_between(t, 0, -new["locked"] * 0.5, alpha=0.6, step="post",
                         color="g", label="linefit (lower half)")
    axes[0].set_yticks([])
    axes[0].legend(fontsize=8)
    axes[0].set_title("lock timeline (up=device, down=replay baseline / green=linefit)")
    axes[1].plot(t, detect["detCrossX"].where(detect["crossValid"].astype(bool)),
                 ".", ms=1.5, color="0.7", label="device")
    axes[1].plot(t, np.where(new["locked"] & new["cross_valid"], new["cross_x"], np.nan),
                 "g-", lw=0.8, label="linefit")
    axes[1].set_ylabel("cross x")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)
    axes[2].plot(t, detect["detCrossY"].where(detect["crossValid"].astype(bool)),
                 ".", ms=1.5, color="0.7", label="device")
    axes[2].plot(t, np.where(new["locked"] & new["cross_valid"], new["cross_y"], np.nan),
                 "g-", lw=0.8, label="linefit")
    axes[2].set_ylabel("cross y")
    axes[2].legend(fontsize=8)
    axes[2].grid(alpha=0.3)
    axes[2].set_xlabel("t (s)")
    for ax in axes:
        ax.axvspan(s0 / 30, s1 / 30, color="blue", alpha=0.06)
    fig.tight_layout()
    fig.savefig(out_dir / "lock_timeline.png", dpi=110)
    plt.close(fig)

    # ---- 融合回放 + 调参
    if args.fuse:
        fuse_res = fusion_study(idx, new, gyro, S, out_dir, (s0, s1))
        metrics["fusion"] = fuse_res

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"summary -> {out_dir}/summary.json")

    # ---- 标注帧
    if args.annotate > 0:
        dfx = new.rename(columns={"locked": "ok"})
        locked_seqs = dfx[dfx["ok"]]["seq"].to_numpy()
        pick = locked_seqs[np.linspace(0, len(locked_seqs) - 1, args.annotate).astype(int)]
        fail_seqs = base[~base["locked"]]["seq"].to_numpy()
        fail_pick = fail_seqs[np.linspace(0, len(fail_seqs) - 1,
                                          min(4, len(fail_seqs))).astype(int)]
        paths = annotate_frames(frames, dfx, out_dir, list(pick), tag="fit_")
        paths += annotate_frames(frames, dfx, out_dir, list(fail_pick), tag="fail_")
        print(f"annotated {len(paths)} frames -> {out_dir}")
    return 0


def annotate_frames(frames, df, out_dir, seqs, tag=""):
    out = []
    for s in seqs:
        row = df.iloc[s]
        img = cv2.cvtColor(frames[s], cv2.COLOR_GRAY2BGR)
        img = cv2.resize(img, (1280, 720), interpolation=cv2.INTER_NEAREST)
        c = np.array([[row["c0x"], row["c0y"]], [row["c1x"], row["c1y"]],
                      [row["c2x"], row["c2y"]], [row["c3x"], row["c3y"]]]) * 4
        if row["ok"] and np.all(np.isfinite(c)):
            q = c.astype(np.int32)
            cv2.polylines(img, [q], True, (0, 0, 255), 1, cv2.LINE_AA)
            for (px, py), nm in zip(q, ("TL", "TR", "BR", "BL")):
                cv2.circle(img, (px, py), 3, (0, 0, 255), -1)
                cv2.putText(img, nm, (px + 4, py + 12), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 0, 255), 1, cv2.LINE_AA)
            H = cv2.getPerspectiveTransform((c / 4).astype(np.float32),
                                            np.array([[0, 0], [1920, 0], [1920, 1080],
                                                      [0, 1080]], np.float32)).astype(np.float64)
            Hinv = np.linalg.inv(H)

            def to_img(nx, ny):
                p = Hinv @ np.array([nx, ny, 1.0])
                return p[:2] / p[2] * 4

            for gx in np.arange(0, 1921, 240):
                p = np.array([to_img(gx, gy) for gy in np.arange(0, 1081, 30)], np.int32)
                cv2.polylines(img, [p], False, (0, 255, 0), 1, cv2.LINE_AA)
            for gy in np.arange(0, 1081, 135):
                p = np.array([to_img(gx, gy) for gx in np.arange(0, 1921, 40)], np.int32)
                cv2.polylines(img, [p], False, (0, 255, 0), 1, cv2.LINE_AA)
        cx, cy = 640, 360
        cv2.line(img, (cx - 15, cy), (cx + 15, cy), (255, 255, 0), 1, cv2.LINE_AA)
        cv2.line(img, (cx, cy - 15), (cx, cy + 15), (255, 255, 0), 1, cv2.LINE_AA)
        txt = f"seq={s} locked={int(row['ok'])} fail={int(row['fail'])}"
        if row["ok"]:
            txt += f" cross=({row['cross_x']:.0f},{row['cross_y']:.0f})"
        cv2.putText(img, txt, (cx + 20, cy - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 0), 1, cv2.LINE_AA)
        path = out_dir / f"annotated_{tag}{s:06d}.png"
        cv2.imwrite(str(path), img)
        out.append(path)
    return out


def visibility_oracle(frames, new, idx):
    """对每个 linefit 失锁 run：取 run 前/后最近锁定帧的四边形线性插值出参考
    四边形，在 run 中点帧做宽带（±15px）边线拟合，判断屏幕是否完整入镜。
    另存 run 中点的标注图（contact sheet 供人工复核）。"""
    det = ReplayDet("linefit")
    runs = []
    unl = ~new["locked"].to_numpy()
    st = None
    for i, u in enumerate(unl):
        if u and st is None:
            st = i
        if not u and st is not None:
            runs.append((st, i - 1))
            st = None
    if st is not None:
        runs.append((st, len(unl) - 1))
    locked_seqs = np.flatnonzero(new["locked"].to_numpy())
    quads = new[["c0x", "c0y", "c1x", "c1y", "c2x", "c2y", "c3x", "c3y"]].to_numpy()
    out = {"runs": []}
    for a, b in runs:
        mid = (a + b) // 2
        prev = locked_seqs[locked_seqs < a]
        nxt = locked_seqs[locked_seqs > b]
        if not len(prev) or not len(nxt):
            out["runs"].append({"start": int(a), "end": int(b), "visible": False,
                                "reason": "no bracketing lock"})
            continue
        p0, p1 = prev[-1], nxt[0]
        w = (mid - p0) / max(p1 - p0, 1)
        ref = quads[p0] * (1 - w) + quads[p1] * w
        g = frames[mid]
        # 宽带拟合（oracle 用）：直接复用 _fit_edges 但带宽 ±15
        low_thr = det.last_low_thr  # 占位，下面重新算
        _, _, _, _, low_thr = det._coarse_parts(g)
        fitted, info = _fit_edges_wide(det, g, ref, low_thr, band=15.0)
        vis = fitted is not None and det._geo_valid_fit(fitted)
        sups = [round(float(i[1]), 2) for i in info] if info else None
        out["runs"].append({"start": int(a), "end": int(b), "len": int(b - a + 1),
                            "mid": int(mid), "visible": bool(vis),
                            "edge_support": sups})
    return out


def _fit_edges_wide(det, g640, ref_det, low_thr, band):
    """oracle 用宽带拟合：临时放宽 EDGE_BAND。"""
    import run_record_replay as self_mod
    old = self_mod.EDGE_BAND
    self_mod.EDGE_BAND = band
    try:
        return det._fit_edges(g640, ref_det, low_thr)
    finally:
        self_mod.EDGE_BAND = old


def contact_sheet(frames, new, out_dir):
    """每个失锁 run 的中点帧拼图（供人工复核 oracle 判定）。"""
    unl = ~new["locked"].to_numpy()
    runs = []
    st = None
    for i, u in enumerate(unl):
        if u and st is None:
            st = i
        if not u and st is not None:
            runs.append((st, i - 1))
            st = None
    if st is not None:
        runs.append((st, len(unl) - 1))
    tiles = []
    for a, b in runs:
        mid = (a + b) // 2
        img = cv2.cvtColor(frames[mid], cv2.COLOR_GRAY2BGR)
        cv2.putText(img, f"{a}-{b}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 0), 2)
        tiles.append(img)
    cols = 5
    rows_n = int(np.ceil(len(tiles) / cols))
    pad = np.zeros_like(tiles[0])
    tiles += [pad] * (rows_n * cols - len(tiles))
    grid = np.vstack([np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(rows_n)])
    path = out_dir / "unlock_runs_contact.png"
    cv2.imwrite(str(path), grid)
    return path


def axis_calibration(frame_ts, locked, cx, cy, gyro, S):
    """相邻锁定帧间的 cross 位移对陀螺积分位移做回归，求真实轴向/符号/有效尺度。
    慢速帧的帧间位移被检测噪声主导（回归无意义），有效尺度用快速帧（>30px/帧）拟合。"""
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    pairs = []
    for i in range(1, len(frame_ts)):
        if not (locked[i] and locked[i - 1]):
            continue
        m = (gts > frame_ts[i - 1]) & (gts <= frame_ts[i])
        if m.sum() < 2:
            continue
        dt = np.diff(np.concatenate([[frame_ts[i - 1]], gts[m]])) * 1e-9
        iwx, iwy, iwz = (gw[m] * dt[:, None]).sum(axis=0)
        pairs.append((cx[i] - cx[i - 1], cy[i] - cy[i - 1], iwx, iwy, iwz))
    p = pd.DataFrame(pairs, columns=["dx", "dy", "iwx", "iwy", "iwz"])

    def reg(col, tgt, mask=None):
        X = p[col].to_numpy()
        Y = p[tgt].to_numpy()
        m = np.abs(X) > 1e-6
        if mask is not None:
            m = m & mask
        slope = float((X[m] * Y[m]).sum() / (X[m] ** 2).sum())
        r2 = 1 - float(((Y[m] - slope * X[m]) ** 2).sum()
                       / (((Y[m] - Y[m].mean()) ** 2).sum() + 1e-12))
        return slope, r2

    best = {}
    for tgt in ("dx", "dy"):
        cands = {a: reg(f"iw{a}", tgt) for a in "xyz"}
        axis = max(cands, key=lambda a: cands[a][1])
        best[tgt] = {"axis": f"w{axis}", "slope": cands[axis][0], "r2": cands[axis][1],
                     "sign": "+" if cands[axis][0] > 0 else "-"}
    # 有效尺度：快速帧回归（慢速帧帧间位移被检测噪声主导）
    fast = (np.hypot(p["dx"], p["dy"]) > 30).to_numpy()
    sh, r2h = reg("iwx", "dx", fast)
    sv, r2v = reg("iwy", "dy", fast)
    return {"S_meta": S,
            "h": best["dx"], "v": best["dy"],
            "slope_h": sh, "slope_v": sv, "r2_fast_h": r2h, "r2_fast_v": r2v,
            "fusion_java_mapping": "dx=+wy, dy=+wx (rot=0)",
            "measured_mapping": f"dx={best['dx']['sign']}w{best['dx']['axis'][1]}, "
                                f"dy={best['dy']['sign']}w{best['dy']['axis'][1]}",
            "note": "慢速帧 R2 低是检测噪声主导；快速帧拟合给有效 S（本段录制约 2050/1920，"
                    "比 meta S=1619 大 ~25%，观看距离比标定近）"}


def clip_test(frames, out_dir):
    """合成裁剪实验：完整入镜帧裁掉右/下边 5~15%（置暗），
    baseline（极值角点）照常锁定但坐标静默偏移，linefit 应拒锁或保持准确。"""
    rows = []
    for s in (10, 30, 50):
        g0 = frames[s]
        dt0 = ReplayDet("linefit")
        dt0.process(g0)
        true_cross = dt0.cross.copy()
        q = dt0.corners.reshape(4, 2) * 2
        rx = (q[1, 0] + q[2, 0]) / 2
        top = (q[0, 1] + q[1, 1]) / 2
        bot = (q[2, 1] + q[3, 1]) / 2
        W = rx - (q[0, 0] + q[3, 0]) / 2
        for side in ("right", "bottom"):
            for frac in (0.05, 0.10, 0.15):
                g = g0.copy()
                if side == "right":
                    g[:, int(rx - W * frac):] = 40
                else:
                    g[int(bot - (bot - top) * frac):, :] = 40
                db = ReplayDet("extrema")
                db.process(g)
                dn = ReplayDet("linefit")
                dn.process(g)
                rows.append({
                    "seq": s, "side": side, "clip_frac": frac,
                    "baseline_locked": db.locked,
                    "baseline_err": float(np.hypot(*(db.cross - true_cross)))
                    if db.locked else None,
                    "linefit_locked": dn.locked, "linefit_fail": dn.last_fail,
                    "linefit_err": float(np.hypot(*(dn.cross - true_cross)))
                    if dn.locked else None})
    r = pd.DataFrame(rows)
    r.to_csv(out_dir / "clip_test.csv", index=False)
    bl = r["baseline_err"].dropna()
    print(f"[clip-test] baseline: locked {r['baseline_locked'].sum()}/{len(r)}, "
          f"silent err median {bl.median():.1f} max {bl.max():.1f} norm px")
    print(f"[clip-test] linefit: locked {r['linefit_locked'].sum()}/{len(r)} "
          f"(其余拒锁) err: "
          f"{r['linefit_err'].dropna().round(1).tolist()}")


def fusion_study(idx, new, gyro, S, out_dir, s_seg):
    """Fusion.java 同规格回放：新检测输出 + 417Hz 陀螺；增益/预测窗调参。

    对比三种映射：(dev) 机载 Fusion.java rot=0 现状 dx=+wy,dy=+wx；
    (fix) 数据回归校正 dx=−wx,dy=+wy，S=meta；(fixS) 校正映射 + 回归有效尺度。
    """
    fts = idx["tsNs"].to_numpy()
    locked = (new["locked"] & new["cross_valid"]).to_numpy()
    cx = new["cross_x"].to_numpy()
    cy = new["cross_y"].to_numpy()
    calib = axis_calibration(fts, locked, cx, cy, gyro, S)
    print(f"[fuse] axis calibration: {calib}")

    def evaluate(fus):
        # 重新锁定外推误差：失锁>=1帧后首次锁定时 |pred - camera|
        errs = []
        was_unl = False
        for i in range(1, len(fus)):
            if not locked[i - 1]:
                was_unl = True
            if locked[i] and was_unl and np.isfinite(fus["fused_x"][i]):
                # 校正前位置 ≈ 上一帧 fused（校正发生在本帧，用 i-1 近似）
                e = np.hypot(fus["fused_x"][i - 1] - cx[i],
                             fus["fused_y"][i - 1] - cy[i])
                errs.append(e)
                was_unl = False
            elif locked[i]:
                was_unl = False
        return np.array(errs)

    results = {"axis_calibration": calib}
    maps = {
        "dev":  dict(S=S, axis_h=("wy", +1), axis_v=("wx", +1)),
        "fix":  dict(S=S, axis_h=("wx", -1), axis_v=("wy", +1)),
        "fixS": dict(S=None, axis_h=("wx", -1), axis_v=("wy", +1)),  # 每轴回归尺度
    }
    # gain/predict 网格只在校正映射上做
    grid = [("dev", 0.3, 1.0)]
    for gain in (0.2, 0.3, 0.5):
        for pred_s in (0.5, 1.0, 2.0):
            grid.append(("fix", gain, pred_s))
    grid.append(("fixS", 0.3, 1.0))
    for mname, gain, pred_s in grid:
        mp = maps[mname]
        S_use = mp["S"]
        # fixS：每轴用回归斜率的绝对值作为有效 S
        kw = dict(mp)
        if mname == "fixS":
            fus = run_fusion(fts, locked, cx, cy, gyro,
                             (abs(calib["slope_h"]), abs(calib["slope_v"])),
                             gain=gain, predict_ns=int(pred_s * 1e9),
                             axis_h=mp["axis_h"], axis_v=mp["axis_v"])
        else:
            fus = run_fusion(fts, locked, cx, cy, gyro, S_use, gain=gain,
                             predict_ns=int(pred_s * 1e9),
                             axis_h=mp["axis_h"], axis_v=mp["axis_v"])
        errs = evaluate(fus)
        key = f"{mname},gain={gain},pred={pred_s}s"
        results[key] = {
            "relock_err_median": float(np.median(errs)) if len(errs) else None,
            "relock_err_p95": float(np.percentile(errs, 95)) if len(errs) else None,
            "relock_err_max": float(errs.max()) if len(errs) else None,
            "n_relock": int(len(errs)),
            "valid_rate": float(fus["valid"].mean()),
        }
        print(f"[fuse] {key}: relock err median "
              f"{results[key]['relock_err_median']:.1f} P95 "
              f"{results[key]['relock_err_p95']:.1f} (n={len(errs)})")
    # 最优档轨迹存 CSV + 图
    fus_best = run_fusion(fts, locked, cx, cy, gyro, S, gain=0.3,
                          axis_h=("wx", -1), axis_v=("wy", +1))
    out = pd.concat([idx, new[["locked", "cross_x", "cross_y"]].reset_index(drop=True),
                     fus_best], axis=1)
    out.to_csv(out_dir / "fusion_replay.csv", index=False)

    # ---- 受控伪失隐 Monte Carlo：锁定段内随机挖窗，窗末外推误差，gyro vs hold ----
    S_eff = (abs(calib["slope_h"]), abs(calib["slope_v"]))
    gyro0 = gyro.copy()
    gyro0["wx"] = gyro0["wy"] = gyro0["wz"] = 0.0
    rng = np.random.default_rng(7)
    mc = []
    for _ in range(80):
        dur = rng.uniform(0.1, 1.0)
        cand = np.nonzero(locked)[0]
        f0 = int(rng.choice(cand))
        f1 = int(np.searchsorted(fts, fts[f0] + dur * 1e9))
        if f1 >= len(locked) - 1 or not locked[f1]:
            continue
        mask = locked.copy()
        mask[f0:f1 + 1] = False
        for tag, gg, Sx in (("gyro", gyro, S_eff), ("hold", gyro0, S_eff)):
            fus = run_fusion(fts, mask, cx, cy, gg, Sx, gain=0.3,
                             axis_h=("wx", -1), axis_v=("wy", +1))
            if np.isfinite(fus["fused_x"][f1]):
                e = float(np.hypot(fus["fused_x"][f1] - cx[f1],
                                   fus["fused_y"][f1] - cy[f1]))
                mc.append({"tag": tag, "dur": dur, "err": e})
    mc_df = pd.DataFrame(mc)
    mc_df.to_csv(out_dir / "fusion_dropout_mc.csv", index=False)
    mc_df["bin"] = pd.cut(mc_df["dur"], [0, 0.2, 0.5, 1.0])
    mc_tab = mc_df.groupby(["bin", "tag"], observed=True)["err"].median()\
        .unstack().round(1)
    print("[fuse] pseudo-dropout MC, window-end extrapolation err median:\n", mc_tab)
    results["dropout_mc_median"] = {f"{iv}:{tag}": float(v)
                                    for (iv, tag), v in mc_df.groupby(
                                        ["bin", "tag"], observed=True)["err"].median().items()}
    results["dropout_mc_note"] = "挖窗 0.1~1.0s，窗末 |外推-相机| 中位；hold=零速度保持基线"

    # ---- 静止段漂移（fix 映射融合输出的高频抖动与低频漂移） ----
    k5 = np.ones(5) / 5
    fx = fus_best["fused_x"].to_numpy()[s_seg[0]:s_seg[1]]
    fy = fus_best["fused_y"].to_numpy()[s_seg[0]:s_seg[1]]
    rx = (fx - np.convolve(fx, k5, "same"))[2:-2]
    ry = (fy - np.convolve(fy, k5, "same"))[2:-2]
    results["still_fused_jitter_std"] = float(np.hypot(rx, ry).std())
    smx = np.convolve(fx, k5, "same")[2:-2]   # 去掉 MA 边缘效应
    smy = np.convolve(fy, k5, "same")[2:-2]
    results["still_fused_drift_ptp"] = float(np.hypot(np.ptp(smx), np.ptp(smy)))
    print(f"[fuse] still-segment fused jitter std {results['still_fused_jitter_std']:.2f} "
          f"norm px, drift ptp {results['still_fused_drift_ptp']:.1f}")

    fig, ax = plt.subplots(figsize=(11, 5))
    ks = [k for k in results if isinstance(results[k], dict)
          and "relock_err_median" in results[k]]
    med = [results[k]["relock_err_median"] for k in ks]
    p95 = [results[k]["relock_err_p95"] for k in ks]
    xpos = np.arange(len(ks))
    ax.bar(xpos - 0.2, med, 0.4, label="median")
    ax.bar(xpos + 0.2, p95, 0.4, label="P95")
    ax.set_xticks(xpos)
    ax.set_xticklabels(ks, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("relock extrapolation err (norm px)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "fusion_gain.png", dpi=110)
    plt.close(fig)
    return results


if __name__ == "__main__":
    sys.exit(main())
