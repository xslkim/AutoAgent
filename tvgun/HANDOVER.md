# TVGun 手机光枪

把手机固定在玩具光枪上打鸭子。PC 全屏显示游戏（相当于电视），手机后置摄像头看着显示器，App 实时解算枪口指向屏幕的哪个像素。点手机屏幕 = 扳机。

定位是 Sinden 式亮边框：游戏画面四周 24px 白边，陀螺传播单应，视觉逐边校正。纯软件，不改显示器硬件。现行客户端是 Android App。

实测与构建流程见 [WORKFLOW.md](WORKFLOW.md)。

## 系统组成

```
PC（Windows）
  scripts/run_tv.py           全屏游戏：黑底 + 24px 白边 + 弹跳鸭子 + 分数
                              HTTP 0.0.0.0:8000，UDP 准星同端口，发现在 port+1
  scripts/guntrack.py         追踪器 Python 参考实现（与 Tracker.java 逐语句对应）
  scripts/run_track_replay.py 录制回放：可用率 / 抖动 / 再锁定
  scripts/diag_smooth.py      手感：感知延迟、静止与运动抖动
  scripts/diag_td.py          相机↔陀螺时间偏移的在线标定检查
  scripts/diag_ts_offset.py   离线扫描时间偏移
  scripts/calib_prop.py       陀螺→相机轴向映射 M
  test_res/                   同步录制（帧 + 陀螺 + 检测）

手机（小米 9，Android 10）
  android/                    纯 Java，无 Gradle。build.sh 构建并安装
    src/com/tvgun/gun/
      Tracker.java            追踪器（guntrack.py 的 Java 移植）
      MainActivity.java       相机、追踪、120Hz UDP 准星、录制、镜头、设置、虚拟按键
      ControlButtons.java     HTTP 事件：POST /coin /start /reload /exit
      UdpEvents.java          UDP 事件：SHOT / RELOAD / COIN / START / EXIT
      Camera2Backend.java     camera2 枚举、会话、帧回调（优先 60fps）
      OverlayView.java        准星、HUD、等级、录制指示
      Recorder.java           视频 + IMU + 检测同步录制（音量下键）
    test/                     TrackerTest、ReplayTest、ControlButtonsTest、UdpEventsTest
```

打鸭子验证端是 `run_tv.py`。投币 / 开始 / 换弹 / 退出不由它处理：HTTP 模式发给外部街机桥接器，UDP 模式发给游戏自己的端口。

## 追踪

`Tracker.java` 与 `scripts/guntrack.py` 语义一致。状态是单应 **H**（640×360 图像坐标 → 1920×1080 规范坐标）。准星 = H · 图像中心。

规范坐标四角 = 白边框外缘 `(0,0) / (1920,0) / (1920,1080) / (0,1080)`。

### 传播

陀螺 tick 只入队。处理一帧时，把 H 从基准积分到该帧曝光中点，再做视觉。输出准星时再积分到当前时刻。相机时间戳 = `image.getTimestamp() + 曝光时间/2`（未知曝光时回退 16.5ms）。

每个陀螺间隔：

`H ← H · (K · (I + [M·(ω−bias)·dt]×) · K⁻¹)⁻¹`

纯旋转，与观看距离无关。`rot = 0` 时

`M = [[0, 1, 0], [1, 0, 0], [0, 0, -1]]`

（`cam_x = +wy`，`cam_y = +wx`，`cam_z = -wz`）。`rot = 180` 时先把 ωx、ωy 取反。`scripts/calib_prop.py` 可复算 M。

### 逐边校正

每条预测可见的屏幕边，投影到图像里，按可见段裁剪，在预测线两侧的带内逐 bin 找亮条纹外侧过零（亚像素）。带的基准宽度 12px，该边持续没有可信测量时以 12px/s 加宽，上限 24px。直线用 TLS，并做 2σ 剔除。

