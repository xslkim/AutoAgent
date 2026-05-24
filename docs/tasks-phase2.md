# 99-tasks Phase 2 — UE adapter 完整 + 跨引擎一致

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。

## Phase 2 出口标准 (✅ 全部达成)

1. ✅ login MVP 跨 Unity / UE 一致（同一份 task DSL）
2. ✅ 5 道防护在 UE 全部生效
3. ✅ Self-hosted runner 稳定
4. ✅ UE shipping build 验证 adapter 不包含到二进制
5. ✅ Slate 私有 API 漂移监测

---

## 进度快照（最后更新：2026-05-24）

| Task | 标题 | 状态 | PR |
|---|---|---|---|
| TASK-0200 | UMG Reflector 完整字段 + NamedSlot | ✅ merged | #102 |
| TASK-0201 | StableId Resolver 三源优先级 | ✅ merged | #103 |
| TASK-0202 | SlateInputDriver — 4 动作 + GameThread marshal | ✅ merged | #104 |
| TASK-0203 | WebSocket server — 连接上限 + negotiate_version | ✅ merged | #107 |
| TASK-0204 | Packaged build — AUTOAGENT_ENABLED + Shipping | ✅ merged | #106 |
| TASK-0205 | Editor module — Pin ID Detail Customization | ✅ merged | #108 |
| TASK-0206 | UE 视觉回归集成 — compare_screenshot RPC | ✅ merged | #110 |
| TASK-0207 | UE 防护验证 — 三层 CI 防护 | ✅ merged | #110 |
| TASK-0208 | UE Login fixture 准备 | ✅ merged | #111 |
| TASK-0209 | UE Login MVP — ULoginController + MockApi | ✅ merged | #111+#113 |
| TASK-0210 | UE e2e + 跨引擎一致性 | ✅ merged | #113 |
| TASK-0211 | Phase 2 出口 gate review | ✅ merged | #114 |

---

### TASK-0200: UMG Reflector 完整字段 + NamedSlot + NoDuplicateNodes

```yaml
title: UMG Reflector 完整实现
phase: 2
engine: unreal
depends_on: [TASK-0011, TASK-0135]
status: merged          # PR #102
pr: 102
goal: WalkChildren 完整实现（含 NamedSlot / 自定义容器）+ 测试
risk: high
```

---

### TASK-0201: StableId Resolver 三源优先级

```yaml
title: FStableIdResolver — UPROPERTY meta + ini + runtime
phase: 2
engine: unreal
depends_on: [TASK-0200]
status: merged          # PR #103
pr: 103
goal: LoadFromPropertyMeta + LoadFromIniRegistry + RegisterRuntime + 测试
risk: medium
```

---

### TASK-0202: SlateInputDriver — 4 动作 + GameThread marshal

```yaml
title: SlateInputDriver — FSlateApplication 事件注入
phase: 2
engine: unreal
depends_on: [TASK-0200]
status: merged          # PR #104
pr: 104
goal: Click/SendText/Drag/Scroll + DispatchToGameThread + OS 层 (Phase 4 补)
risk: high
notes: >
  v1.0 时 click/drag 新增 input_layer="os" (Win32/macOS/Linux) + key_press (PR #132)
```

---

### TASK-0203: WebSocket server — 连接上限 + negotiate_version

```yaml
title: uWS server 嵌入 UE plugin + subprotocol 校验
phase: 2
engine: unreal
depends_on: [TASK-0011]
status: merged          # PR #107
pr: 107
goal: 完整 WebSocket server (连接上限 + negotiate_version + 帧解析测试)
risk: high
```

---

### TASK-0204: Packaged build — AUTOAGENT_ENABLED + Shipping 零开销

```yaml
title: Shipping / Development packaged build 兼容
phase: 2
engine: unreal
depends_on: [TASK-0200, TASK-0201, TASK-0202, TASK-0203]
status: merged          # PR #106
pr: 106
goal: AUTOAGENT_ENABLED 宏 + Shipping build 零开销
risk: high
```

---

### TASK-0205: Editor module — Pin ID Detail Customization

```yaml
title: AutoAgentEditor module — Details Panel 定制 + 未 pin 扫描
phase: 2
engine: unreal
depends_on: [TASK-0201]
status: merged          # PR #108
pr: 108
goal: BindWidget Property Detail + AutoAgentIds.ini editor + scanner
risk: medium
```

---

### TASK-0206: UE 视觉回归集成 — compare_screenshot RPC + baseline 映射

```yaml
title: UE Screenshot Comparison Tool 接入框架视觉回归
phase: 2
engine: unreal
depends_on: [TASK-0204]
status: merged          # PR #110
pr: 110
goal: compare_screenshot RPC + baseline 路径映射 + CI
risk: medium
```

---

### TASK-0207: UE 防护验证 — 三层 CI 防护 UE 专项测试

```yaml
title: 防护 0.1 + 0.2 在 UE 故意触发验证 (56 个用例)
phase: 2
engine: unreal
depends_on: [TASK-0204]
status: merged          # PR #110
pr: 110
goal: .uasset deny + SetVisibility deny + AUTOAGENT_ALLOW_VISUAL 豁免
risk: medium
```

---

### TASK-0208: UE Login fixture 准备

```yaml
title: UE LoginMap + ULoginUserWidget C++ class
phase: 2
engine: unreal
depends_on: [TASK-0012]
status: merged          # PR #111
pr: 111
goal: UE 侧 login fixture 完整可用（manual 占位 → AI 脚手架）
mode: manual
risk: low
```

---

### TASK-0209: UE Login MVP — ULoginController + UMockApi

```yaml
title: AI 在 UE 实现 ULoginController（镜像 Unity TASK-0132）
phase: 2
engine: unreal
depends_on: [TASK-0200, TASK-0201, TASK-0202, TASK-0203, TASK-0204, TASK-0205, TASK-0206, TASK-0207, TASK-0208]
status: merged          # PR #111 + #113
pr: 111
goal: 同一份 task DSL 在 UE 跑通 login MVP
risk: high
max_iterations: 5
```

---

### TASK-0210: UE e2e + 跨引擎一致性

```yaml
title: UE e2e + 跨 Unity/UE 行为一致性比对 (2 scripts + 15 offline tests)
phase: 2
engine: unreal
depends_on: [TASK-0209]
status: merged          # PR #113
pr: 113
goal: 同 DSL 在两引擎产出相同行为
risk: medium
```

---

### TASK-0211: Phase 2 出口 gate review

```yaml
title: Phase 2 完成 review
phase: 2
engine: unreal
depends_on: [TASK-0210]
status: merged          # PR #114
pr: 114
goal: 人工签发 Phase 3 启动
mode: manual
risk: high
```
