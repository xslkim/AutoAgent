#!/usr/bin/env python3
"""TVGun 光枪追踪器 v4 —— Python 参考实现（与 Java 移植版逐语句对应）。

核心改动（相对 Detector.java + Fusion.java 的旧管线）：
  1. 状态为单应 H（640x360 图像坐标 -> 1920x1080 规范坐标），而非四角+准星；
  2. 帧间由陀螺传播 H：p_new = K·R·K⁻¹·p_old，H ← H·(K·R·K⁻¹)⁻¹，
     R = I+[M·∫(ω-bias)dt]×，M 为两段录制回归出的设备轴→相机轴映射（rot=0）；
  3. 每帧对"预测可见"的每条屏幕边独立做亮边带直线拟合（不依赖完整闭环四边形）：
     每 bin 取亮条纹外侧过零边（亚像素），TLS+2σ 剔除得边线；内侧暗度校验
     拒绝文字屏/灯具假边。校正分两路：
       - 4 边（FULL）：角点=邻边交点 → DLT 解 H_meas → 按比例收敛（绝对复位）；
       - 1-3 边（PARTIAL/EDGE）：图像空间相似校正——平移 t 由 n_eᵀt=o_e 截断
         特征值 2x2 解（平行边对时截掉病态方向）、旋转=夹角加权均值、尺度=
         平行边对间距变化；全部 slew 限幅防可视跳变。
     4 边=FULL，2-3 边=PARTIAL，1 边=EDGE，0 边且视觉丢失<T_MAX=GYRO，否则 DEAD；
  4. 采集（失锁重建）遍历多个候选亮域逐个做四边拟合 + 内部暗度/环形中空校验，
     拒绝灯具/文字屏等干扰（广角录制中旧算法的主要失败源）；
  5. 静止时在线估计陀螺零偏（视觉确认不动 + |ω| 小）。

坐标约定：
  - 图像坐标：640x360，x 右 y 下，主点 (320,180)，焦距 f = 320/tan(fovH/2)；
  - 规范坐标：1920x1080，边框外缘四角 = (0,0)/(1920,0)/(1920,1080)/(0,1080)（沿用旧约定）；
  - 屏幕边线：top L=(0,1,0), right L=(1,0,-1920), bottom L=(0,1,-1080), left L=(1,0,0)，
    图像边线 l = Hᵀ·L（s=H·p ⟹ l_img = Hᵀ·L_screen）。
  - rot=180（sensorLandscape 翻转）时 ωx,ωy 取反后走同一 M（等价 diag(-1,-1,1)·M）。

只使用 numpy + 标准数学，便于纯 Java 移植；采集阶段的连通域用 cv2（Java 侧已有手写 CCL）。
"""
from __future__ import annotations

import collections

import numpy as np

NORM_W, NORM_H = 1920.0, 1080.0
IMG_W, IMG_H = 640.0, 360.0

# 设备轴 -> 相机轴（rot=0），由 calib_prop.py 在两段录制上回归一致得出
M_ROT0 = np.array([[0.0, 1.0, 0.0],
                   [1.0, 0.0, 0.0],
                   [0.0, 0.0, -1.0]])

# 屏幕边线（外缘），顺序 top, right, bottom, left；角点 i = 边 i-1 ∩ 边 i (TL,TR,BR,BL)
EDGE_LINES = np.array([
    [0.0, 1.0, 0.0],          # top:    Y=0
    [1.0, 0.0, -NORM_W],      # right:  X=1920
    [0.0, 1.0, -NORM_H],      # bottom: Y=1080
    [1.0, 0.0, 0.0],          # left:   X=0
])
SCREEN_CORNERS = np.array([[0.0, 0.0], [NORM_W, 0.0],
                           [NORM_W, NORM_H], [0.0, NORM_H]])  # TL,TR,BR,BL

# ---- 等级 ----
GRADE_DEAD, GRADE_GYRO, GRADE_EDGE, GRADE_PARTIAL, GRADE_FULL = 0, 1, 2, 3, 4
GRADE_NAMES = ["DEAD", "GYRO", "EDGE", "PARTIAL", "FULL"]


class TrackerParams:
    fov_h_deg = 67.94          # 镜头水平视场角（meta.viewAngle）
    rotation = 0               # detRotation: 0 or 180

    # 边测量
    band = 12.0                # 预测线两侧带宽（640 px；条纹宽 ~7px + 预测误差）
    band_grow = 12.0           # 边连续未测到/测量不可信时每秒带宽外扩（px/s），上限 band_max
    band_max = 24.0
    edge_bin_w = 3.0           # 纵向分箱宽
    min_edge_bins = 12         # 最少有效 bin
    min_support = 0.45         # 支撑率下限（相对可见段）
    max_sigma = 2.5            # 外包络残差 σ 上限（px）
    trim_rounds = 2
    min_visible_len = 28.0     # 边在图内可见长度下限（px）
    dark_margin = 25           # 内侧暗度校验：内侧中位亮度须 < low_thr - margin（余量）
    inside_off = 10.0          # 内侧采样距离（px，垂直边向四边形内）
    frame_white = 0.0          # FRAME opt-in, zero retains legacy recording behavior
    frame_dark = 0.0

    # H 校正（相似校正 / DLT 混合 + 增益）
    gain_full = 0.6            # FULL 校正增益
    gain_partial = 0.5
    gain_edge = 0.35
    # v3 自适应增益（one-euro 式）：创新量小 → 用 gain_min 平滑噪声；
    # 创新量大 → 升到满增益跟手/快速再锁定。innov 为校正前准星位移（norm px）
    gain_min = 0.35            # 稳态最小增益（FULL；PARTIAL/EDGE 按比例折算）。
                               # 实测权衡：再小会让视差/积分误差积累成慢速摆动
                               # （运动中 MA7 抖动 1.8→2.7px），再大静止噪声上升
    sim_scale_min_edges = 4    # 尺度校正的最少边数（PARTIAL 的间距比尺度太噪）
    gain_ramp_lo = 1.0         # innov < lo → gain_min（过小无意义：σ_meas≈0.5-0.6px；
                               # 过大会形成"误差积累→跨阈→校正"极限环，运动中可见 ~3px 摆动）
    gain_ramp_hi = 12.0        # innov > hi → 满增益（线性过渡）
    gain_motion_k = 0.0        # 运动因子（已实测否决：运动时校正多为真实视差/积分
                               # 误差，少信视觉反而积累——留档勿开）
    slew_cap = 0.0             # 已停用（0=不限幅）：实测限幅会把正确的采集结果
                               # 拖到几十帧才收敛，期间的输出比跳变更糟；
                               # 防假跳变由几何/中空/暗度/一致性门控负责

    # GYRO / DEAD
    t_gyro_max = 3.0           # 无视觉外推时限（s）

    # 零偏估计
    bias_alpha = 0.02          # 静止时 EMA
    bias_max_rate = 0.06       # |ω| 低于此值且视觉确认不动才更新（rad/s）
    # v3 连续零偏估计：FULL 帧把残余校正（图像平移/旋转）折算成角速度误差
    # 缓慢并入零偏——静止学习只覆盖"放着不动"，游玩中零偏会漂（实测两段
    # 录制起止漂移 ~0.01-0.02 rad/s），GYRO 段 1-3s 漂移可达 20-30px
    bias_dyn = True
    bias_dyn_beta = 0.03       # 每 FULL 帧并入比例（~1.1s 时间常数 @30fps）
    bias_dyn_innov_max = 15.0  # 创新量门（norm px，排除再锁定瞬态）
    bias_dyn_rate_max = 1.5    # 陀螺速率门（rad/s，排除运动模糊/快速瞬态）
    bias_dyn_clamp = 0.08      # 零偏总量钳位（rad/s）

    # v3 输出预测：snapshot_ahead(now, ahead) 把 H 传播到将来时刻，
    # 陀螺队尾之后用 ω 的短时 EMA 匀速外推——补偿曝光→处理→传输→渲染
    # 的端到端延迟（实测感知滞后 p95 达 60-100px，是"手感"的主因）
    predict_ema_tau = 0.03     # ω 外推用 EMA 时间常数（s）；v4 起 15→30ms：
                               # 外推噪声 ∝ σ·rem 是"飘"的主源之一，τ 加倍
                               # 噪声 ÷1.6，代价是加速度段外推滞后略增
    predict_max_ahead = 0.25   # 外推时限（s）
    predict_max_ang = 0.5      # 单次外推角度上限（rad）
    predict_damp_tau = 0.08    # v4 起阻尼式外推 θ=ω·τ(1-e^(-t/τ))：外推量饱和
                               # （回甩过冲与外推噪声封顶 ω·τ），代价是持续
                               # 匀速运动欠预测（lag p95 +~25px，中位不变）
    # v4.1 减速感知外推缩放：外推量 × min(1, |ω_ema|/ω_peak)。ω_EMA 有 τ 滞后，
    # 急停瞬间仍按 ~0.5-1 rad/s 外推几十 px，再花 ~0.3s 衰减回来——用户看到
    # 的"快速移动到位后漂移"主要是这个；ω_peak（|ω_raw| 峰值保持，τ=150ms
    # 衰减）在减速时立即压低缩放比，匀速段不受影响（比值≈1 满预测）
    predict_decel_scale = True
    w_peak_tau = 0.15          # ω 峰值保持的衰减时间常数（s）

    # v4 输出平滑（只作用于 snapshot_ahead 显示/射击路径；内部 H 与 process
    # 帧率输出不变——回放等价/伪失锁 MC 语义不受影响）。根因：v3 把 30Hz
    # 视觉校正阶跃（innov 中位 ~6px × 增益）与 ω_EMA 外推噪声（~0.5-1px/tick）
    # 直接放进 120Hz 输出，实测 jerk p50≈1.7-2.0px，肉眼可见"飘"
    out_mode = "oneuro"        # "v3"（不平滑，基线）| "oneuro" | "offset"
    # one-euro（商用体感外设标准方案）：速度低 → 重滤波藏阶跃/震颤；
    # 速度高 → 近乎直通不糊；单 cutoff 两轴共用（指向稳定感的正确做法）
    oe_min_cutoff = 1.5        # Hz，静止截止频率
    oe_beta = 0.02             # 速度系数（cutoff = min + beta·|dhat|）；
                               # v4 实测：0.08 对 2px 校正阶跃近乎直通（截止
                               # 冲到 ~20Hz），0.02 时阶跃瞬时通过 <30%
    oe_dcutoff = 1.0           # 导数通道截止（Hz）
    # offset（误差状态分离）：校正对 H 的位移 Δ 的 (1-φ) 存入显示偏移 d
    # （输出 = H·c + d，连续性不破），d 按自适应 τ 衰减——小偏移慢衰减
    # 藏噪声，大偏移（再锁定）快衰减保收敛；φ 为立即通过比例
    off_instant = 0.3
    off_tau_max = 0.45         # |d|→0 时的衰减时间常数（s）
    off_tau_min = 0.04         # |d| 很大时的衰减时间常数下限（s）
    off_d_scale = 8.0          # τ = τ_max/(1+|d|/d_scale)

    v3 = True                  # False 时退化为 v2 行为（基线对照）

    # v5 在线时间标定（td）：相机↔陀螺时间戳的有效偏移随会话/重启变化
    # （7 段录制离线扫描最优 δ 从 -42ms 到 +36ms 互不一致，两段大样本录制
    # 差 58ms），任何固定值都无法对准——快速甩动时 30ms 错位在 5 rad/s 下
    # 就是 70~100px 的视觉/IMU 失配，是"快移到位后漂移/不稳"的主根因。
    # 方案：4 边测量帧的四角中位位移（/f → 视觉角位移）与陀螺积分角在线
    # 相关，δ 网格扫描取归一化残差最小者 EMA 收敛，用于 process 的传播时刻
    # （等价于把帧时间戳对齐到陀螺时钟）。全程自动，无需用户标定动作。
    td_est = True
    td_max = 0.100           # δ 搜索半径（s）
    td_step = 0.004          # 扫描步长（s）
    td_min_pairs = 10        # 触发一次估计的最少运动约束
    td_every = 10            # 每隔多少帧尝试一次估计（v5.1 试过 5：0921 早期
                             # 假峰复活（+82.8ms 摆动），回滚——预热需要足够
                             # 的数据窗口，不是扫描次数）
    td_min_mag = 1.5         # 有效运动约束下限（px，|om| 低于此的边不计入；
                             # 边线噪声 ~0.5px，小约束会抬高残差下限）
    td_max_gap = 0.40        # 相邻测量帧最大间隔（s；弱可见会话边帧稀疏需放宽，
                             # 旋转用 Rodrigues 精确式，大间隔不一阶近似）
    td_err_max = 0.50        # 应用门：积累曲线最优残差超过则不更新 δ̂
                             # （单次扫描积累门 0.6；在线残差比离线全局
                             # 拟合高，真实会话积累最小值 0.1-0.45）
    td_slew_ns = 0.5e6       # δ̂ 应用限速（ns/帧 ≈15ms/s）：δ̂ 突变让积分
                             # 窗口端点跳动，输出瞬间跳 ω·Δ（实测 jerk p95
                             # 恶化 30%+）；限速后每帧 ≤0.5ms×ω ≤1.2px

    # 采集
    acq_max_cand = 5           # 候选亮域上限
    acq_min_seeds = 10         # 高亮种子下限（宽放低；四边拟合+暗度校验兜底）
    acq_min_blob_frac = 0.006  # 候选域面积下限
    acq_dark_frac = 0.30       # 内环（缩 18%）内亮像素占比上限（中空校验）
    acq_thr = 190.0            # 高阈值夹紧下限（沿用）
    low_thr_ratio = 0.75
    low_thr_min = 150


