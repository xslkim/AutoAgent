# 引擎 adapter 与 CI 指南

> 本文档记录 2026-05 这一轮工作的成果：三引擎 adapter 实现、跨引擎 e2e 验证、
> self-hosted CI 自动化、agent runner 切换。每一块都写清「做了什么 / 起什么作用 /
> 以后怎么用」。

---

## 1. 概览

这一轮把 AutoAgent 从「只有协议规范 + 编排骨架」推进到「三引擎 adapter 全部端到端
跑通 + CI 自动化」。

**关键成果**

- Unity / Godot / Unreal 三个引擎 adapter 实现并验证通过
- 一份 wire protocol 驱动三个引擎 —— 跨引擎一致性得到证明
- self-hosted runner + 3 个 CI workflow，推代码即自动编译 + 测试三引擎
- agent runner 从 claude CLI 换成 opencode + DeepSeek
- take_screenshot + 三引擎 baseline 截图
- 测试基建（仓库根一条 `pytest` 跑全部）

**主线提交**

| commit | 内容 |
|---|---|
| `f674c00` | agent runner 改用 opencode + DeepSeek |
| `98de01a` | TASK-0007 + TASK-0008b：Unity adapter + metadata |
| `51aff17` / `fa5f027` | TASK-0009：Godot adapter + headless 自测 |
| `3f4456f` / `351b7e6` | TASK-0011：Unreal adapter + Automation 测试 |
| `68b5784` | take_screenshot 三引擎实现 + subprotocol 拒绝验证 |
| `99160f4` | 测试基建：根 pytest.ini + integration 脚本 |
| `e61843d` | TASK-0014：三引擎 baseline 截图 |
| `28737af`…`cdd68d1` | TASK-0013：3 个 CI workflow 接 self-hosted runner |

---

## 2. 三引擎 adapter

### 2.1 架构（三引擎一致）

每个 adapter 都是同一个模式：引擎内部跑一个 WebSocket server（端口 `27842`，
subprotocol `autoagent.v1`），用 JSON-RPC 2.0 暴露 wire protocol。外部客户端
（测试脚本 / 未来的 MCP server）连上来，调 `dump_tree` / `find_widget` / `click`
等方法驱动引擎里的 UI。

**五个组成部分**

