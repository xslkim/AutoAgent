# 00 - 产品总览

> AutoAgent UI Framework：让 AI Agent 在游戏引擎已有的 UI 上自动开发交互逻辑、自动验证、闭环迭代。

## 一、产品定位

**一句话**：程序员在 Unity / UE / Godot 引擎里手动搭好**静态视觉骨架**（仅 UI 树 + 图片 + 文字显示元素，**不放任何交互控件**），框架自动遍历 UI 树注入 ID/meta；AI Agent 接到任务描述（含 UI 元素 ID 与目标 logical_role）后自动写引擎代码（C# / C++ / GDScript），在代码里**运行时赋予视觉节点对应的交互控件能力**（Unity `AddComponent`；UE 包裹 / 替换为 UMG widget；Godot 替换节点并迁移视觉）并实现交互逻辑；框架自动启动引擎模拟用户操作、收集日志和截图，AI 看反馈判断是否完成，形成闭环。

**不做什么**：
- ❌ 不生成 UI 视觉（不替代美术）
- ❌ 不做 Figma → 引擎自动导入（已论证不可行）
- ❌ 不支持多人在线 PvP（反作弊会拦反射注入）

### 程序员搭建边界（normative）

程序员在引擎工程文件（`.unity` / `.uasset` / `.tscn`）里**只放视觉骨架**——目的只有一个：和美术稿视觉对齐。**不放任何交互控件**，控件功能由 AI 在源码里运行时实现：Unity 用 `AddComponent`，UE 用包裹 / 替换 UMG widget，Godot 用替换节点 + 视觉迁移。

| 类别 | 程序员可手放 | 谁负责 |
|---|---|---|
| **图片 / 容器**：`Image` / `RawImage` / `Sprite` / `TextureRect` / `UImage`、`Canvas` / `CanvasLayer`、`Panel` / `VerticalBox` / `Container` / `RectTransform` | ✅ | 程序员手放，对齐美术稿。`Mask` / `RectMask2D` 由 AI 在代码里加 |
| **文字显示**：`Text` / `TextMeshPro` / `UTextBlock` / `Label`（纯显示，不接收输入） | ✅ | 程序员手放（美术决定字体 / 字号 / 颜色） |
| **交互控件**：`Button`、`InputField` / `TMP_InputField` / `UEditableTextBox` / `LineEdit`、`Slider`、`Toggle` / `CheckBox`、`Dropdown` / `ComboBox`、`ScrollView` / `ScrollBar` / `ScrollBox` / `ScrollRect`、`ListView` / `TreeView`、`Mask` / `RectMask2D`（裁剪） | ❌ | AI 在源码里按引擎模型运行时创建 / 挂载 / 替换 |

