# 99-tasks Phase 3 — Godot adapter 完整 + 三引擎一致

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。

## Phase 3 出口标准 (✅ 全部达成)

1. ✅ 三引擎完成 login MVP，同任务 DSL 行为一致
2. ✅ 三引擎视觉回归通过（各 baseline 独立维护）
3. ✅ Godot release export 反射 self-check 通过
4. ✅ 5 道防护在 Godot 全部生效

---

## 进度快照（最后更新：2026-05-24）

| Task | 标题 | 状态 | PR |
|---|---|---|---|
| TASK-0300 | ControlReflector 完整 + 防护测试 | ✅ merged | #115 |
| TASK-0301 | Stable ID manager | ✅ merged | #114 |
| TASK-0302 | Input driver — mouse_filter + parse_input_event | ✅ merged | #114 |
| TASK-0303 | WebSocket server + subprotocol | ✅ merged | #114 |
| TASK-0304 | ClassDB cache 自维护 | ✅ merged | #117 |
| TASK-0305 | Editor Plugin pin scanner | ✅ merged | #117 |
| TASK-0306 | 视觉回归集成 — compare_screenshot RPC | ✅ merged | #118 |
| TASK-0307 | Login fixture (login.tscn + LineEdit/Button) | ✅ merged | #119 |
| TASK-0308 | Login MVP — LoginController + MockApi | ✅ merged | #119 |
| TASK-0309 | Phase 3 出口 gate review | ✅ merged | #120 |

---

### TASK-0300: ControlReflector 完整 + 防护测试 54 个

```yaml
title: Godot ControlReflector 完整 (含 release export ClassDB cache)
phase: 3
engine: godot
depends_on: [TASK-0009, TASK-0211]
status: merged          # PR #115
pr: 115
goal: 全字段 dump + ClassDB cache + release export self-check
risk: medium
```

---

### TASK-0301: Stable ID manager — set_meta + Inspector pin

```yaml
title: Godot stable ID manager + mouse_filter 输入保护
phase: 3
engine: godot
depends_on: [TASK-0300]
status: merged          # PR #114
pr: 114
goal: set_meta API + Inspector 扩展 + Hash ID fallback
risk: low
```

---

### TASK-0302: Input driver — mouse_filter + parse_input_event

```yaml
title: Godot input driver — click/text/drag/scroll
phase: 3
engine: godot
depends_on: [TASK-0300]
status: merged          # PR #114
pr: 114
goal: mouse_filter 检查 + LineEdit + Drag + Scroll
notes: >
  v1.0 时新增 key_press 和 input_layer="os" (DisplayServer.cursor_set_position),
  对标 Unity/UE (PR #132)
risk: medium
```

---

### TASK-0303: WebSocket server — TCPServer + subprotocol

```yaml
title: Godot WebSocket server + subprotocol autoagent.v1
phase: 3
engine: godot
depends_on: [TASK-0009]
status: merged          # PR #114
pr: 114
goal: TCPServer accept + WebSocketPeer + subprotocol 校验 + poll
risk: medium
```

---

### TASK-0304: ClassDB cache — Release export 反射缺口对策

```yaml
title: Godot ClassDB cache 自维护 + self-check
phase: 3
engine: godot
depends_on: [TASK-0300]
status: merged          # PR #117
pr: 117
goal: build-time scanner 生成 class_db_cache.gd + release self-check
risk: high
```

---

### TASK-0305: Editor Plugin — Pin ID inspector + 未 pin scanner

```yaml
title: Godot Editor Plugin — Pin ID UI + scanner
phase: 3
engine: godot
depends_on: [TASK-0301]
status: merged          # PR #117
pr: 117
goal: Inspector 定制 + 未 pin 节点 scan
risk: low
```

---

### TASK-0306: 视觉回归集成 — compare_screenshot RPC + e2e

```yaml
title: Godot 视觉回归集成 — Image.compute_image_metrics + baseline
phase: 3
engine: godot
depends_on: [TASK-0303]
status: merged          # PR #118
pr: 118
goal: take_screenshot + compare_screenshot + 17 offline tests
risk: low
```

---

### TASK-0307: Login fixture — login.tscn (manual)

```yaml
title: Godot login.tscn 完整化 (LineEdit/Button 场景)
phase: 3
engine: godot
depends_on: [TASK-0010]
status: merged          # PR #119
pr: 119
goal: login.tscn + LineEdit + Button fixture
mode: manual
risk: low
```

---

### TASK-0308: Login MVP — AI 实现 LoginController + MockApi

```yaml
title: 同任务 DSL 在 Godot 跑通 login MVP
phase: 3
engine: godot
depends_on: [TASK-0300, TASK-0301, TASK-0302, TASK-0303, TASK-0304, TASK-0305, TASK-0306, TASK-0307]
status: merged          # PR #119
pr: 119
goal: AI 写 LoginController.gd + MockApi + autonomous loop
risk: high
max_iterations: 5
```

---

### TASK-0309: Phase 3 出口 + 三引擎一致性 gate review

```yaml
title: Phase 3 完成 review — 三引擎 login MVP 一致
phase: 3
engine: all
depends_on: [TASK-0308]
status: merged          # PR #120
pr: 120
goal: 三引擎 e2e 全绿 + 视觉回归 + 行为 trace 对比
mode: manual
risk: high
```
