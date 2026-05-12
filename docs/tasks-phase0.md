# 99-tasks Phase 0 — 协议规范 + 三引擎 PoC

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。

## Phase 0 出口标准（go/no-go gate）

1. 三引擎 dump UI 树 parent/children 正确
2. Unity / Godot screenshot 非空（不是黑屏）
3. Self-hosted UE runner online + nightly 跑通
4. 防护 0.1（路径白名单）+ 0.2（源码 diff）拦下故意破坏
5. Subprotocol 握手在三引擎都正确返回 `autoagent.v1`
6. `negotiate_version` JSON-RPC 握手符合 [01-protocol-spec.md](01-protocol-spec.md) 规范
7. Orchestration scaffolding 跑通 1 个 echo 任务（TASK-0022 通过）
8. 故意让 agent 违反路径白名单 → 顶层正确捕获 needs_human
9. 故意 kill 掉一个 in_progress agent → 顶层 resume 时正确恢复
10. 写 stop_signal → 顶层正确停机

任意一项 fail → Phase 1 不启动。

---

### TASK-0000: Repo bootstrap

```yaml
title: Repo bootstrap (gitignore / README / dir skeleton / LICENSE)
phase: 0
engine: none
depends_on: []
goal: 建立 monorepo 基础骨架，确保 Phase 0 可以开始
output:
  - .gitignore (Unity + UE + Godot + Python + IDE 模板合并)
  - README.md (项目简介 + docs 链接)
  - LICENSE (MIT)
  - 目录骨架: adapters/{unity,unreal,godot}/.gitkeep
  - 目录骨架: mcp-server/.gitkeep, protocol/.gitkeep
  - 目录骨架: scripts/{ci,e2e}/.gitkeep
  - 目录骨架: fixtures/{unity,unreal,godot}-test-project/.gitkeep
  - 目录骨架: baselines/.gitkeep, .github/workflows/.gitkeep
verification:
  - git ls-files | grep -E "(adapters/unity|mcp-server|baselines)" 命中
  - cat README.md | head -20 含项目名
  - cat LICENSE 是标准 MIT
mode: manual
risk: low
```

**Context**：仓库已 `git init`，无现有内容。本任务是所有后续工作的前置。

---

### TASK-0001: 协议 schema JSON 文件

```yaml
title: Wire Protocol JSON Schema 文件
phase: 0
engine: none
depends_on: [TASK-0000]
goal: 把 01-protocol-spec.md 的 schema 落到机器可校验的 JSON Schema 文件
output:
  - protocol/schema/node.json (节点 schema, visual/behavior/meta/engine_extras)
  - protocol/schema/methods.json (所有 wire method 的 input/output schema)
  - protocol/schema/events.json (事件 notification schema)
  - protocol/schema/errors.json (错误码 enum)
  - protocol/README.md (使用说明)
  - protocol/tests/test_schema_valid.py (pytest 验证)
verification:
  - pytest protocol/tests/test_schema_valid.py -v
  - 所有 schema 文件都是合法 JSON Schema (Draft 2020-12)
  - 一个 sample node 通过 node.json 验证
  - 一个 sample dump_tree request 通过 methods.json 验证
mode: auto-with-review
risk: medium
```

**Context**：所有三引擎 adapter 必须遵循同一份 schema。

---

### TASK-0001b: Fixture 辅助脚本

```yaml
title: scripts/fixtures/bootstrap_fixture_assets.py + validate_static_fixtures.py
phase: 0
engine: none
depends_on: [TASK-0000]
goal: 为三引擎 fixture 搭建提供辅助脚本——生成占位 PNG 资源 + 静态验证 fixture 无交互控件
output:
  - scripts/fixtures/bootstrap_fixture_assets.py (生成 8 张占位 PNG: btn_login_{normal,hover,pressed,disabled}.png, input_bg_{normal,focused}.png, panel_bg.png, slot_bg.png)
  - scripts/fixtures/validate_static_fixtures.py (引擎静态检查: 场景文件存在 / 命名合规 / 无交互控件误入 / sprite 和 font 齐全)
  - scripts/fixtures/tests/ (pytest)
verification:
  - python scripts/fixtures/bootstrap_fixture_assets.py 执行后在 fixtures/*/ 下生成 PNG
  - python scripts/fixtures/validate_static_fixtures.py --engine all 对占位 fixture 跑通（至少文件存在性检查通过）
mode: auto-with-review
risk: low
```

