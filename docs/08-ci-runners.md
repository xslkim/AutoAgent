# 08 - CI Runner 规格

> 三引擎在 GitHub Actions 上的运行环境定义。
> **关键事实：视觉回归 / e2e 测试不能跑在普通 ubuntu-latest runner 上**——UI 渲染需要 GPU 或 Xvfb；字体、color space、分辨率必须显式控制；UE 需要 self-hosted。

## 一、Runner 矩阵

| 引擎 | Build | Unit Test | E2E + Screenshot | 触发频率 |
|---|---|---|---|---|
| Unity 2023 | `windows-latest`（DX11 WARP） | `windows-latest` | `windows-latest`（保留显示） | 每 PR |
| Godot 4.6 | `ubuntu-latest`（Xvfb） | `ubuntu-latest`（Xvfb） | `ubuntu-latest`（Xvfb + 软渲） | 每 PR |
| UE 5.7 | **`self-hosted-windows-gpu`** | **`self-hosted-windows-gpu`** | **`self-hosted-windows-gpu`** | **Nightly only** |
| MCP server (Python) | `ubuntu-latest` | `ubuntu-latest` | (与引擎 e2e 一起跑) | 每 PR |

`self-hosted-windows-gpu` = 用户提供的 Windows 11 + RTX 30/40 系 / 32GB RAM / 200GB+ SSD runner。**Phase 0 必须先确认这台机器到位**，否则 UE 不能上 CI（也就不能进 Phase 2）。

## 二、Unity Runner 规格

### 2.1 Windows runner（推荐 + 默认）
- OS：Windows Server 2022 / Windows 11
- Image：`windows-latest`（GitHub-hosted）
- Unity install：`game-ci/unity-builder@v4` action（自动安装 Unity 2023.2.20f1）
- License：Personal license activated via `UNITY_LICENSE` GitHub secret（GameCI 标准流程）
- GPU：软件渲染 DX11 WARP 足够 UGUI 截图
- 字体：Windows 自带 + 测试 fixture 自带（commit 到 `fixtures/unity-test-project/Assets/Fonts/`）
- 分辨率：1920x1080（强制 `-screen-width 1920 -screen-height 1080`）
- Color space：Linear（在 `ProjectSettings/GraphicsSettings.asset` 锁定，不允许 PR 改）

### 2.2 启动命令
```powershell
# ❌ 错误（截图会黑屏）
Unity.exe -batchmode -nographics

# ✅ 正确
Unity.exe -batchmode `
          -screen-width 1920 -screen-height 1080 -screen-fullscreen 0 `
          -projectPath fixtures/unity-test-project `
          -executeMethod AutoAgent.Test.E2ERunner.Run `
          -logFile -
```

**关键**：`-nographics` 禁用渲染会让截图返回空帧。必须保留显示（虚拟也行，但不能 nographics）。

### 2.3 性能预算
- 启动 Unity batchmode：~30s
- 单 e2e 任务（启动 + 4 动作 + 4 截图）：~90s
- 单次 PR Unity job：~5 min（含编译）

### 2.4 Linux 备选（不推荐 MVP）
Linux + Xvfb + Vulkan 软渲在 UGUI 字体渲染上不稳定（默认 fallback 到 sans-serif，与 Windows 像素不一致）。如必须用：
- `xvfb-run -a -s "-screen 0 1920x1080x24"`
- 安装字体：`apt install fonts-noto fonts-liberation fonts-dejavu`
- baseline 必须独立子目录 `baselines/unity/linux/`

## 三、Godot Runner 规格

### 3.1 Linux runner（推荐 + 默认）
- OS：Ubuntu 22.04
- Image：`ubuntu-latest`
- Godot install：从 GitHub Release 下载 `Godot_v4.6-stable_linux.x86_64`
- 字体：`apt install fonts-noto fonts-noto-cjk`
- Xvfb：必需

### 3.2 启动命令
```bash
xvfb-run -a -s "-screen 0 1920x1080x24" \
  godot --headless=false --path fixtures/godot-test-project \
        --script res://test/e2e_runner.gd
```

**注意**：`--headless` 在 Godot 4.x 不渲染屏幕，截图返回空。必须 `--headless=false`（默认）+ Xvfb 提供虚拟显示。

