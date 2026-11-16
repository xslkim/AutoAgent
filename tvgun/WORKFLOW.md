# TVGun 开发与实测流程

> 装到手机上的包必须和当前源码是同一次构建。构建失败不会卸掉手机里已有的 App。
> 每次实测按下面的顺序做。功能与协议见 [HANDOVER.md](HANDOVER.md)。

## 1. 版本识别机制（已内建，先知道怎么查）

APK 构建时 `build.sh` 会把 `git describe --always --dirty --tags` 嵌入 App
（生成 `out/gen/.../Version.java`，不入库）。运行中有**三个地方**能看到当前版本：

| 位置 | 查法 | 期望输出 |
|---|---|---|
| **HUD 左下角** | 打开 App 直接看屏幕（灰色小字） | 如 `3407e3e` 或 `3407e3e-dirty` |
| **logcat** | `adb shell "logcat -d -s tvgun:I"` 找 `tvgun version` | `tvgun version 3407e3e` |
| **录制 meta.txt** | 录制目录的 `meta.txt` 里 `appVersion=` 行 | `appVersion=3407e3e` |

**规则：任何测试开始前，先看 HUD 左下角的版本号，确认等于预期 commit。**
**规则：任何录制数据回传时，meta.txt 的 appVersion 必须与预期一致，否则数据作废重录。**

没有 `appVersion=` 的录制，用 `detect.csv` 的 `failStage` 判别：现行追踪器只写 0..4
（0=DEAD 1=GYRO 2=EDGE 3=PARTIAL 4=FULL），且 fusedX/Y 与 detCrossX/Y 恒等、blobFrac 恒为 0。
出现 6/7 的是更早的检测管线，不要当现行追踪器的数据。

## 2. 标准实测流程（每次实测按顺序走）

1. **同步代码**：`git pull`，确认 `git log --oneline -1` 是要测的 commit。
2. **安装 APK**：`cd android && bash build.sh install`（机器无关，自动探测 JDK/SDK；
   失败时用 `JAVAC=/JAVA11=/ANDROID_SDK=` 环境变量指定）。APK 是本地构建产物，不入库。
3. **核对版本**：打开 App，看 HUD 左下角版本号 == 预期 commit。
   **构建失败不会让手机上的旧 App 消失**——装完必须看版本号，不看等于没装。
4. **冒烟录制**：音量下键录 5~10 秒，拉回看 `meta.txt` 的 `appVersion=` 与
   `detect.csv` schema（failStage 只有 0..4）。通过才开始正式测试。
5. **回传数据**：整个录制目录 push 到 `test_res/`（frames.bin 走 LFS），
   附一句 HUD 版本截图或 logcat `tvgun version` 行。

## 3. 构建环境约定

- `android/build.sh` 自动探测：javac（任意 JDK）→ Java 11+（d8/apksigner 需要）→
  Android SDK（最新 platform 与 build-tools）。探测顺序：Android Studio JBR →
  已知安装路径 → PATH。
- 探测失败时的环境变量覆盖：`JAVAC=<javac路径>`、`JAVA11=<java11+路径>`、
  `ANDROID_SDK=<sdk根目录>`。
- 各机器已验证配置：
  - 开发机（D:\tvgun）：JDK8 javac + JRE17（D:\Tools）+ android-35/build-tools 36.0.0；
  - 实测机：Android Studio JBR + 本机 SDK。

## 4. APK 不入库

- `android/tvgun.apk` 由 `build.sh` 生成本地文件，`.gitignore` 忽略 `*.apk`。安装一律重新构建。
- `android/tvgun.apk.idsig`、`android/out/`、`android/debug.keystore` 同样不入库。

## 5. 数据可信度检查清单（分析数据前先做）

1. `meta.txt` 有 `appVersion=` 且与目标 commit 一致；
2. `detect.csv` 的 `failStage` 只有 0..4（不是 6/7）；
3. `frames.bin` 尺寸 = 帧数 × 230400；
4. 时钟统一：`gyro.csv` 与 `frames_idx.csv` 的 tsNs 在同一 CLOCK_MONOTONIC 上
   （`meta.txt` 的 clock 行有说明；camera2 的 `camera2TsOffsetNs` 应 < 0.5s）。

不满足任何一条：数据作废，按 §2 重录。

## 6. 常见坑

- **构建成功 ≠ 安装成功**：`build.sh` 不带 `install` 参数只编译不安装。
- **install 成功 ≠ 版本正确**：装完不看 HUD 版本号 = 没装。
- **git pull 成功 ≠ LFS 成功**：网络不通时 frames.bin 只会是 3 行指针文件，
  `git lfs pull` 或换网络后再拉；分析前先看文件大小对不对（§5.3）。
- **服务器地址**：手机与 PC 连同一 WiFi 即自动连接。发现走 UDP 广播，PC 在 `:8001` 应答。
  找不到 TV 时用保存的地址兜底，长按屏幕可手改。PC 防火墙放行 **TCP 8000、UDP 8000、UDP 8001**。
- **UDP 事件模式（Godot 单端口游戏）**：长按屏幕把"事件模式"设为 `udp`、
  "UDP 模式目标端口"默认 9000——坐标流与事件（SHOT/RELOAD/COIN/START/EXIT
  文本包）同发该端口，PC 防火墙改放行 **UDP 9000**（发现仍走 UDP 8001 不变）。
- **预测提前量（手感旋钮）**：长按屏幕对话框第二项，默认 90ms。准星明显拖尾
  （快速甩动时跟不上）→ 调大（电视延迟高，100-130）；准星回甩/ overshoot →
  调小（电竞显示器，50-70）。调完立即生效，无需重启。
- **60fps 相机**：camera2 优先锁 60fps。处理跟不上时丢到最新帧，大约退回 30fps。
  `meta.txt` 的 `fpsRange=` 是实际档位。
- **Windows 行尾**：本仓库 .gitattributes 未统一行尾，跨机器 diff 出 CRLF 差异属正常。