**Context**：TASK-0008a/0010/0012 的手动 fixture 搭建依赖这两个脚本。`bootstrap_fixture_assets.py` 生成占位图使 fixture 场景可搭建；`validate_static_fixtures.py` 用于手动搭建后的自检。

---

### TASK-0002: MCP Server skeleton

```yaml
title: Python MCP server 骨架（stdio + dummy tools）
phase: 0
engine: none
depends_on: [TASK-0001]
goal: 建立 mcp-server Python 项目，实现 stdio MCP entry，注册 dummy tools 占位
output:
  - mcp-server/pyproject.toml (uv 管理, 依赖 mcp / websockets / scikit-image / pydantic)
  - mcp-server/src/autoagent_mcp/__init__.py
  - mcp-server/src/autoagent_mcp/server.py (MCP entry, stdio)
  - mcp-server/src/autoagent_mcp/tools/__init__.py (dummy stubs for 17 tools)
  - mcp-server/src/autoagent_mcp/cli.py (autoagent-mcp CLI)
  - mcp-server/tests/test_server_starts.py
  - mcp-server/README.md
verification:
  - uv run autoagent-mcp --help 正常输出
  - pytest mcp-server/tests/ -v
  - Claude Code 配置 .mcp.json 后能启动并 list 出 17 个 tools
mode: auto-with-review
risk: medium
```

**Context**：tools 用 stub 实现（接收参数、返回 mock 数据），Phase 1 才连真实 wire protocol。

---

### TASK-0003: 路径白名单 CI 脚本（防护 0.1）

```yaml
title: scripts/ci/check_changed_paths.py — 路径白名单
phase: 0
engine: none
depends_on: [TASK-0000]
goal: 实现 PR diff 路径白名单检查脚本，违反立即 fail
output:
  - scripts/ci/check_changed_paths.py
  - scripts/ci/path_whitelist.yml (规则配置)
  - scripts/ci/tests/test_check_paths.py
  - scripts/ci/tests/fixtures/ (mock diff 测试数据)
verification:
  - pytest scripts/ci/tests/test_check_paths.py -v
  - 模拟改 .unity 文件 → exit code 非 0
  - 模拟改 adapters/unity/Runtime/*.cs → exit code 0
  - 模拟改 .env → exit code 非 0
mode: auto-with-review
risk: medium
```

---

### TASK-0004: 源码 diff 审计 CI 脚本（防护 0.2，初版 regex）

```yaml
title: scripts/ci/audit_visual_writes.py — 源码 diff 审计 (regex 初版)
phase: 0
engine: none
depends_on: [TASK-0003]
goal: 用 regex 扫源码 diff，禁止 AI 写 visual 字段
output:
  - scripts/ci/audit_visual_writes.py
  - scripts/ci/visual_write_rules.yml (regex 规则, 三语言)
  - scripts/ci/tests/test_audit.py
verification:
  - pytest scripts/ci/tests/test_audit.py -v
  - 测试 case 包含: image.color = ... (Unity), SetVisibility (UE), .modulate = (Godot) → fail
  - 测试 case 包含: 顶部声明 AUTOAGENT_ALLOW_VISUAL → 跳过
mode: auto-with-review
risk: medium
```

---

### TASK-0005: dump 前后 diff CI 脚本（防护 0.3）

