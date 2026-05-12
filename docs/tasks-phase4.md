# 99-tasks Phase 4 — OS 输入 + LPIPS + 优化 + v1.0

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。
> Phase 4 启动前 (Phase 3 完成后) 必须重新拆 anchor 为 PR-sized task。下面是 anchor 列表。

## Phase 4 出口标准

1. OS 输入双轨可用（三平台）
2. LPIPS 子进程化 + 内存隔离生效
3. 大场景（1000+ 节点）性能达标
4. Stress test nightly 全绿
5. v1.0 changelog + migration guide 完成
6. 文档与实际实现 sync 完成

---

### TASK-0115: 高级反射 method 实现 + 视觉写入拒绝

> 从 Phase 1 移至 Phase 4，与 [02-mcp-server.md](02-mcp-server.md) MCP tool 分组一致。

```yaml
title: invoke_method / get_property / set_property wire method 实现 + MCP tool 暴露
phase: 4
engine: unity
depends_on: [TASK-0112]
status: anchor
goal: 实现 invoke_method / get_property / set_property; visual 字段写入抛 -32003
output:
  - adapters/unity/Runtime/Reflection/ScriptInvoker.cs
  - adapters/unity/Runtime/Reflection/PropertyAccessor.cs (含 category 校验)
  - mcp-server/src/autoagent_mcp/tools/reflection.py (MCP tool 暴露)
  - adapters/unity/Tests/Runtime/PropertyAccessorTests.cs
verification:
  - 测试: invoke_method 调用 MonoBehaviour 公开方法成功
  - 测试: get_property 读 behavior 字段成功
  - 测试: set_property category=behavior → 成功
  - 测试: set_property category=visual → 抛 -32003 VisualPropertyWrite
risk: medium
```

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
mode: manual
risk: low
```