**例外说明**：`Image.raycastTarget` / `Control.mouse_filter` / `Widget.Visibility`（"是否参与命中测试"）属于 `behavior` 字段（不是 `visual`），AI 可以在代码里改这些以让自己挂的控件能被点击——这条豁免明确写进 [06 防护 0.2](06-visual-regression.md#22-源码-diff-审计-astregex-扫描)。

## 二、目标用户

| 角色 | 用法 |
|---|---|
| 游戏程序员 | 搭完静态视觉骨架（仅图片 + 文字 + 容器，不放控件），pin stable ID 并声明 logical_role，写一份任务 DSL，让 AI Agent 实现交互；review PR |
| 技术美术 | 给 UI 元素 pin stable ID；定义"美术约束"（哪些视觉属性不允许 AI 修改） |
| QA | 用框架做回归测试、视觉回归 |
| AI Agent (Claude Code) | 框架的"程序员"，读任务 → 写代码 → 跑测试 → 看日志 → 迭代 |

## 三、核心使用场景

### 场景 1：实现一个登录界面的交互（MVP 验证场景）

```
1. 程序员在 Unity 里搭好 Login Canvas，只放视觉骨架：
   - LoginPanel (Image)
     - AccountInputBg (Image)  ← 输入框背景图，没挂 InputField
     - PasswordInputBg (Image) ← 输入框背景图
     - LoginButtonBg (Image)   ← 按钮视觉，没挂 Button
       - LoginButtonLabel (TMP_Text "Login")
     - ErrorLabel (TMP_Text, 初始空)
   - WelcomePanel (Image, 初始 inactive)
     - WelcomeText (TMP_Text)
2. 程序员给每个节点 pin stable ID + 声明目标 logical_role:
   - account_input_bg   (meta.logical_role="input")
   - password_input_bg  (meta.logical_role="input")
   - login_button_bg    (meta.logical_role="button")
   - error_label / welcome_text (meta.logical_role="text_display")
3. 程序员写任务 DSL：
   "实现登录功能：用户在 account_input_bg / password_input_bg 输入文本，
    点击 login_button_bg 后调用 mock API（POST /login）。
    返回成功 → 隐藏 login_panel，显示 welcome_text；
    返回失败 → 在 error_label 显示错误信息。"
4. AI Agent 读任务 + 当前 UI 树 dump（看到节点 type=Image, meta.logical_role=button）
5. AI Agent 写 LoginController.cs，在 Awake() 里:
   - account_input_bg.gameObject.AddComponent<TMP_InputField>()
   - password_input_bg.gameObject.AddComponent<TMP_InputField>() + contentType=Password
   - login_button_bg.gameObject.AddComponent<Button>() + AddListener(OnLogin)
   - 同时把 raycastTarget=true 设上（behavior 字段，允许写）
6. AI Agent 触发 GitHub Actions CI，CI 跑：
   - 路径白名单 + 源码 diff 审计（防护 0）通过
   - dump_before（fixture 加载完）vs dump_after（AI Awake 后）：
     visual 字段无变化（OK），behavior 字段有新组件（预期）
   - 单元测试 / e2e: 模拟点击 login_button_bg → mock API 收到 POST
7. CI 通过 → AI 自动 commit + PR
8. CI 失败 → AI 读日志 → 修代码 → 再触发（autonomous loop）
```

### 场景 2：给已有"图片按钮"添加新功能（增量场景）

```
1. UI 已经有 settings_button_bg (Image, logical_role="button") + settings_panel (Image)
2. 任务 DSL: "点击 settings_button_bg 切换 settings_panel 显隐"
3. AI 读 UI 树 → 在代码里 AddComponent<Button>() → 写 Toggle 行为 → 测试 → PR
```

### 场景 3：复杂列表 + 数据绑定

```
1. UI 视觉骨架: inventory_list (Image 容器) + ItemTemplate (Image 子节点，作为 prefab 模板)
   注意：程序员不挂 ScrollRect / RectMask2D，AI 代码里加
2. 任务 DSL: "调用 mock API GET /inventory，返回的物品列表渲染到 inventory_list"
3. AI 在代码里 AddComponent<ScrollRect> + AddComponent<RectMask2D>，
   Instantiate ItemTemplate 填充数据 → 写 InventoryController + Item ViewModel → 测试 → PR
```

## 四、关键约束（硬约束，不可违反）

| 约束 | 说明 |
|---|---|
| 引擎语言 | Unity 纯 C#，UE 纯 C++，Godot GDScript（必要时 GDExtension）。"纯 C# / 纯 C++"指**业务逻辑全部用文本代码**，不在蓝图图表 / prefab 上挂可视化脚本节点。**仍可使用 prefab / Widget Blueprint (WBP) / .tscn 作为"纯数据的视觉骨架容器"**——它们用来声明 UI 树 + 图片资源 + StableId/LogicalRole/StateSprites meta，但不承载任何逻辑（无 Blueprint event graph、无 onClick UnityEvent 序列化）。AI 通过 BindWidget / GetWidgetFromName 在 C++/C# 代码里拿到这些视觉骨架节点，运行时挂控件实现交互 |
| 美术保真 | AI 只能写 behavior + meta，禁止修改 visual 属性（color / sprite / position / scale 等）和结构（parent / sibling order）。`raycastTarget` / `mouse_filter` / `Visibility` 归 behavior，AI 可写。`meta.state_sprites` 例外见 [06 §三 防护 1 例外条款](06-visual-regression.md) |
| 跨引擎统一 | 同一份任务 DSL 能在三引擎落地；引擎 adapter 独立实现 |
| 输入双轨 | 引擎事件层（默认）+ OS 级（fallback for 焦点丢失 / 全屏独占 / 引擎事件注入失败的测试场景；**不**承诺绕过反作弊，不用于 PvP 上线包） |
| 适用范围 | 仅单机 / PvE / 开发阶段 / QA 包；PvP 上线版必须移除 SDK |
| 任务粒度 | 1 个任务 = 1 个 PR（半天到 2 天工作量） |

## 五、MVP 定义（必须达成才算第一阶段成功）

**MVP 验收 case**：login 界面 canonical task

- 三引擎（Unity → UE → Godot 顺序）都能从同一份任务 DSL 自动实现 login 功能
- AI Agent 全程无人工干预完成
- e2e 测试通过：模拟输入账号密码 → 点击按钮 → mock API 收到请求 → UI 状态切换正确
- 视觉回归通过：截图与基线对比 SSIM ≥ 0.95

每个引擎 phase 出口标准：MVP case 在该引擎下跑通。

## 六、版本路线图

| Version | Phase | 产出 |
|---|---|---|
| v0.1 | Phase 0 | 协议规范 v0.1 + 三引擎各 200 行 PoC（4 动作） |
| v0.2 | Phase 1 | Unity adapter 完整 + MCP server + 视觉回归 + login MVP |
| v0.3 | Phase 2 | UE adapter 完整 + login MVP 跨引擎一致 |
| v0.4 | Phase 3 | Godot adapter 完整 + 三引擎一致 |
| v1.0 | Phase 4 | OS 输入双轨（仅测试场景）+ Vision fallback (LPIPS / Claude Vision) + 性能优化 |

## 七、术语表

| 术语 | 定义 |
|---|---|
| Adapter | 引擎特定的 UI 反射 + 输入注入插件（Unity adapter / UE adapter / Godot adapter） |
| Wire Protocol | 框架与 adapter 之间的 WebSocket + JSON-RPC 协议 |
| MCP Server | 暴露给 AI Agent 的 Model Context Protocol 服务器 |
| Stable ID | 节点的稳定标识符，跨美术迭代不变 |
| Pin ID | 美术/程序员手动钉死的 ID（持久化到组件字段） |
| Visual / Behavior / Meta | 节点属性的三类分组，AI 只能写 behavior + meta |
| Logical Role | 节点的"逻辑控件角色"标签（`button` / `input` / `slider` / `toggle` / `scroll_container` / `text_display` / `image_only` / ...），写在 `meta.logical_role`。**程序员搭 fixture 时声明**（pin ID 时一起写），任务 DSL 按 logical_role 引用而非 type，AI 据此按引擎模型实现对应控件能力（Unity `AddComponent`；UE 包裹 / 替换；Godot 替换迁移） |
| State Sprites | `meta.state_sprites` 字段：节点的多状态视觉资源映射（`{ normal, hover, pressed, focused, disabled } → sprite_ref`），美术 commit 多套 sprite；AI 在代码里按状态切换 `Image.sprite`——此切换属于 behavior 而非 visual 写入（**05/06 防护 0.2 的明确豁免**） |
| Test Fixture | 用户预先在引擎里搭好的最小测试场景（commit 到 repo），含视觉骨架 + pinned ID + logical_role + state_sprites |
| Canonical Task | MVP 验收用的标准任务（首版 = login 界面） |
| Autonomous Loop | AI Agent 写代码 → 触发 CI → 读结果 → 修复 → 再触发的自迭代闭环 |

## 八、文档导航

| 文档 | 内容 | 状态 |
|---|---|---|
| 00-product-overview.md | 本文档 | ✅ |
| 01-protocol-spec.md | Wire Protocol（adapter ↔ MCP server）的 JSON schema、命令、事件 | ✅ |
| 02-mcp-server.md | MCP Server 的 tools API、架构、配置 | ✅ |
| 03-adapter-unity.md | Unity adapter 设计：UGUI / UI Toolkit 反射、EventSystem 注入 | ✅ |
| 04-adapter-unreal.md | UE adapter 设计：UWidgetTree 反射、Slate 注入 | ✅ |
| 05-adapter-godot.md | Godot adapter 设计：SceneTree 反射、parse_input_event 注入 | ✅ |
| 06-visual-regression.md | 视觉回归 + 美术保真五道防护（含源码层审计） | ✅ |
| 07-agent-operations.md | AI Agent 自治边界（迭代上限 / 路径白名单 / secret / 失败停机） | ✅ |
| 08-ci-runners.md | CI 运行环境规格（GPU runner / Xvfb / 字体 / 分辨率 / color space） | ✅ |
| 09-orchestration.md | 自动化调度（两层 agent + 状态文件 + DAG + 自然语言裁决） | ✅ |
| 10-fixture-setup-guide.md | 三引擎静态 fixture 搭建步骤 + 辅助脚本 | ✅ |
| tasks.md | 任务清单索引（按 Phase 拆分） | ✅ |
| canonical-tasks/login.yaml | Login MVP 任务 DSL（AI 输入的标准化任务描述） | 未来产出（TASK-0132） |
| canonical-tasks/README.md | 任务 DSL schema 规范（字段定义、校验规则、parser 行为） | 未来产出（TASK-0132 同步创建） |
| runners-inventory.md | Self-hosted runner 清单 | 未来产出（TASK-0013） |
| orchestrator-prompt.md | 顶层 Claude /loop 启动 prompt 模板 | 未来产出（TASK-0021） |
| user-guide-orchestration.md | 用户日常操作指南 | 未来产出（TASK-0021） |
| phase0-gate-report.md | Phase 0 出口 gate 检查结果 | 未来产出（TASK-0023） |
| dry-run-report.md | Orchestration 端到端 dry run 报告 | 未来产出（TASK-0022） |
| users/il2cpp-setup.md | 用户 IL2CPP link.xml 配置指南 | 未来产出（TASK-0104） |
| migration/v0.x-to-v1.0.md | v1.0 迁移指南 | 未来产出（TASK-0408） |

## 九、执行约定（工程层面）

| 项 | 约定 | 来源 |
|---|---|---|
| Background Agent | Claude Code 本地 background mode | Q1 = A |
| CI 策略 | Unity / Godot 每 PR 跑，UE 只 nightly 跑 | Q2 = C |
| MCP 技术栈 | Python 3.11+ + stdio transport | Q3 = A |
| 测试 Fixture | 用户手动在三引擎里准备最小项目并 commit | Q4 = B |
| MVP 验收 | login 界面 canonical task | Q5 = A |
| AI 执行模式 | Autonomous loop：写代码 → 触发 CI → 读结果 → 修复 → 再触发 | Q6 = C |
| 引擎顺序 | Unity 2023.x LTS → UE 5.7 → Godot 4.6 | 用户指定 |
| 任务粒度 | 1 task = 1 PR | Q2 (granularity) = A |
| 文档语言 | 中文为主，代码 / API 名 / 术语英文 | 默认 |
| 代码语言 | 英文（注释 / 命名 / commit message） | 默认 |
| Repo 结构 | Monorepo（`<REPO_ROOT>` 下分目录；当前作者环境为 `D:\AutoAgent`） | 默认 |
| Git 流程 | 每任务一个 feature branch + PR，main 保护 | 默认 |
| Branch 命名 | `task/XXX-short-desc` | 默认 |
| PR 命名 | `[TASK-XXX] Title` | 默认 |
| Framework License | MIT | 默认 |

## 十、Repo 目录结构

> Windows 示例为 `D:\AutoAgent\`；任何文档中 `<REPO_ROOT>` 占位符均指代此根目录，跨平台等价。

```
<REPO_ROOT>\
├─ docs\                       # 本套文档
│  ├─ 00-product-overview.md
│  ├─ 01-protocol-spec.md
│  ├─ 02-mcp-server.md
│  ├─ 03-adapter-unity.md
│  ├─ 04-adapter-unreal.md
│  ├─ 05-adapter-godot.md
│  ├─ 06-visual-regression.md
│  ├─ 07-agent-operations.md
│  ├─ 08-ci-runners.md
│  ├─ 09-orchestration.md
│  └─ tasks.md
├─ protocol\                   # 协议 schema 共用定义（JSON Schema 文件）
│  └─ schema\
├─ mcp-server\                 # Python MCP Server
│  ├─ pyproject.toml
│  ├─ src\autoagent_mcp\
│  └─ tests\
├─ adapters\
│  ├─ unity\                   # Unity Plugin（Unity Package Manager 格式）
│  │  ├─ package.json
│  │  ├─ Runtime\
│  │  └─ Tests\
│  ├─ unreal\                  # UE Plugin
│  │  ├─ AutoAgent.uplugin
│  │  ├─ Source\
│  │  └─ Tests\
│  └─ godot\                   # Godot addon
│     ├─ plugin.cfg
│     ├─ scripts\
│     └─ tests\
├─ fixtures\                   # 三引擎测试 fixture（Phase 0 用户准备）
│  ├─ unity-test-project\
│  ├─ unreal-test-project\
│  └─ godot-test-project\
├─ scripts\                    # CI / e2e 脚本
│  ├─ ci\
│  └─ e2e\
└─ .github\workflows\          # GitHub Actions
   ├─ unity-ci.yml
   ├─ godot-ci.yml
   └─ unreal-nightly.yml
```