```yaml
title: scripts/ci/diff_visual_dump.py — dump 前后 visual diff
phase: 0
engine: none
depends_on: [TASK-0001, TASK-0003]
goal: 对比 e2e 测试的 before.json / after.json 的 visual 字段，任何变化 fail
output:
  - scripts/ci/diff_visual_dump.py
  - scripts/ci/tests/test_diff_visual.py
verification:
  - pytest scripts/ci/tests/test_diff_visual.py -v
  - 测试 case: 同一棵树 visual 完全一致 → exit 0
  - 测试 case: 某节点 color 变化 → exit 非 0 + 输出节点 ID + 字段
mode: auto-with-review
risk: medium
```

---

### TASK-0006: GitHub Actions workflows 初版

```yaml
title: GitHub Actions 7 个 workflow 文件初版
phase: 0
engine: none
depends_on: [TASK-0003, TASK-0004, TASK-0005]
goal: 建立 7 个 workflow 文件，初版含 Step 1+2 防护 0
output:
  - .github/workflows/source-audit.yml
  - .github/workflows/mcp-pr.yml
  - .github/workflows/unity-pr.yml
  - .github/workflows/godot-pr.yml
  - .github/workflows/unreal-pr-lint.yml
  - .github/workflows/unreal-nightly.yml
  - .github/workflows/visual-baseline.yml
verification:
  - GitHub Actions 列表显示 7 个 workflow
  - 推一个 sample PR，source-audit + mcp-pr 跑通
  - unreal-nightly cron 配置正确（02:00 UTC）
mode: auto-with-review
risk: high
path_exception: [".github/workflows/**"]
```

---

### TASK-0007: Unity adapter PoC + 单元测试

```yaml
title: Unity adapter PoC — 4 动作 + WebSocket + subprotocol + negotiate_version
phase: 0
engine: unity
depends_on: [TASK-0001, TASK-0008a]
goal: Unity adapter 最小可行版，能 dump UI 树 + 4 动作 (click/drag/text/scroll) + 完整握手
output:
  - adapters/unity/package.json
  - adapters/unity/Runtime/AutoAgent.Runtime.asmdef
  - adapters/unity/Runtime/AutoAgentBootstrap.cs
  - adapters/unity/Runtime/Server/WebSocketServer.cs
  - adapters/unity/Runtime/Server/ProtocolHandler.cs
  - adapters/unity/Runtime/Reflection/UGuiReflector.cs
  - adapters/unity/Runtime/Reflection/NodeSerializer.cs
  - adapters/unity/Runtime/Input/EngineInputDriver.cs
  - adapters/unity/Tests/Runtime/UGuiReflectorTests.cs
  - adapters/unity/Tests/Runtime/InputDriverTests.cs
verification:
  - Unity Test Runner: parent/children 一致性测试通过
  - PlayMode 测试: PocPlaygroundScene 跑 4 动作全部成功
  - wscat 连 ws://127.0.0.1:27842 with subprotocol "autoagent.v1" → 收到 negotiate_version
  - 错误 subprotocol 连接 → adapter 拒绝握手
mode: auto-with-review
risk: medium
```

---

### TASK-0008a: Unity 测试 fixture 项目 — 视觉骨架（手动）

```yaml
title: Unity 测试项目 + PocPlaygroundScene + LoginScene（仅视觉骨架 + 节点命名）
phase: 0
engine: unity
depends_on: [TASK-0000]
goal: 用户在 Unity 里手动建立 fixture 项目并 commit。严格遵循 [00 §四]——只放 Image / TMP_Text / 容器，不挂任何 Selectable 子类。节点命名 = 未来 PinnedId
output:
  - fixtures/unity-test-project/Packages/manifest.json
  - fixtures/unity-test-project/ProjectSettings/*
  - fixtures/unity-test-project/Assets/Scenes/PocPlaygroundScene.unity（视觉骨架）
  - fixtures/unity-test-project/Assets/Scenes/LoginScene.unity（视觉骨架）
  - fixtures/unity-test-project/Assets/Sprites/UI/*.png
  - fixtures/unity-test-project/Assets/Fonts/*.ttf / *.otf
verification:
  - 在 Unity 打开能正常加载
  - 两个 scene 都能 Play 起来（纯视觉，无交互）
  - GameObject 命名严格遵循 stable ID 清单（如 "login_button_bg", "account_input_bg"...）
  - grep -r "Button\|TMP_InputField\|Toggle\|Slider\|ScrollRect" Assets/Scenes/*.unity → 无匹配
  - metadata（PinnedId/LogicalRole）待 TASK-0008b 补，此时可以不填
mode: manual
risk: low
```

