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

## 进度快照（最后更新：2026-05-23）

| Task | 标题 | 状态 | PR |
|---|---|---|---|
| TASK-0115 | invoke_method / get_property / set_property | ✅ merged | #121 |
| TASK-0400 | Windows SendInput OS 层输入驱动 | 🔶 pr-open | #125 |
| TASK-0401 | macOS CGEventPost | ⬜ anchor | — |
| TASK-0402 | Linux uinput / XTest | ⬜ anchor | — |
| TASK-0403 | LPIPS subprocess 化 | ✅ merged | #122 |
| TASK-0404 | Claude Vision 裁决稳定化 | ✅ merged | #123 |
| TASK-0405C | MCP 层 dump_tree_delta delta cache | ✅ merged | #124 |
| TASK-0405 | 增量 dump 协议 v0.2（三引擎 adapter） | ⬜ anchor | — |
| TASK-0406 | 大场景 dump 性能优化 | ⬜ anchor | — |
| TASK-0407 | 三引擎大场景 stress test + nightly | ⬜ anchor | — |
| TASK-0408 | v1.0 release prep | ⬜ anchor | — |
| TASK-0409 | 文档 review + final polish | ⬜ anchor | — |

---

### TASK-0115: 高级反射 method 实现 + 视觉写入拒绝

```yaml
title: invoke_method / get_property / set_property wire method 实现 + MCP tool 暴露
phase: 4
engine: unity
depends_on: [TASK-0112]
status: merged          # PR #121 — 2026-05-22
pr: 121
goal: 实现 invoke_method / get_property / set_property; visual 字段写入抛 -32003
output:
  - adapters/unity/Runtime/Reflection/ScriptInvoker.cs
  - adapters/unity/Runtime/Reflection/PropertyAccessor.cs (含 category 校验)
  - mcp-server/src/autoagent_mcp/tools/reflect.py (MCP tool 暴露)
  - adapters/unity/Tests/Runtime/PropertyAccessorTests.cs
verification:
  - 测试: invoke_method 调用 MonoBehaviour 公开方法成功
  - 测试: get_property 读 behavior 字段成功
  - 测试: set_property category=behavior → 成功
  - 测试: set_property category=visual → 抛 -32003 VisualPropertyWrite
notes: >
  EventStreamTests 4 条失败根因：Spawn() 缺 typeof(RectTransform)，
  DumpActiveScene() 跳过无 RectTransform 的节点。修复后 CI 全绿。
risk: medium
```

---

### TASK-0403: LPIPS subprocess 化

```yaml
title: LPIPS PyTorch 子进程隔离
phase: 4
engine: none
depends_on: [TASK-0309]
status: merged          # PR #122 — 2026-05-22
pr: 122
output:
  - mcp-server/src/autoagent_mcp/vision/lpips_worker.py   (子进程入口)
  - mcp-server/src/autoagent_mcp/vision/lpips_subprocess.py (IPC + singleton)
  - mcp-server/src/autoagent_mcp/tools/visual.py           (新增 compare_lpips_to_baseline)
  - mcp-server/tests/test_lpips_subprocess.py              (28 tests)
verification:
  - pytest tests/test_lpips_subprocess.py → 28/28 passed
  - pytest tests/ → 全绿
notes: >
  CI tool count 25→26，mcp-pr.yml / test_server_starts.py 同步更新。
  LpipsProcess singleton: threading.Lock, atexit shutdown, auto-restart on crash.
risk: medium
```

---

### TASK-0404: Claude Vision 多模态裁决稳定化

```yaml
title: LLM 二次裁决产品化
phase: 4
engine: none
depends_on: [TASK-0403]
status: merged          # PR #123 — 2026-05-22
pr: 123
output:
  - mcp-server/src/autoagent_mcp/vision/claude_judge.py   (重写)
  - mcp-server/src/autoagent_mcp/tools/judge.py           (重写)
  - mcp-server/tests/test_claude_judge.py                 (50 tests)
verification:
  - pytest tests/test_claude_judge.py → 50/50 passed
  - pytest tests/ → 全绿
notes: >
  新增：重试（指数退避）、max_per_session 限额、结果缓存（keyed by path+size+mtime+model）。
  global _session_count 必须在函数体最顶部声明（Python SyntaxError 陷阱）。
  JudgeResult 新增 skipped / skip_reason 字段。
risk: low
```

---

### TASK-0405C: MCP 层 dump_tree_delta delta cache

