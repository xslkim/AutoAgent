# AI Agent UI 开发框架 - 架构方案 v1.0

> 多引擎（Unity / Unreal / Godot）AI Agent 驱动的 UI 开发框架。
> 经过 6 轮联网调研后定型。

## 项目目标

构建一个开发框架，让 AI Agent（Claude Code 类外部 Agent）通过 MCP 协议驱动 Unity / Unreal / 未来 Godot 三个引擎，实现 UI 开发的闭环：

```
程序员手动放置静态 UI → 框架遍历 UI 树添加 ID/meta
                    → AI 接任务（描述功能 + ID 列表）
                    → AI 写引擎代码（C# / C++ / GDScript）
                    → 框架自动运行，模拟用户操作
                    → 日志 + 视觉对比 回传 AI
                    → AI 判断完成或继续迭代
```

**硬约束**：
- **业务逻辑全部文本代码**：Unity 纯 C#，Unreal 纯 C++，Godot GDScript（必要时 GDExtension）。允许 `.unity` / `.prefab` / `.uasset` (WBP) / `.tscn` 作为**纯数据的视觉骨架容器**（含 UI 树 + 图片 + meta，不含逻辑节点 / Blueprint Event Graph / UnityEvent 序列化引用）。详见 [docs/00-product-overview.md §四 程序员搭建边界](docs/00-product-overview.md)。
- 任务描述统一（同一份 prompt 驱动多引擎）
- 引擎插件独立实现
- OS 级输入注入 + 引擎事件层 双轨（OS 级**仅用于焦点丢失 / 全屏独占 / 引擎事件注入失败的 QA 场景，不绕过反作弊**）
- AI Agent 自决策迭代
- 覆盖：按钮 / 输入 / 拖拽 / 动画 / 场景切换 / 网络 mock 全场景
- **仅适用于：单机 / PvE / 开发阶段 / QA 包**（PvP 反作弊会拦反射注入，上线包必须移除 SDK）

> **本文档状态**：v1.0 顶层架构稿，已被 `docs/00-09` 系列产品文档取代。当两份文档冲突时，以 `docs/` 系列为准。

## 关键决策（已经过调研验证）

### 决策 1：完全自研，不基于任何现成 SDK

| 候选方案 | 否决理由 |
|---|---|
| 纯 Poco | UE SDK 实质停滞（仅声明 4.26+，无 UE5），无 Godot，主仓 16 个月零 commit |
| AltTester UE SDK | **闭源 binary plugin + 私有 EULA + 源码额外付费**，再分发法律灰区，集成进框架分发给客户会卡死 |
| GameDriver | 闭源商业 SaaS，订阅模式与"AI Agent 任意调用"冲突 |
| UE Remote Control API | 必须 Editor preset 预注册，无 UWidgetTree 枚举，无 Slate 输入注入 |
| Unity-MCP / UE-MCP 各项目 | 几乎全部聚焦 Editor 操作，**没有运行时 UI 自动化**——这是市场空白 |

**结论：完全自研，但借开源做设计参考**。
- 协议设计参考 Poco `AbstractDumper / AbstractNode / StdRpcReactor`（Apache-2.0）
- 协议设计参考 WebDriver BiDi（W3C 标准）
- Unity 实现参考 AltTester Unity SDK 架构（GPL，clean room，**只学不抄**）
- UE 实现基于 `UWidgetTree::ForEachWidget` + `FSlateApplication::ProcessMouseButtonDownEvent`
- Godot 实现基于 `SceneTree` + `Input.parse_input_event`

### 决策 2：Figma 不做自动导入，仅作视觉 ground truth

**反复验证后确认 Figma → 游戏 UI 自动化不可行**：
- 零商业游戏案例（搜遍 GitHub / Reddit / GDC）
- 工具自我定位 "experimental / game jamming / prototyping"
- 17+ 项不支持的 Figma 功能（多 fill / 内阴影 / Layer Blur / stroke 渐变 / Boolean ops...）
- 游戏 UI 特有能力 Figma 全部无法表达：Sprite Atlas / 9-Slice / Shader / 状态机动画 / 粒子 / 动态数据绑定 / Safe Area / 本地化 / TMP 富文本 / Mask / Linear color space
- "假装匹配"问题：Figma 按钮转出来 4-6 层嵌套 vs 手搭 1 层
- 必须强加给美术的规范一长串，破坏一条就废
- 大厂工作流是手搭

**Figma 在框架里的最终角色**：
- ❌ 自动生成 Prefab/UMG
- ✅ 美术产出 PNG + 字体 + 整体效果图（程序员手动放置）
- ✅ 视觉验收 ground truth（截图 baseline 对比）
- ✅（可选 Phase 4）Figma MCP 读视觉规格（坐标/尺寸/颜色 token），让 AI 对照规格设值

