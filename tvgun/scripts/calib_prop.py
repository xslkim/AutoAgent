#!/usr/bin/env python3
"""陀螺→相机旋转传播模型的标定与验证。

对连续锁定帧对（未平滑的 linefit 四角），在 24 个带符号置换矩阵（proper rotations）
中搜索设备陀螺轴→相机轴映射 M，使 T = K·(M·RΔ·Mᵀ)ᵀ·K⁻¹ 预测的四角位移与实测
位移误差最小；同时扫描焦距尺度因子。两段录制分别标定，验证一致性。

用法:
  .venv/Scripts/python.exe scripts/calib_prop.py --rec test_res/record_20260921_230150
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_record_replay import ReplayDet, load_recording  # noqa: E402

IMG_C = np.array([320.0, 180.0])  # 640x360 主点


def proper_signed_permutations():
    mats = []
    for perm in itertools.permutations(range(3)):
        P = np.zeros((3, 3))
        for i, j in enumerate(perm):
            P[i, j] = 1
        for signs in itertools.product((1, -1), repeat=3):
            M = np.diag(signs) @ P
            if round(np.linalg.det(M)) == 1:
                mats.append(M)
    return mats


def raw_quads(frames):
    """未平滑 linefit 四角（alpha=1），返回 quads[n,8]（640 坐标）与 locked 掩模。"""
    det = ReplayDet("linefit", alpha=1.0)
    n = len(frames)
    quads = np.full((n, 8), np.nan)
    locked = np.zeros(n, bool)
    for s in range(n):
        det.process(frames[s])
        if det.locked and not det.tracked:  # tracked 帧的参考传播会污染标定
            quads[s] = det.corners * 2.0    # det(320) -> 640 坐标
            locked[s] = True
    return quads, locked


def calib(frames, idx, gyro, fov_h_deg, label):
    quads, locked = raw_quads(frames)
    f_nom = 320.0 / np.tan(np.radians(fov_h_deg) / 2)
    gts = gyro["tsNs"].to_numpy()
    gw = gyro[["wx", "wy", "wz"]].to_numpy()
    fts = idx["tsNs"].to_numpy()

    pairs = []
    for i in range(1, len(frames)):
        if not (locked[i] and locked[i - 1]):
            continue
        m = (gts > fts[i - 1]) & (gts <= fts[i])
        if m.sum() < 2:
            continue
        # 梯形积分：端点半步
        ts = np.concatenate([[fts[i - 1]], gts[m], [fts[i]]])
        w = np.vstack([[gw[m][0]], gw[m], [gw[m][-1]]])
        dt = np.diff(ts) * 1e-9
        wmid = (w[:-1] + w[1:]) / 2
        iw = (wmid * dt[:, None]).sum(axis=0)   # rad，设备轴
        move = np.abs(quads[i] - quads[i - 1]).max()
        pairs.append((quads[i - 1].reshape(4, 2), quads[i].reshape(4, 2), iw, move))
    print(f"[{label}] {len(pairs)} locked pairs, f_nom={f_nom:.1f}")

    mats = proper_signed_permutations()
    scales = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2]

    def predict(q0, iw, M, f):
        th = M @ iw                      # 相机轴角增量
        # RΔ ≈ I + [th]x；图像点 p_new = K RΔ K⁻¹ p_old
        K = np.array([[f, 0, 320], [0, f, 180], [0, 0, 1.0]])
        W = np.array([[0, -th[2], th[1]], [th[2], 0, -th[0]], [-th[1], th[0], 0]])
        T = K @ (np.eye(3) + W) @ np.linalg.inv(K)
        ph = np.hstack([q0, np.ones((4, 1))]) @ T.T
        return ph[:, :2] / ph[:, 2:3]

    results = []
    sig_mask = np.array([p[3] > 1.0 for p in pairs])   # 显著运动对（>1px）
    for M in mats:
        for sc in scales:
            errs = []
            for q0, q1, iw, mv in pairs:
                e = np.abs(predict(q0, iw, M, f_nom * sc) - q1).max()
                errs.append(e)
            errs = np.array(errs)
            # 用显著运动对的中位误差打分（静止对被检测噪声主导）
            score = np.median(errs[sig_mask]) if sig_mask.any() else np.median(errs)
            results.append((score, M, sc, errs))
    results.sort(key=lambda r: r[0])
    for score, M, sc, errs in results[:3]:
        print(f"[{label}] score(median err on moving pairs)={score:.3f}px scale={sc}")
        print("  M=\n", M.astype(int))
        e = np.array(errs)
        print(f"  all-pairs err median={np.median(e):.3f} P90={np.percentile(e, 90):.3f} "
              f"moving-pairs n={int(sig_mask.sum())}")
    return results[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True)
    args = ap.parse_args()
    rec = Path(args.rec)
    frames, idx, gyro, detect, meta = load_recording(rec)
    fov = float(meta.get("viewAngle", 67.94))
    calib(frames, idx, gyro, fov, rec.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