```yaml
title: MCP 层 dump_tree_delta：in-memory snapshot + delta cache
phase: 4
engine: none
depends_on: []
status: merged          # PR #124 — 2026-05-22
pr: 124
output:
  - mcp-server/src/autoagent_mcp/tree_cache.py            (TreeCache + DeltaResult)
  - mcp-server/src/autoagent_mcp/tools/dump.py            (新增 dump_tree_delta tool)
  - mcp-server/src/autoagent_mcp/tools/__init__.py        (TOOL_NAMES → 27)
  - mcp-server/tests/test_tree_cache.py                   (29 tests)
  - mcp-server/tests/test_server_starts.py                (EXPECTED_COUNT=27)
  - .github/workflows/mcp-pr.yml                         (grep '^27)
verification:
  - pytest tests/test_tree_cache.py → 29/29 passed
  - pytest tests/ → 445/445 passed
notes: >
  不动三引擎 adapter，仅在 MCP 层实现 snapshot 比对。
  store() 生成 secrets.token_hex(4)（8 hex），LRU 保留最近 20 条。
  diff() 返回 changed / removed_ids / unchanged_count / full_snapshot。
  tool count 26→27。
risk: low
```

---

### TASK-0400: OS 级输入 — Windows SendInput

```yaml
title: Windows SendInput native plugin
phase: 4
engine: unity          # Unity 侧实现；UE/Godot 待后续 anchor
depends_on: []
status: pr-open        # PR #125 — 待合并，CI 运行中
pr: 125
output:
  - adapters/unity/Runtime/Input/Win32InputDriver.cs      (新增)
  - adapters/unity/Runtime/Input/EngineInputDriver.cs     (click/drag/key_press 加 inputLayer)
  - adapters/unity/Runtime/Server/ProtocolHandler.cs      (提取 input_layer / button)
  - adapters/unity/Runtime/AutoAgentBootstrap.cs          (RunDrag 加 inputLayer)
  - adapters/unity/Tests/Runtime/Win32InputDriverTests.cs (新增)
  - mcp-server/src/autoagent_mcp/tools/click.py           (三工具透传 input_layer)
  - mcp-server/tests/test_click_input_layer.py            (15 tests)
verification:
  - pytest tests/test_click_input_layer.py → 15/15 passed
  - pytest tests/ → 460/460 passed
  - Unity 手动：Play Mode 发 input_layer="os" click → 系统光标肉眼可见跳到节点位置
pending_manual_verification: |
  1. Unity Editor 打开项目，Console 无编译错误
  2. Test Runner → PlayMode → 全绿（回归）
  3. 在 Windows 上发 input_layer="os" click，观察鼠标光标移动
  注意：窗口化 Editor 可能有坐标偏移（ClientToScreen 拿到的是 Editor 主窗口）；
        Game View 最大化时偏移最小，验证时推荐此模式。
notes: >
  Win32InputDriver 用 #if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN 保护；
  非 Windows 平台所有方法抛 WireException(-32603) stub，编译不报错。
  ToAbsolute()：Unity 底左原点 → Win32 ABSOLUTE (0-65535)，通过
  ClientToScreen + Y-flip + 虚拟屏幕缩放处理窗口偏移和多显示器。
  默认 input_layer="engine" 不写入 wire params，向后兼容旧 adapter。
risk: medium
```

---

### TASK-0401: OS 级输入 — macOS CGEventPost

```yaml
title: macOS native plugin
phase: 4
engine: all
depends_on: [TASK-0400]
status: anchor
risk: medium
```

---

### TASK-0402: OS 级输入 — Linux uinput / XTest

```yaml
title: Linux native plugin
phase: 4
engine: all
depends_on: [TASK-0400]
status: anchor
risk: medium
```

---

### TASK-0405: 增量 dump (协议 v0.2)

```yaml
title: 协议 v0.2 — 节点增量更新, 减少 token
phase: 4
engine: all
depends_on: [TASK-0309]
status: anchor          # MCP 层已有 0405C 作为低风险先行版
notes: >
  TASK-0405C 已在 MCP 层实现 delta cache（不改协议/adapter）。
  完整 TASK-0405 需三引擎 adapter 支持增量推送（高风险，高工作量）。
risk: high
```

---

### TASK-0406: 性能优化 — 大场景 dump

```yaml
title: 1000+ 节点场景 dump < 100ms
phase: 4
engine: all
depends_on: [TASK-0405]
status: anchor
risk: medium
```

---

### TASK-0407: 三引擎大场景 stress test

```yaml
title: stress test 套件 + CI nightly
phase: 4
engine: all
depends_on: [TASK-0406]
status: anchor
risk: medium
```

---

### TASK-0408: v1.0 release prep

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

### TASK-0409: 文档 review + final polish

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