### 决策 3：美术保真四道防护

1. **非侵入硬约束**：协议层 schema 把属性分成 visual / behavior / meta 三类，AI 只能写 behavior + meta，禁写 visual / 结构
2. **ID 稳定性**：默认 ID = `hash(hierarchy_path + node_name + element_type)`；美术可在引擎手动 pin（持久化到组件字段）；孤儿 ID 检测 + 拒绝 AI 自动猜测
3. **视觉回归**：用引擎自带工具（Unity Graphics Test Framework / UE Screenshot Comparison Tool），业界阈值 LPIPS<0.10 / SSIM≥0.95，多模态 LLM 二次裁决
4. **资源 GUID 追踪**：引擎自带（Unity .meta / UE AssetRegistry / Godot .uid），框架尊重

### 决策 4：双轨输入

- **引擎事件层**（默认主轨）：
  - Unity: `EventSystem.current.RaycastAll` + `ExecuteEvents.Execute<IPointerClickHandler>()`
  - UE: `FSlateApplication::ProcessMouseButtonDownEvent`（必须 GameThread）
  - Godot: `Input.parse_input_event(InputEventMouseButton.new())`
- **OS 级输入**（fallback）：Windows SendInput / macOS CGEventPost / Linux XTest
  - 用于焦点丢失 / 全屏独占 / 引擎事件注入失败的 QA 测试场景
  - **不**承诺绕过反作弊；**不**用于 PvP 上线包（与 [00 §四 关键约束](docs/00-product-overview.md) 一致）

## 最终架构图

```
┌────────────────────────────────────────────────────────────────┐
│  Claude Code / AI Agent                                         │
│  Inputs: 任务 DSL + Figma 截图 baseline + (可选)Figma MCP 规格 │
└────────────────────────────────────────────────────────────────┘
            ↓ MCP
┌────────────────────────────────────────────────────────────────┐
│  Framework MCP Server (自研, Python/Node)                       │
│  Tools: list_widgets / dump_tree / click_by_id / send_text /   │
│         drag / scroll / take_screenshot / compare_to_baseline /│
│         pin_id / list_orphan_ids / audit_visual_changes        │
└────────────────────────────────────────────────────────────────┘
            ↓ WebSocket + JSON-RPC
┌────────────────────────────────────────────────────────────────┐
│  统一协议层 (自研)                                              │
│  Schema: visual / behavior / meta 三类属性分离                │
│  ⚠️ 冻结前每个引擎跑完 click/drag/text-input/scroll PoC        │
└────────────────────────────────────────────────────────────────┘
       ↓              ↓              ↓
┌──────────┐  ┌──────────────┐  ┌──────────┐
│ Unity    │  │ UE           │  │ Godot    │
│ adapter  │  │ adapter      │  │ adapter  │
│ C# 自研  │  │ C++ 自研     │  │ GDScript │
│ EventSys │  │ Slate 反射   │  │ +热点    │
│ + 反射   │  │ +FPointerEv  │  │ GDExt    │
│ ~1.5 月  │  │ ~2.5-3 月    │  │ ~1 月    │
└──────────┘  └──────────────┘  └──────────┘
            ↓
┌────────────────────────────────────────────────────────────────┐
│  视觉回归 (用引擎自带 + 业界阈值)                              │
│  Unity Graphics Test Framework / UE Screenshot Comparison      │
│  + LPIPS<0.10 / SSIM≥0.95 + Claude Vision 二次裁决            │
└────────────────────────────────────────────────────────────────┘
```

## 美术工作流（独立于框架）

```
Figma 设计
  → 美术导出 PNG 切片 + 字体 + 整图效果图
  → 程序员在引擎里手动放置静态 UI（Unity Canvas / UE UMG / Godot Control）
  → 框架启动，遍历 UI 树，给每个元素分配 ID/meta
  → AI Agent 接任务，加交互逻辑
  → 自动跑、视觉对比、闭环
```

## 工作量估算

| 模块 | 工作量 |
|---|---|
| 协议规范 v0.1 + 三引擎 PoC（4 动作验证） | 2 周 |
| Unity adapter | 1.5 月 |
| UE adapter | 2.5-3 月 |
| Godot adapter | 1 月 |
| MCP server | 2 周 |
| 视觉回归（用引擎自带） | 0.5 月 |
| OS 输入双轨 | 0.5 月 |
| ID 稳定 + 美术保真四道防护 | 0.5 月 |
| Figma MCP 读规格（Phase 4 可选） | 0.5 月 |
| **总计** | **~6.5-7 月**（单人）/ **~3.5 月**（2 人并行） |

## 阶段执行计划