def _skew(v):
    return np.array([[0.0, -v[2], v[1]],
                     [v[2], 0.0, -v[0]],
                     [-v[1], v[0], 0.0]])


class Tracker:
    """单应传播 + 逐边视觉校正追踪器。输入 640x360 灰度帧 + 陀螺 tick。

    传播是**惰性**的：on_gyro 只入队原始 tick 并在线更新零偏；状态基准
    (H, base_ts) 只在视觉校正/采集后前进；任何时刻的输出由 _prop_from_base
    从基准出发对缓存 tick 重积分得到（不消费队列）。process(frame_ts) 先把
    H 传播到 frame_ts（与帧曝光严格对齐）再做视觉；snapshot(now_ts) 传播到
    now 输出准星。真机事故复盘：worker 处理帧时陀螺已积到"当前"（曝光后
    ~0.1-0.2s），快速运动时预测位置越过实测边 → 边饿死 → GYRO。惰性传播
    使预测始终贴合曝光时刻，且支持 aim 以陀螺速率输出。"""

    def __init__(self, params: TrackerParams | None = None):
        p = self.P = params or TrackerParams()
        f = (IMG_W / 2) / np.tan(np.radians(p.fov_h_deg) / 2)
        self.K = np.array([[f, 0, IMG_W / 2], [0, f, IMG_H / 2], [0, 0, 1.0]])
        self.Ki = np.linalg.inv(self.K)
        self.H = None              # 3x3，img->norm（基准时刻 _h_ts 的 H）
        self._h_ts = -1            # 基准时间戳（ns）
        self.grade = GRADE_DEAD
        self.bias = np.zeros(3)    # 设备轴零偏
        self.cross = np.array([np.nan, np.nan])
        self.n_edges = 0           # 本帧测到的边数
        self.last_vision_t = -1e18
        self.t = 0.0
        self._gq = collections.deque(maxlen=2048)   # (ts,wx,wy,wz)，已按时间有序
        self._gyro_last = -1       # 上一 tick 时间（dt 计算）
        # 诊断
        self.innov = np.nan        # 本帧校正前平均约束残差（norm px 量级）
        self.edges_meas = []       # 本帧测到的边 (idx, line, sigma, support)
        self.acq_candidate = -1
        self.edge_seen_t = [-1e18] * 4   # 每条边最近一次测到的时间（s）
        self._frame_no = 0
        self.meas_cross = np.array([np.nan, np.nan])  # FULL DLT 未平滑测量准星（真值锚点）
        self.innov_pre = np.nan      # 满增益创新量（自适应增益输入/动态零偏门控）
        self._g_eff_last = 0.1       # 最近一次校正实际使用的增益
        self._w_ema = np.zeros(3)  # 外推用角速度 EMA（原始轴，未减零偏）
        self._w_ema_ts = -1
        self._w_peak = 0.0         # |ω_raw| 峰值保持（减速感知外推缩放）
        self._w_peak_ts = -1
        # v4 输出平滑状态
        self._oe = None            # one-euro: [xhat, yhat, dxhat, dyhat]，ts 另记
        self._oe_ts = -1
        self._out_off = np.zeros(2)  # offset 模式显示偏移（norm px）
        self._out_off_ts = -1
        self._cross_pre = None       # process 开头的未校正准星（offset 连续性用）
        # v5 在线时间标定状态
        self._gcum = collections.deque(maxlen=4096)  # (ts,thx,thy,thz) 陀螺累积积分
        self._gcum_th = np.zeros(3)
        self._td_pairs = collections.deque(maxlen=96)  # (t0,t1,ang_v) 运动帧对
        self._td_lines = None      # 上一 ≥2 边测量帧的边线 {edge_idx: line}
        self._td_lines_t = -1.0
        self._td_init = False      # 已有可用 δ̂
        self._td_curve = None      # 残差曲线跨扫描 EMA 积累（51 点网格）
        self._td_ok = 0            # 已积累的有效扫描次数（<8 不应用，预热）
        self._td_last_min = None   # 上次积累曲线 argmin（ms；首应用稳定性判定）
        self._td_stable = 0        # argmin 连续一致次数
        self._td_target_ns = None  # δ̂ 目标值（process 按 td_slew_ns 限速逼近）
        self.td_ns = 0.0           # 当前 δ̂（ns；帧时刻 +δ̂ = 陀螺时钟对应时刻）
        self._td_log = []          # 诊断：每次扫描 (frame_no, best_ms, err)

    # ---------------------------------------------------------------- 陀螺
    def on_gyro(self, ts_ns, wx, wy, wz):
        # 零偏在线学习（每 tick 一次；H 传播与此无关）
        if self._gyro_last >= 0:
            dt = (ts_ns - self._gyro_last) * 1e-9
            if 0 < dt <= 0.1:
                w_raw = np.array([wx, wy, wz], dtype=np.float64)  # float32 输入值拓宽
                # （与 Java float 参数 widened to double 的行为一致）
                if getattr(self, "_vision_still", False) \
                        and np.abs(w_raw).max() < self.P.bias_max_rate:
                    a = self.P.bias_alpha
                    self.bias = (1 - a) * self.bias + a * w_raw
                # 外推用 ω EMA（时间常数 ~30ms，抗单样本噪声）
                if self._w_ema_ts >= 0:
                    a_e = dt / (dt + self.P.predict_ema_tau)
                    self._w_ema = (1 - a_e) * self._w_ema + a_e * w_raw
                else:
                    self._w_ema = w_raw.copy()
                self._w_ema_ts = ts_ns
                # ω 峰值保持（减速感知外推缩放用）：瞬时抬升，τ=150ms 衰减
                wm = float(np.linalg.norm(w_raw))
                if wm >= self._w_peak or self._w_peak_ts < 0:
                    self._w_peak = wm
                else:
                    self._w_peak *= np.exp(-dt / self.P.w_peak_tau)
                self._w_peak_ts = ts_ns
                # v5：陀螺累积积分（td 扫描的 ∫[a,b] 取值来源；原始 ω，
                # 零偏 ~0.01rad/s×33ms≈0.15px 对 δ 估计可忽略）
                self._gcum_th = self._gcum_th + w_raw * dt
        self._gyro_last = ts_ns
        self._gq.append((ts_ns, wx, wy, wz))
        self._gcum.append((ts_ns, self._gcum_th[0], self._gcum_th[1],
                           self._gcum_th[2]))

    def _prop_from_base(self, ts_ns):
        """从基准 (H, _h_ts) 出发对 (_h_ts, ts_ns] 内的缓存 tick 重积分，
        返回 ts_ns 时刻的 H（不修改基准，不消费队列）。H 为 None 时返回 None。"""
        if self.H is None:
            return None
        H = self.H.copy()
        prev_ts = None
        for ts_g, wx, wy, wz in self._gq:
            if ts_g <= self._h_ts:
                prev_ts = ts_g          # 窗口前一个 tick 作为 dt 锚点
                continue
            if ts_g > ts_ns:
                break
            dt = (ts_g - prev_ts) * 1e-9 if prev_ts is not None else 0.0
            prev_ts = ts_g
            if dt <= 0 or dt > 0.1:
                continue
            w = np.array([wx, wy, wz]) - self.bias
            if self.P.rotation == 180:
                w = w * np.array([-1.0, -1.0, 1.0])
            th = M_ROT0 @ (w * dt)
            T = self.K @ (np.eye(3) + _skew(th)) @ self.Ki
            try:
                H = _norm_h(H @ np.linalg.inv(T))
            except np.linalg.LinAlgError:
                return None
        return H

    def _propagate_to(self, ts_ns):
        """把基准推进到 ts_ns（process 用）：H 传播 + 基准时间更新 + 清理旧 tick。
        保留 ts_ns 处的 tick 作为下一次积分的 dt 锚点。"""
        if self.H is not None and ts_ns > self._h_ts:
            self.H = self._prop_from_base(ts_ns)
        self._h_ts = ts_ns
        while self._gq and self._gq[0][0] < ts_ns:
            self._gq.popleft()

    # ---------------------------------------------------------------- 准星输出
    def snapshot(self, now_ns):
        """传播到 now 并返回当前准星（供 aim 线程以任意速率调用；不推进基准）。"""
        H = self._prop_from_base(now_ns) if now_ns > self._h_ts else self.H
        if H is None or self.grade == GRADE_DEAD:
            return self.cross[0], self.cross[1], GRADE_DEAD
        c = H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        self.cross = c[:2] / c[2]
        return self.cross[0], self.cross[1], self.grade

    def snapshot_ahead(self, now_ns, ahead_ns):
        """预测 now+ahead 时刻的准星（补偿曝光→处理→传输→渲染的端到端延迟）。
        先按队列陀螺传播（与 snapshot 相同），队尾之后用 ω 的短时 EMA 匀速
        外推（predict_damp_tau>0 时为阻尼外推）；外推限时/限角防甩尾过冲。
        ahead=0 退化为 snapshot。v4：返回值经 out_mode 输出平滑。"""
        p = self.P
        if self.H is None or self.grade == GRADE_DEAD:
            return self.cross[0], self.cross[1], GRADE_DEAD
        ahead_ns = int(min(max(ahead_ns, 0), p.predict_max_ahead * 1e9))
        tgt = now_ns + ahead_ns
        H = self._prop_from_base(tgt) if tgt > self._h_ts else self.H
        if H is None:
            return self.cross[0], self.cross[1], GRADE_DEAD
        last_ts = self._h_ts
        # 队列可能含前瞻样本（真机管道延迟/回放 slack）：外推余量必须
        # 相对最后一个 ≤tgt 的 tick，而非物理队尾（否则前瞻样本会
        # 把 rem 压成 0，外推被错误关闭）
        for ts_g, *_ in reversed(self._gq):
            if ts_g <= tgt:
                last_ts = ts_g
                break
        rem = (tgt - max(last_ts, self._h_ts)) * 1e-9
        if rem > 0:
            w = self._w_ema - self.bias
            if p.rotation == 180:
                w = w * np.array([-1.0, -1.0, 1.0])
            if p.predict_damp_tau > 0:
                rem_eff = p.predict_damp_tau * (1.0 - np.exp(-rem / p.predict_damp_tau))
            else:
                rem_eff = rem
            th = M_ROT0 @ (w * rem_eff)
            if p.predict_decel_scale:
                wm = float(np.linalg.norm(w))
                if self._w_peak > 1e-6:
                    th = th * min(1.0, wm / self._w_peak)
            n = float(np.linalg.norm(th))
            if n > p.predict_max_ang:
                th = th * (p.predict_max_ang / n)
            T = self.K @ (np.eye(3) + _skew(th)) @ self.Ki
            try:
                H = _norm_h(H @ np.linalg.inv(T))
            except np.linalg.LinAlgError:
                H = None
            if H is None:
                return self.cross[0], self.cross[1], self.grade
        c = H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        cc = c[:2] / c[2]
        if p.out_mode == "offset":
            cc = cc + self._decay_out_off(now_ns)
        elif p.out_mode == "oneuro":
            cc = self._oneuro(cc, now_ns)
        return cc[0], cc[1], self.grade

    # ---------------------------------------------------------------- v4 输出平滑
    def _decay_out_off(self, now_ns):
        """offset 模式：显示偏移 d 按自适应 τ 向 0 衰减（惰性，按调用时刻结算）。
        τ = τ_max/(1+|d|/d_scale)：小偏移慢衰减（藏测量噪声/校正阶跃），
        大偏移（再锁定/采集融合）快衰减（保收敛）。"""
        p = self.P
        if self._out_off_ts < 0:
            return self._out_off
        dt = (now_ns - self._out_off_ts) * 1e-9
        if dt <= 0:
            return self._out_off
        m = float(np.hypot(self._out_off[0], self._out_off[1]))
        tau = max(p.off_tau_max / (1.0 + m / p.off_d_scale), p.off_tau_min)
        self._out_off = self._out_off * np.exp(-dt / tau)
        self._out_off_ts = now_ns
        return self._out_off

    def _oneuro(self, c, now_ns):
        """one-euro 滤波（2D 单 cutoff）：|速度|小 → 截止低重滤波（静止/慢瞄
        藏住 30Hz 校正阶跃与 ω_EMA 外推噪声）；|速度|大 → 截止高近乎直通
        （快速运动不糊、校正即过——运动中阶跃本身不可见）。同一 now 重复
        调用不推进状态（diag 会对同一时刻多次采样）。"""
        p = self.P
        if self._oe is None:
            self._oe = np.array([c[0], c[1], 0.0, 0.0])
            self._oe_ts = now_ns
            return self._oe[:2].copy()
        dt = (now_ns - self._oe_ts) * 1e-9
        if dt < 1e-4:
            return self._oe[:2].copy()
        dt = min(dt, 0.05)
        xhat, yhat, dxhat, dyhat = self._oe

        def alpha(cutoff):
            return 1.0 / (1.0 + (1.0 / (2.0 * np.pi * cutoff)) / dt)

        a_d = alpha(p.oe_dcutoff)
        dx = (c[0] - xhat) / dt
        dy = (c[1] - yhat) / dt
        dxhat = dxhat + a_d * (dx - dxhat)
        dyhat = dyhat + a_d * (dy - dyhat)
        cutoff = p.oe_min_cutoff + p.oe_beta * float(np.hypot(dxhat, dyhat))
        a = alpha(cutoff)
        xhat = xhat + a * (c[0] - xhat)
        yhat = yhat + a * (c[1] - yhat)
        self._oe = np.array([xhat, yhat, dxhat, dyhat])
        self._oe_ts = now_ns
        return self._oe[:2].copy()

    # ---------------------------------------------------------------- 主入口
    def process(self, g640: np.ndarray, ts_ns):
        p = self.P
        # 1) 先把基准（与 H）传播到帧曝光时刻（v5：+δ̂ 对齐到陀螺时钟；
        #    δ̂ 向目标限速逼近，突变会让输出瞬间跳 ω·Δ）
        if self._td_target_ns is not None:
            d = self._td_target_ns - self.td_ns
            self.td_ns += d if abs(d) <= p.td_slew_ns \
                else p.td_slew_ns * (1.0 if d > 0 else -1.0)
        self._propagate_to(ts_ns + int(round(self.td_ns)))
        self.t = ts_ns * 1e-9
        self._frame_no += 1
        self.edges_meas = []
        self.innov = np.nan
        self.innov_pre = np.nan
        self.meas_cross[:] = np.nan
        self.acq_candidate = -1
        # v4 offset：校正前（已传播到 ts）的准星，帧末用来保持输出连续
        if p.out_mode == "offset" and self.H is not None:
            cp = self.H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
            self._cross_pre = cp[:2] / cp[2]
        else:
            self._cross_pre = None

        # 2) 阈值（与旧管线一致的全图直方图法）
        thr, low_thr = self._thresholds(g640)

        # 3) 跟踪路径：逐边测量 + H 校正
        corrected = False
        if self.H is not None:
            meas = self._measure_edges(g640, low_thr)
            self.edges_meas = meas
            if meas and p.td_est:
                self._td_note_lines(meas)
            if meas:
                # 动态零偏的残余分解必须在校正应用前做（校正后残余被增益削减）
                dec4 = self._sim_decompose(meas) if len(meas) == 4 else None
                self._apply_correction(meas)
                corrected = True
                self.last_vision_t = self.t
                self.n_edges = len(meas)
                self.grade = {4: GRADE_FULL, 3: GRADE_PARTIAL, 2: GRADE_PARTIAL,
                              1: GRADE_EDGE}[len(meas)]
                self._update_bias()
                if dec4 is not None:
                    self._update_bias_dyn(dec4)
            else:
                self.n_edges = 0
                if self.t - self.last_vision_t > p.t_gyro_max:
                    self.H = None
                else:
                    self.grade = GRADE_GYRO

        # 4) 采集路径：无 H 时必须采集；GYRO 超 0.3s 或边数长期不足时并行采集
        #    （追踪漂移/偏置超出门限时由采集纠回；采集校验严格，不会错锁）
        need_acq = self.H is None
        if not need_acq and self.grade == GRADE_GYRO \
                and self.t - self.last_vision_t > 0.3:
            need_acq = True
        if not need_acq and self.n_edges < 3 and self._frame_no % 5 == 0:
            need_acq = True
        if need_acq:
            cands = self._acq_candidates(g640, thr, low_thr)
            h_acq = self._acquire(g640, thr, low_thr, cands)
            acq_edges = 4
            if h_acq is None:
                h_acq = self._acquire_partial(g640, thr, low_thr, cands)
                acq_edges = 2
            if h_acq is not None:
                ca = (h_acq @ np.array([IMG_W / 2, IMG_H / 2, 1.0]))
                ca = ca[:2] / ca[2]
                if acq_edges == 4:
                    self.meas_cross = ca.copy()     # 采集 DLT 也是真值锚点
                if self.H is None:
                    self.H = h_acq
                    self.grade = GRADE_FULL if acq_edges == 4 else GRADE_PARTIAL
                    self.n_edges = acq_edges
                    self.last_vision_t = self.t
                    self.edge_seen_t = [self.t] * 4
                else:
                    # 与现有 H 比较：采集自身的 ~1px 噪声不引入——以**四角最大位移**
                    # 为准（仅看准星会漏判：形状不同的四边形中心可能恰好重合）
                    cb = self.H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
                    cb = cb[:2] / cb[2]
                    dist = float(np.hypot(*(ca - cb)))
                    qa = (np.linalg.inv(h_acq) @ np.hstack([SCREEN_CORNERS, np.ones((4, 1))]).T).T
                    qa = qa[:, :2] / qa[:, 2:3]
                    qb = (np.linalg.inv(self.H) @ np.hstack([SCREEN_CORNERS, np.ones((4, 1))]).T).T
                    qb = qb[:, :2] / qb[:, 2:3]
                    cdist = float(np.abs(qa - qb).max())
                    if cdist > 6.0:
                        g_mix = 0.9 if dist > 100 else 0.7
                        if self.P.slew_cap > 0 and dist > self.P.slew_cap:
                            g_mix = g_mix * self.P.slew_cap / dist
                        h = (1 - g_mix) * self.H.reshape(9) + g_mix * h_acq.reshape(9)
                        self.H = _norm_h(h.reshape(3, 3))
                        self.grade = GRADE_FULL if acq_edges == 4 else GRADE_PARTIAL
                        self.n_edges = acq_edges
                        self.last_vision_t = self.t
                        self.edge_seen_t = [self.t] * 4
        if self.H is None:
            self.grade = GRADE_DEAD
            self.cross[:] = np.nan
            # 失锁即重置输出平滑（无连续性可保；重锁定应直接跳到真值）
            self._oe = None
            self._oe_ts = -1
            self._out_off[:] = 0.0
            self._out_off_ts = -1
            self._cross_pre = None
            return

        # 5) 输出准星 = H·图像中心
        c = self.H @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        self.cross = c[:2] / c[2]

        # 5.5) v5 在线时间标定：周期性 δ 扫描
        if p.td_est and self._frame_no % p.td_every == 0:
            self._td_scan()

        # 6) v4 offset：本帧校正/采集对 H 的总位移的 (1-φ) 存入显示偏移
        if self._cross_pre is not None and np.isfinite(self.cross).all():
            step = self._cross_pre - self.cross
            self._out_off += (1.0 - p.off_instant) * step
            self._out_off_ts = ts_ns
        self._cross_pre = None

    # ---------------------------------------------------------------- 阈值
    @staticmethod
    def _thresholds(g640):
        g = g640[::2, ::2]
        hist = np.bincount(g.ravel(), minlength=256)
        need = int(g.size * 0.02) + 1
        acc, thr = 0, 255
        for v in range(255, -1, -1):
            acc += int(hist[v])
            if acc >= need:
                thr = v
                break
        thr = min(max(thr, TrackerParams.acq_thr), 254)
        low_thr = max(TrackerParams.low_thr_min, int(thr * TrackerParams.low_thr_ratio))
        return thr, low_thr

    # ---------------------------------------------------------------- 边测量
    def _measure_edges(self, g640, low_thr):
        p = self.P
        Hn = _norm_h(self.H)
        lines_pred = Hn.T @ EDGE_LINES.T     # 3x4：每列一条预测图像边线
        # 预测四角（图像坐标）
        Hi = np.linalg.inv(Hn)
        pc = (Hi @ np.hstack([SCREEN_CORNERS, np.ones((4, 1))]).T).T
        pc = pc[:, :2] / pc[:, 2:3]
        meas = []
        for e in range(4):
            # 边 e 端点 = 角点 e 与 e+1（top: TL->TR, right: TR->BR, ...）
            p0, p1 = pc[e], pc[(e + 1) % 4]
            seg = _clip_segment(p0, p1, 4.0)
            if seg is None:
                continue
            q0, q1 = seg
            if np.hypot(*(q1 - q0)) < p.min_visible_len:
                continue
            # 每边自适应带宽：连续未测到越久带宽越大
            band_e = min(p.band + p.band_grow * (self.t - self.edge_seen_t[e]),
                         p.band_max)
            lp = lines_pred[:, e]
            nrm = np.hypot(lp[0], lp[1])
            if nrm < 1e-12:
                continue
            lp = lp / nrm
            cen = pc.mean(axis=0)
            fit = _fit_line_band(g640, low_thr, q0, q1, band_e, p, cen=cen)
            if fit is None:
                continue
            line, sigma, support, pa, pb = fit
            mid = (q0 + q1) / 2
            # 创新门限：拟合线与预测线的平均有向距离（随带宽动态放宽）
            innov = abs(line[0] * mid[0] + line[1] * mid[1] + line[2]
                        - (lp[0] * mid[0] + lp[1] * mid[1] + lp[2]))
            # 两线夹角门限（防止贴合到交叉亮结构）
            ang = abs(line[0] * lp[1] - line[1] * lp[0])
            if innov > band_e or ang > 0.10:
                if DEBUG_SEQ == self._frame_no - 1:
                    print(f"dbg py seq {DEBUG_SEQ} edge {e}: gate innov={innov:.1f} ang={ang:.3f} band={band_e:.1f}")
                continue
            # 内侧暗度：沿边多点向四边形内采样，中位亮度须暗
            d_in = np.array([-line[0], -line[1]])     # line 法向朝外 -> 内侧为负
            L = np.hypot(*(q1 - q0))
            n_s = max(3, int(L / 40))
            ts = np.linspace(0.15, 0.85, n_s)
            samp = []
            for tt in ts:
                sp = q0 + (q1 - q0) * tt + d_in * p.inside_off
                if p.frame_white > 0 and p.frame_dark > 0:
                    border = q0 + (q1 - q0) * tt
                    norm = Hn @ np.array([border[0], border[1], 1.0])
                    norm = norm[:2] / norm[2]
                    inset = p.frame_white + p.frame_dark * 0.5
                    if e == 0:
                        norm[1] = inset
                    elif e == 1:
                        norm[0] = NORM_W - inset
                    elif e == 2:
                        norm[1] = NORM_H - inset
                    else:
                        norm[0] = inset
                    projected = Hi @ np.array([norm[0], norm[1], 1.0])
                    sp = projected[:2] / projected[2]
                xi, yi = int(round(sp[0])), int(round(sp[1]))
                if 0 <= xi < g640.shape[1] and 0 <= yi < g640.shape[0]:
                    samp.append(int(g640[yi, xi]))
            if len(samp) >= 3 and np.median(samp) > low_thr - p.dark_margin:
                if DEBUG_SEQ == self._frame_no - 1:
                    print(f"dbg py seq {DEBUG_SEQ} edge {e}: darkness reject med={np.median(samp):.0f} thr={low_thr}")
                continue    # 内侧不暗：文字屏/灯具等假边
            # 约束点 = 实测支撑段首末位置（不再用预测端点）
            # 仅当创新量可信时重置带宽计时（边界拟合不收窄带宽，防"窄带锁定错误线"）
            if innov < min(band_e / 2, 5.0):
                self.edge_seen_t[e] = self.t
            meas.append((e, line, sigma, support, pa, pb))
        return meas

    # ---------------------------------------------------------------- H 校正
    def _apply_correction(self, meas):
        """两种机制：
        - 4 边（FULL）：角点交点 -> DLT 直接解 H_meas，向它按比例收敛（绝对复位，
          消除相似校正无法观测的透视自由度漂移）；
        - 1-3 边：图像空间相似校正（平移/旋转/尺度）——每边提供法向偏移 o_e
          （预测线到实测线的有向距离）与夹角 δθ_e；平移由 n_eᵀt=o_e 最小二乘，
          旋转=夹角加权均值，尺度=平行边对间距比。良态、无病态求解。"""
        p = self.P
        h = _norm_h(self.H).reshape(9)
        g = {4: p.gain_full, 3: p.gain_partial, 2: p.gain_partial,
             1: p.gain_edge}[len(meas)]
        if len(meas) == 4:
            lines = {e: line for e, line, sigma, support, pa, pb in meas}
            corners = []
            ok = True
            for k in range(4):
                cr = np.cross(lines[(k - 1) % 4], lines[k])
                if abs(cr[2]) < 1e-9:
                    ok = False
                    break
                corners.append(cr[:2] / cr[2])
            if ok and _geo_valid(np.array(corners)):
                H_meas = _h_from_corners(np.array(corners))
                if H_meas is not None:
                    Hm = _norm_h(H_meas)
                    if float((Hm.reshape(9) @ h)) < 0:
                        Hm = -Hm
                    self._blend_h(Hm, g)
                    return
            # 4 边但角点非法：退回相似校正
        self._similarity_correction(meas, g)

    # ------------------------------------------------------------ v5 在线时间标定
    def _td_note_lines(self, meas):
        """≥1 边测量帧：与上一测量帧的共同边构成帧对 (t0,t1,{e:(l0,l1)})。
        边线本身是带内新拟合的纯图像测量，不含陀螺与预测状态。"""
        p = self.P
        cur = {e: line.copy() for e, line, sigma, support, pa, pb in meas}
        if self._td_lines is not None:
            gap = self.t - self._td_lines_t
            if 0 < gap <= p.td_max_gap:
                edges = {e: (self._td_lines[e], cur[e])
                         for e in cur if e in self._td_lines}
                if edges:
                    self._td_pairs.append((self._td_lines_t, self.t, edges))
        if cur:
            self._td_lines = cur
            self._td_lines_t = self.t

    def _td_scan(self):
        """δ 网格扫描：对每个候选 δ，用陀螺积分旋转 T(δ)=K(I+[M∫ω]x)K⁻¹
        把帧对首帧的每条共同边线变换到末帧时刻（纯旋转对任意角度精确），
        与实测末帧边线的法向偏移作残差；每个 δ 拟合尺度 k=Σom·op/Σop²
        （吸收焦距误差/平移视差/卷帘快门的幅度系统差——无 k 时这些系统
        差会把 argmin 推到错误 δ，实测可发散到搜索边界），归一化中位残差
        最小者并入 δ̂ EMA。1 边帧也贡献约束（该法向的 1D 位移）。"""
        p = self.P
        if len(self._td_pairs) < p.td_min_pairs or len(self._gcum) < 8:
            return
        g = np.asarray(self._gcum)
        gts = g[:, 0] * 1e-9
        cum = g[:, 1:4]
        pairs = [q for q in self._td_pairs
                 if q[0] - p.td_max >= gts[0] and q[1] + p.td_max <= gts[-1]]
        if len(pairs) < p.td_min_pairs:
            return

        def rot_vec(t0, t1):
            def at(tt):
                i = int(np.clip(np.searchsorted(gts, tt), 1, len(gts) - 1))
                ta, tb = gts[i - 1], gts[i]
                w = (tt - ta) / max(tb - ta, 1e-9)
                return cum[i - 1] + (cum[i] - cum[i - 1]) * w
            return at(t1) - at(t0)

        sgn = np.array([-1.0, -1.0, 1.0]) if p.rotation == 180 else None
        deltas = np.arange(-p.td_max, p.td_max + 1e-9, p.td_step)
        curve = np.full(len(deltas), np.nan)
        ncnt = np.zeros(len(deltas), dtype=int)
        for i, d in enumerate(deltas):
            om_l, op_l = [], []
            for t0, t1, edges in pairs:
                th = rot_vec(t0 + d, t1 + d)
                if sgn is not None:
                    th = th * sgn
                th = M_ROT0 @ th
                # Rodrigues 精确旋转（帧对间隔可达 0.4s，一阶 skew 在
                # 大角度下误差 5-10% 会污染快速段）
                ang = float(np.linalg.norm(th))
                if ang < 1e-9:
                    R = np.eye(3)
                else:
                    S = _skew(th)
                    R = np.eye(3) + (np.sin(ang) / ang) * S \
                        + ((1.0 - np.cos(ang)) / (ang * ang)) * (S @ S)
                T = self.K @ R @ self.Ki
                TiT = np.linalg.inv(T).T
                for l0, l1 in edges.values():
                    lp = TiT @ l0
                    n2 = float(lp[0] * lp[0] + lp[1] * lp[1])
                    if n2 < 1e-12:
                        continue
                    lp = lp / np.sqrt(n2)
                    la = l1 if float(l0[:2] @ l1[:2]) >= 0 else -l1
                    if float(l0[:2] @ lp[:2]) < 0:
                        lp = -lp
                    om_l.append(float(l0[2] - la[2]))
                    op_l.append(float(l0[2] - lp[2]))
            om = np.array(om_l)
            op = np.array(op_l)
            # 只用有效运动约束（|om|≥td_min_mag）：边线拟合噪声 ~0.5px，
            # 把小运动约束算进归一化会把残差下限抬到 0.3-0.5 淹没判别力；
            # 按 om 门控与 δ 无关，不引入选择偏差
            sel = np.abs(om) >= p.td_min_mag
            if sel.sum() < p.td_min_pairs:
                continue
            ncnt[i] = int(sel.sum())
            oms = om[sel]
            ops = op[sel]
            s = float(ops @ ops)
            k = float(oms @ ops / s) if s > 1e-12 else 0.0
            curve[i] = float(np.median(np.abs(oms - k * ops))
                             / max(float(np.median(np.abs(oms))), 1e-9))
        if np.isfinite(curve).sum() < len(deltas) * 0.6:
            return
        bi = int(np.nanargmin(curve))
        self._td_log.append((self._frame_no, deltas[bi] * 1e3, curve[bi]))
        if curve[bi] > 0.6:
            return                      # 本次扫描质量差，不积累
        # 残差曲线跨扫描 EMA 积累：真 δ 恒定，积累后曲线最小值随数据变锐。
        # 预热 ≥8 次扫描后才允许应用（0921 实测：早期稀少约束下 +82.8ms 的
        # 偶然假最小值曾把输出甩出去 ~5s）；扫描按有效约束数加权
        # （<30 约束的扫描降权，稀释偶然性）；之后与当前 δ̂ 不一致的扫描
        # 再降权（0.06）防偏差段拉动已收敛估计
        n_sel = ncnt[bi]
        w = 0.25
        if self._td_ok >= 8:
            w = 0.25 if abs(deltas[bi] * 1e9 - self.td_ns) <= 20e6 else 0.06
        w *= min(1.0, n_sel / 30.0)
        if self._td_curve is None:
            self._td_curve = curve.copy()
        else:
            keep = np.isfinite(self._td_curve)
            both = keep & np.isfinite(curve)
            self._td_curve[both] = (1.0 - w) * self._td_curve[both] \
                + w * curve[both]
            self._td_curve[~keep] = curve[~keep]
        self._td_ok += 1
        if self._td_ok < 8:
            return
        bi2 = int(np.nanargmin(self._td_curve))
        if bi2 == 0 or bi2 == len(deltas) - 1:
            return                      # 顶到搜索边界：疑似发散/越界，不采用
        if self._td_curve[bi2] >= p.td_err_max:
            return
        # 首次应用要求积累曲线 argmin 连续 2 次一致（±8ms）——把早期
        # 不稳定挡在门外；之后由滞回接管
        min_ms = float(deltas[bi2] * 1e3)
        if self._td_last_min is not None \
                and abs(min_ms - self._td_last_min) <= 8.0:
            self._td_stable += 1
        else:
            self._td_stable = 0
        self._td_last_min = min_ms
        if not self._td_init and self._td_stable < 2:
            return
        # 抛物线亚网格细化（积累曲线在最值附近光滑，~1-2ms 精度）
        y0, y1, y2 = self._td_curve[bi2 - 1:bi2 + 2]
        den = float(y0 - 2.0 * y1 + y2)
        off = 0.0
        if den > 1e-12:
            off = float(np.clip(0.5 * (y0 - y2) / den, -1.0, 1.0)) \
                * p.td_step
        new_ns = (deltas[bi2] + off) * 1e9
        # 滞回：与当前 δ̂ 不同的候选须显著更优（-0.03）才切换
        cur_i = int(np.argmin(np.abs(deltas * 1e9 - self.td_ns)))
        if not self._td_init or bi2 == cur_i \
                or self._td_curve[bi2] < self._td_curve[cur_i] - 0.03:
            # 死区：与当前 δ̂ 差 ≤2ms 的更新多为抛物线 hunting 抖动，
            # 每次目标更新都经限速斜坡向 aim 流注入涟漪（jerk p95 来源）
            if self._td_target_ns is None \
                    or abs(float(new_ns) - self._td_target_ns) > 2e6:
                self._td_target_ns = float(new_ns)  # process 限速逼近
            self._td_init = True

    def _adapt_gain(self, g_base, dist):
        """one-euro 式自适应增益：创新量小（稳态）→ 小增益平滑 30Hz 测量噪声；
        创新量大（真实运动/再锁定）→ 满增益跟手。v2 固定增益在运动中产生
        可见的 30Hz 阶跃（实测 FULL innov p95 达 8-12px）。
        运动因子：|ω| 大时视觉测量被卷帘快门/时间戳残差污染（误差∝|ω|），
        陀螺传播对纯旋转精确，故高速再按比例少信视觉。"""
        if not self.P.v3:
            return g_base
        lo, hi = self.P.gain_ramp_lo, self.P.gain_ramp_hi
        frac = 0.0 if dist <= lo else (1.0 if dist >= hi else (dist - lo) / (hi - lo))
        g = g_base * (self.P.gain_min + (1.0 - self.P.gain_min) * frac)
        w = float(np.linalg.norm(self._w_ema))
        return g / (1.0 + self.P.gain_motion_k * w)

    def _blend_h(self, H_target, g):
        """向目标 H 收敛，准星位移 slew 限幅。"""
        p = self.P
        h0 = _norm_h(self.H)
        c0 = h0 @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        c0 = c0[:2] / c0[2]
        c1 = H_target @ np.array([IMG_W / 2, IMG_H / 2, 1.0])
        c1 = c1[:2] / c1[2]
        self.meas_cross = c1.copy()     # 未平滑真值锚点（诊断/评测用）
        dist = float(np.hypot(*(c1 - c0)))
        self.innov = dist
        self.innov_pre = dist
        gg = self._adapt_gain(g, dist)
        self._g_eff_last = gg
        if p.slew_cap > 0 and dist > p.slew_cap:
            gg = gg * p.slew_cap / dist
        h = (1 - gg) * h0.reshape(9) + gg * H_target.reshape(9)
        self.H = _norm_h(h.reshape(3, 3))

    def _sim_decompose(self, meas):
        """相似校正分解（不应用）：平移 t 由 n_eᵀt=o_e 截断特征值 2x2 解
        （平行边对时截掉病态方向）、旋转=夹角加权均值、尺度=平行边对间距比。
        良态、无病态求解。返回 (t, theta, s) 满增益量；失败 None。"""
        p = self.P
        Hn = _norm_h(self.H)
        Hi = np.linalg.inv(Hn)
        pc_pred = (Hi @ np.hstack([SCREEN_CORNERS, np.ones((4, 1))]).T).T
        pc_pred = pc_pred[:, :2] / pc_pred[:, 2:3]
        cen = pc_pred.mean(axis=0)
        lines_pred = Hn.T @ EDGE_LINES.T
        # 平移：n_eᵀ t = o_e（o_e = 实测中点到预测线的有向距离，法向统一朝外）
        trows, tvals, tw = [], [], []
        angles, aw = [], []
        outs = {}
        for e, line, sigma, support, pa, pb in meas:
            lp = lines_pred[:, e]
            nrm = np.hypot(lp[0], lp[1])
            if nrm < 1e-12:
                continue
            lp = lp / nrm
            # 预测线法向统一朝外（背离预测质心），否则 o/δθ 符号混乱
            me = (pc_pred[e] + pc_pred[(e + 1) % 4]) / 2
            if lp[0] * (me[0] - cen[0]) + lp[1] * (me[1] - cen[1]) < 0:
                lp = -lp
            mid = (pa + pb) / 2
            o = lp[0] * mid[0] + lp[1] * mid[1] + lp[2]     # >0 = 实测在预测外侧
            le = float(np.hypot(*(pb - pa)))
            w = support * max(le, 1.0)
            outs[e] = (o, lp)
            trows.append(lp[:2])
            tvals.append(o)
            tw.append(w)
            dth = np.arctan2(lp[0] * line[1] - lp[1] * line[0],
                             lp[0] * line[0] + lp[1] * line[1])
            angles.append(dth)
            aw.append(w)
        if not trows:
            return None
        A = np.stack(trows)
        b = np.array(tvals)
        W = np.diag(np.array(tw) / max(tw))
        # 2x2 加权最小二乘；平行边对（top+bottom / left+right）时 A 行近反平行，
        # 垂直于边的方向病态——按特征值截断，只沿可观测方向校正
        ata = A.T @ W @ A
        atb = A.T @ W @ b
        ev, V = np.linalg.eigh(ata)
        t = np.zeros(2)
        for i in range(2):
            if ev[i] > 0.04 * ev[-1]:
                t += (V[:, i] @ atb) / ev[i] * V[:, i]
        theta = float(np.average(angles, weights=aw))
        # 尺度：平行边对间距变化（o 已统一朝外）
        s = 1.0
        s_list = []
        for e0, e1 in ((0, 2), (3, 1)):
            if e0 not in outs or e1 not in outs:
                continue
            o0, lp0 = outs[e0]
            o1, lp1 = outs[e1]
            n_axis = lp0[:2] - lp1[:2]
            na = np.hypot(*n_axis)
            if na < 1e-6:
                continue
            n_axis = n_axis / na
            D_pred = abs(n_axis @ (pc_pred[e0] - pc_pred[e1]))
            if D_pred > 20:
                s_list.append(1.0 + (o0 + o1) / D_pred)
        if s_list:
            s = float(np.clip(np.mean(s_list), 0.9, 1.1))
        if DEBUG_SEQ == self._frame_no - 1:
            print(f"dbg py seq {DEBUG_SEQ}: simcorr t={np.round(t,3)} "
                  f"theta={np.degrees(theta):.3f} s={s:.4f}")
        return t, theta, s

    def _similarity_correction(self, meas, g):
        p = self.P
        dec = self._sim_decompose(meas)
        if dec is None:
            return
        t, theta, s = dec
        # v5.1：尺度校正仅 FULL（4 边）启用——PARTIAL 时 s 来自单平行边对
        # 间距比，σ≈0.7%/帧（σ_o≈1px/间距200px），×增益后每帧 ~0.3% 的
        # 尺度抖动经杠杆放大成准星抖动，还漂移 H 的尺度→回 FULL 跳变；
        # 实测关 PARTIAL 尺度后重锁定跳变中位 29.6→9.2px（220120）
        if len(meas) < p.sim_scale_min_edges:
            s = 1.0
        cx0, cy0 = IMG_W / 2, IMG_H / 2
        c0 = self.H @ np.array([cx0, cy0, 1.0])
        c0 = c0[:2] / c0[2]
        # v3 自适应增益：以满增益校正的准星位移为创新量
        if p.v3:
            Cf = _sim_matrix(t, theta, s, cx0, cy0)
            Hf = _norm_h(self.H @ np.linalg.inv(Cf))
            cf = Hf @ np.array([cx0, cy0, 1.0])
            cf = cf[:2] / cf[2]
            self.innov_pre = float(np.hypot(*(cf - c0)))
            g = self._adapt_gain(g, self.innov_pre)
            self._g_eff_last = g
        #  fractional 应用 + slew 限幅
        t = t * g
        theta = theta * g
        s = 1.0 + (s - 1.0) * g
        if abs(theta) > np.radians(3):
            theta = np.sign(theta) * np.radians(3)
        # C(p) = s·R(θ)·(p-c) + c + t
        C = _sim_matrix(t, theta, s, cx0, cy0)
        # slew 限幅：比较校正前后准星
        H1 = _norm_h(self.H @ np.linalg.inv(C))
        c1 = H1 @ np.array([cx0, cy0, 1.0])
        c1 = c1[:2] / c1[2]
        dist = float(np.hypot(*(c1 - c0)))
        self.innov = dist
        if p.slew_cap > 0 and dist > p.slew_cap:
            # 缩小 t 与角度/尺度（简单回退：整体向单位阵插值）
            frac = p.slew_cap / max(dist, 1e-9)
            Ci = (1 - frac) * np.eye(3) + frac * np.linalg.inv(C)
            self.H = _norm_h(self.H @ Ci)
        else:
            self.H = H1

    # ---------------------------------------------------------------- 零偏
    def _update_bias(self):
        p = self.P
        # 视觉校正量小且陀螺读数小 -> 认为静止，更新零偏
        # （调用处保证 meas 非空；innov 已更新）
        # 陀螺读数在 on_gyro 中处理：此处只检查视觉侧条件
        # 简化：innov 小即视觉稳定
        if np.isfinite(self.innov) and self.innov < 2.0:
            self._vision_still = True
        else:
            self._vision_still = False

    def _update_bias_dyn(self, dec):
        """v3 连续零偏：FULL 帧残余校正分解（校正前计算）折算角速度误差缓慢并入零偏。
        环路模型：零偏误差 ε 使预测四边形每帧漂移 d=f·ε·dt（旋转光流），
        校正环以增益 g 消除状态误差 e：e'=(1-g)(e+d)；稳态残余（= 校正
        分解出的满增益量）t = d/g_prev（g_prev 是上一帧校正增益——漂移
        发生前的那次增益），故 ε = t·g_prev/(f·dt)（g 小残余被放大 1/g
        倍——信噪比反而好，这是相对两帧精确式 d≈0.2px 淹没在噪声里的
        关键优势；瞬态 e 的污染在多次运动方向间平均为零，注入测试闭环
        验证收敛正确）。轴向映射由数值实验钉死：+t_y→+ε_x、-t_x→+ε_y、
        -θ→+ε_z。仅相邻两帧均为 FULL（GYRO/非 FULL 校正/采集融合插入
        都会破坏 d/g 关系）。"""
        p = self.P
        if not (p.v3 and p.bias_dyn):
            return
        if not np.isfinite(self.innov_pre) or self.innov_pre > p.bias_dyn_innov_max:
            return
        if dec is None:
            return
        t, theta, s = dec
        now = self.t
        prev = getattr(self, "_bias_dyn_prev", None)
        self._bias_dyn_prev = (t.copy(), theta, self._g_eff_last, now, self._frame_no)
        if prev is None:
            return
        pt, pth, pg, pts, pseq = prev
        if pseq != self._frame_no - 1:      # 只要相邻 FULL 对
            return
        dt = now - pts
        if dt < 0.02 or dt > 0.15:
            return
        if np.abs(self._w_ema).max() > p.bias_dyn_rate_max:
            return
        if np.abs(t).max() > 30.0 or abs(theta) > np.radians(3):
            return
        g = min(max(pg, 0.02), 1.0)
        f = self.K[0, 0]
        eps_cam = np.array([t[1] * g / f / dt, -t[0] * g / f / dt, -theta * g / dt])
        if np.abs(eps_cam).max() > 0.1:
            return
        eps_dev = np.linalg.inv(M_ROT0) @ eps_cam
        if p.rotation == 180:
            eps_dev = eps_dev * np.array([-1.0, -1.0, 1.0])
        self.bias = self.bias + p.bias_dyn_beta * eps_dev
        np.clip(self.bias, -p.bias_dyn_clamp, p.bias_dyn_clamp, out=self.bias)

    # ---------------------------------------------------------------- 采集
    def _acq_candidates(self, g640, thr, low_thr):
        """连通域候选枚举：返回 [(ci, quad640)]（面积降序，前 acq_max_cand 个，
        均通过种子/面积/粗四边形校验）。"""
        import cv2
        p = self.P
        g = g640[::2, ::2]
        dh, dw = g.shape
        npx = dw * dh
        mask = (g >= low_thr).astype(np.uint8)
        nlab, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        if nlab <= 1:
            return []
        hi = np.bincount(labels[g >= thr].ravel(), minlength=nlab)
        area = stats[:, cv2.CC_STAT_AREA]
        cand = [i for i in range(1, nlab)
                if hi[i] >= p.acq_min_seeds and area[i] >= p.acq_min_blob_frac * npx]
        cand.sort(key=lambda i: -area[i])
        out = []
        for ci, i in enumerate(cand[:p.acq_max_cand]):
            ys, xs = np.nonzero(labels == i)
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
                wy, wx = np.nonzero(win == i)
                if len(wx) == 0:
                    return float(cx), float(cy)
                return float(wx.mean() + i0), float(wy.mean() + j0)

            quad = np.array([refine(*pts["tl"]), refine(*pts["tr"]),
                             refine(*pts["br"]), refine(*pts["bl"])]) * 2.0  # ->640
            if not _quad_valid(quad):
                continue
            out.append((ci, quad))
        return out

    def _acquire(self, g640, thr, low_thr, cands=None):
        p = self.P
        if cands is None:
            cands = self._acq_candidates(g640, thr, low_thr)
        for ci, quad in cands:
            lines = []
            ok = True
            cen = quad.mean(axis=0)
            for e in range(4):
                q0, q1 = quad[e], quad[(e + 1) % 4]   # top: TL->TR, right: TR->BR, ...
                fit = _fit_line_band(g640, low_thr, q0, q1, p.band, p, cen=cen)
                if fit is None:
                    ok = False
                    break
                line, sigma, support, _, _ = fit
                lines.append(line)
            if not ok:
                continue
            # 四角 = 相邻边交点
            corners = []
            for k in range(4):
                cr = np.cross(lines[(k - 1) % 4], lines[k])
                if abs(cr[2]) < 1e-9:
                    ok = False
                    break
                corners.append(cr[:2] / cr[2])
            if not ok:
                continue
            corners = np.array(corners)
            if not _geo_valid(corners):
                continue
            # 中空校验：内缩四边形内亮像素占比须低（游戏区为黑）
            if not _hollow_check(g640, corners, low_thr, p.acq_dark_frac):
                continue
            # 由四角直接解 H（DLT）
            H = _h_from_corners(corners)
            if H is None:
                continue
            self.acq_candidate = ci
            return _norm_h(H)
        return None

    # ---------------------------------------------------------------- 部分采集
    def _acquire_partial(self, g640, thr, low_thr, cands=None):
        """屏幕部分入镜时的重建/纠回。
        - GYRO（已有 H）：直接用候选拟合边对现有 H 做相似校正（粗四边形可能是
          被图像边缘裁切的错误形状，绝不用它来初始化有 H 的状态）；
        - DEAD（无 H）：用"拟合边修正的角点"重建——相邻两边均拟合成功的角点 =
          交点（真值）；仅单边拟合的角点 = 粗角点在拟合线上的垂足（裁切只影响
          垂直方向，沿边方向仍可信）；均不可用的角点保留粗值；再满增益相似校正；
        - 末尾一致性校验（预测线与实测线 <4px、<3°），中空校验拒绝灯具/文字屏。
        返回 H 或 None。"""
        p = self.P
        if cands is None:
            cands = self._acq_candidates(g640, thr, low_thr)
        h_save = self.H
        for ci, quad in cands:
            cen = quad.mean(axis=0)
            fits = {}
            for e in range(4):
                q0, q1 = quad[e], quad[(e + 1) % 4]
                fit = _fit_line_band(g640, low_thr, q0, q1, p.band, p, cen=cen)
                if fit is None:
                    continue
                line, sigma, support, pa, pb = fit
                fits[e] = (line, sigma, support, pa, pb)
            if len(fits) < 2:
                continue
            # 要求至少一对相邻边 或 一横一纵两个方向的边（纯平行边对信息不足）
            es = set(fits)
            adjacent = any(e in es and (e + 1) % 4 in es for e in range(4))
            two_axes = (es & {0, 2}) and (es & {1, 3})
            if not (adjacent or two_axes):
                continue
            meas = [(e, *fits[e]) for e in sorted(fits)]
            if not _hollow_check(g640, quad, low_thr, p.acq_dark_frac):
                continue
            if h_save is not None:
                # GYRO：在现有 H 上做相似校正（粗四边形不可信，不用于初始化）
                self.H = h_save.copy()
                self._similarity_correction(meas, 0.7)
                H1 = self.H
                self.H = h_save
            else:
                # DEAD：修正角点重建
                corners = quad.copy()
                for k in range(4):
                    e_prev, e_next = (k - 1) % 4, k
                    if e_prev in fits and e_next in fits:
                        cr = np.cross(fits[e_prev][0], fits[e_next][0])
                        if abs(cr[2]) > 1e-9:
                            corners[k] = cr[:2] / cr[2]
                    elif e_prev in fits or e_next in fits:
                        fe = fits[e_prev if e_prev in fits else e_next][0]
                        corners[k] = corners[k] - (fe[0] * corners[k][0]
                                                   + fe[1] * corners[k][1] + fe[2]) * fe[:2]
                H0 = _h_from_corners(corners)
                if H0 is None:
                    continue
                self.H = _norm_h(H0)
                self._similarity_correction(meas, 1.0)
                H1 = self.H
                self.H = h_save
            if H1 is None:
                continue
            # 一致性校验：校正后预测线与实测线贴合（平均距离 <4px，夹角 <3°）
            ok = True
            for e, line, sigma, support, pa, pb in meas:
                lp = H1.T @ EDGE_LINES[e]
                nrm = np.hypot(lp[0], lp[1])
                if nrm < 1e-12:
                    ok = False
                    break
                lp = lp / nrm
                mid = (pa + pb) / 2
                dist = abs(lp[0] * mid[0] + lp[1] * mid[1] + lp[2]
                           - (line[0] * mid[0] + line[1] * mid[1] + line[2]))
                ang = abs(lp[0] * line[1] - lp[1] * line[0])
                if dist > 4.0 or ang > np.sin(np.radians(3)):
                    ok = False
                    break
            if not ok:
                continue
            self.acq_candidate = ci
            return H1
        return None