**Context**：本任务只搭视觉骨架 + 节点命名。StableIdComponent 由 TASK-0007（Unity adapter）产出，metadata（PinnedId / LogicalRole / StateSprites）由 TASK-0008b 后补。这与 Godot/UE 不同——Unity 的 metadata 依赖 adapter 自己的 MonoBehaviour 组件，所以必须分两步走，避免循环依赖。

---

### TASK-0008b: Unity 测试 fixture — 补 StableIdComponent metadata（手动）

```yaml
title: 给 Unity fixture 节点补 StableIdComponent + PinnedId + LogicalRole + StateSprites
phase: 0
engine: unity
depends_on: [TASK-0007, TASK-0008a]
goal: TASK-0007 实现 StableIdComponent 后，回到 Unity Editor 给所有关键节点挂组件 + 填 metadata
output:
  - 所有 LoginScene / PocPlaygroundScene 关键节点挂 StableIdComponent
  - PinnedId 填入（= GameObject 名称）
  - LogicalRole 填入（按 01 协议取值表）
  - StateSprites 填入（button 4 状态 / input 2 状态）
verification:
  - dump_tree 输出所有关键节点 stable_id_source = "pinned"
  - dump_tree 输出 LogicalRole 非空（除 image_only 节点）
  - dump_tree 输出 StateSprites 字段包含 sprite 引用
  - fixture 加载后立即 dump（无业务代码运行）→ behavior.attached_components 为空（Phase 0 阶段无 AI 控件挂载）
mode: manual
risk: low
path_exception: ["fixtures/unity-test-project/Assets/Scenes/LoginScene.unity", "fixtures/unity-test-project/Assets/Scenes/PocPlaygroundScene.unity"]
```

---

### TASK-0009: Godot adapter PoC + 单元测试

```yaml
title: Godot adapter PoC — 4 动作 + TCPServer/WebSocket + subprotocol
phase: 0
engine: godot
depends_on: [TASK-0001, TASK-0010]
goal: Godot adapter 最小可行版（GDScript）
output:
  - adapters/godot/addons/autoagent/plugin.cfg
  - adapters/godot/addons/autoagent/plugin.gd
  - adapters/godot/addons/autoagent/runtime/autoagent.gd
  - adapters/godot/addons/autoagent/runtime/server/websocket_server.gd
  - adapters/godot/addons/autoagent/runtime/server/protocol_handler.gd
  - adapters/godot/addons/autoagent/runtime/reflection/control_reflector.gd
  - adapters/godot/addons/autoagent/runtime/input/engine_input_driver.gd
  - adapters/godot/addons/autoagent/tests/unit/test_control_reflector.gd (GUT)
  - adapters/godot/addons/autoagent/tests/unit/test_input_driver.gd
verification:
  - GUT 跑通: parent/children 一致性, 4 动作全部成功
  - wscat 连 ws://127.0.0.1:27842 with subprotocol "autoagent.v1" → 收到 negotiate_version
  - 错误 subprotocol 被拒
mode: auto-with-review
risk: medium
```

---

### TASK-0010: Godot 测试 fixture 项目（手动）

