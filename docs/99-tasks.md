# 99 - 任务清单（Tasks）

> 所有任务由 AI Agent（Claude Code background mode）执行，规则见 [07-agent-operations.md](07-agent-operations.md)。
> 每个任务 = 1 个 PR。任务之间有 `depends_on` 关系，agent 按拓扑顺序执行。
> Phase 0 + Phase 1 任务详写；Phase 2/3/4 anchor 列表，每个 anchor 在该 phase 启动前拆成 3-5 个 PR-sized task。

## 一、文档使用说明

### 任务字段

每个任务用 YAML 描述，字段含义：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✅ | 简短标题（PR title 用） |
| `phase` | int | ✅ | 0 / 1 / 2 / 3 / 4 |
| `engine` | enum | ✅ | `none` / `unity` / `unreal` / `godot` / `all` |
| `depends_on` | list | ✅ | 必须先完成的 task ID 列表 |
| `goal` | string | ✅ | 一句话目标 |
| `output` | list | ✅ | 要创建/修改的文件路径 + 简述 |
| `verification` | list | ✅ | 完成验收方式（unit/e2e/acceptance） |
| `effort` | string | ✅ | 估时（如 `4h`、`1d`、`3d`） |
| `mode` | enum | ✅ | `manual` / `auto-with-review` / `auto-merge-safe` |
| `risk` | enum | ✅ | `low` / `medium` / `high` |
| `max_iterations` | int | ⬜ | 默认见 [07 §2.1](07-agent-operations.md#21-单任务最大迭代次数) |
| `path_exception` | list | ⬜ | 突破路径白名单的明确豁免（[07 §3.3](07-agent-operations.md#33-例外申请流程)） |
| `negative_test` | bool | ⬜ | 故意破坏 / 违规验证类任务。CI fail 是预期 verification；**违规不计入** [07 §2.3](07-agent-operations.md) 全局违规计数 |
| `sandbox_only` | bool | ⬜ | 任务 commit 推到独立 sandbox repo，不污染主 repo PR 历史 / cost session / global counters。常与 `negative_test` 一起用 |

### 任务状态

- `pending`：未开始
- `in-progress`：AI agent 正在执行
- `pr-open`：已开 PR 等 review
- `merged`：已合并
- `blocked`：依赖未完成 / 等人工干预
- `anchor`：占位任务，待该 phase 启动前细化

状态字段不在 YAML 里手动维护，由 agent + GitHub status check 自动更新（写在 PR body 里，详见 07）。

## 二、任务总表

| Phase | 任务数 | 详细程度 | 时长 | 关键产出 |
|---|---|---|---|---|
| Phase 0 | 23 | 详写 | 2-3 周 | 协议 schema + 三引擎 PoC + CI gate + 故意破坏验证 + orchestration scaffolding |
| Phase 1 | 35 | 详写 | 2 月 | Unity adapter 完整 + MCP server + 视觉回归 + login MVP |
| Phase 2 | 12 (anchor) | anchor | 2.5-3 月 | UE adapter 完整 + 跨引擎 MVP 一致 |
| Phase 3 | 10 (anchor) | anchor | 1 月 | Godot adapter 完整 + 三引擎一致 |
| Phase 4 | 10 (anchor) | anchor | 1 月 | OS 输入 / LPIPS / 性能优化 / v1.0 release |
| **合计** | **90** | | **~7 月** | |

---

## 三、Phase 0 — 协议规范 + 三引擎 PoC（详写）

> 出口标准（go/no-go gate，详见本文档 §八）：
> 1. 三引擎 dump UI 树 parent/children 正确
> 2. Unity / Godot screenshot 非空（不是黑屏）
> 3. Self-hosted UE runner online + nightly 跑通
> 4. 防护 0.1（路径白名单）+ 0.2（源码 diff）拦下故意破坏
> 5. Subprotocol 握手在三引擎都正确返回 `autoagent.v1`
> 6. `negotiate_version` JSON-RPC 握手符合 [01-protocol-spec.md](01-protocol-spec.md) 规范

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
effort: 1h
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
effort: 4h
mode: auto-with-review
risk: medium
```

**Context**：所有三引擎 adapter 必须遵循同一份 schema。后续 dump 输出做 schema 校验时直接用这些文件。

**Risk**：协议 schema 改动会触发所有 adapter 改动，medium risk。

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
  - mcp-server/src/autoagent_mcp/tools/__init__.py (dummy stubs for 12 core + 5 aux tools，见 [02 §三 分组](02-mcp-server.md))
  - mcp-server/src/autoagent_mcp/cli.py (autoagent-mcp CLI)
  - mcp-server/tests/test_server_starts.py
  - mcp-server/README.md
verification:
  - uv run autoagent-mcp --help 正常输出
  - pytest mcp-server/tests/ -v
  - Claude Code 配置 .mcp.json 后能启动并 list 出 12 个 tool
effort: 1d
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
  - scripts/ci/path_whitelist.yml (规则配置, 见 06-visual-regression.md §2.1)
  - scripts/ci/tests/test_check_paths.py
  - scripts/ci/tests/fixtures/ (mock diff 测试数据)
verification:
  - pytest scripts/ci/tests/test_check_paths.py -v
  - 模拟改 .unity 文件 → exit code 非 0
  - 模拟改 adapters/unity/Runtime/*.cs → exit code 0
  - 模拟改 .env → exit code 非 0
effort: 4h
mode: auto-with-review
risk: medium
```

**Context**：CI 第一步，所有引擎 workflow 都跑这个。

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
effort: 1d
mode: auto-with-review
risk: medium
```

**Context**：regex 是初版，Phase 4 升级 AST。

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
effort: 4h
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
goal: 建立 7 个 workflow 文件 (见 08-ci-runners.md §八)，初版含 Step 1+2 防护 0
output:
  - .github/workflows/source-audit.yml (跑 check_changed_paths + audit_visual_writes)
  - .github/workflows/mcp-pr.yml (Python lint + pytest)
  - .github/workflows/unity-pr.yml (windows-latest, Unity install via GameCI)
  - .github/workflows/godot-pr.yml (ubuntu-latest, Xvfb)
  - .github/workflows/unreal-pr-lint.yml (self-hosted, lint only)
  - .github/workflows/unreal-nightly.yml (cron, self-hosted, full build)
  - .github/workflows/visual-baseline.yml (path filter, human review gate)
verification:
  - GitHub Actions 列表显示 7 个 workflow
  - 推一个 sample PR，source-audit + mcp-pr 跑通
  - unreal-nightly cron 配置正确（02:00 UTC）
effort: 2d
mode: auto-with-review
risk: high
path_exception: [".github/workflows/**"]
```

**Risk**：CI 配置错误会 block 后续所有任务，high risk，必须人工 review。

---

### TASK-0007: Unity adapter PoC + 单元测试

```yaml
title: Unity adapter PoC — 4 动作 + WebSocket + subprotocol + negotiate_version
phase: 0
engine: unity
depends_on: [TASK-0001, TASK-0008]
goal: Unity adapter 最小可行版，能 dump UI 树 + 4 动作 (click/drag/text/scroll) + 完整握手
output:
  - adapters/unity/package.json
  - adapters/unity/Runtime/AutoAgent.Runtime.asmdef
  - adapters/unity/Runtime/AutoAgentBootstrap.cs (RuntimeInitializeOnLoadMethod)
  - adapters/unity/Runtime/Server/WebSocketServer.cs (websocket-sharp 封装)
  - adapters/unity/Runtime/Server/ProtocolHandler.cs (subprotocol + negotiate_version)
  - adapters/unity/Runtime/Reflection/UGuiReflector.cs
  - adapters/unity/Runtime/Reflection/NodeSerializer.cs
  - adapters/unity/Runtime/Input/EngineInputDriver.cs
  - adapters/unity/Tests/Runtime/UGuiReflectorTests.cs (parent/children 正确性)
  - adapters/unity/Tests/Runtime/InputDriverTests.cs (4 动作 PlayMode)
verification:
  - Unity Test Runner: parent/children 一致性测试通过 (无重复节点, 每个 child 的 parent_id 都在 nodes 列表里)
  - PlayMode 测试: PocPlaygroundScene 跑 4 动作全部成功
  - 用 wscat / nodejs 连 ws://127.0.0.1:27842 with subprotocol "autoagent.v1" → 收到 negotiate_version
  - 用错误 subprotocol 连接 → adapter 拒绝握手
effort: 5d
mode: auto-with-review
risk: medium
```

**Context**：参考 [03-adapter-unity.md](03-adapter-unity.md) §三、四、五。fixture 由 TASK-0008 准备。

---

### TASK-0008: Unity 测试 fixture 项目（手动）

```yaml
title: Unity 2023 测试项目 + PocPlaygroundScene + LoginScene（只放视觉骨架）
phase: 0
engine: unity
depends_on: [TASK-0000]
goal: 用户在 Unity 里手动建立 fixture 项目并 commit。严格遵循 [00 §四 程序员搭建边界]——只放 Image / TMP_Text / 容器，**不挂任何 Selectable 子类**
output:
  - fixtures/unity-test-project/Packages/manifest.json (依赖 com.autoagent.unity local)
  - fixtures/unity-test-project/ProjectSettings/* (ColorSpace=Linear 锁定)
  - fixtures/unity-test-project/Assets/Scenes/PocPlaygroundScene.unity（视觉骨架）：
    - click_target (Image, logical_role=button) + state_sprites (normal/hover/pressed)
    - text_target (Image + 子 TMP_Text 占位, logical_role=input)
    - drag_source / drag_target (Image, logical_role=draggable / drop_zone)
    - scroll_container (Image 视口 + Image content + 30 Image item, logical_role=scroll_container)
    - 5 个 click_target_variant_N 共测 click（不是 5 个按钮，是 5 个 Image+button role）
    每节点挂 StableIdComponent + PinnedId + LogicalRole + StateSprites（如适用）
  - fixtures/unity-test-project/Assets/Scenes/LoginScene.unity（视觉骨架）：
    - LoginPanel (Image, logical_role=image_only)
      - AccountInputBg (Image, logical_role=input) + 子 AccountInputText (TMP_Text, logical_role=text_display)
      - PasswordInputBg (Image, logical_role=input) + 子 PasswordInputText (TMP_Text)
      - LoginButtonBg (Image, logical_role=button) + state_sprites + 子 LoginButtonLabel (TMP_Text "Login")
      - ErrorLabel (TMP_Text, logical_role=text_display, 初始 empty)
    - WelcomePanel (Image, logical_role=image_only, 初始 inactive)
      - WelcomeText (TMP_Text, logical_role=text_display)
  - fixtures/unity-test-project/Assets/Sprites/UI/btn_login_{normal,hover,pressed,disabled}.png（4 套按钮 sprite）
  - fixtures/unity-test-project/Assets/Sprites/UI/input_bg_{normal,focused}.png
  - fixtures/unity-test-project/Assets/Fonts/Roboto-Regular.ttf
  - fixtures/unity-test-project/Assets/Fonts/NotoSansCJK-Regular.otf
verification:
  - 在 Unity 2023.2.20f1 打开能正常加载
  - 两个 scene 都能 Play 起来（什么交互都没有，纯视觉）
  - StableIdComponent 字段已 pin (PinnedId 非空) + LogicalRole 已填
  - grep -r "Button\|TMP_InputField\|Toggle\|Slider\|ScrollRect" Assets/Scenes/*.unity → 无匹配（强约束）
  - 用 adapter PoC dump 整棵树，每个 logical_role != image_only 的节点都有非空 LogicalRole
effort: 5h
mode: manual
risk: low
```

**Context**：用户手动操作。AI 不能改 .unity 文件（路径白名单禁）。**严格不放控件**——AI 在 [TASK-0132] 里通过源码 AddComponent 实现交互。

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
  - adapters/godot/addons/autoagent/runtime/autoagent.gd (autoload singleton)
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
effort: 4d
mode: auto-with-review
risk: medium
```

---

### TASK-0010: Godot 测试 fixture 项目（手动）

```yaml
title: Godot 4.3 测试项目 + poc_playground.tscn + login.tscn（只放视觉骨架）
phase: 0
engine: godot
depends_on: [TASK-0000]
goal: 用户在 Godot 里手动建立 fixture。严格遵循 [00 §四 程序员搭建边界]——只放 TextureRect / ColorRect / Label / Container，**不放 Button / LineEdit / HSlider / ScrollContainer 等交互 Control**
output:
  - fixtures/godot-test-project/project.godot
  - fixtures/godot-test-project/scenes/poc_playground.tscn（视觉骨架）：
    - click_target (TextureRect, logical_role=button) + state_sprites
    - text_target (TextureRect + 子 Label 占位, logical_role=input)
    - drag_source / drag_target (TextureRect)
    - scroll_container (TextureRect 视口 + content + 30 TextureRect item)
  - fixtures/godot-test-project/scenes/login.tscn（视觉骨架）：
    - LoginPanel (Control + ColorRect bg)
      - AccountInputBg (TextureRect, logical_role=input)
      - PasswordInputBg (TextureRect, logical_role=input)
      - LoginButtonBg (TextureRect, logical_role=button) + state_sprites
        - LoginButtonLabel (Label "Login")
      - ErrorLabel (Label, 初始 empty)
    - WelcomePanel (Control, visible=false)
      - WelcomeText (Label)
  - fixtures/godot-test-project/assets/ui/btn_login_{normal,hover,pressed,disabled}.png
  - fixtures/godot-test-project/assets/ui/input_bg_{normal,focused}.png
  - fixtures/godot-test-project/assets/fonts/*.ttf
  - 每个节点 set_meta autoagent_pinned_id + autoagent_logical_role；button/input 节点设 autoagent_state_sprites
verification:
  - Godot 4.3 打开正常
  - 两个 scene 跑起来不报错（纯视觉，无交互）
  - grep 'type="Button"\|type="LineEdit"\|type="HSlider"\|type="ScrollContainer"' scenes/*.tscn → 无匹配（强约束）
  - grep 'autoagent_pinned_id' 在 .tscn 里能看到 meta 数据
  - grep 'autoagent_logical_role' 同样能看到
effort: 4h
mode: manual
risk: low
```

---

### TASK-0011: UE adapter PoC + 单元测试

```yaml
title: UE 5.6 adapter PoC — 4 动作 + uWS WebSocket + subprotocol
phase: 0
engine: unreal
depends_on: [TASK-0001, TASK-0012, TASK-0013]
goal: UE adapter 最小可行版（C++），能在 packaged build 跑
output:
  - adapters/unreal/AutoAgent.uplugin
  - adapters/unreal/Source/AutoAgent/AutoAgent.Build.cs
  - adapters/unreal/Source/AutoAgent/Public/AutoAgentSubsystem.h (UGameInstanceSubsystem)
  - adapters/unreal/Source/AutoAgent/Public/Server/WebSocketServer.h (uWS 包装)
  - adapters/unreal/Source/AutoAgent/Public/Reflection/UmgReflector.h
  - adapters/unreal/Source/AutoAgent/Public/Reflection/StableIdResolver.h
  - adapters/unreal/Source/AutoAgent/Public/Input/SlateInputDriver.h
  - adapters/unreal/Source/AutoAgent/Private/* (对应 cpp)
  - adapters/unreal/Source/AutoAgent/Tests/UmgReflectorTest.cpp (UE Automation Test)
  - adapters/unreal/Tests/PocE2ETest.cpp (含 NoDuplicateNodes / ParentChildConsistent)
verification:
  - Self-hosted runner 编译通过 (Development Editor + Development)
  - UE Automation: AutoAgent.UmgReflectorTest 全绿
  - 用 wscat 连 ws://127.0.0.1:27842 with subprotocol "autoagent.v1" → 收到 negotiate_version
  - PocPlaygroundMap 跑 4 动作全部成功
effort: 7d
mode: auto-with-review
risk: high
```

**Risk**：UE C++ + uWS 集成 + Slate 输入注入 + GameThread 跨线程 marshal 是最复杂的一块，high risk。

---

### TASK-0012: UE 测试 fixture 项目（手动）

```yaml
title: UE 5.6 测试项目 + PocPlaygroundMap + LoginMap（只放视觉骨架）
phase: 0
engine: unreal
depends_on: [TASK-0000]
goal: 用户在 UE 5.6 里手动建立 fixture。严格遵循 [00 §四 程序员搭建边界]——WidgetTree 只放 UImage / UTextBlock / UCanvasPanel / UVerticalBox 等，**不放 UButton / UEditableTextBox / USlider / UScrollBox 等交互 widget**
output:
  - fixtures/unreal-test-project/AutoAgentTest.uproject (C++ project, UE 5.6)
  - fixtures/unreal-test-project/Source/AutoAgentTest/* (C++ user widget classes)
    - ULoginUserWidget.h/.cpp
      （BindWidget 全部指向 UImage / UTextBlock；UPROPERTY meta 含
        AutoAgentId="login_button_bg" + AutoAgentLogicalRole="button" 等）
    - UPocPlaygroundUserWidget.h/.cpp（同样只 BindWidget UImage）
  - fixtures/unreal-test-project/Content/UI/WBP_LoginScreen.uasset（视觉骨架）：
    - LoginPanel (UCanvasPanel)
      - AccountInputBg (UImage, logical_role=input)
      - PasswordInputBg (UImage, logical_role=input)
      - LoginButtonBg (UImage, logical_role=button) + state_sprites（4 张 png）
        - LoginButtonLabel (UTextBlock "Login")
      - ErrorLabel (UTextBlock, initially empty)
    - WelcomePanel (UCanvasPanel, initially Hidden)
      - WelcomeText (UTextBlock)
  - fixtures/unreal-test-project/Content/UI/WBP_PocPlayground.uasset（视觉骨架）
  - fixtures/unreal-test-project/Content/UI/Sprites/btn_login_{normal,hover,pressed,disabled}.png
  - fixtures/unreal-test-project/Content/UI/Sprites/input_bg_{normal,focused}.png
  - fixtures/unreal-test-project/Content/Maps/PocPlaygroundMap.umap
  - fixtures/unreal-test-project/Content/Maps/LoginMap.umap
  - fixtures/unreal-test-project/Content/UI/Fonts/* (NotoSansCJK + Roboto)
  - fixtures/unreal-test-project/Config/DefaultEngine.ini (锁定分辨率/color space)
  - fixtures/unreal-test-project/Config/AutoAgentIds.ini（备用注册表）
verification:
  - UE 5.6 打开 + 编译通过
  - PIE 跑两个 map 不报错（纯视觉，无交互响应）
  - 在 .h / .uasset 里 grep 'UButton\|UEditableTextBox\|USlider\|UScrollBox' → 0 matches（强约束；UButton 仅在 AI 写的 NativeConstruct 里出现）
  - 在 .h 里 grep 'AutoAgentId' 能看到至少 7 个声明
  - 在 .h 里 grep 'AutoAgentLogicalRole' 同样
effort: 1.5d
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
goal: 用户准备并上线 self-hosted runner（08-ci-runners.md §4.1 规格）
output:
  - 用户手动: Windows 11 + VS 2022 + UE 5.6 + GPU + 32GB RAM + 200GB SSD
  - 用户手动: 安装 GitHub Actions runner agent，标签 self-hosted, Windows, UE-5.6, GPU
  - docs/runners-inventory.md (记录 runner ID / hostname / 维护负责人)
verification:
  - GitHub Actions Settings → Runners 显示该 runner online
  - workflow_dispatch 触发一个 hello-world job 跑通
  - UE 5.6 路径在 PATH 中
effort: 1d
mode: manual
risk: medium
```

**Context**：没有 self-hosted runner，UE adapter 上不了 CI，Phase 2 也开始不了。

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
  - 6 张图人工肉眼 review 通过 (元素正确、字体不豆腐、color 正确)
  - 每张图配 .meta.json: {engine_version, resolution, color_space, captured_at, captured_by, runner_label}
effort: 4h
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
    (本地 / sandbox repo 起脚本：克隆 sandbox 副本 + 故意 commit + 跑 CI workflow + 断言 fail)
  - 一组演示 commit (推到独立 sandbox repo, 不 push 到 main repo)
verification:
  - sandbox: 改 fixtures/unity-test-project/Assets/Scenes/LoginScene.unity → CI fail with PathViolation
  - sandbox: 改 baselines/unity/windows/login_screen.png → CI fail
  - sandbox: 改 .env → CI fail
  - 失败信息含具体路径 + 违反的规则
  - **main repo 全局违规计数不增加**（见下方 negative_test 例外）
effort: 4h
mode: manual  # 必须人工执行：违规演示不走 autonomous loop
risk: medium
negative_test: true
sandbox_only: true
```

**Context**：本任务故意触发 [07 §3 路径白名单](07-agent-operations.md) + [07 §2.4 失败模式](07-agent-operations.md) 里"立即停 + 不重试"的拦截路径——正是 autonomous loop 永远**不应**做的事。所以必须：
- `mode: manual`：由人工在 sandbox repo 跑，**不**由 background agent 调度
- `sandbox_only: true`：所有 commit 推到独立 sandbox repo（如 `<org>/AutoAgent-negative-tests`），不污染主 repo PR 历史 / 全局违规计数 / cost session
- `negative_test: true`：orchestrator / agent contract 解释为"预期 CI fail 才算 verification 通过"，**违规不计入** [07 §2.3 全局上限](07-agent-operations.md) 的 "连续 3 次路径违规 → 全局停" 计数

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
  - sandbox: fixture .cpp 写 SetVisibility(...) → CI fail (UE)
  - sandbox: fixture .gd 写 .modulate = ... → CI fail (Godot)
  - sandbox: 文件顶部加 // AUTOAGENT_ALLOW_VISUAL: ... 注释 → CI 跳过
  - **main repo 全局违规计数不增加**
effort: 4h
mode: manual
risk: medium
negative_test: true
sandbox_only: true
```

**Context**：与 TASK-0015 相同的 `negative_test` / `sandbox_only` 约束——见上方 Context。

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
  - state/budget.json (初始: today_usd=0, session_usd=0, task_count=0)
  - state/events.jsonl (空文件)
  - .gitignore 加 state/* 但保留 state/*/.gitkeep
  - .env.agent.example (commit, 含 AGENT_ANTHROPIC_KEY / AGENT_GITHUB_TOKEN 占位符)
  - .gitignore 加 .env.agent (绝不进 git)
verification:
  - ls state/queue / state/ready / ... 全部存在
  - cat state/budget.json 是合法 JSON
  - git status 显示 .env.agent 被 ignore
  - .env.agent.example 不含真实 secret
effort: 1h
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
  - scripts/orchestrator/poll.py (一轮 polling, 详见 09 §8)
  - scripts/orchestrator/spawn.py (spawn 单个 Python agent)
  - scripts/orchestrator/collect.py (扫 in_progress + awaiting_ci 收集结果)
  - scripts/orchestrator/stop.py (写 stop_signal)
  - scripts/orchestrator/resume.py (删 stop_signal)
  - scripts/orchestrator/status.py (打印当前状态摘要)
  - scripts/orchestrator/lib/ (state_io.py, dag.py, budget.py, events.py)
  - scripts/orchestrator/tests/test_*.py (单元测试)
verification:
  - python scripts/orchestrator/status.py 在空 state/ 上不崩
  - python scripts/orchestrator/poll.py --dry-run 输出"无任务可调度"
  - 单测覆盖: dag 算法 / state 转移 / budget 累计 / 事件追加
  - 故意造死循环依赖 → poll.py 应报错退出
  - 故意造孤儿 PID → poll.py 健康检查应 detect
effort: 2d
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
  - scripts/agent/prompt_template.py (build_prompt 函数)
  - scripts/agent/worktree.py (setup/cleanup git worktree)
  - scripts/agent/classify.py (分类 claude exit code → failed/needs_human)
  - scripts/agent/tests/test_*.py
verification:
  - 用 mock claude CLI (echo + exit 0) 跑 dry run，agent 能写 result.json
  - 用 mock claude (exit 1 + 路径违规 stderr) → result.status=needs_human
  - 用 mock claude (timeout) → result.status=failed
  - worktree 创建成功后被 git worktree list 看到
  - .env.agent 加载后 ANTHROPIC_API_KEY 不出现在 child env outside agent process
  - log 不包含明文 secret (单测断言)
effort: 2d
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
  - docs/user-guide-orchestration.md (用户怎么启动/停止/裁决 needs_human)
  - .claude/skills/autoagent-loop.md (可选, 包装成 /autoagent-loop skill)
verification:
  - prompt 模板包含: state 目录路径 / poll 命令 / 自然语言裁决规则 / ScheduleWakeup 节奏
  - 用户指南覆盖: 首次启动 / 每日观察 / needs_human 裁决说法 / 紧急停机 / 恢复
  - 模板里的所有命令路径存在 (静态 lint)
  - 写完后用户人工试跑 1 个 echo 任务 (TASK-0022 再做)
effort: 4h
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
  - state/queue/TASK-DRY-001.json (echo task: 仅创建 docs/dry-run.md commit + push + PR)
  - docs/dry-run-report.md (dry run 全程截图 + log + 时间线)
verification:
  - 用户在主 Claude Code 会话 /loop 启动顶层
  - 顶层 poll 找到 ready, spawn Python agent
  - Python agent spawn claude CLI, claude 在 worktree 创建 docs/dry-run.md 并 PR
  - 顶层 collect 检测 result.status=awaiting_ci, 移到 awaiting_ci/
  - 顶层 poll PR check, all green, 移到 done/
  - 整个流程无人工干预 (除最初 /loop 启动)
  - events.jsonl 含完整事件链
  - 故意触发 1 次 needs_human (改 task 强制让 agent 改 .gitignore), 用户用自然语言 "approve 重试" → 顶层正确解析并恢复
  - 故意 kill in_progress agent → 顶层 resume 能正确恢复 (僵尸检测)
  - 故意写 stop_signal → 顶层下轮 polling 停机
effort: 4h
mode: manual
risk: high
```

---

### TASK-0017: Phase 0 出口 gate review（手动）

```yaml
title: Phase 0 10 个 go/no-go gate 全量 review
phase: 0
engine: all
depends_on: [TASK-0007, TASK-0009, TASK-0011, TASK-0013, TASK-0014, TASK-0015, TASK-0016, TASK-0022]
goal: 人工逐项确认 10 个 gate 全部通过，签发 Phase 1 启动
output:
  - docs/phase0-gate-report.md (gate 检查结果 + 截图证据 + 签字)
verification:
  - Gate 1: 三引擎 dump_tree 在 fixture 上跑 → parent/children 完全一致 (附 dump JSON sample)
  - Gate 2: Unity / Godot 在 PR runner take_screenshot 拿到非黑屏图
  - Gate 3: Self-hosted UE runner nightly 跑 build + e2e 全绿 (附 Action run URL)
  - Gate 4: 故意破坏 PR (TASK-0015 + 0016) 全部 CI fail (附 Action run URL)
  - Gate 5: 三引擎 wscat 测试 subprotocol 握手成功 (附终端截图)
  - Gate 6: negotiate_version 三引擎都返回完整 JSON-RPC response (附 wireshark/log)
  - Gate 7: orchestration scaffolding 跑通 1 个 echo 任务 (TASK-0022 通过, 附 events.jsonl + screenshot)
  - Gate 8: 故意让 agent 违反路径白名单 → 顶层正确捕获 needs_human (附 needs_human/ JSON)
  - Gate 9: 故意 kill 掉一个 in_progress agent → 顶层 resume 时正确恢复 (附 events.jsonl)
  - Gate 10: 写 stop_signal → 顶层正确停机 (附 events.jsonl)
  - 任意一项 fail → Phase 1 不启动, 标 needs-investigation
effort: 1d
mode: manual
risk: high
```

---

## 四、Phase 1 — Unity adapter 完整 + login MVP（详写）

> 出口标准：login MVP case 在 Unity 完整闭环跑通；故意破坏验证升级到防护 0.2 源码层。

### Group A: Unity adapter — UI 反射完整化

---

### TASK-0100: UGUI 完整字段 dump

```yaml
title: UGuiReflector 实现 visual + behavior + meta 三类完整字段
phase: 1
engine: unity
depends_on: [TASK-0007]
goal: 让 dump_tree 输出符合 protocol/schema/node.json 的完整节点
output:
  - adapters/unity/Runtime/Reflection/UGuiReflector.cs (扩展)
  - adapters/unity/Runtime/Reflection/NodeSerializer.cs (visual/behavior/meta serializer)
  - adapters/unity/Tests/Runtime/NodeSerializerTests.cs
verification:
  - PlayMode 测试: dump 输出通过 protocol/schema/node.json JSON Schema 验证
  - 测试: visible / alpha / color / sprite_ref / interactable / event_handlers 全字段非空
effort: 1d
mode: auto-with-review
risk: low
```

---

### TASK-0101: StableIdComponent + IdAllocator 实现

```yaml
title: Unity StableIdComponent + 自动 hash + pinned 优先
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 实现 stable ID 三种来源 (pinned / auto-hash / fallback)
output:
  - adapters/unity/Runtime/Meta/StableIdComponent.cs (MonoBehaviour + serialized fields)
  - adapters/unity/Runtime/Meta/IdAllocator.cs (启动时遍历, hash 算法)
  - adapters/unity/Tests/Runtime/IdAllocatorTests.cs
verification:
  - 测试: 已 pin 节点 stable_id_source = "pinned"
  - 测试: 未 pin 节点 stable_id_source = "hash"
  - 测试: hash ID 在重复 name 时加序号后缀
  - 测试: pin 后场景重启 ID 仍稳定
effort: 1d
mode: auto-with-review
risk: low
```

---

### TASK-0102: Unity Editor Inspector for Pin ID

```yaml
title: StableIdInspector — Pin ID 编辑器 UI
phase: 1
engine: unity
depends_on: [TASK-0101]
goal: 美术 / 程序员能在 Unity Inspector 里 pin ID
output:
  - adapters/unity/Editor/AutoAgent.Editor.asmdef
  - adapters/unity/Editor/StableIdInspector.cs (CustomEditor for StableIdComponent)
  - adapters/unity/Editor/Tests/StableIdInspectorTests.cs
verification:
  - 在 Editor 里挂 StableIdComponent → Inspector 显示 Pin ID / Role / Intent / Tags 输入框
  - 输入 + apply → SerializeField 持久化
  - EditorTest 验证字段写入
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0103: OrphanTracker

```yaml
title: OrphanTracker — 持久化上次 dump ID 列表 + 当前 diff
phase: 1
engine: unity
depends_on: [TASK-0101]
goal: 实现 list_orphan_ids 功能
output:
  - adapters/unity/Runtime/Meta/OrphanTracker.cs
  - 持久化文件: Library/AutoAgent/last_scan.json (gitignore)
  - adapters/unity/Tests/Runtime/OrphanTrackerTests.cs
verification:
  - 测试: 第一次 dump → 无 orphan
  - 测试: pin 一个节点, 重启, dump → 该节点 found
  - 测试: 删除一个节点, 重启, dump → 该节点 in orphans
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0104: link.xml + IL2CPP 验证

```yaml
title: IL2CPP link.xml 模板 + IL2CPP build 验证
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 保证 IL2CPP build 反射不被裁
output:
  - adapters/unity/Runtime/Resources/AutoAgent.link.xml
  - docs/users/il2cpp-setup.md (用户业务代码 link.xml 指南)
  - .github/workflows/unity-pr.yml (扩展, 加 IL2CPP build job)
verification:
  - CI: Mono build pass + IL2CPP build pass
  - IL2CPP 包跑 PocPlaygroundScene 4 动作全部成功
  - 包大小增量 < 5MB
effort: 1d
mode: auto-with-review
risk: medium
```

---

### Group B: Unity adapter — 输入注入完整

---

### TASK-0105: EngineInputDriver — click 完整实现

```yaml
title: Click 模拟完整: PointerDown → Up → Click 序列
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 引擎事件层 click 在所有 Selectable 子类工作（含 AI AddComponent 后挂上的 Button/Toggle/...）
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (Click 实现完整)
  - adapters/unity/Tests/Runtime/ClickTests.cs
verification:
  - 测试 setup: 在测试 GameObject 上代码 AddComponent<Button> / AddComponent<Toggle>（模拟 AI 业务代码做的事）
  - 测试: Click → Button.onClick 触发
  - 测试: Click → Toggle.onValueChanged 触发
  - 测试: 节点未 AddComponent<Selectable> 子类 → 抛 -32002 WidgetNotInteractable + 错误消息含 "AddComponent" 提示
  - 测试: 不可交互 widget (interactable=false) 抛 -32002
  - 测试: 父链 CanvasGroup interactable=false 时也抛 -32002
effort: 1d
mode: auto-with-review
risk: low
```

---

### TASK-0106: EngineInputDriver — send_text

```yaml
title: send_text — TMP_InputField + 旧 InputField 兼容
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 send_text + clear_first（要求节点已 AddComponent<TMP_InputField> 或 <InputField>）
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (SendText 方法)
  - adapters/unity/Tests/Runtime/SendTextTests.cs
verification:
  - 测试 setup: 测试 GameObject 上 AddComponent<TMP_InputField>
  - 测试: TMP_InputField 设值 + onValueChanged 触发
  - 测试: 旧 InputField 设值 + onValueChanged 触发
  - 测试: clear_first=true 清空旧值
  - 测试: 节点未 AddComponent input field → 抛 WidgetNotInteractable + 错误消息含 "AddComponent<TMP_InputField>" 提示
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0107: EngineInputDriver — drag 多帧序列

```yaml
title: Drag — OnBeginDrag → 多帧 OnDrag → OnEndDrag → OnDrop coroutine
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 drag, 分帧避免单帧 IDragHandler 实现出问题
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (Drag 实现)
  - adapters/unity/Tests/Runtime/DragTests.cs
verification:
  - 测试: drag_source → drag_target, IDropHandler 触发
  - 测试: duration_ms 分帧数正确（默认 200ms ≈ 12 frames @ 60fps）
  - 测试: 中途 from 节点消失正确报错
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0108: EngineInputDriver — scroll

```yaml
title: Scroll — ScrollRect 滚动（要求节点已 AddComponent<ScrollRect> + <RectMask2D>）
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 scroll
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (Scroll 实现)
  - adapters/unity/Tests/Runtime/ScrollTests.cs
verification:
  - 测试 setup: 测试代码 AddComponent<ScrollRect> + <RectMask2D> + 填充 30 Image item
  - 测试: scroll down 100 → ScrollRect.normalizedPosition 正确变化
  - 测试: 滚动后某 item 进入视口
  - 测试: 节点未 AddComponent<ScrollRect> → 抛 WidgetNotInteractable
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0109: EngineInputDriver — key_press

```yaml
title: Key press — Unity Input 事件 + EventSystem 转发
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 key_press
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (KeyPress 实现)
  - adapters/unity/Tests/Runtime/KeyPressTests.cs
verification:
  - 测试: 按 Enter → InputField.onSubmit 触发 (聚焦时)
  - 测试: 按 Tab → 焦点切换
effort: 4h
mode: auto-with-review
risk: low
```

---

### Group C: 截图 + wait

---

### TASK-0110: ScreenshotCapturer

```yaml
title: ScreenshotCapturer — fullscreen / node / rect 三模式
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 实现 take_screenshot
output:
  - adapters/unity/Runtime/Screenshot/ScreenshotCapturer.cs
  - adapters/unity/Tests/Runtime/ScreenshotTests.cs
verification:
  - 测试: fullscreen 截图非空 (非黑屏)
  - 测试: node 模式截单个节点 bounds 正确
  - 测试: rect 模式截指定矩形
  - 输出 PNG / JPG 都正确
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0111: wait_for

```yaml
title: wait_for — widget_appeared / disappeared / visible / text_changed
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 实现 wait_for 条件等待
output:
  - adapters/unity/Runtime/Server/WaitConditions.cs
  - adapters/unity/Tests/Runtime/WaitForTests.cs
verification:
  - 测试: widget_appeared 等到节点可见
  - 测试: text_changed 等到文本变化
  - 测试: 超时返回 -32005 TimeoutError
effort: 4h
mode: auto-with-review
risk: low
```

---

### Group D: 协议完整

---

### TASK-0112: 完整协议 method 路由

```yaml
title: ProtocolHandler — JSON-RPC dispatcher 完整版
phase: 1
engine: unity
depends_on: [TASK-0100, TASK-0105, TASK-0110, TASK-0111]
goal: 路由所有 wire protocol method 到对应实现
output:
  - adapters/unity/Runtime/Server/JsonRpcDispatcher.cs
  - adapters/unity/Runtime/Server/ProtocolHandler.cs (完整路由)
  - adapters/unity/Tests/Runtime/DispatcherTests.cs
verification:
  - 测试: 全部 wire method (dump_tree / find_widget / get_widget / click / send_text / drag / scroll / key_press / take_screenshot / wait_for / pin_id / list_orphan_ids / get_engine_info) 路由正确
  - 测试: 未知 method → -32601 MethodNotFound
  - 测试: invalid params → -32602 InvalidParams
effort: 1d
mode: auto-with-review
risk: low
```

---

### TASK-0113: 完整错误码 + GameThread marshaling

```yaml
title: 错误码完整 + 跨线程调用引擎 API marshal 到主线程
phase: 1
engine: unity
depends_on: [TASK-0112]
goal: 所有 error codes (01 §六) 实现; WebSocket 线程消息 marshal 到 main thread
output:
  - adapters/unity/Runtime/Server/MainThreadDispatcher.cs
  - adapters/unity/Runtime/Server/ErrorCodes.cs
  - adapters/unity/Tests/Runtime/ThreadMarshallingTests.cs
verification:
  - 测试: WebSocket 线程发消息, 引擎 API 调用全部在 main thread
  - 测试: 所有错误码都有 enum + 测试覆盖
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0114: 事件流 emit

```yaml
title: 事件 notification — scene_changed / widget_appeared / disappeared / clicked / text_changed
phase: 1
engine: unity
depends_on: [TASK-0112]
goal: 实现事件流推送
output:
  - adapters/unity/Runtime/Server/EventEmitter.cs
  - adapters/unity/Runtime/Reflection/SceneChangeWatcher.cs
  - adapters/unity/Runtime/Reflection/WidgetLifecycleWatcher.cs
  - adapters/unity/Tests/Runtime/EventStreamTests.cs
verification:
  - 测试: 切场景 → scene_changed 推送
  - 测试: 新节点出现 → widget_appeared 推送
  - 测试: 输入框文本变化 → text_changed 推送
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0115: invoke_method / get_property / set_property + 视觉写拒绝

```yaml
title: 高级反射 method 实现 + 视觉写入拒绝
phase: 1
engine: unity
depends_on: [TASK-0112]
goal: 实现 invoke_method / get_property / set_property; visual 字段写入抛 -32003
output:
  - adapters/unity/Runtime/Reflection/ScriptInvoker.cs
  - adapters/unity/Runtime/Reflection/PropertyAccessor.cs (含 category 校验)
  - adapters/unity/Tests/Runtime/PropertyAccessorTests.cs
verification:
  - 测试: invoke_method 调用 MonoBehaviour 公开方法成功
  - 测试: get_property 读 behavior 字段成功
  - 测试: set_property category=behavior → 成功
  - 测试: set_property category=visual → 抛 -32003 VisualPropertyWrite
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0116: pin_id / list_orphan_ids wire 实现

```yaml
title: pin_id / list_orphan_ids wire method 实现
phase: 1
engine: unity
depends_on: [TASK-0103, TASK-0112]
goal: 暴露 pin / orphan 功能给 wire protocol
output:
  - adapters/unity/Runtime/Meta/PinIdHandler.cs
  - adapters/unity/Tests/Runtime/PinIdTests.cs
verification:
  - 测试: pin_id 调用后, 重新 dump 该节点 stable_id_source = "pinned"
  - 测试: list_orphan_ids 返回正确 orphan 列表
effort: 4h
mode: auto-with-review
risk: low
```

---

### Group E: MCP Server 完整

---

### TASK-0117: MCP tool 完整实现 — wire dispatcher

```yaml
title: MCP tools 全部连真实 wire protocol (不再 dummy)
phase: 1
engine: none
depends_on: [TASK-0002, TASK-0112]
goal: 12 个 MCP tools 全部实现, 调用 wire method
output:
  - mcp-server/src/autoagent_mcp/connector/websocket_client.py
  - mcp-server/src/autoagent_mcp/tools/dump.py / click.py / text.py / etc.
  - mcp-server/tests/test_tools.py (mock adapter 跑全部 tool)
verification:
  - pytest mcp-server/tests/test_tools.py -v 全绿
  - 用 fake adapter 跑通 12 core MVP tools + 5 aux tools（共 17 个，见 [02 §三 分组](02-mcp-server.md)）
effort: 2d
mode: auto-with-review
risk: medium
```

---

### TASK-0118: connect_engine / disconnect / session 管理

```yaml
title: Session 管理 — 单连接 + heartbeat + 重连
phase: 1
engine: none
depends_on: [TASK-0117]
goal: MCP server 连 adapter 的 session lifecycle
output:
  - mcp-server/src/autoagent_mcp/connector/session.py
  - mcp-server/src/autoagent_mcp/connector/heartbeat.py
  - mcp-server/tests/test_session.py
verification:
  - 测试: connect_engine 成功后 heartbeat 30s 一次
  - 测试: 连接断开 → 自动重连 5 次退避
  - 测试: 5 次重连失败 → 返回 ConnectionError
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0119: 自动重连 + 错误处理

```yaml
title: 错误透传 + adapter 崩溃恢复
phase: 1
engine: none
depends_on: [TASK-0118]
goal: adapter 错误透传给 AI; adapter 崩溃返回 EngineDisconnected
output:
  - mcp-server/src/autoagent_mcp/connector/error_handler.py
  - mcp-server/tests/test_error_recovery.py
verification:
  - 测试: adapter 返回 -32001 → MCP tool 返回结构化 error
  - 测试: adapter 进程 kill → 下一个 tool call 返回 EngineDisconnected
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0120: 日志规范实现

```yaml
title: 结构化 JSON 日志 + 文件 rotate
phase: 1
engine: none
depends_on: [TASK-0117]
goal: 实现 02-mcp-server.md §六 日志规范
output:
  - mcp-server/src/autoagent_mcp/logging.py
  - mcp-server/tests/test_logging.py
verification:
  - 测试: 每个 tool call 生成 JSON 日志
  - 测试: 文件 rotate 50MB × 5
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0121: 配置文件加载

```yaml
title: ~/.autoagent/config.toml 加载 + 校验
phase: 1
engine: none
depends_on: [TASK-0117]
goal: 实现 02-mcp-server.md §七 配置加载
output:
  - mcp-server/src/autoagent_mcp/config.py
  - mcp-server/tests/test_config.py
verification:
  - 测试: 默认配置加载 ok
  - 测试: 用户覆盖配置正确合并
  - 测试: 非法配置抛 ValidationError
effort: 4h
mode: auto-with-review
risk: low
```

---

### Group F: 视觉回归实现

---

### TASK-0122: SSIM 实现

```yaml
title: scikit-image SSIM 视觉对比
phase: 1
engine: none
depends_on: [TASK-0117]
goal: 实现 SSIM diff (MVP, 不含 LPIPS)
output:
  - mcp-server/src/autoagent_mcp/vision/comparator.py
  - mcp-server/src/autoagent_mcp/vision/diff_image.py (生成 diff 图)
  - mcp-server/tests/test_vision_ssim.py
verification:
  - 测试: 同图 SSIM = 1.0
  - 测试: 已知 95% similar 图 SSIM ≥ 0.95
  - 测试: 完全不同图 SSIM < 0.5
  - LPIPS 关键字检查不存在 (MVP 不含)
effort: 1d
mode: auto-with-review
risk: low
```

---

### TASK-0123: compare_to_baseline tool

```yaml
title: MCP tool compare_to_baseline 实现
phase: 1
engine: none
depends_on: [TASK-0122]
goal: 暴露视觉对比给 AI
output:
  - mcp-server/src/autoagent_mcp/tools/vision.py
  - mcp-server/tests/test_compare_tool.py
verification:
  - 测试: 同图返回 pass=true, score≈1.0
  - 测试: 阈值 0.95 以下返回 pass=false 且生成 diff_path
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0124: take_screenshot tool 端到端

```yaml
title: MCP take_screenshot 串到 adapter
phase: 1
engine: unity
depends_on: [TASK-0110, TASK-0117]
goal: AI 端能调 take_screenshot 拿到引擎截图文件
output:
  - mcp-server/src/autoagent_mcp/tools/screenshot.py
  - mcp-server/tests/integration/test_take_screenshot.py
verification:
  - 集成测试: 起 Unity adapter mock, MCP 端调用 → 拿到 PNG 文件
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0125: audit_visual_changes tool — dump diff

```yaml
title: MCP audit_visual_changes — 缓存 dump + diff visual 字段
phase: 1
engine: none
depends_on: [TASK-0117]
goal: AI 自检"我有没有不小心改了视觉" (运行时, 与 防护 0.3 配合)
output:
  - mcp-server/src/autoagent_mcp/tools/audit.py
  - mcp-server/src/autoagent_mcp/state/dump_cache.py
  - mcp-server/tests/test_audit_tool.py
verification:
  - 测试: 两次 dump 一致 → 无 diff
  - 测试: visual 字段变化 → 列出节点 + 字段
effort: 4h
mode: auto-with-review
risk: low
```

---

### TASK-0126: Claude Vision 二次裁决（可选）

```yaml
title: SSIM 报警时调 Claude Vision 二次裁决
phase: 1
engine: none
depends_on: [TASK-0122, TASK-0121]
goal: 实现 06 §5.5 LLM 二次裁决
output:
  - mcp-server/src/autoagent_mcp/vision/llm_judge.py
  - mcp-server/tests/test_llm_judge.py (mock Anthropic API)
verification:
  - 测试: ssim ≥ 0.95 → 跳过 LLM
  - 测试: ssim < 0.92 → 调用 LLM 返回 verdict + reason
  - max_diff_per_session 上限生效
effort: 1d
mode: auto-with-review
risk: medium
```

---

### Group G: AI Operating Contract 实施

---

### TASK-0127: 路径白名单 yml 完整规则

```yaml
title: scripts/ci/path_whitelist.yml 完整规则 (07 §3.2)
phase: 1
engine: none
depends_on: [TASK-0003]
goal: path_whitelist.yml 完全对齐 07-agent-operations.md §3.2
output:
  - scripts/ci/path_whitelist.yml (完整版)
  - scripts/ci/check_changed_paths.py (扩展支持 path_exception field from PR body)
  - scripts/ci/tests/test_check_paths_full.py
verification:
  - 全部 ✅ / ❌ 路径用例覆盖
  - PR body 含 path_exception YAML 时正确豁免
effort: 4h
mode: auto-with-review
risk: medium
```

---

### TASK-0128: 源码 diff 审计完整规则 (Unity C#)

```yaml
title: visual_write_rules.yml — Unity C# 完整禁字段
phase: 1
engine: none
depends_on: [TASK-0004]
goal: visual_write_rules.yml 覆盖 06 §2.2 全部 Unity 禁字段
output:
  - scripts/ci/visual_write_rules.yml (Unity 部分完整)
  - scripts/ci/audit_visual_writes.py (扩展 Roslyn AST 选项, 仍以 regex 默认)
  - scripts/ci/tests/test_audit_unity_full.py (覆盖 transform / rectTransform / color / sprite / SetActive 全部)
verification:
  - pytest 全绿
  - 抓得到 image.color =, transform.position =, rt.anchoredPosition =, SetActive(false), .enabled = (Image)
  - AUTOAGENT_ALLOW_VISUAL 注释豁免生效
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0129: AI agent CLI 工具

```yaml
title: autoagent CLI — start / stop / reset / status
phase: 1
engine: none
depends_on: [TASK-0121]
goal: 实现 07 §8 紧急停机 + §9 人工恢复用 CLI
output:
  - mcp-server/src/autoagent_mcp/cli.py (扩展)
    - autoagent-start --task / --resume
    - autoagent-stop
    - autoagent-reset --session / --global
    - autoagent-status
  - mcp-server/tests/test_cli.py
verification:
  - autoagent-stop 写 ~/.autoagent/STOP 文件
  - autoagent-status 显示当前 session 状态
  - autoagent-reset --session 清 session counter
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0130: Cost tracking + daily report

```yaml
title: Cost tracking — Anthropic API 用量计 + EOD 报告
phase: 1
engine: none
depends_on: [TASK-0120]
goal: 实现 07 §2.2 / §7.1 cost tracking
output:
  - mcp-server/src/autoagent_mcp/cost_tracker.py
  - mcp-server/src/autoagent_mcp/cli.py (cost 子命令)
  - 输出: ~/.autoagent/cost-daily.csv
verification:
  - 测试: 模拟 token 用量, cost 计算正确
  - 测试: session 上限 $50 触达 → session 停
  - 测试: global 上限 $200 触达 → 全局停
effort: 1d
mode: auto-with-review
risk: medium
```

---

### Group H: Login MVP 验收

---

### TASK-0131: Login fixture 程序员准备（手动确认）

```yaml
title: TASK-0008 的 LoginScene 完整性确认（视觉骨架 + logical_role + state_sprites）
phase: 1
engine: unity
depends_on: [TASK-0008]
goal: 确认 LoginScene 满足 MVP 验收要求；fixture 完全不含交互控件
output:
  - 在 LoginScene 里所有元素都 pin ID + LogicalRole：
    - login_panel (image_only)
    - account_input_bg (input) + 子 account_input_text (text_display)
    - password_input_bg (input) + 子 password_input_text (text_display)
    - login_button_bg (button) + 子 login_button_label (text_display)
    - error_label (text_display)
    - welcome_panel (image_only)
    - welcome_text (text_display)
  - login_button_bg 设 state_sprites (normal/hover/pressed/disabled)
  - account_input_bg / password_input_bg 设 state_sprites (normal/focused)
  - WelcomePanel 初始 inactive
  - ErrorLabel 初始 empty
  - 截图 baselines/unity/windows/login_screen.png 通过 review（视觉骨架的 normal 态）
verification:
  - 手动 PlayMode → 看起来正确，所有 UI 不响应任何输入（视觉骨架的预期行为）
  - dump_tree 输出 ≥ 7 个 pinned ID 且每个 LogicalRole 非空（除 image_only 节点）
  - dump_tree 输出的 type 字段：所有非容器节点都是 Image / TMP_Text（无 Button / TMP_InputField）
  - behavior.attached_components 字段在所有节点上为空数组（fixture 阶段还没 AI 代码）
effort: 3h
mode: manual
risk: low
path_exception: ["fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"]
```

---

### TASK-0132: AI Agent 实现 LoginController.cs (autonomous loop 真实试运行)

```yaml
title: MVP 任务 — AI 写 LoginController 实现登录交互（含 AddComponent 控件）
phase: 1
engine: unity
depends_on: [TASK-0117, TASK-0118, TASK-0119, TASK-0120, TASK-0121, TASK-0122, TASK-0123, TASK-0124, TASK-0125, TASK-0126, TASK-0127, TASK-0128, TASK-0129, TASK-0130, TASK-0131]
goal: 给 Claude Code 任务 DSL, autonomous loop 实现 login 功能。AI 必须在源码里 AddComponent 引擎控件，fixture 阶段视觉骨架无控件
output:
  - fixtures/unity-test-project/Scripts/LoginController.cs (AI 实现)
    Awake() 里:
      - account_input_bg.gameObject.AddComponent<TMP_InputField>() + 设 textComponent 指向子 account_input_text + caretWidth 等
      - password_input_bg.gameObject.AddComponent<TMP_InputField>() + contentType=Password
      - login_button_bg.gameObject.AddComponent<Button>() + AddListener(OnLoginClicked)
      - 三个节点 raycastTarget=true (behavior 字段，合法)
      - 配合 StableIdComponent.StateSprites 设置 Button.spriteState / InputField focused 状态切换
  - fixtures/unity-test-project/Scripts/MockApi.cs (AI 实现 mock POST /login)
  - fixtures/unity-test-project/Scripts/Tests/LoginControllerTests.cs (AI 写测试)
  - 任务 DSL: docs/canonical-tasks/login.yaml (人工写, 给 AI 输入)
verification:
  - 任务 DSL 按 logical_role 引用节点（如 "the input field with id account_input_bg, logical_role=input"）
  - 源码 diff 审计通过（防护 0.2，含 §2.5 logical_role 实现豁免）
  - dump_before vs dump_after：
    - visual 字段完全一致
    - after 中 account_input_bg / password_input_bg 的 behavior.attached_components 包含 TMP_InputField
    - after 中 login_button_bg 的 behavior.attached_components 包含 Button
    - 所有 pinned_id 都还在
  - AI 在 ≤ 5 iterations 内完成
  - 单元测试: 输入 valid 触发 mock API, 调用次数正确
  - e2e: send_text → click → mock 收到 POST → welcome_text 出现
  - PR 自动 open + 全部 CI step 绿
effort: 2d (AI iterating; 用户监督)
mode: auto-with-review
risk: high
max_iterations: 5
```

**Context**：这是 Phase 1 真正的"AI 自动化"试运行。前面所有任务都是为这一刻铺路。重点观察 AI 在"fixture 没有任何控件" + "logical_role 取值表 + state_sprites 已声明"的语境下，能否正确 AddComponent 实现交互。

---

### TASK-0133: e2e 测试 — login 流程

```yaml
title: e2e — Unity headless 跑 login 完整流程
phase: 1
engine: unity
depends_on: [TASK-0132]
goal: CI 端到端跑 login 验证
output:
  - fixtures/unity-test-project/Scripts/Tests/E2ELoginRunner.cs
  - scripts/e2e/unity_login.sh (启动 headless Unity + 跑 e2e + 检查日志)
verification:
  - bash scripts/e2e/unity_login.sh 退出码 0
  - 日志包含: send_text 成功 / click 成功 / mock API 收到 POST / welcome_text 显示
effort: 1d
mode: auto-with-review
risk: medium
```

---

### TASK-0134: 视觉回归 baseline + 比对

```yaml
title: Login 视觉回归 — 先创建 welcome_screen baseline 再做 compare 全流程
phase: 1
engine: unity
depends_on: [TASK-0133, TASK-0123, TASK-0132]
goal: |
  分两步:
  (1) 在 TASK-0132 实现的 LoginController 跑通后, take_screenshot 拿到 welcome_panel 状态 →
      人工 review → commit 为 baselines/unity/windows/welcome_screen.png (TASK-0014 只拍了 fixture 视觉骨架初始态, 不含 welcome state)
  (2) e2e 跑完后自动 take_screenshot + compare_to_baseline, 验证 login_screen + welcome_screen 两张都 SSIM ≥ 0.95
output:
  - fixtures/unity-test-project/Scripts/Tests/E2ELoginRunner.cs (扩展)
  - 在 e2e 里 take_screenshot login_panel + welcome_panel 两张
  - baselines/unity/windows/welcome_screen.png + .meta.json (本任务首次创建, 人工 approve)
  - 比对 baselines/unity/windows/login_screen.png (已存在, TASK-0014 产出) + welcome_screen.png (本任务产出)
verification:
  - 步骤 (1): welcome_screen.png 人工 review approve, commit 走 path_exception
  - 步骤 (2): SSIM ≥ 0.95 → CI green
  - 故意改 fixture LoginScene (path exception PR) 让视觉变化 → SSIM < 0.92 → CI fail + diff 图生成
effort: 6h (含 baseline 创建 + review + 回归实现)
mode: auto-with-review
risk: high  # 涉及 baseline 创建 ([07 §2.1] baseline 任务 max_iterations=1)
max_iterations: 1
path_exception: ["baselines/unity/windows/welcome_screen.png", "baselines/unity/windows/welcome_screen.meta.json"]
```

**Context**：TASK-0014 在 Phase 0 只能产出"fixture 视觉骨架初始态"的 baseline（welcome_panel 此时 inactive，截不到）。welcome_screen baseline 必须等 TASK-0132 AI 实现登录交互后才能截到，所以 Phase 1 末由本任务**首次创建**。任何其他用户态截图同理：**baseline 在第一个能复现该状态的任务里创建，不是在 fixture 准备阶段创建**。

---

### TASK-0135: Phase 1 出口 gate review（手动）

```yaml
title: Phase 1 出口 review — login MVP + 5 道防护
phase: 1
engine: unity
depends_on: [TASK-0132, TASK-0133, TASK-0134, TASK-0128]
goal: 人工签发 Phase 1 完成
output:
  - docs/phase1-gate-report.md
verification:
  - Gate 1: TASK-0132 完整 autonomous loop (AI 自己写代码 + 自己跑 CI + 自己修 + PR)
  - Gate 2: 故意推 PR 在 LoginController.cs 写 image.color = ... → 防护 0.2 拦下
  - Gate 3: 故意推 PR 改 LoginScene.unity → 防护 0.1 拦下
  - Gate 4: dump 前后 visual diff gate 拦下故意 visual 写入 → 防护 0.3 验证
  - Gate 5: SSIM 视觉回归通过 (login + welcome 截图)
  - Gate 6: AI 全程不需要人工敲键盘 (除 review/approve PR)
  - 任意一项 fail → Phase 2 不启动
effort: 1d
mode: manual
risk: high
```

---

## 五、Phase 2 — UE adapter 完整 + 跨引擎一致（anchor）

> Phase 2 启动前 (Phase 1 完成后) 必须重新拆 anchor 为 PR-sized task。下面是 anchor 列表。

---

### TASK-0200: UE — UI 树遍历完整实现 (anchor)

```yaml
title: UE UMG 树遍历完整 (从 RootWidget 单一递归)
phase: 2
engine: unreal
depends_on: [TASK-0011, TASK-0135]
status: anchor
goal: 实现 04-adapter-unreal.md §三的完整版遍历
includes:
  - WalkChildren 完整实现 (含 NamedSlot / 自定义容器)
  - NoDuplicateNodes / ParentChildConsistent 单元测试
  - 完整 NodeData 字段映射 (visual / behavior / meta)
  - Slate 原生 SWidget 支持 (Phase 2 末)
effort_estimate: 5d
risk: high
```

---

### TASK-0201: UE — Stable ID Resolver (anchor)

```yaml
title: FStableIdResolver — UPROPERTY meta + ini + runtime register
phase: 2
engine: unreal
depends_on: [TASK-0200]
status: anchor
goal: 实现 04 §六完整 StableIdResolver
includes:
  - LoadFromPropertyMeta 实现 (反射所有 UClass 的 UPROPERTY meta)
  - LoadFromIniRegistry 实现 (Config/AutoAgentIds.ini)
  - RegisterRuntime API
  - Hash ID 算法 (诊断用)
  - 单元测试: 三种来源优先级正确
effort_estimate: 4d
risk: medium
```

---

### TASK-0202: UE — Slate 输入注入 (anchor)

```yaml
title: SlateInputDriver — click/text/drag/scroll 完整 + GameThread marshal
phase: 2
engine: unreal
depends_on: [TASK-0200]
status: anchor
goal: 实现完整的 4 动作 + 跨线程安全
includes:
  - Click (FSlateApplication::ProcessMouseButtonDownEvent)
  - SendText (ProcessKeyCharEvent 逐字符)
  - Drag (多帧 OnMouseMove + OnMouseUp)
  - Scroll (FSlateApplication::OnMouseWheel)
  - GameThread marshal (FFunctionGraphTask)
  - Modal widget / SetUserFocus 处理
effort_estimate: 1w
risk: high
```

---

### TASK-0203: UE — uWebSockets 集成 + subprotocol (anchor)

```yaml
title: uWS server 嵌入 UE plugin + subprotocol 校验
phase: 2
engine: unreal
depends_on: [TASK-0011]
status: anchor
goal: 完整 WebSocket server (RTTI 适配, ThirdParty 静态库)
includes:
  - uWS 作为 ThirdParty 静态库集成
  - 处理 RTTI / exception 配置
  - subprotocol 校验 + negotiate_version
  - GameThread queue (TQueue Mpsc)
  - 单元测试: 100 并发 connections 不崩
effort_estimate: 4d
risk: high
```

---

### TASK-0204: UE — Packaged build 兼容 (anchor)

```yaml
title: Shipping / Development packaged build 跑 adapter
phase: 2
engine: unreal
depends_on: [TASK-0200, TASK-0201, TASK-0202, TASK-0203]
status: anchor
goal: 验证 04 §七 packaged build 兼容性
includes:
  - AUTOAGENT_ENABLED 编译宏
  - Cooked 资源 reference 适配 (sprite_ref path 差异)
  - Shipping build size 增量 < 5MB
  - Hot reload 后 adapter 自动重启
effort_estimate: 3d
risk: high
```

---

### TASK-0205: UE — Editor module (Pin ID Detail Customization) (anchor)

```yaml
title: AutoAgentEditor module — Pin ID UI in Detail Panel
phase: 2
engine: unreal
depends_on: [TASK-0201]
status: anchor
goal: 04 §六 Editor 工具
includes:
  - BindWidget Property Detail Customization
  - AutoAgentIds.ini visual editor
  - 未 pin 节点 scanner
effort_estimate: 4d
risk: medium
```

---

### TASK-0206: UE 视觉回归集成 (anchor)

```yaml
title: UE Screenshot Comparison Tool 接入框架视觉回归
phase: 2
engine: unreal
depends_on: [TASK-0204]
status: anchor
goal: 让 06 §5.1 在 UE 跑通
includes:
  - Functional Screenshot Test Actor 集成
  - Saved/Automation/Comparisons → 框架 baseline 目录映射
  - 跨引擎 baseline 隔离 (windows 子目录)
effort_estimate: 3d
risk: medium
```

---

### TASK-0207: UE 故意破坏验证 (anchor)

```yaml
title: 防护 0.1 + 0.2 在 UE 故意触发验证
phase: 2
engine: unreal
depends_on: [TASK-0204]
status: anchor
goal: 镜像 TASK-0015 + TASK-0016 到 UE
includes:
  - 故意推 .uasset 修改 → CI fail
  - 故意推 SetVisibility(...) → CI fail
  - AUTOAGENT_ALLOW_VISUAL 注释豁免验证
effort_estimate: 2d
risk: medium
```

---

### TASK-0208: UE Login fixture 准备 (manual)

```yaml
title: UE LoginMap + ULoginUserWidget C++ class
phase: 2
engine: unreal
depends_on: [TASK-0012]
status: anchor
goal: UE 侧的 login fixture 完整可用
includes:
  - ULoginUserWidget.h 含全部 UPROPERTY meta=(AutoAgentId=...)
  - LoginMap.umap GameMode 自动 CreateWidget
  - Welcome 隐藏初始
effort_estimate: 1d
mode: manual
risk: low
```

---

### TASK-0209: UE Login MVP — AI 实现 (anchor)

```yaml
title: AI 在 UE 实现 ULoginController (镜像 TASK-0132)
phase: 2
engine: unreal
depends_on: [TASK-0200, TASK-0201, TASK-0202, TASK-0203, TASK-0204, TASK-0205, TASK-0206, TASK-0207, TASK-0208]
status: anchor
goal: 同一份 task DSL 在 UE 跑通
includes:
  - 复用 docs/canonical-tasks/login.yaml (engine 字段切 unreal)
  - AI 写 ULoginController + UMockApi
  - autonomous loop 完整闭环
effort_estimate: 3d
risk: high
max_iterations: 5
```

---

### TASK-0210: UE login MVP — e2e + 跨引擎一致性 (anchor)

```yaml
title: UE e2e + 跨 Unity/UE 行为一致性比对
phase: 2
engine: unreal
depends_on: [TASK-0209]
status: anchor
goal: 验证同任务 DSL 在两引擎产出相同行为
includes:
  - UE e2e 跑 login (UE Automation Framework)
  - 视觉回归通过
  - 行为 trace 对比 Unity (相同事件流序列)
effort_estimate: 2d
risk: medium
```

---

### TASK-0211: Phase 2 出口 gate review (manual)

```yaml
title: Phase 2 完成 review
phase: 2
engine: unreal
depends_on: [TASK-0210]
status: anchor
goal: 人工签发 Phase 3 启动
includes:
  - 所有 Phase 2 task merged
  - login MVP 跨 Unity / UE 一致
  - 5 道防护在 UE 全部生效
  - Self-hosted runner 稳定 (无超时 / OOM)
effort_estimate: 1d
mode: manual
risk: high
```

---

## 六、Phase 3 — Godot adapter 完整（anchor）

---

### TASK-0300: Godot — UI 树反射完整 (anchor)

```yaml
title: ControlReflector 完整 (含 release export ClassDB cache)
phase: 3
engine: godot
depends_on: [TASK-0009, TASK-0211]
status: anchor
includes:
  - 全字段 dump 符合 schema
  - ClassDB cache 构建脚本 (build-time)
  - release export 反射 self-check
effort_estimate: 4d
risk: medium
```

---

### TASK-0301: Godot — Stable ID (anchor)

```yaml
title: set_meta 持久化 + Inspector pin
phase: 3
engine: godot
depends_on: [TASK-0300]
status: anchor
includes:
  - set_meta API 封装
  - Editor Plugin Inspector 扩展
  - Hash ID fallback
effort_estimate: 2d
risk: low
```

---

### TASK-0302: Godot — Input driver (anchor)

```yaml
title: parse_input_event — click/text/drag/scroll
phase: 3
engine: godot
depends_on: [TASK-0300]
status: anchor
includes:
  - mouse_filter 检查
  - LineEdit text input
  - Drag 多帧
effort_estimate: 4d
risk: medium
```

---

### TASK-0303: Godot — TCPServer + WebSocketPeer (anchor)

```yaml
title: 完整 WebSocket server + subprotocol
phase: 3
engine: godot
depends_on: [TASK-0009]
status: anchor
includes:
  - TCPServer accept loop
  - WebSocketPeer.accept_stream + supported_protocols
  - selected_protocol 校验
  - poll 调度
effort_estimate: 3d
risk: medium
```

---

### TASK-0304: Godot — Release export 反射缺口对策 (anchor)

```yaml
title: ClassDB cache 自维护 + self-check
phase: 3
engine: godot
depends_on: [TASK-0300]
status: anchor
includes:
  - build-time scanner 生成 class_db_cache.gd
  - 运行时优先查 cache
  - release self-check 脚本
effort_estimate: 3d
risk: high
```

---

### TASK-0305: Godot — Editor plugin (anchor)

```yaml
title: Pin ID inspector + 未 pin scanner
phase: 3
engine: godot
depends_on: [TASK-0301]
status: anchor
effort_estimate: 2d
risk: low
```

---

### TASK-0306: Godot 视觉回归集成 (anchor)

```yaml
title: Image.compute_image_metrics 接入 + baseline
phase: 3
engine: godot
depends_on: [TASK-0303]
status: anchor
includes:
  - take_screenshot via Viewport.get_texture()
  - 框架 vision diff 集成
effort_estimate: 2d
risk: low
```

---

### TASK-0307: Godot login fixture (manual)

```yaml
title: login.tscn 完整化
phase: 3
engine: godot
depends_on: [TASK-0010]
status: anchor
mode: manual
effort_estimate: 4h
risk: low
```

---

### TASK-0308: Godot login MVP — AI 实现 (anchor)

```yaml
title: 同任务 DSL 在 Godot 跑通
phase: 3
engine: godot
depends_on: [TASK-0300, TASK-0301, TASK-0302, TASK-0303, TASK-0304, TASK-0305, TASK-0306, TASK-0307]
status: anchor
includes:
  - AI 写 LoginController.gd
  - autonomous loop
effort_estimate: 2d
risk: high
max_iterations: 5
```

---

### TASK-0309: Phase 3 出口 + 三引擎一致性 review (manual)

```yaml
title: 三引擎完成 review
phase: 3
engine: all
depends_on: [TASK-0308]
status: anchor
goal: 同一份 task DSL 在三引擎产出一致 login MVP
includes:
  - 三引擎 e2e 全绿
  - 视觉回归通过 (各引擎独立 baseline)
  - 行为 trace 对比一致 (event 序列)
effort_estimate: 1d
mode: manual
risk: high
```

---

## 七、Phase 4 — OS 输入 + LPIPS + 优化（anchor）

---

### TASK-0400: OS 级输入 — Windows SendInput (anchor)

```yaml
title: Windows SendInput native plugin
phase: 4
engine: all
depends_on: [TASK-0309]
status: anchor
includes:
  - Unity / UE / Godot native plugin (P/Invoke / DLL)
  - 测试场景: 引擎事件层注入失败 → fallback OS
effort_estimate: 1w
risk: medium
```

---

### TASK-0401: OS 级输入 — macOS CGEventPost (anchor)

```yaml
title: macOS native plugin
phase: 4
engine: all
depends_on: [TASK-0400]
status: anchor
effort_estimate: 1w
risk: medium
```

---

### TASK-0402: OS 级输入 — Linux uinput / XTest (anchor)

```yaml
title: Linux native plugin
phase: 4
engine: all
depends_on: [TASK-0400]
status: anchor
effort_estimate: 1w
risk: medium
```

---

### TASK-0403: LPIPS subprocess 化 (anchor)

```yaml
title: LPIPS PyTorch 子进程隔离
phase: 4
engine: none
depends_on: [TASK-0309]
status: anchor
includes:
  - autoagent-mcp[lpips] extras
  - lpips_subprocess.py (子进程 + IPC)
  - 内存隔离测试
effort_estimate: 4d
risk: medium
```

---

### TASK-0404: Claude Vision 多模态裁决稳定化 (anchor)

```yaml
title: LLM 二次裁决产品化
phase: 4
engine: none
depends_on: [TASK-0403]
status: anchor
includes:
  - 失败重试
  - max_diff_per_session 调优
  - 裁决结果缓存
effort_estimate: 3d
risk: low
```

---

### TASK-0405: 增量 dump (协议 v0.2) (anchor)

```yaml
title: 协议 v0.2 — 节点增量更新, 减少 token
phase: 4
engine: all
depends_on: [TASK-0309]
status: anchor
includes:
  - protocol/schema/v0.2/* 草案
  - 三引擎 adapter 增量推送
  - 兼容 v0.1
effort_estimate: 1w
risk: high
```

---

### TASK-0406: 性能优化 — 大场景 dump (anchor)

```yaml
title: 1000+ 节点场景 dump < 100ms
phase: 4
engine: all
depends_on: [TASK-0405]
status: anchor
includes:
  - 三引擎反射性能 profiling
  - Godot GDExtension 重写热点
  - UE Slate 反射缓存
effort_estimate: 1w
risk: medium
```

---

### TASK-0407: 三引擎大场景 stress test (anchor)

```yaml
title: stress test 套件 + CI nightly
phase: 4
engine: all
depends_on: [TASK-0406]
status: anchor
effort_estimate: 4d
risk: medium
```

---

### TASK-0408: v1.0 release prep (anchor)

```yaml
title: changelog + migration guide + tag
phase: 4
engine: none
depends_on: [TASK-0400, TASK-0401, TASK-0402, TASK-0403, TASK-0405, TASK-0406]
status: anchor
includes:
  - CHANGELOG.md 初版
  - docs/migration/v0.x-to-v1.0.md
  - SemVer git tag 流程
effort_estimate: 2d
mode: manual
risk: low
```

---

### TASK-0409: 文档 review + final polish (anchor)

```yaml
title: 全文档 review + sync 实际实现
phase: 4
engine: none
depends_on: [TASK-0408]
status: anchor
includes:
  - 00-08 文档对照实际实现勘误
  - example / quickstart 补全
  - API reference 自动生成 (Sphinx / Doxygen)
effort_estimate: 1w
mode: manual
risk: low
```

---

## 八、Go/No-Go Gates 汇总

> 每个 phase 出口必须人工 review 全部 gate 通过才能进下个 phase。

### Phase 0 出口 (TASK-0017 验证)
1. ☐ 三引擎 dump UI 树 parent/children 正确（无重复节点 / 无层级错误）
2. ☐ Unity / Godot 在 PR runner 上 take_screenshot 拿到非黑屏
3. ☐ Self-hosted UE runner online + nightly 通过
4. ☐ 防护 0.1（路径白名单）+ 0.2（源码 diff）能拦下故意破坏
5. ☐ Subprotocol 握手在三引擎都正确返回 `autoagent.v1`
6. ☐ `negotiate_version` JSON-RPC 握手符合 [01](01-protocol-spec.md) 规范
7. ☐ Orchestration scaffolding 跑通 1 个 echo 任务（详见 [09](09-orchestration.md) §15）
8. ☐ 故意让 agent 违反路径白名单 → 顶层正确捕获 needs_human
9. ☐ 故意 kill 掉一个 in_progress agent → 顶层 resume 时正确恢复
10. ☐ 写 stop_signal → 顶层正确停机

### Phase 1 出口 (TASK-0135 验证)
1. ☐ AI Agent 完整 autonomous loop（写代码 → CI → 修 → PR）跑通 login MVP
2. ☐ 防护 0.2 拦下 AI 在 .cs 写 visual 字段
3. ☐ 防护 0.1 拦下 AI 改 .unity 文件
4. ☐ 防护 0.3 dump 前后 visual diff 拦下故意写入
5. ☐ SSIM 视觉回归通过 login + welcome
6. ☐ 全程无人工敲键盘（除 review/approve PR）
7. ☐ AI 单任务平均迭代数 < 3
8. ☐ Cost tracking 正常工作

### Phase 2 出口 (TASK-0211 验证)
1. ☐ 所有 Phase 2 task merged
2. ☐ login MVP 跨 Unity / UE 一致（同一份 task DSL）
3. ☐ 5 道防护在 UE 全部生效
4. ☐ Self-hosted runner 稳定（连续 7 天 nightly 无超时 / OOM）
5. ☐ UE shipping build 验证 adapter 不包含到二进制
6. ☐ Slate 私有 API 漂移监测脚本到位

### Phase 3 出口 (TASK-0309 验证)
1. ☐ 三引擎完成 login MVP，同任务 DSL 行为一致
2. ☐ 三引擎视觉回归通过（各 baseline 独立维护）
3. ☐ Godot release export 反射 self-check 通过
4. ☐ 5 道防护在 Godot 全部生效

### Phase 4 出口 (TASK-0408 / TASK-0409)
1. ☐ OS 输入双轨可用（三平台）
2. ☐ LPIPS 子进程化 + 内存隔离生效
3. ☐ 大场景（1000+ 节点）性能达标
4. ☐ Stress test nightly 全绿
5. ☐ v1.0 changelog + migration guide 完成
6. ☐ 文档与实际实现 sync 完成

---

## 九、修订历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-05-10 | 0.1 | 初版（Phase 0/1 详写，Phase 2-4 anchor） |
| 2026-05-10 | 0.2 | Phase 0 加 5 个 orchestration task (TASK-0018~0022) + 4 个新 gate (7~10)，对应 docs/09-orchestration.md |