一条边要同时通过支撑率、残差、创新量、与预测线的夹角、内侧暗度，才采纳。用来拒绝文字屏和灯具。

- **4 边（FULL）**：邻边交点 → DLT → 按增益向测量单应收敛。尺度校正只在 4 边时启用。
- **1–3 边（PARTIAL / EDGE）**：图像空间相似校正。平移用截断特征值的 2×2 最小二乘，旋转用夹角加权，不做尺度。
- **0 边**：进入 GYRO，只靠陀螺，最长 3 秒，超时为 DEAD。

增益随校正前创新量变化：小于 1px 时用基础增益的 0.35 倍，大于 12px 时用满增益。基础增益 FULL 0.6、PARTIAL 0.5、EDGE 0.35。

### 采集

失锁、GYRO 超过 0.3 秒、或可见边长期少于 3 条时，重新采集。最多试 5 个亮连通域，每个做四边拟合、几何校验、中空校验（内缩后的四边形里亮像素不超过 30%）。四边都过才重建 H。

屏幕只进入一部分时走部分采集：用能拟合上的边重建，相邻双边的角点用交点，单边角点投到拟合线上，再做一致性校验。已有 H 时，不用被裁切的粗四边形去初始化。

### 零偏

两路同时学习，都在设备轴上：

- 静止：校正量很小且 `|ω| < 0.06 rad/s` 时做 EMA。
- 游玩中：相邻 FULL 帧上，把校正前残余折成角速度误差，以 β = 0.03 缓慢并入，绝对值钳在 0.08 rad/s。

### 等级

| 等级 | 含义 |
|---|---|
| FULL | 4 边 |
| PARTIAL | 2–3 边 |
| EDGE | 1 边。只约束法向，另一方向靠陀螺 |
| GYRO | 0 边，且视觉丢失不超过 3 秒 |
| DEAD | 超过 3 秒，或尚未锁定 |

HUD 显示这五档。准星内部以陀螺速率更新。

### 相机与陀螺的时间偏移

每次开机、每次换镜头，相机时间戳和陀螺时间戳的有效偏差都会变，范围大约 ±100ms。追踪器在线估计这个偏差 δ：

- 观测是边测量帧对的实测边线，对照陀螺积分旋转预测的边线，看法向残差。每个候选 δ 同时拟合一个尺度，吸收焦距和视差。
- 搜索 ±100ms、步长 4ms。残差曲线跨多次扫描做 EMA。只用位移足够大的约束。
- 预热、与当前估计不一致的扫描降权、首次应用要连续一致、切换有滞回、亚网格细化。应用到传播时刻时限速约 0.5ms/帧。

不需要用户做标定动作。`scripts/diag_td.py`、`scripts/diag_ts_offset.py` 用来核对。

### 显示与射击用的预测

屏幕上的准星和开枪用的都是 `snapshotAhead(now, predictMs)`，默认提前 **90ms**（上限 250ms）。长按屏幕可改。内部 H 和逐帧 `process` 的输出不经过这一级。

预测含四件事：角速度短时 EMA（τ = 30ms）、阻尼外推（时间常数 80ms，角度上限 0.5rad）、减速时按峰值角速度缩小外推、以及 one-euro 输出滤波（最低截止 1.5Hz，速度系数 0.02）。静止和慢瞄滤得重，快速运动接近直通。

准星以 **120Hz** UDP 上报。0.6 秒没有新坐标，电视端准星消失。

## 通信

坐标系一律是 1920×1080 规范坐标。手机和 PC 在同一 WiFi。PC 防火墙放行 **TCP 8000、UDP 8000、UDP 8001**。UDP 事件模式改打游戏端口时，再放行那个端口（默认 UDP 9000）；发现仍用 UDP 8001。

找不到电视时，回退到手机里保存的地址，出厂兜底是 `192.168.3.19:8000`。连上同一 WiFi 后手机会广播发现，PC 应答后自动改连。长按屏幕仍可手改地址。