| 职责 | Unity (C#) | Godot (GDScript) | Unreal (C++) |
|---|---|---|---|
| 启动入口 | `AutoAgentBootstrap` | `autoagent.gd`（autoload） | `UAutoAgentSubsystem` |
| WebSocket server | `WebSocketServer.cs` | `websocket_server.gd` | `AutoAgentWebSocketServer` |
| 协议分发 | `ProtocolHandler.cs` | `protocol_handler.gd` | `AutoAgentProtocolHandler` |
| UI 树反射 | `UGuiReflector.cs` | `control_reflector.gd` | `AutoAgentUmgReflector` |
| 输入驱动 | `EngineInputDriver.cs` | `engine_input_driver.gd` | `AutoAgentSlateInputDriver` |

**线程模型**：Unity / UE 用后台线程收 WebSocket 包 + 主线程处理（UMG/Slate 只能在
主线程访问）；Godot 全主线程轮询（`WebSocketPeer` 非阻塞，无需后台线程）。

### 2.2 Unity adapter — `adapters/unity/`

- UPM 包 `com.autoagent.runtime`，Unity 2023.2.20f1
- **接入 fixture 项目**：`fixtures/unity-test-project/Packages/manifest.json` 里加
  `"com.autoagent.runtime": "file:../../../adapters/unity"`（`file:` 路径相对
  `Packages/` 目录，向上三级到仓库根）
- **metadata**：`StableIdComponent` 是个 MonoBehaviour，挂在 UI 节点上记录 pinned id /
  逻辑角色 / 状态贴图。TASK-0008b 由编辑器脚本 `AutoAgentMetadataBuilder.cs` 批量挂
  （菜单 **Tools → AutoAgent → Apply LoginScene Metadata**）
- **验证**：Unity Test Runner，PlayMode 8 个测试（`UGuiReflectorTests` 4 +
  `InputDriverTests` 4）

### 2.3 Godot adapter — `adapters/godot/addons/autoagent/`

- EditorPlugin + autoload，Godot 4.6
- **接入 fixture 项目**：adapter 在 `adapters/godot/`，靠 Windows 目录 junction 链进
  fixture 项目（Godot 的 addon 必须在 `res://addons/` 下）：
  ```
  mklink /J fixtures\godot-test-project\addons\autoagent adapters\godot\addons\autoagent
  ```
  该 junction 路径已被 `.gitignore`（真正的文件跟踪在 `adapters/godot/`）。装好后在
  Godot 里启用 AutoAgent 插件
- **metadata**：Godot 节点原生支持 metadata（`autoagent_pinned_id` /
  `autoagent_logical_role` / `autoagent_state_sprites`），直接写在 `.tscn` 里 ——
  所以 Godot 没有 Unity TASK-0008b 那种「单独挂组件」的步骤
- **验证**：`tests/headless_input_test.tscn`（GUT-free 自测，9 项检查）。编辑器里打开
  该场景按 F6，或 `godot --headless ... headless_input_test.tscn`。
  > GUT（Godot 单元测试框架）因为用户的 Godot dev 构建与 GUT 稳定版 API 不兼容，
  > 放弃了，改用这个不依赖第三方框架的自测

### 2.4 Unreal adapter — `adapters/unreal/`

- UE 插件 `AutoAgent`，UE 5.7
- **接入 fixture 项目**：junction 链进 fixture 项目的 `Plugins/`：
  ```
  mklink /J fixtures\unreal-test-project\Plugins\AutoAgent adapters\unreal
  ```
  该路径已 `.gitignore`
- **metadata**：UE 用 UPROPERTY 的 `meta` 标签（`AutoAgentId` / `AutoAgentLogicalRole`）
  + `Config/AutoAgentIds.ini` 镜像。adapter 运行时**读 ini**（meta 标签是 editor-only
  的，打包构建里会被剥掉；ini 在打包构建里也能读）
- **验证**：UE Automation 测试 `AutoAgent.StableIdResolver` 和 `AutoAgent.InputDriver`
  （`AutoAgentTests.cpp`，用 UE 内置 Automation 框架，无第三方依赖）

---

## 3. wire protocol 速览

- 地址 `ws://127.0.0.1:27842`，subprotocol 必须是 `autoagent.v1`（错误的会被拒）
- JSON-RPC 2.0
- 方法：`negotiate_version` / `dump_tree` / `find_widget` / `get_widget` /
  `click` / `send_text` / `drag` / `scroll` / `take_screenshot`
- 节点 JSON schema 权威定义：`protocol/schema/node.json`

---

## 4. e2e 验证 — `scripts/e2e/login_smoke.py`

引擎无关的端到端冒烟测试。同一个脚本、同一份协议，三个引擎通用 —— 这正是「跨引擎
一致性」的证明。8 项检查：握手 / negotiate_version / dump_tree + schema 校验 /
pinned 节点覆盖 / find_widget / state_sprites / take_screenshot / 错误 subprotocol 拒绝。

**怎么用**

1. 启动任一引擎并加载 Login 场景：
   - Unity：打开 `LoginScene` → 按 Play
   - Godot：运行 `login.tscn`
   - Unreal：PIE 运行 `LoginMap`（用 New Editor Window 模式）
2. 终端跑 `python scripts/e2e/login_smoke.py`

依赖：`pip install websockets jsonschema`

---

## 5. take_screenshot 与 baseline 截图

- 三引擎都实现了 `take_screenshot` 协议方法
- **采集 baseline**：`python scripts/e2e/capture_baseline.py --engine <unity|godot|unreal> --scene <login_screen|poc_playground>`
  —— 连引擎、调 take_screenshot、存 PNG 到 `baselines/<engine>/windows/<scene>.png`
  并生成 `.meta.json`
- 已采集的 6 张 baseline 在 `baselines/{unity,godot,unreal}/windows/`
- **UE 注意**：PIE 必须用 **New Editor Window** 模式 —— Selected Viewport 嵌入模式下
  截图会抓到整个编辑器窗口

---

## 6. CI —— self-hosted runner

### 6.1 runner

- GitHub Actions self-hosted runner 装在用户机器（`F5090`），目录 `D:\actions-runner`
- 标签 `self-hosted` / `Windows` / `X64`
- **常驻**：目前是 `run.cmd` 前台跑（关窗口就停）。建议用管理员 PowerShell 装服务：
  ```
  cd D:\actions-runner
  ./svc install
  ./svc start
  ```
- 为什么要 self-hosted：GitHub 云端 runner 没装游戏引擎、没 GPU、磁盘小，跑不了引擎
  编译。self-hosted = CI 任务在用户自己这台装了三引擎的机器上跑

### 6.2 三个 workflow

| workflow | 触发 | 在 runner 上做什么 |
|---|---|---|
| `unity-pr.yml` | PR 改 `adapters/unity/**` 等，或手动 | Unity batch 模式跑 8 个 PlayMode 测试 |
| `godot-pr.yml` | PR 改 `adapters/godot/**` 等，或手动 | Godot headless 跑 `headless_input_test`（9 项） |
| `unreal-nightly.yml` | 每晚 02:00 UTC，或手动 | `Build.bat` 编译 + `UnrealEditor-Cmd` 跑 Automation 测试 |

每个 workflow 还有个 `lint` job 跑在 GitHub 云端（fixture 静态检查，免费、快）。

### 6.3 怎么用

- **自动**：推一个改了对应 adapter 的 PR → CI 自动在 runner 上编译 + 测试
- **手动**：GitHub 仓库 → **Actions** → 选 workflow → **Run workflow**
- 引擎可执行文件路径**写死在 workflow 里**（换机器 / 换引擎版本要改 workflow）：
  - Unity `C:\Program Files\Unity 2023.2.20f1\Editor\Unity.exe`
  - Godot `D:\test\godot\bin\godot.windows.editor.dev.x86_64.mono.exe`
  - Unreal `C:\Program Files\Epic Games\UE_5.7`

### 6.4 CI 注意点（踩过的坑）

- workflow 的引擎步骤用 `shell: powershell`（runner 上没有 PowerShell 7 `pwsh`）
- Unity / Godot 是 GUI 程序，PowerShell `&` 调用不阻塞 —— 必须用
  `Start-Process -Wait -PassThru` 才能等它跑完并取退出码
- Godot / UE 的 adapter 靠 junction，CI 全新 checkout 没有 —— workflow 里有一步专门
  建 junction
- UE 全新构建要从零编译大型 PCH，默认 19 路并行会撑爆提交内存（页面文件）——
  workflow 里限制了 `-MaxParallelActions=4`
- runner 跑 CI 时尽量别在编辑器里开着同一个项目（CI 用的是独立 checkout 目录，
  一般不冲突，但 Unity 项目锁要注意）

---

## 7. agent runner —— 从 claude 换成 opencode

- Python agent `scripts/agent/run_task.py` 不再 spawn `claude` CLI，改 spawn
  `opencode`（用 DeepSeek V4 Pro）
- 原因：用户没有 Claude API key
- opencode 的 model + API key 配在 `~/.config/opencode/opencode.json`
- `.env.agent` 只需填 `AGENT_GITHUB_TOKEN`（opencode 的 key 它自己管）
- `run_task.py` 会自动识别命令是 opencode 还是 claude：opencode 用 positional arg
  传 prompt，claude 用 stdin
- **注意**：orchestrator 的真 `/loop` 在换 opencode 后还没端到端验证过（TASK-0022）

---

## 8. 测试

- **全量测试**：仓库根目录直接 `pytest` —— 根 `pytest.ini` 配好了，一条命令跑全部
  5 个组件共 270 个测试（importlib 导入模式解决多 `tests/` 包重名冲突）
- **CI 防护本地验证**：
  ```
  bash scripts/ci/tests/integration/test_path_violation.sh
  bash scripts/ci/tests/integration/test_visual_audit.sh
  ```
  验证防护 0.1（路径白名单）/ 0.2（视觉写审计）能拦下违规

---

## 9. 命令速查

```bash
# 全量单元测试（仓库根）
pytest

# e2e 冒烟（先启动某个引擎的 Login 场景）
python scripts/e2e/login_smoke.py

# 采集 baseline 截图
python scripts/e2e/capture_baseline.py --engine unity --scene login_screen

# CI 防护本地验证
bash scripts/ci/tests/integration/test_path_violation.sh
bash scripts/ci/tests/integration/test_visual_audit.sh

# 看编排状态
python scripts/orchestrator/status.py
```

**junction（换机器 / 重新 clone 后需重建）**

```
mklink /J fixtures\godot-test-project\addons\autoagent  adapters\godot\addons\autoagent
mklink /J fixtures\unreal-test-project\Plugins\AutoAgent adapters\unreal
```

Unity 不用 junction —— 它在 `manifest.json` 里用 `file:` 引用。
