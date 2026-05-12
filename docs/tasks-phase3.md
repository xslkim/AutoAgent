# 99-tasks Phase 3 — Godot adapter 完整

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。
> Phase 3 启动前 (Phase 2 完成后) 必须重新拆 anchor 为 PR-sized task。下面是 anchor 列表。

## Phase 3 出口标准

1. 三引擎完成 login MVP，同任务 DSL 行为一致
2. 三引擎视觉回归通过（各 baseline 独立维护）
3. Godot release export 反射 self-check 通过
4. 5 道防护在 Godot 全部生效

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
mode: manual
risk: high
```