### 发现

手机向 UDP `:8001`（游戏端口 + 1）广播 `TVGUN_DISCOVER`。PC 回复 `TVGUN_HERE <游戏端口>`。手机用应答的源地址作为服务器。

### HTTP 模式（默认，`eventMode = http`）

电视端 `run_tv.py`：

| 端点 | 行为 |
|---|---|
| UDP `:8000` 文本 `x,y` | 120Hz 准星。无连接，只保留最新 |
| `POST /shot` `{"x","y"}` | 开枪，返回 `{"hit":bool,"score":int}` |
| `POST /aim` `{"x","y"}` | 兼容的准星上报，返回 `{"ok":true}` |
| `GET /state` | `{"score","target":{"x","y","r"}}` |

虚拟按键发给 `http://<server>` 上的桥接器，正文 `{}`，成功体为 `{"ok":true}`：

| 端点 | 按键 |
|---|---|
| `POST /coin` | 投币 |
| `POST /start` | 开始 |
| `POST /reload` | 换弹 |
| `POST /exit` | 退出 |

### UDP 事件模式（`eventMode = udp`）

对接单 UDP 端口的游戏（Godot）。坐标流 `x,y` 和事件包发到同一端口，默认 **9000**。主机仍是发现或手填的地址。事件是 ASCII 文本，无应答：`SHOT`、`RELOAD`、`COIN`、`START`、`EXIT`。命中由游戏按最新坐标自行判定。

## 手机操作

| 操作 | 作用 |
|---|---|
| 点画面 | 开枪。坐标与当时显示的预测准星相同 |
| 长按画面 | 设置：`host:port`、预测提前量 ms、事件模式 `http`/`udp`、UDP 端口 |
| 左下「投币」「开始」 | 虚拟按键 |
| 右下「换弹」「退出」 | 虚拟按键。退出需 1.5 秒内按两次 |
| 音量上 | 切换后置镜头 |
| 音量下 | 开始 / 停止录制 |

预测提前量：电视、游戏模式大约 90–130ms；电竞显示器大约 50–70ms。准星甩动时拖在后面就调大，停住后冲过头就调小。范围 0–250，立即生效。

HUD 左下角是构建版本（`git describe --always --dirty --tags`）。等级、录制秒数、服务器地址也在 HUD 上。

相机走 camera2，优先锁定 60fps；处理跟不上时丢到最新帧，大约退回 30fps。没有 camera2 时用旧 Camera API。后置镜头含 MIUI 隐藏的 vendor id，候选是小米 9 上探到的 `20/21/60–63/100/120`，换手机要重探。

## 已知限制

- **没有两点校准。** 枪管和光轴的安装差、边框外缘大约 13px、广角大约再多 7px，都会变成固定瞄点偏差。流畅性不受影响。
- **陀螺尺度和轴对准没有在线 3×3 标定。** 长时间只靠陀螺时，误差主要随转过的角度积累。完全离开画面超过大约 1 秒，回到画面后靠采集和逐边校正收敛。
- **EDGE 只钉住边的法向。** 另一个方向继续靠陀螺，直到再次看到至少两条边。
- **主摄水平视场大约 68°。** 常用距离下屏幕经常只有一部分入画，部分采集可以锁；大范围动作用大约 92° 的超广角。超广角下边框仍接近直线，不做畸变校正。
- **暗光下 camera2 帧率可能降到大约 28fps。** `fpsRange` 在 legacy 设备上是软约束。
- **超广角预览在亮画面下还没有单独目验过。**

## 录制数据（`test_res/`）

每个目录：

