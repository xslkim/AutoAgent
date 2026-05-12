# AI Agent UI 开发框架 - 架构摘要

> 多引擎（Unity / Unreal / Godot）AI Agent 驱动的 UI 开发框架。
> **本文档是架构决策摘要。详细规范以 [docs/](docs/) 系列为准。当冲突时，以 docs/ 为准。**

## 项目目标

构建一个开发框架，让 AI Agent（Claude Code 类外部 Agent）通过 MCP 协议驱动 Unity / Unreal / Godot 三个引擎，实现 UI 开发的闭环：

```
程序员手动放置静态 UI → 框架遍历 UI 树添加 ID/meta
                      → AI 接任务（描述功能 + ID 列表）
                      → AI 写引擎代码（C# / C++ / GDScript）
                      → 框架自动运行，模拟用户操作
                      → 日志 + 视觉对比 回传 AI
                      → AI 判断完成或继续迭代
```

**硬约束**：
- **业务逻辑全部文本代码**：Unity 纯 C#，UE 纯 C++，Godot GDScript。允许 `.unity` / `.prefab` / `.uasset` (WBP) / `.tscn` 作为纯数据的视觉骨架容器（含 UI 树 + 图片 + meta，不含逻辑节点 / Blueprint Event Graph / UnityEvent 序列化引用）。
- 任务描述统一（同一份 prompt 驱动多引擎）
- 引擎插件独立实现
- OS 级输入注入 + 引擎事件层 双轨（OS 级仅用于焦点丢失 / 全屏独占 / 引擎事件注入失败的 QA 场景，不绕过反作弊）
- AI Agent 自决策迭代
- **仅适用于：单机 / PvE / 开发阶段 / QA 包**（PvP 反作弊会拦反射注入，上线包必须移除 SDK）

## 关键决策摘要

### 决策 1：完全自研

不基于任何现成 SDK（Poco/AltTester/GameDriver/UE Remote Control 均有不可接受限制）。借开源做设计参考（协议参考 Poco/WebDriver BiDi；Unity 参考 AltTester 架构 clean room）。

### 决策 2：Figma 不做自动导入，仅作视觉 ground truth

反复验证后确认 Figma → 游戏 UI 自动化不可行。Figma 在框架内的角色：美术产出 PNG + 字体 + 效果图 → 程序员手动放置 → Figma 截图作为视觉验收 baseline。

### 决策 3：美术保真五道防护

> 编号与 [06-visual-regression.md](docs/06-visual-regression.md) 对齐。防护 0 是源码层审计——最重要的一道，因为 AI 直接写源码，能绕过 runtime API 层（防护 1）。

0. **源码层审计**（最重要）：PR diff 路径白名单 + AST/regex 扫描视觉字段写入 + dump 前后 diff gate + PR review
1. **协议层 Schema 权限分离**：runtime setter 拒绝 visual / 结构写入（`-32003` / `-32004`）
2. **ID 稳定性**：pinned / auto declared，禁止 hash ID 用于任务 contract
3. **视觉回归**：SSIM ≥ 0.95 + Claude Vision 二次裁决（LPIPS Phase 4 引入，子进程化）
4. **资源 GUID 追踪**：引擎自带（.meta / AssetRegistry / .uid）

### 决策 4：双轨输入

- **引擎事件层**（默认主轨）：EventSystem / FSlateApplication / Input.parse_input_event
- **OS 级输入**（fallback）：仅用于引擎事件注入失败场景，不承诺绕过反作弊

## 最终架构图

```
┌────────────────────────────────────────────────────────────────┐
│  Claude Code / AI Agent                                         │
│  Inputs: 任务 DSL + Figma 截图 baseline                         │
└────────────────────────────────────────────────────────────────┘
            ↓ MCP
┌────────────────────────────────────────────────────────────────┐
│  Framework MCP Server (自研, Python)                            │
│  Tools: list_widgets / dump_tree / click_by_id / send_text /   │
│         drag / scroll / take_screenshot / compare_to_baseline   │
└────────────────────────────────────────────────────────────────┘
            ↓ WebSocket + JSON-RPC
┌────────────────────────────────────────────────────────────────┐
│  统一协议层 (自研)                                              │
│  Schema: visual / behavior / meta 三类属性分离                  │
└────────────────────────────────────────────────────────────────┘
       ↓              ↓              ↓
┌──────────┐  ┌──────────────┐  ┌──────────┐
│ Unity    │  │ UE           │  │ Godot    │
│ adapter  │  │ adapter      │  │ adapter  │
│ C#       │  │ C++          │  │ GDScript │
└──────────┘  └──────────────┘  └──────────┘
            ↓
┌────────────────────────────────────────────────────────────────┐
│  视觉回归（引擎自带 + 业界阈值 + Claude Vision 二次裁决）       │
└────────────────────────────────────────────────────────────────┘
```

## 美术工作流

```
Figma 设计
  → 美术导出 PNG 切片 + 字体 + 整图效果图
  → 程序员在引擎里手动放置静态 UI（仅视觉骨架，不放交互控件）
  → 框架启动，遍历 UI 树，给每个元素分配 ID/meta
  → AI Agent 接任务，加交互逻辑
  → 自动跑、视觉对比、闭环
```

## 文档导航

| 文档 | 内容 |
|---|---|
| [00-product-overview.md](docs/00-product-overview.md) | 产品总览、约束、术语、MVP 定义 |
| [01-protocol-spec.md](docs/01-protocol-spec.md) | Wire Protocol 完整规范 |
| [02-mcp-server.md](docs/02-mcp-server.md) | MCP Server 设计 |
| [03-adapter-unity.md](docs/03-adapter-unity.md) | Unity adapter 设计 |
| [04-adapter-unreal.md](docs/04-adapter-unreal.md) | Unreal adapter 设计 |
| [05-adapter-godot.md](docs/05-adapter-godot.md) | Godot adapter 设计 |
| [06-visual-regression.md](docs/06-visual-regression.md) | 视觉回归 + 美术保真防护 |
| [07-agent-operations.md](docs/07-agent-operations.md) | AI Agent 执行边界与规则 |
| [08-ci-runners.md](docs/08-ci-runners.md) | CI 运行环境规格 |
| [09-orchestration.md](docs/09-orchestration.md) | 自动化调度架构 |
| [10-fixture-setup-guide.md](docs/10-fixture-setup-guide.md) | 三引擎静态 fixture 搭建指南 |
| [tasks.md](docs/tasks.md) | 任务清单索引 |
