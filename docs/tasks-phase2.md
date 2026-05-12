# 99-tasks Phase 2 — UE adapter 完整 + 跨引擎一致

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。
> Phase 2 启动前 (Phase 1 完成后) 必须重新拆 anchor 为 PR-sized task。下面是 anchor 列表。

## Phase 2 出口标准

1. login MVP 跨 Unity / UE 一致（同一份 task DSL）
2. 5 道防护在 UE 全部生效
3. Self-hosted runner 稳定（连续 7 天 nightly 无超时 / OOM）
4. UE shipping build 验证 adapter 不包含到二进制
5. Slate 私有 API 漂移监测脚本到位

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
  - Modal widget / SetUserFocus 处理
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
  - Cooked 资源 reference 适配
  - Shipping build size 增量 < 5MB
  - Hot reload 后 adapter 自动重启
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
  - Self-hosted runner 稳定
mode: manual
risk: high
```
