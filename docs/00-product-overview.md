# 00 - 产品总览

> AutoAgent UI Framework：让 AI Agent 在游戏引擎已有的 UI 上自动开发交互逻辑、自动验证、闭环迭代。

## 一、产品定位

**一句话**：程序员在 Unity / UE / Godot 引擎里手动搭好静态 UI（Canvas + Image / UMG / Control），框架自动遍历 UI 树注入 ID/meta；AI Agent 接到任务描述（含 UI 元素 ID）后自动写引擎代码（C# / C++ / GDScript），框架自动启动引擎模拟用户操作、收集日志和截图，AI 看反馈判断是否完成，形成闭环。

**不做什么**：
- ❌ 不生成 UI 视觉（不替代美术）
- ❌ 不做 Figma → 引擎自动导入（已论证不可行）
- ❌ 不支持多人在线 PvP（反作弊会拦反射注入）

## 二、目标用户

| 角色 | 用法 |
|---|---|
| 游戏程序员 | 搭完静态 UI 后，写一份任务 DSL，让 AI Agent 实现交互；review PR |
| 技术美术 | 给 UI 元素 pin stable ID；定义"美术约束"（哪些视觉属性不允许 AI 修改） |
| QA | 用框架做回归测试、视觉回归 |
| AI Agent (Claude Code) | 框架的"程序员"，读任务 → 写代码 → 跑测试 → 看日志 → 迭代 |

## 三、核心使用场景

### 场景 1：实现一个登录界面的交互（MVP 验证场景）

```
1. 程序员在 Unity 里搭好 Login Canvas（手动拖 Image / InputField / Button）
2. 框架启动，遍历 Canvas，给每个元素分配 ID：
   - login_panel / account_input / password_input / login_button / error_label
3. 程序员写任务 DSL：
   "实现登录功能：用户在 account_input 和 password_input 输入文本，
    点击 login_button 后调用 mock API（POST /login）。
    返回成功 → 隐藏 login_panel，显示 welcome_text；
    返回失败 → 在 error_label 显示错误信息。"
4. AI Agent 读任务 + 当前 UI 树 dump
5. AI Agent 写 LoginController.cs，挂到 login_panel 上
6. AI Agent 触发 GitHub Actions CI，CI 跑：
   - 编译通过
   - 单元测试通过
   - e2e 测试：启动 Unity headless → 框架模拟点击 login_button → 检查
     network mock 收到 POST → 检查 welcome_text 出现
7. CI 通过 → AI 自动 commit + PR
8. CI 失败 → AI 读日志 → 修代码 → 再触发（autonomous loop）
```

### 场景 2：给已有按钮添加新功能（增量场景）

```
1. UI 已经有 settings_button + settings_panel
2. 任务 DSL: "点击 settings_button 切换 settings_panel 显隐"
3. AI 读 UI 树 → 写 Toggle 行为 → 测试 → PR
```

### 场景 3：复杂列表 + 数据绑定

```
1. UI 有 inventory_list (ScrollView + Item Prefab)
2. 任务 DSL: "调用 mock API GET /inventory，返回的物品列表渲染到 inventory_list"
3. AI 读 UI 树 → 写 InventoryController + Item ViewModel → 测试列表渲染、滚动、点击 → PR
```

## 四、关键约束（硬约束，不可违反）

| 约束 | 说明 |
|---|---|
| 引擎语言 | Unity 纯 C#（不用预制件），UE 纯 C++（不用蓝图），Godot GDScript（必要时 GDExtension） |
| 美术保真 | AI 只能写 behavior + meta，禁止修改 visual 属性（color / sprite / position / scale 等）和结构（parent / sibling order） |
| 跨引擎统一 | 同一份任务 DSL 能在三引擎落地；引擎 adapter 独立实现 |
| 输入双轨 | 引擎事件层（默认）+ OS 级（fallback for 全屏独占 / 反作弊场景） |
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
| v1.0 | Phase 4 | OS 输入双轨 + Vision fallback + Figma MCP（可选）+ 性能优化 |

## 七、术语表

| 术语 | 定义 |
|---|---|
| Adapter | 引擎特定的 UI 反射 + 输入注入插件（Unity adapter / UE adapter / Godot adapter） |
| Wire Protocol | 框架与 adapter 之间的 WebSocket + JSON-RPC 协议 |
| MCP Server | 暴露给 AI Agent 的 Model Context Protocol 服务器 |
| Stable ID | 节点的稳定标识符，跨美术迭代不变 |
| Pin ID | 美术/程序员手动钉死的 ID（持久化到组件字段） |
| Visual / Behavior / Meta | 节点属性的三类分组，AI 只能写 behavior + meta |
| Test Fixture | 用户预先在引擎里搭好的最小测试场景（commit 到 repo） |
| Canonical Task | MVP 验收用的标准任务（首版 = login 界面） |
| Autonomous Loop | AI Agent 写代码 → 触发 CI → 读结果 → 修复 → 再触发的自迭代闭环 |

## 八、文档导航

| 文档 | 内容 |
|---|---|
| 00-product-overview.md | 本文档 |
| 01-protocol-spec.md | Wire Protocol（adapter ↔ MCP server）的 JSON schema、命令、事件 |
| 02-mcp-server.md | MCP Server 的 tools API、架构、配置 |
| 03-adapter-unity.md | Unity adapter 设计：UGUI / UI Toolkit 反射、EventSystem 注入 |
| 04-adapter-unreal.md | UE adapter 设计：UWidgetTree 反射、Slate 注入 |
| 05-adapter-godot.md | Godot adapter 设计：SceneTree 反射、parse_input_event 注入 |
| 06-visual-regression.md | 视觉回归 + 美术保真四道防护 |
| 99-tasks.md | 任务清单（Phase 0-4，含顺序 / 目标 / 产出 / 验证） |

## 九、执行约定（工程层面）

| 项 | 约定 | 来源 |
|---|---|---|
| Background Agent | Claude Code 本地 background mode | Q1 = A |
| CI 策略 | Unity / Godot 每 PR 跑，UE 只 nightly 跑 | Q2 = C |
| MCP 技术栈 | Python 3.11+ + stdio transport | Q3 = A |
| 测试 Fixture | 用户手动在三引擎里准备最小项目并 commit | Q4 = B |
| MVP 验收 | login 界面 canonical task | Q5 = A |
| AI 执行模式 | Autonomous loop：写代码 → 触发 CI → 读结果 → 修复 → 再触发 | Q6 = C |
| 引擎顺序 | Unity 2023.x LTS → UE 5.6 → Godot 4.3 | 用户指定 |
| 任务粒度 | 1 task = 1 PR | Q2 (granularity) = A |
| 文档语言 | 中文为主，代码 / API 名 / 术语英文 | 默认 |
| 代码语言 | 英文（注释 / 命名 / commit message） | 默认 |
| Repo 结构 | Monorepo（D:\AutoAgent 下分目录） | 默认 |
| Git 流程 | 每任务一个 feature branch + PR，main 保护 | 默认 |
| Branch 命名 | `task/XXX-short-desc` | 默认 |
| PR 命名 | `[TASK-XXX] Title` | 默认 |
| Framework License | MIT | 默认 |

## 十、Repo 目录结构

```
D:\AutoAgent\
├─ docs\                       # 本套文档
│  ├─ 00-product-overview.md
│  ├─ 01-protocol-spec.md
│  ├─ ...
│  └─ 99-tasks.md
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
