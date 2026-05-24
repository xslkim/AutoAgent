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

## 进度快照（最后更新：2026-05-24 — v1.0 final）

| Task | 标题 | 状态 | PR |
|---|---|---|---|
| TASK-0115 | invoke_method / get_property / set_property | ✅ merged | #121 |
| TASK-0400 | Windows SendInput OS 层输入驱动 | ✅ merged | #125 |
| TASK-0401 | macOS CGEventPost | ✅ merged | #126 |
| TASK-0402 | Linux uinput / XTest | ✅ merged | #126 |
| TASK-0403 | LPIPS subprocess 化 | ✅ merged | #122 |
| TASK-0404 | Claude Vision 裁决稳定化 | ✅ merged | #123 |
| TASK-0405C | MCP 层 dump_tree_delta delta cache | ✅ merged | #124 |
| TASK-0405 | 增量 dump v0.2 (Unity adapter TreeCache) | ✅ merged | #130 |
| TASK-0406 | 大场景 dump 性能优化 (fast hash + stress) | ✅ merged | #131 |
| TASK-0407 | Stress test 13 cases | ✅ merged | #131 |
| TASK-0408 | v1.0 release prep | ✅ merged | #127 |
| TASK-0409 | 文档 review + final polish | ✅ merged | #128 |
| UE+Godot OS | UE C++ 三平台 + Godot GDScript OS 层 | ✅ merged | #132 |
| TASK-0408 | v1.0 release prep | ✅ merged | #127 |
| TASK-0409 | 文档 review + final polish | ✅ merged | #128 |

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
status: merged          # PR #125 — 2026-05-23
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
title: macOS CGEventPost native plugin
phase: 4
engine: unity
depends_on: [TASK-0400]
status: merged          # PR #126 — 2026-05-23
pr: 126
goal: 实现 macOS CGEventPost OS 层输入驱动
output:
  - adapters/unity/Assets/AutoAgent/Runtime/Input/MacInputDriver.cs (新增)
  - adapters/unity/Assets/AutoAgent/Runtime/Input/EngineInputDriver.cs (#if OSX dispatch)
  - adapters/unity/Assets/AutoAgent/Tests/Runtime/MacInputDriverTests.cs (新增)
verification:
  - CGKeyCode constants + MapKey + platform guard test 跨平台可跑
  - macOS-only ToScreenPoint 测试 (Assume → Assert.Ignore)
notes: >
  CoreGraphics CGEventPost API: CGEventCreateMouseEvent / CGEventCreateKeyboardEvent /
  CGEventCreateScrollWheelEvent + CGEventPost(kCGHIDEventTap) + CFRelease。
  PostAndRelease helper 模式。Drag 使用 CGEventLeftMouseDragged。
  macOS 10.14+ 需要辅助功能权限。
risk: medium
```

---

### TASK-0402: OS 级输入 — Linux XTest

```yaml
title: Linux X11 XTest native plugin
phase: 4
engine: unity
depends_on: [TASK-0400]
status: merged          # PR #126 — 2026-05-23
pr: 126
goal: 实现 Linux X11 XTest OS 层输入驱动
output:
  - adapters/unity/Assets/AutoAgent/Runtime/Input/LinuxInputDriver.cs (新增)
  - adapters/unity/Assets/AutoAgent/Runtime/Input/EngineInputDriver.cs (#if LINUX dispatch)
  - adapters/unity/Assets/AutoAgent/Tests/Runtime/LinuxInputDriverTests.cs (新增)
verification:
  - X11 keycode constants + MapKey + platform guard test 跨平台可跑
  - Linux-only ToX11Coords 测试 (Assume → Assert.Ignore)
notes: >
  libX11.so.6 + libXtst.so.6 P/Invoke。持久 X11 Display 连接（lazy-init + lock）。
  XTestFakeMotionEvent / XTestFakeButtonEvent / XTestFakeKeyEvent + XFlush。
  Scroll 通过 X11 button 4 (up) / button 5 (down) 模拟。
risk: medium
```

---

### TASK-0405: 增量 dump (协议 v0.2)

```yaml
title: 协议 v0.2 — 节点增量更新, 减少 token
phase: 4
engine: all
depends_on: [TASK-0309]
status: merged          # PR #130 — 2026-05-24
pr: 130
goal: Unity adapter TreeCache + dump_tree_delta wire protocol + MCP fallback
notes: >
  TreeCache.cs (SHA256→FNV-1a hash, LRU eviction), ProtocolHandler dump_tree_delta,
  negotiate_version capabilities, MCP dump.py feature detection + fallback.
risk: high
```

---

### TASK-0406: 性能优化 — 大场景 dump

```yaml
title: 1000+ 节点场景 dump < 100ms
phase: 4
engine: all
depends_on: [TASK-0405]
status: merged          # PR #131 — 2026-05-24
pr: 131
goal: FNV-1a fast hash + List pre-allocation + stress test 13 cases
risk: medium
```

---

### TASK-0407: 三引擎大场景 stress test

```yaml
title: stress test 套件 + CI nightly
phase: 4
engine: all
depends_on: [TASK-0406]
status: merged          # PR #131 — 2026-05-24
pr: 131
goal: test_tree_cache_stress.py 13 cases + stress_dump_tree.py benchmark
risk: medium
```

---

### TASK-0408: v1.0 release prep

```yaml
title: changelog + migration guide + tag
phase: 4
engine: none
depends_on: [TASK-0400, TASK-0401, TASK-0402, TASK-0403, TASK-0405, TASK-0406]
status: merged          # PR #127 + #128 — 2026-05-23
pr: 127
includes:
  - CHANGELOG.md 初版 (v1.0.0 — 三引擎 + 五道防护 + 三平台 OS 输入)
  - docs/migration/v0.x-to-v1.0.md (10 项 breaking/新增变更)
  - scripts/release.sh (SemVer tag 自动化)
  - docs/quickstart.md (5 分钟上手指南)
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
status: merged          # PR #128 — 2026-05-23
pr: 128
includes:
  - quickstart.md 创建 + ARCHITECTURE.md 文档导航更新
  - tasks.md / tasks-phase4.md 任务状态同步
  - 0405/0406/0407 标记 v1.1
  - 00-08 深度勘误 + API reference 自动生成 → v1.1
mode: manual
risk: low
```