```yaml
title: Godot 测试项目 + poc_playground.tscn + login.tscn（只放视觉骨架）
phase: 0
engine: godot
depends_on: [TASK-0000]
goal: 用户在 Godot 里手动建立 fixture。严格遵循 [00 §四]——只放 TextureRect / ColorRect / Label / Container
output:
  - fixtures/godot-test-project/project.godot
  - fixtures/godot-test-project/scenes/poc_playground.tscn（视觉骨架）
  - fixtures/godot-test-project/scenes/login.tscn（视觉骨架）
  - fixtures/godot-test-project/assets/ui/*.png
  - fixtures/godot-test-project/assets/fonts/*.ttf
  - 每个节点 set_meta autoagent_pinned_id + autoagent_logical_role
verification:
  - Godot 打开正常
  - 两个 scene 跑起来不报错（纯视觉，无交互）
  - grep 'type="Button"\|type="LineEdit"\|type="HSlider"\|type="ScrollContainer"' scenes/*.tscn → 无匹配
mode: manual
risk: low
```

---

### TASK-0011: UE adapter PoC + 单元测试

```yaml
title: UE adapter PoC — 4 动作 + uWS WebSocket + subprotocol
phase: 0
engine: unreal
depends_on: [TASK-0001, TASK-0012, TASK-0013]
goal: UE adapter 最小可行版（C++），能在 packaged build 跑
output:
  - adapters/unreal/AutoAgent.uplugin
  - adapters/unreal/Source/AutoAgent/AutoAgent.Build.cs
  - adapters/unreal/Source/AutoAgent/Public/AutoAgentSubsystem.h
  - adapters/unreal/Source/AutoAgent/Public/Server/WebSocketServer.h
  - adapters/unreal/Source/AutoAgent/Public/Reflection/UmgReflector.h
  - adapters/unreal/Source/AutoAgent/Public/Reflection/StableIdResolver.h
  - adapters/unreal/Source/AutoAgent/Public/Input/SlateInputDriver.h
  - adapters/unreal/Source/AutoAgent/Private/* (对应 cpp)
  - adapters/unreal/Source/AutoAgent/Tests/UmgReflectorTest.cpp
  - adapters/unreal/Tests/PocE2ETest.cpp
verification:
  - Self-hosted runner 编译通过 (Development Editor + Development)
  - UE Automation: AutoAgent.UmgReflectorTest 全绿
  - wscat 验证 subprotocol 握手
  - PocPlaygroundMap 跑 4 动作全部成功
mode: auto-with-review
risk: high
```

---

### TASK-0012: UE 测试 fixture 项目（手动）

```yaml
title: UE 测试项目 + PocPlaygroundMap + LoginMap（只放视觉骨架）
phase: 0
engine: unreal
depends_on: [TASK-0000]
goal: 用户在 UE 里手动建立 fixture。严格遵循 [00 §四]——WidgetTree 只放 UImage / UTextBlock / UCanvasPanel
output:
  - fixtures/unreal-test-project/AutoAgentTest.uproject
  - fixtures/unreal-test-project/Source/AutoAgentTest/*
  - fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset（视觉骨架）
  - fixtures/unreal-test-project/Content/UI/WBP_PocPlayground.uasset（视觉骨架）
  - fixtures/unreal-test-project/Content/UI/Sprites/*.png
  - fixtures/unreal-test-project/Content/Maps/*.umap
  - fixtures/unreal-test-project/Content/UI/Fonts/*
  - fixtures/unreal-test-project/Config/DefaultEngine.ini
verification:
  - UE 打开 + 编译通过
  - PIE 跑两个 map 不报错（纯视觉，无交互响应）
  - 在 .h / .uasset 里 grep 'UButton\|UEditableTextBox\|USlider\|UScrollBox' → 0 matches
mode: manual
risk: low
```

---

### TASK-0013: Self-hosted UE runner 上线

```yaml
title: Self-hosted Windows GPU runner 配置 + GitHub Actions 注册
phase: 0
engine: unreal
depends_on: [TASK-0000]
goal: 用户准备并上线 self-hosted runner
output:
  - 用户手动: Windows 11 + VS 2022 + UE + GPU + 32GB RAM + 200GB SSD
  - 用户手动: 安装 GitHub Actions runner agent
  - docs/runners-inventory.md (记录 runner ID / hostname / 维护负责人)
verification:
  - GitHub Actions Settings → Runners 显示该 runner online
  - workflow_dispatch 触发一个 hello-world job 跑通
mode: manual
risk: medium
```