| 文件 | 内容 |
|---|---|
| `meta.txt` | 相机、时钟、`appVersion=`、`fpsRange=`、`predictMs=` |
| `frames.bin` | 640×360 uint8 灰度，按帧拼接。字节数 = 帧数 × 230400。Git LFS |
| `frames_idx.csv` | `seq,tsNs` |
| `gyro.csv` | `tsNs,wx,wy,wz`，与帧同一 `CLOCK_MONOTONIC` |
| `detect.csv` | 逐帧检测与融合。`failStage` 存等级 0–4 |

分析前先做 [WORKFLOW.md](WORKFLOW.md) 里的可信度检查。`record_wide_20260925_214838/` 来自更早的检测管线，不要用来评现行追踪器。

其余目录都是现行录制格式，覆盖主摄约 68° 和超广角约 92°，含静止、瞄角、出画和快甩：

`record_20260921_230150`、`record_wide_20260921_235354`、`record_20260925_235405`、`record_wide_20260925_235333`、`record_20260926_114948`、`record_20261002_004842`、`record_20261002_094620`、`record_20261002_220120`、`record_20261002_220523`，以及 `record_20260929_223451`、`record_20260929_223525`、`record_20260929_223638`。

回放时 Java 与 Python 的等级在个别重运动、长时间 GYRO 的录制上会因反馈链分叉而不逐帧相同；可用率和抖动仍对齐。`record_20260925_235405` 是这种情况。

## 新电脑

1. 克隆仓库，并用 git-lfs 拉下 `frames.bin`。
2. Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)：

```bash
uv venv .venv && uv pip install -r requirements.txt
uv pip uninstall opencv-python-headless && uv pip install opencv-python
```

电视窗口需要带 GUI 的 `opencv-python`。

3. 安装 App：`cd android && bash build.sh install`。编出来的 `android/tvgun.apk` 不入库。`build.sh` 自动找 JDK、Java 11+（d8 / apksigner）和 Android SDK。找不到时：

```bash
JAVAC=<javac> JAVA11=<java11+> ANDROID_SDK=<sdk> bash build.sh install
```

4. 手机打开 USB 调试，`adb devices` 显示 `device`。小米 9，Android 10。
5. 手机与 PC 同一局域网，防火墙放行上面的端口。
6. 启动电视端：`.venv/Scripts/python.exe scripts/run_tv.py --port 8000 --seed 42`。手机对着画面应出现 FULL 或 PARTIAL，电视上出现青色准星。

## 命令

```bash
# 电视端。--selftest 做接口自检
.venv/Scripts/python.exe scripts/run_tv.py --port 8000 --seed 42

# 构建并安装
cd android && bash build.sh install

adb shell am start -n com.tvgun.gun/.MainActivity
adb shell input keyevent KEYCODE_VOLUME_UP      # 切镜头
adb shell input keyevent KEYCODE_VOLUME_DOWN    # 录制开关
adb shell "logcat -d -s tvgun:I"

# 把录制拉回仓库（Git Bash 下避免路径被转换）
MSYS_NO_PATHCONV=1 adb pull /storage/emulated/0/Android/data/com.tvgun.gun/files/record/<目录> D:\tvgun\test_res\xxx

# 回放与手感
.venv/Scripts/python.exe scripts/run_track_replay.py --rec test_res/record_20260921_230150
.venv/Scripts/python.exe scripts/diag_smooth.py --rec test_res/record_20260921_230150
.venv/Scripts/python.exe scripts/diag_td.py
.venv/Scripts/python.exe scripts/calib_prop.py --rec test_res/record_20260921_230150

# 桌面 JVM 测试（javac 任意 JDK 8+）
javac -encoding UTF-8 -d /tmp/jcls android/src/com/tvgun/gun/Tracker.java android/src/com/tvgun/gun/ControlButtons.java android/src/com/tvgun/gun/UdpEvents.java android/test/*.java
java -cp /tmp/jcls TrackerTest
java -cp /tmp/jcls ControlButtonsTest
java -cp /tmp/jcls UdpEventsTest
java -cp /tmp/jcls ReplayTest
```