| Phase | 内容 | 时长 | 出口标准 |
|---|---|---|---|
| 0 | 协议规范 v0.1 + 三引擎各 200 行 PoC（click/drag/text/scroll） | 2 周 | 三引擎都能跑通最小 4 动作 |
| 1 | Unity 单引擎完整闭环（含视觉回归 + 美术保真） | 2 月 | Claude Code 通过 MCP 完成一个真实 UI 任务 |
| 2 | UE 接入 | 2.5-3 月 | UE 跑通同一份任务 DSL，验证协议跨引擎一致性 |
| 3 | Godot 接入 | 1 月 | 三引擎一致 |
| 4 | OS 输入双轨 + Vision fallback + Figma MCP 集成 + 优化 | 1 月 | QA 场景全覆盖（焦点丢失 / 全屏独占 / 引擎事件失败）|

## 隐藏风险（必须心理建设）

1. **UE Slate 私有 API 漂移**：每次 UE 5.x 升级要回归 dump/click/text 三件套。长期人力成本可能高于另两引擎之和。
2. **Godot release export 反射 silent failure**（issue [#99722](https://github.com/godotengine/godot/issues/99722)）：开发期跑通的代码到打包后才报"找不到节点"。必须 SDK 内置 release-mode 自检。
3. **三套输入注入语义完全不同**：协议 schema 冻结前 Phase 0 PoC 必跑。
4. **反作弊边界**：仅适用于单机/PvE/开发阶段/QA 包，PvP 上线版必须移除 SDK。OS 输入双轨**不**承诺绕过任何反作弊系统——README 第一行写清楚。
5. **Unity 官方 MCP 演进风险**：Unity AI Beta 2026 已上线，未来可能压缩自研 Unity adapter 差异化空间，要预留替换路径。
6. **Figma MCP 是新东西**：API 还在演进，框架要做版本兼容。

## 执行前最后 3 个待确认问题

1. **资源投入**：单人 7 月 / 2 人并行 3.5 月，哪个？是否要砍 Godot 推迟到 v2？
2. **Phase 1 起步引擎**：Unity（最成熟、自研最容易、最快验证闭环）→ UE → Godot 的顺序对吗？
3. **Phase 0 后是否设 go/no-go gate**：三引擎 PoC（2 周）跑完后，如果某引擎超出预期难度，允许调整 scope 吗？

## 调研引用清单

### Poco SDK
- [AirtestProject/Poco GitHub](https://github.com/AirtestProject/Poco)
- [Poco-SDK 各引擎接入](https://github.com/AirtestProject/Poco-SDK)
- [Poco implementation guide](https://poco.readthedocs.io/en/latest/source/doc/implementation_guide.html)

### AltTester
- [AltTester Unity SDK (GPL-3.0)](https://github.com/alttester/AltTester-Unity-SDK)
- [AltTester Unreal SDK 公告](https://alttester.com/the-next-chapter-for-alttester-expanding-with-unreal-sdk-and-licensing-updates/)
- [AltTester UE 2.2 release](https://alttester.com/alttester-2-2-release-ui-toolkit-support-for-unreal-engine/)

### UE 自研基础
- [UWidgetTree Documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/UMG/UWidgetTree)
- [FSlateApplication API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Slate/FSlateApplication)
- [UE Automation Driver](https://dev.epicgames.com/documentation/en-us/unreal-engine/automation-driver-in-unreal-engine)
- [UE Screenshot Comparison Tool](https://dev.epicgames.com/documentation/en-us/unreal-engine/screenshot-comparison-tool-in-unreal-engine)

### Unity 自研基础
- [Unity UQuery Manual](https://docs.unity3d.com/Manual/UIE-UQuery.html)
- [Unity Graphics Test Framework](https://docs.unity3d.com/Packages/com.unity.testframework.graphics@7.2/manual/index.html)
- [Unity AI Beta 2026](https://discussions.unity.com/t/unity-ai-beta-2026-is-here/1703625)

### Godot 自研基础
- [Godot Control class](https://docs.godotengine.org/en/4.3/classes/class_control.html)
- [Godot release export reflection issue #99722](https://github.com/godotengine/godot/issues/99722)
- [Godot WebSocket](https://docs.godotengine.org/en/stable/tutorials/networking/websocket.html)

### Figma 反向验证
- [UnityFigmaBridge](https://github.com/simonoliver/UnityFigmaBridge)
- [TrackMan/Unity.Package.FigmaToUnity](https://github.com/TrackMan/Unity.Package.FigmaToUnity)
- [figma2umg](https://github.com/Buvi-Games/figma2umg)
- [Figma MCP Guide](https://help.figma.com/hc/en-us/articles/32132100833559-Guide-to-the-Figma-MCP-server)

### 视觉回归
- [LPIPS & SSIM 2025 Practical Guide](https://unifiedimagetools.com/en/articles/ai-image-quality-metrics-lpips-ssim-2025)
- [MLLM as a UI Judge (arXiv 2510.08783)](https://arxiv.org/html/2510.08783v1)