---

### TASK-0014: 视觉 baseline 初次截图（手动）

```yaml
title: 三引擎初次 baseline 截图 + commit
phase: 0
engine: all
depends_on: [TASK-0007, TASK-0009, TASK-0011]
goal: 在三个 fixture project 跑 take_screenshot，人工 review 后 commit baseline
output:
  - baselines/unity/windows/poc_playground.png + .meta.json
  - baselines/unity/windows/login_screen.png + .meta.json
  - baselines/unreal/windows/poc_playground.png + .meta.json
  - baselines/unreal/windows/login_screen.png + .meta.json
  - baselines/godot/linux/poc_playground.png + .meta.json
  - baselines/godot/linux/login_screen.png + .meta.json
verification:
  - 6 张图人工肉眼 review 通过
  - 每张图配 .meta.json
mode: manual
risk: low
path_exception: ["baselines/**"]
```

---

### TASK-0015: 故意破坏验证 — 防护 0.1（路径白名单）

```yaml
title: 验证 CI 拦下: 故意改 fixture/.unity / Sprites / .uasset
phase: 0
engine: all
depends_on: [TASK-0006]
goal: 在 sandbox repo 故意推 PR 触发路径白名单违规，确认 CI 立即 fail
output:
  - scripts/ci/tests/integration/test_path_violation.sh
  - 一组演示 commit (推到独立 sandbox repo)
verification:
  - sandbox: 改 .unity 文件 → CI fail with PathViolation
  - sandbox: 改 baselines/ → CI fail
  - sandbox: 改 .env → CI fail
  - main repo 全局违规计数不增加
mode: manual
risk: medium
negative_test: true
sandbox_only: true
```

---

### TASK-0016: 故意破坏验证 — 防护 0.2（源码 diff）

```yaml
title: 验证 CI 拦下: 故意在 C# 写 image.color = ...
phase: 0
engine: unity
depends_on: [TASK-0006, TASK-0007]
goal: 在 sandbox repo 故意推 PR 在 fixture script 改 visual 属性，确认 CI 拦下
output:
  - scripts/ci/tests/integration/test_visual_audit.sh
  - 一组演示 commit (sandbox repo)
verification:
  - sandbox: fixture .cs 写 image.color = Color.red → CI fail
  - sandbox: 文件顶部加 // AUTOAGENT_ALLOW_VISUAL: ... 注释 → CI 跳过
  - main repo 全局违规计数不增加
mode: manual
risk: medium
negative_test: true
sandbox_only: true
```

---

### TASK-0018: Orchestration — state/ 目录初始化

```yaml
title: 创建 state/ 目录骨架 + .gitignore + 文件锁约定
phase: 0
engine: none
depends_on: [TASK-0000]
goal: 为自动化调度建立状态文件根目录 + 初始 budget.json
output:
  - state/{queue,ready,in_progress,awaiting_ci,done,failed,needs_human,blocked,logs}/.gitkeep
  - state/budget.json (初始)
  - state/events.jsonl (空文件)
  - .gitignore 加 state/* 但保留 state/*/.gitkeep
  - .env.agent.example (commit)
  - .gitignore 加 .env.agent
verification:
  - ls state/queue / state/ready / ... 全部存在
  - cat state/budget.json 是合法 JSON
  - git status 显示 .env.agent 被 ignore
mode: manual
risk: low
```

---

### TASK-0019: Orchestration — scripts/orchestrator/*.py（顶层 helper）