### 3.3 性能预算
- 启动 Godot：~5s
- 单 e2e 任务：~30s
- 单次 PR Godot job：~2 min

## 四、Unreal Runner 规格

### 4.1 Self-hosted Windows GPU runner（必需）

**为什么不能用 GitHub-hosted**：
- UE 5.7 编译需 ~30GB SSD + 16GB RAM 峰值
- Vulkan / DX12 截图需要真实 GPU（软渲性能太差）
- 编译时间在 GitHub-hosted ubuntu-latest 上 1+ 小时，超出免费额度
- UE Marketplace license 流程繁琐

**Self-hosted runner 规格**：
- OS：Windows 11
- Visual Studio 2022（含 "C++ Desktop Development" + "Game Development with C++"）
- UE 5.7（Epic Games Launcher 安装 或 source build）
- GPU：NVIDIA RTX 3060+ 推荐
- RAM：32GB
- SSD：200GB+（含 UE source + DerivedDataCache + 项目）
- GitHub Actions self-hosted runner agent 安装
- 标签：`self-hosted, Windows, UE-5.7, GPU`

### 4.2 启动命令
```cmd
"%UE_INSTALL%\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" ^
  fixtures/unreal-test-project/AutoAgentTest.uproject ^
  -ExecCmds="Automation RunTests AutoAgent.E2E; Quit" ^
  -unattended -ResX=1920 -ResY=1080 ^
  -log -ABSLOG="%CD%\ue-log.txt"
```

**注意**：**不要**加 `-nullrhi`。null RHI 模式下 Slate widget 不渲染、不可截图。

### 4.3 性能预算
- 编译（incremental）：~5 min
- 编译（clean）：~30 min
- 单 e2e 任务：~3 min
- 单次 nightly UE job：~15 min（incremental）/ ~45 min（clean）

### 4.4 触发频率
- 每 PR 跑：仅 lint + C++ static check（5 min，不编译）
- Nightly 全跑：每天 UTC 02:00（含 build + e2e + screenshot diff）
- Nightly fail → 自动开 GitHub Issue，标 `nightly-fail`，不影响 PR merge

## 五、字体规范

### 5.1 三引擎统一约定
所有 fixture project 内置以下字体（避免依赖系统字体）：
- `NotoSansCJK-Regular.otf`（中日韩通用，覆盖中文需求）
- `Roboto-Regular.ttf`（拉丁字母 UI 默认）
- `RobotoMono-Regular.ttf`（等宽，调试用）

字体放在：
- Unity：`fixtures/unity-test-project/Assets/Fonts/`
- UE：`fixtures/unreal-test-project/Content/UI/Fonts/`
- Godot：`fixtures/godot-test-project/assets/fonts/`

### 5.2 缺失字体处理
任何 baseline 截图发现"豆腐方块"（U+25A1 / U+FFFD 字符渲染） → CI fail，提示用户补字体。这是 hard rule。

## 六、Color Space & 分辨率（必锁定）

### 6.1 锁定项

| 项 | 锁定值 | 锁定方式 |
|---|---|---|
| 分辨率 | 1920x1080 | runner 启动参数强制 |
| Color Space | Linear | Unity / UE ProjectSettings 锁定，路径白名单禁修改 |
| DPI scale | 1.0 | runner 启动参数 `--no-dpi-aware`（Windows） |
| VSync | off | runner 启动参数 |
| Frame rate cap | 60 | runner 启动参数 |
| Texture filtering | bilinear | 引擎 ProjectSettings |

### 6.2 跨平台 baseline 隔离
即使锁定上述项，不同 GPU 驱动 / OS 仍可能导致 1-2 像素差异。Baseline 按 `{engine}/{os}/` 子目录分：

```
baselines/
├─ unity/windows/login_screen.png
├─ unity/linux/login_screen.png      # 如果 Phase 4 加 Linux runner
├─ unreal/windows/login_screen.png
└─ godot/linux/login_screen.png
```

CI 选择 baseline 时按 runner OS 自动匹配。

## 七、Cache 策略