# ================================================================ 几何工具

DEBUG_SEQ = -1   # 调试：非负时打印该帧的逐边测量细节


def _sim_matrix(t, theta, s, cx0, cy0):
    """图像空间相似变换 C(p) = s·R(θ)·(p-c) + c + t 的 3x3 矩阵。"""
    ct, st = np.cos(theta), np.sin(theta)
    return np.array([[s * ct, -s * st, cx0 - s * ct * cx0 + s * st * cy0 + t[0]],
                     [s * st, s * ct, cy0 - s * st * cx0 - s * ct * cy0 + t[1]],
                     [0.0, 0.0, 1.0]])


def _norm_h(H):
    """单应规范化为 H[2,2]=1（正号）。||H||=1 规范化会让 h22 ~ 1/340，
    导致准星 = (H·c)/w 的分母 w≈0.003——h8 噪声被放大数百倍，不可用。"""
    if H is None:
        return None
    s = H[2, 2]
    if abs(s) < 1e-12:
        return H
    return H / s


def _clip_segment(p0, p1, inset):
    """线段与图内矩形 [inset, W-inset]x[inset, H-inset] 求交，返回端点或 None。"""
    x0, y0 = inset, inset
    x1, y1 = IMG_W - inset, IMG_H - inset
    d = p1 - p0
    t0, t1 = 0.0, 1.0
    for pp, dd, lo, hi in ((p0[0], d[0], x0, x1), (p0[1], d[1], y0, y1)):
        if abs(dd) < 1e-12:
            if pp < lo or pp > hi:
                return None
            continue
        ta = (lo - pp) / dd
        tb = (hi - pp) / dd
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 >= t1:
            return None
    return p0 + d * t0, p0 + d * t1