```yaml
title: 顶层 Claude 用的调度 helper 脚本（poll/spawn/collect/stop/resume/status）
phase: 0
engine: none
depends_on: [TASK-0018]
goal: 实现 docs/09-orchestration.md §8 + §13 描述的 6 个 helper 脚本
output:
  - scripts/orchestrator/poll.py
  - scripts/orchestrator/spawn.py
  - scripts/orchestrator/collect.py
  - scripts/orchestrator/stop.py
  - scripts/orchestrator/resume.py
  - scripts/orchestrator/status.py
  - scripts/orchestrator/lib/ (state_io.py, dag.py, budget.py, events.py)
  - scripts/orchestrator/tests/test_*.py
verification:
  - python scripts/orchestrator/status.py 在空 state/ 上不崩
  - python scripts/orchestrator/poll.py --dry-run 输出"无任务可调度"
  - 单测覆盖: dag 算法 / state 转移 / budget 累计 / 事件追加
mode: auto-with-review
risk: medium
```

---

### TASK-0020: Orchestration — scripts/agent/run_task.py（Python agent）

```yaml
title: 单任务 Python agent — spawn claude CLI + 验证产出 + 写 result.json
phase: 0
engine: none
depends_on: [TASK-0018, TASK-0019]
goal: 实现 docs/09-orchestration.md §9 描述的 run_task.py
output:
  - scripts/agent/run_task.py (主入口)
  - scripts/agent/prompt_template.py
  - scripts/agent/worktree.py
  - scripts/agent/classify.py
  - scripts/agent/tests/test_*.py
verification:
  - 用 mock claude CLI (echo + exit 0) 跑 dry run，agent 能写 result.json
  - 用 mock claude (exit 1 + 路径违规 stderr) → result.status=needs_human
  - worktree 创建成功
  - log 不包含明文 secret
mode: auto-with-review
risk: high
```

---

### TASK-0021: Orchestration — 顶层 Claude /loop 启动 prompt + 操作指南

```yaml
title: 写顶层 Claude Code 会话的 /loop 启动 prompt + 用户日常操作指南
phase: 0
engine: none
depends_on: [TASK-0019, TASK-0020]
goal: 用户可以打开 Claude Code, /loop 一次启动整个调度系统
output:
  - docs/orchestrator-prompt.md (顶层 /loop 启动用的完整 prompt 模板)
  - docs/user-guide-orchestration.md (用户怎么启动/停止/裁决)
verification:
  - prompt 模板包含所有必要说明
  - 用户指南覆盖完整操作流程
mode: manual
risk: low
```

---

### TASK-0022: Orchestration — 端到端 dry run

```yaml
title: 用 1 个 echo 任务验证整套 orchestration 跑通
phase: 0
engine: none
depends_on: [TASK-0019, TASK-0020, TASK-0021]
goal: Phase 0 真正启动前, 验证 spawn → claude → PR → CI → done 整链路
output:
  - state/queue/TASK-DRY-001.json (echo task)
  - docs/dry-run-report.md (dry run 全程记录)
verification:
  - 顶层 poll 找到 ready, spawn Python agent
  - Python agent spawn claude CLI, claude 在 worktree 创建 PR
  - 顶层 collect 检测 status=awaiting_ci
  - 顶层 poll PR check, all green, 移到 done/
  - 整个流程无人工干预 (除最初 /loop 启动)
  - 故意触发 needs_human + 自然语言裁决
  - 故意 kill in_progress agent → 顶层 resume 正确恢复
  - 故意写 stop_signal → 顶层停机
mode: manual
risk: high
```

### TASK-0023: Phase 0 出口 gate review（手动）

```yaml
title: Phase 0 10 个 go/no-go gate 全量 review
phase: 0
engine: all
depends_on: [TASK-0007, TASK-0008b, TASK-0009, TASK-0011, TASK-0013, TASK-0014, TASK-0015, TASK-0016, TASK-0022]
goal: 人工逐项确认 10 个 gate 全部通过，签发 Phase 1 启动
output:
  - docs/phase0-gate-report.md (gate 检查结果 + 截图证据 + 签字)
verification:
  - Gate 1-10 逐一确认
  - 任意一项 fail → Phase 1 不启动
mode: manual
risk: high
```