| Cache 项 | 路径 | 生效条件 | 大小 |
|---|---|---|---|
| Unity Library | `fixtures/unity-test-project/Library` | 每次 PR | ~2GB |
| UE DerivedDataCache | `<ue>/Engine/DerivedDataCache` | nightly | ~10GB |
| Godot import cache | `fixtures/godot-test-project/.godot` | 每次 PR | ~200MB |
| Python deps (mcp-server) | `~/.cache/uv` | 每次 PR | ~500MB |
| C++ build artifacts (UE) | `Intermediate/Build` | nightly | ~5GB |

GitHub Actions cache key 用 `${{ runner.os }}-${{ hashFiles('lockfile') }}`。

## 八、Workflow 文件清单

```
.github/workflows/
├─ unity-pr.yml                # 每 PR 触发，windows-latest，5 min
├─ godot-pr.yml                # 每 PR 触发，ubuntu-latest，2 min
├─ unreal-nightly.yml          # 02:00 UTC 触发，self-hosted，15-45 min
├─ unreal-pr-lint.yml          # 每 PR 触发，self-hosted，5 min（仅 C++ lint）
├─ mcp-pr.yml                  # 每 PR 触发，ubuntu-latest，1 min
├─ source-audit.yml            # 每 PR 触发（全引擎），防护 0.1+0.2，30s
├─ visual-baseline.yml         # 仅 baseline path PR 触发，含人工 review gate
└─ dispatch-from-agent.yml     # workflow_dispatch，给 background agent 用
```

## 九、CI 步骤模板（每个 workflow 共用）

```yaml
jobs:
  validate:
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # 需要 origin/main 比对

      - name: Step 1 — 路径白名单（防护 0.1）
        run: python scripts/ci/check_changed_paths.py

      - name: Step 2 — 源码 diff 审计（防护 0.2）
        run: python scripts/ci/audit_visual_writes.py

      - name: Step 3 — 编译 + 单元测试
        run: <engine-specific>

      - name: Step 4 — E2E（含 dump before/after diff，防护 0.3）
        run: <engine-specific>

      - name: Step 5 — 视觉回归（防护 3）
        run: python scripts/ci/visual_regression.py
```

每个引擎 workflow 都跑相同 5 步骤。失败行为见 [07-agent-operations.md §2.4](07-agent-operations.md)。

## 十、失败处理

| Job 失败 | 行为 |
|---|---|
| Unity PR fail | PR 标 fail，AI agent 看 log 修，重试 ≤5 次 |
| Godot PR fail | 同上 |
| MCP PR fail | 同上 |
| Source audit fail | PR 立即关闭，AI 标 `needs-human-review`，不重试 |
| Path violation | PR 立即关闭，**不重试**，连续 3 次 → 全局停 |
| UE nightly fail | 自动开 GitHub Issue，标 `nightly-fail`，不影响 PR merge |
| Self-hosted runner offline | UE PR lint 不能跑 → 标 pending → 等 runner 恢复 |
| GitHub Actions quota exhausted | 全局停，通知 |

## 十一、Phase 0 必须验证（go/no-go gate）

Phase 0 出口前必须验证以下事实：

1. ☐ 三个引擎在 CI 都能 dump 一棵 parent/children 正确的 UI 树（无重复节点、无层级错误）
2. ☐ Unity / Godot 在 PR runner 上 `take_screenshot` 能拿到非空像素（不是黑屏）
3. ☐ Self-hosted UE runner 在 nightly 跑通 `编译 + e2e + 截图`
4. ☐ 防护 0.1（路径白名单）+ 0.2（源码 diff）能拦下故意触发的 visual 修改
5. ☐ Subprotocol 握手在三引擎都正确返回 `autoagent.v1`
6. ☐ Negotiate_version JSON-RPC 握手在三引擎都符合 `01-protocol-spec.md` 规范

任意一项 fail → Phase 0 不算完成，**不进 Phase 1**。

## 十二、本地复现 CI

开发者本地复现 CI 失败（避免"CI 上 fail，本地不重现"）：

```bash
# 跑路径白名单
python scripts/ci/check_changed_paths.py --base origin/main

# 跑源码审计
python scripts/ci/audit_visual_writes.py --diff origin/main...HEAD

# 跑视觉回归（需引擎和测试 fixture 已 setup）
python scripts/ci/visual_regression.py --engine unity
```

每个 CI step 都是独立 Python 脚本，本地能复现。这是工程纪律。