def _fit_line_band(g640, low_thr, q0, q1, band, p: TrackerParams, cen=None):
    """沿 q0->q1 线段 ±band 带内定位亮边条纹的**外侧过零边**（亚像素）：
    每个纵向 bin 把像素按 perp 聚合为强度剖面，估计亮/暗电平，从带外侧向
    内扫描亮→暗中点的过零位置（线性插值），要求内侧连续 ≥3px 保持亮
    （排除孤立亮斑）；得到每 bin 一个边点，TLS+2σ 剔除拟合直线。
    相比 95 分位包络：条纹靠近带边时无截断偏差（运动滞后时不产生系统误差）。
    cen = 四边形内侧参考点（定法向朝外）；缺省则法向任意。
    返回 (line, sigma, support, pt0, pt1)：line 为图像齐次线（法向朝外），
    pt0/pt1 = 支撑段首末 bin 中心在拟合线上的位置（约束点）。失败 None。"""
    d = q1 - q0
    L = float(np.hypot(*d))
    if L < 1:
        return None
    d = d / L
    nv = np.array([-d[1], d[0]])
    if cen is not None:
        mid = (q0 + q1) / 2
        if nv[0] * (mid[0] - cen[0]) + nv[1] * (mid[1] - cen[1]) < 0:
            nv = -nv      # 法向朝外（perp 高端 = 条纹外侧）
    x0 = max(int(min(q0[0], q1[0]) - band - 2), 0)
    x1 = min(int(max(q0[0], q1[0]) + band + 2), int(IMG_W))
    y0 = max(int(min(q0[1], q1[1]) - band - 2), 0)
    y1 = min(int(max(q0[1], q1[1]) + band + 2), int(IMG_H))
    sub = g640[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.nonzero(np.ones_like(sub))
    xx = xx + x0
    yy = yy + y0
    val = sub[yy - y0, xx - x0]
    perp = (xx - q0[0]) * nv[0] + (yy - q0[1]) * nv[1]
    lon = (xx - q0[0]) * d[0] + (yy - q0[1]) * d[1]
    sel = (np.abs(perp) <= band) & (lon >= 0) & (lon <= L)
    if sel.sum() < p.min_edge_bins * 2:
        return None
    perp, lon, val = perp[sel], lon[sel], val[sel]
    n_bins = int(L / p.edge_bin_w)
    if n_bins < p.min_edge_bins:
        return None
    bi = np.minimum((lon / p.edge_bin_w).astype(int), n_bins - 1)
    pts = []          # (lon_center, perp_cross)
    pt_bins = []
    for b in range(n_bins):
        m = bi == b
        if m.sum() < 4:
            continue
        bp = perp[m]
        bv = val[m]
        bright = np.median(bv[bv >= low_thr]) if (bv >= low_thr).any() else np.nan
        dark = np.median(bv[bv < low_thr]) if (bv < low_thr).any() else np.nan
        if not np.isfinite(bright) or not np.isfinite(dark) or bright - dark < 30:
            continue
        mid_lvl = (bright + dark) / 2
        # 聚合到整数 perp 栅格（圆心像素最近邻），从带外侧向内找过零
        ip = np.clip(np.round(bp).astype(int), int(-band), int(band))
        rows = np.zeros(2 * int(band) + 1)
        cnt = np.zeros(2 * int(band) + 1)
        idxp = ip - int(-band)
        np.add.at(rows, idxp, bv)
        np.add.at(cnt, idxp, 1)
        rows = np.where(cnt > 0, rows / np.where(cnt > 0, cnt, 1), np.nan)
        # 外侧 = 高 perp（法向朝外由调用处保证？此处 nv 方向任意：
        # 统一从 perp 高端向内扫，调用方负责法向定向——条纹是对称的，
        # 边框条纹特征 = 外侧暗内侧亮；若扫到的是内侧边缘会偏一条纹宽，
        # 由内侧暗度校验兜底拒绝）
        cross = None
        for k in range(len(rows) - 1, 3, -1):
            r0, r1 = rows[k], rows[k - 1]
            if np.isnan(r0) or np.isnan(r1):
                continue
            if r0 < mid_lvl <= r1:
                inward = rows[k - 4:k - 1]
                if np.isnan(inward).any() or (inward >= mid_lvl).sum() < 2:
                    continue
                frac = (mid_lvl - r0) / (r1 - r0 + 1e-9)
                cross = (k - 1 + frac) + int(-band)
                break
        if cross is None:
            continue
        pts.append(((b + 0.5) * p.edge_bin_w, cross))
        pt_bins.append(b)
    support = len(pts) / n_bins
    if len(pts) < p.min_edge_bins or support < p.min_support:
        return None
    arr = np.array(pts)   # (lon, perp_cross)
    # TLS 于 (lon, perp) 平面
    sigma = float("inf")
    keep_bins = np.array(pt_bins)
    for _ in range(p.trim_rounds + 1):
        ctr = arr.mean(axis=0)
        cov = np.cov((arr - ctr).T)
        eigval, eigvec = np.linalg.eigh(cov)
        nv_l = eigvec[:, 0]      # (lon, perp) 平面的法向
        res = (arr - ctr) @ nv_l
        sigma = float(res.std())
        if sigma < 1e-9:
            break
        inl = np.abs(res - res.mean()) <= 2 * sigma
        if inl.all():
            break
        arr = arr[inl]
        keep_bins = keep_bins[inl]
        if len(arr) < p.min_edge_bins:
            return None
    if sigma > p.max_sigma:
        return None
    # (lon,perp) 线 -> 图像线：点 = q0 + d*lon + nv*perp
    # 图像法向 = nv_l[1]*nv（perp 分量）+ nv_l[0]*d（lon 分量）
    normal = nv_l[1] * nv + nv_l[0] * d
    nl = np.hypot(*normal)
    if nl < 1e-12:
        return None
    normal = normal / nl
    if normal @ nv < 0:            # 法向统一朝外（perp 高端）
        normal = -normal
    ctr_img = q0 + d * ctr[0] + nv * ctr[1]
    line = np.array([normal[0], normal[1], -normal @ ctr_img])
    # 支撑段端点（首末 bin 中心投影到线上）
    lon0 = (keep_bins[0] + 0.5) * p.edge_bin_w
    lon1 = (keep_bins[-1] + 0.5) * p.edge_bin_w
    pa = q0 + d * lon0
    pb = q0 + d * lon1
    pa = pa - (line[0] * pa[0] + line[1] * pa[1] + line[2]) * line[:2]
    pb = pb - (line[0] * pb[0] + line[1] * pb[1] + line[2]) * line[:2]
    return line, sigma, support, pa, pb


def _quad_valid(quad640):
    pts = quad640
    area = 0.0
    for i in range(4):
        j = (i + 1) % 4
        area += pts[i, 0] * pts[j, 1] - pts[j, 0] * pts[i, 1]
    if abs(area) / 2 < 0.02 * IMG_W * IMG_H:
        return False
    for i in range(4):
        j = (i + 1) % 4
        if np.hypot(*(pts[j] - pts[i])) < 40:
            return False
    return True


def _geo_valid(corners640):
    tl, tr, br, bl = corners640

    def ang(p, q):
        return np.arctan2(q[1] - p[1], q[0] - p[0])

    def ang_diff(a, b):
        dd = (a - b) % np.pi
        return dd - np.pi if dd > np.pi / 2 else (dd + np.pi if dd < -np.pi / 2 else dd)

    lim = np.deg2rad(15)
    if abs(ang_diff(ang(tl, tr), ang(bl, br))) > lim:
        return False
    if abs(ang_diff(ang(tl, bl), ang(tr, br))) > lim:
        return False
    w = (np.hypot(*(tr - tl)) + np.hypot(*(br - bl))) / 2
    h = (np.hypot(*(bl - tl)) + np.hypot(*(br - tr))) / 2
    if w <= 0 or h <= 0:
        return False
    asp = max(w, h) / min(w, h)
    return 1.1 <= asp <= 3.0


def _hollow_check(g640, corners640, low_thr, max_frac):
    """内缩（线性 0.82）四边形内 >= low_thr 像素占比须 <= max_frac（边框环中空）。"""
    import cv2
    cen = corners640.mean(axis=0)
    inner = cen + (corners640 - cen) * 0.82
    mask = np.zeros(g640.shape, np.uint8)
    cv2.fillConvexPoly(mask, inner.astype(np.int32), 1)
    n = int(mask.sum())
    if n < 100:
        return False
    bright = int(((g640 >= low_thr) & (mask > 0)).sum())
    return bright / n <= max_frac


def _h_from_corners(corners640):
    """DLT 解 img->norm 单应。"""
    A = []
    for (x, y), (X, Y) in zip(corners640, SCREEN_CORNERS):
        A.append([x, y, 1, 0, 0, 0, -X * x, -X * y, -X])
        A.append([0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y])
    A = np.array(A)
    try:
        _, _, vt = np.linalg.svd(A)
    except np.linalg.LinAlgError:
        return None
    H = vt[-1].reshape(3, 3)
    if abs(H[2, 2]) < 1e-12:
        return None
    return H / H[2, 2]


# ================================================================ 自测
if __name__ == "__main__":
    """合成场景冒烟：亮环 + 干扰块采集；陀螺匀速 wx 传播方向；空帧 4s -> DEAD。"""
    W, Hh = 640, 360
    g = np.full((Hh, W), 10, np.uint8)
    g[75:286, 100:103] = 255
    g[75:286, 537:541] = 255
    g[75:79, 100:541] = 255
    g[282:286, 100:541] = 255
    g[300:335, 10:55] = 250      # 干扰亮块
    tr = Tracker(TrackerParams())
    tr.process(g, 1_000_000_000)
    assert tr.grade == GRADE_FULL, f"ring acquire: grade={tr.grade}"
    assert abs(tr.cross[0] - 960) < 30 and abs(tr.cross[1] - 540) < 30, f"cross {tr.cross}"
    # 陀螺传播：wy=-0.1 rad/s 1s（200Hz tick），跨 30 个空帧
    t = 1_000_000_000
    for k in range(200):
        t += 5_000_000
        tr.on_gyro(t, 0.0, -0.1, 0.0)
    blank = np.full((Hh, W), 10, np.uint8)
    for k in range(30):
        tr.process(blank, 1_000_000_000 + 5_000_000 * (k + 1))
    assert tr.grade == GRADE_GYRO, f"grade after blanks={tr.grade}"
    dy = tr.cross[1] - 540
    assert dy < -20, f"propagation dy={dy}"
    # 4s 空帧 -> DEAD -> 重新采集
    t2 = 2_000_000_000
    for k in range(120):
        t2 += 33_333_333
        tr.process(blank, t2)
    assert tr.grade == GRADE_DEAD, f"grade after 4s blanks={tr.grade}"
    tr.process(g, t2 + 33_333_333)
    assert tr.grade == GRADE_FULL, "re-acquire after DEAD"
    print(f"guntrack selftest PASS (cross=({tr.cross[0]:.1f},{tr.cross[1]:.1f}), bias={tr.bias.round(4)})")
