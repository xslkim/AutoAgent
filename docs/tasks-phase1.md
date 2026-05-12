# 99-tasks Phase 1 — Unity adapter 完整 + login MVP

> 返回索引：[tasks.md](tasks.md)
> 字段说明见索引文档 §一。

## Phase 1 出口标准

1. AI Agent 完整 autonomous loop 跑通 login MVP
2. 防护 0.2 拦下 AI 在 .cs 写 visual 字段
3. 防护 0.1 拦下 AI 改 .unity 文件
4. 防护 0.3 dump 前后 visual diff 拦下故意写入
5. SSIM 视觉回归通过 login + welcome
6. 全程无人工敲键盘（除 review/approve PR）
7. AI 单任务平均迭代数 < 3
8. Cost tracking 正常工作

---

### Group A: Unity adapter — UI 反射完整化

---

### TASK-0100: UGUI 完整字段 dump

```yaml
title: UGuiReflector 实现 visual + behavior + meta 三类完整字段
phase: 1
engine: unity
depends_on: [TASK-0007]
goal: 让 dump_tree 输出符合 protocol/schema/node.json 的完整节点
output:
  - adapters/unity/Runtime/Reflection/UGuiReflector.cs (扩展)
  - adapters/unity/Runtime/Reflection/NodeSerializer.cs
  - adapters/unity/Tests/Runtime/NodeSerializerTests.cs
verification:
  - PlayMode 测试: dump 输出通过 protocol/schema/node.json JSON Schema 验证
  - 测试: visible / alpha / color / sprite_ref / interactable / event_handlers 全字段非空
mode: auto-with-review
risk: low
```

---

### TASK-0101: StableIdComponent + IdAllocator 实现

```yaml
title: Unity StableIdComponent + 自动 hash + pinned 优先
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 实现 stable ID 三种来源 (pinned / auto-hash / fallback)
output:
  - adapters/unity/Runtime/Meta/StableIdComponent.cs (MonoBehaviour + serialized fields)
  - adapters/unity/Runtime/Meta/IdAllocator.cs (启动时遍历, hash 算法)
  - adapters/unity/Tests/Runtime/IdAllocatorTests.cs
verification:
  - 测试: 已 pin 节点 stable_id_source = "pinned"
  - 测试: 未 pin 节点 stable_id_source = "hash"
  - 测试: hash ID 在重复 name 时加序号后缀
mode: auto-with-review
risk: low
```

---

### TASK-0102: Unity Editor Inspector for Pin ID

```yaml
title: StableIdInspector — Pin ID 编辑器 UI
phase: 1
engine: unity
depends_on: [TASK-0101]
goal: 美术 / 程序员能在 Unity Inspector 里 pin ID
output:
  - adapters/unity/Editor/AutoAgent.Editor.asmdef
  - adapters/unity/Editor/StableIdInspector.cs
  - adapters/unity/Editor/Tests/StableIdInspectorTests.cs
verification:
  - 在 Editor 里挂 StableIdComponent → Inspector 显示 Pin ID / Role / Intent / Tags 输入框
  - 输入 + apply → SerializeField 持久化
mode: auto-with-review
risk: low
```

---

### TASK-0103: OrphanTracker

```yaml
title: OrphanTracker — 持久化上次 dump ID 列表 + 当前 diff
phase: 1
engine: unity
depends_on: [TASK-0101]
goal: 实现 list_orphan_ids 功能
output:
  - adapters/unity/Runtime/Meta/OrphanTracker.cs
  - 持久化文件: Library/AutoAgent/last_scan.json (gitignore)
  - adapters/unity/Tests/Runtime/OrphanTrackerTests.cs
verification:
  - 测试: 第一次 dump → 无 orphan
  - 测试: pin 一个节点, 重启, dump → 该节点 found
  - 测试: 删除一个节点, 重启, dump → 该节点 in orphans
mode: auto-with-review
risk: low
```

---

### TASK-0104: link.xml + IL2CPP 验证

```yaml
title: IL2CPP link.xml 模板 + IL2CPP build 验证
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 保证 IL2CPP build 反射不被裁
output:
  - adapters/unity/Runtime/Resources/AutoAgent.link.xml
  - docs/users/il2cpp-setup.md (用户业务代码 link.xml 指南)
  - .github/workflows/unity-pr.yml (扩展, 加 IL2CPP build job)
verification:
  - CI: Mono build pass + IL2CPP build pass
  - IL2CPP 包跑 PocPlaygroundScene 4 动作全部成功
  - 包大小增量 < 5MB
mode: auto-with-review
risk: medium
```

---

### Group B: Unity adapter — 输入注入完整

---

### TASK-0105: EngineInputDriver — click 完整实现

```yaml
title: Click 模拟完整: PointerDown → Up → Click 序列
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 引擎事件层 click 在所有 Selectable 子类工作
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (Click 实现完整)
  - adapters/unity/Tests/Runtime/ClickTests.cs
verification:
  - 测试: Click → Button.onClick 触发
  - 测试: Click → Toggle.onValueChanged 触发
  - 测试: 节点未 AddComponent → 抛 -32002 WidgetNotInteractable
mode: auto-with-review
risk: low
```

---

### TASK-0106: EngineInputDriver — send_text

```yaml
title: send_text — TMP_InputField + 旧 InputField 兼容
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 send_text + clear_first
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (SendText 方法)
  - adapters/unity/Tests/Runtime/SendTextTests.cs
verification:
  - 测试: TMP_InputField 设值 + onValueChanged 触发
  - 测试: clear_first=true 清空旧值
  - 测试: 节点未 AddComponent input field → 抛 WidgetNotInteractable
mode: auto-with-review
risk: low
```

---

### TASK-0107: EngineInputDriver — drag 多帧序列

```yaml
title: Drag — OnBeginDrag → 多帧 OnDrag → OnEndDrag → OnDrop coroutine
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 drag, 分帧避免单帧 IDragHandler 实现出问题
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (Drag 实现)
  - adapters/unity/Tests/Runtime/DragTests.cs
verification:
  - 测试: drag_source → drag_target, IDropHandler 触发
  - 测试: duration_ms 分帧数正确
mode: auto-with-review
risk: medium
```

---

### TASK-0108: EngineInputDriver — scroll

```yaml
title: Scroll — ScrollRect 滚动
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 scroll
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (Scroll 实现)
  - adapters/unity/Tests/Runtime/ScrollTests.cs
verification:
  - 测试: scroll down → ScrollRect.normalizedPosition 正确变化
  - 测试: 节点未 AddComponent<ScrollRect> → 抛 WidgetNotInteractable
mode: auto-with-review
risk: low
```

---

### TASK-0109: EngineInputDriver — key_press

```yaml
title: Key press — Unity Input 事件 + EventSystem 转发
phase: 1
engine: unity
depends_on: [TASK-0105]
goal: 实现 key_press
output:
  - adapters/unity/Runtime/Input/EngineInputDriver.cs (KeyPress 实现)
  - adapters/unity/Tests/Runtime/KeyPressTests.cs
verification:
  - 测试: 按 Enter → InputField.onSubmit 触发
  - 测试: 按 Tab → 焦点切换
mode: auto-with-review
risk: low
```

---

### Group C: 截图 + wait

---

### TASK-0110: ScreenshotCapturer

```yaml
title: ScreenshotCapturer — fullscreen / node / rect 三模式
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 实现 take_screenshot
output:
  - adapters/unity/Runtime/Screenshot/ScreenshotCapturer.cs
  - adapters/unity/Tests/Runtime/ScreenshotTests.cs
verification:
  - 测试: fullscreen 截图非空 (非黑屏)
  - 测试: node 模式截单个节点 bounds 正确
  - 输出 PNG / JPG 都正确
mode: auto-with-review
risk: medium
```

---

### TASK-0111: wait_for

```yaml
title: wait_for — widget_appeared / disappeared / visible / text_changed
phase: 1
engine: unity
depends_on: [TASK-0100]
goal: 实现 wait_for 条件等待
output:
  - adapters/unity/Runtime/Server/WaitConditions.cs
  - adapters/unity/Tests/Runtime/WaitForTests.cs
verification:
  - 测试: widget_appeared 等到节点可见
  - 测试: text_changed 等到文本变化
  - 测试: 超时返回 -32005 TimeoutError
mode: auto-with-review
risk: low
```

---

### Group D: 协议完整

---

### TASK-0112: 完整协议 method 路由

```yaml
title: ProtocolHandler — JSON-RPC dispatcher 完整版
phase: 1
engine: unity
depends_on: [TASK-0100, TASK-0105, TASK-0110, TASK-0111]
goal: 路由所有 wire protocol method 到对应实现
output:
  - adapters/unity/Runtime/Server/JsonRpcDispatcher.cs
  - adapters/unity/Runtime/Server/ProtocolHandler.cs (完整路由)
  - adapters/unity/Tests/Runtime/DispatcherTests.cs
verification:
  - 测试: 全部 wire method 路由正确
  - 测试: 未知 method → -32601 MethodNotFound
mode: auto-with-review
risk: low
```

---

### TASK-0113: 完整错误码 + GameThread marshaling

```yaml
title: 错误码完整 + 跨线程调用引擎 API marshal 到主线程
phase: 1
engine: unity
depends_on: [TASK-0112]
goal: 所有 error codes 实现; WebSocket 线程消息 marshal 到 main thread
output:
  - adapters/unity/Runtime/Server/MainThreadDispatcher.cs
  - adapters/unity/Runtime/Server/ErrorCodes.cs
  - adapters/unity/Tests/Runtime/ThreadMarshallingTests.cs
verification:
  - 测试: WebSocket 线程发消息, 引擎 API 调用全部在 main thread
  - 测试: 所有错误码都有 enum + 测试覆盖
mode: auto-with-review
risk: medium
```

---

### TASK-0114: 事件流 emit

```yaml
title: 事件 notification — scene_changed / widget_appeared / disappeared / clicked / text_changed
phase: 1
engine: unity
depends_on: [TASK-0112]
goal: 实现事件流推送
output:
  - adapters/unity/Runtime/Server/EventEmitter.cs
  - adapters/unity/Runtime/Reflection/SceneChangeWatcher.cs
  - adapters/unity/Runtime/Reflection/WidgetLifecycleWatcher.cs
  - adapters/unity/Tests/Runtime/EventStreamTests.cs
verification:
  - 测试: 切场景 → scene_changed 推送
  - 测试: 新节点出现 → widget_appeared 推送
  - 测试: 输入框文本变化 → text_changed 推送
mode: auto-with-review
risk: medium
```

---

### TASK-0116: pin_id / list_orphan_ids wire 实现

```yaml
title: pin_id / list_orphan_ids wire method 实现
phase: 1
engine: unity
depends_on: [TASK-0103, TASK-0112]
goal: 暴露 pin / orphan 功能给 wire protocol
output:
  - adapters/unity/Runtime/Meta/PinIdHandler.cs
  - adapters/unity/Tests/Runtime/PinIdTests.cs
verification:
  - 测试: pin_id 调用后, 重新 dump 该节点 stable_id_source = "pinned"
  - 测试: list_orphan_ids 返回正确 orphan 列表
mode: auto-with-review
risk: low
```

---

### Group E: MCP Server 完整

---

### TASK-0117: MCP tool 完整实现 — wire dispatcher

```yaml
title: MCP tools 全部连真实 wire protocol (不再 dummy)
phase: 1
engine: none
depends_on: [TASK-0002, TASK-0112]
goal: MCP tools 全部实现, 调用 wire method
output:
  - mcp-server/src/autoagent_mcp/connector/websocket_client.py
  - mcp-server/src/autoagent_mcp/tools/dump.py / click.py / text.py / etc.
  - mcp-server/tests/test_tools.py (mock adapter 跑全部 tool)
verification:
  - pytest mcp-server/tests/test_tools.py -v 全绿
  - 用 fake adapter 跑通全套 tools
mode: auto-with-review
risk: medium
```

---

### TASK-0118: connect_engine / disconnect / session 管理

```yaml
title: Session 管理 — 单连接 + heartbeat + 重连
phase: 1
engine: none
depends_on: [TASK-0117]
goal: MCP server 连 adapter 的 session lifecycle
output:
  - mcp-server/src/autoagent_mcp/connector/session.py
  - mcp-server/src/autoagent_mcp/connector/heartbeat.py
  - mcp-server/tests/test_session.py
verification:
  - 测试: connect_engine 成功后 heartbeat 30s 一次
  - 测试: 连接断开 → 自动重连 5 次退避
mode: auto-with-review
risk: medium
```

---

### TASK-0119: 自动重连 + 错误处理

```yaml
title: 错误透传 + adapter 崩溃恢复
phase: 1
engine: none
depends_on: [TASK-0118]
goal: adapter 错误透传给 AI; adapter 崩溃返回 EngineDisconnected
output:
  - mcp-server/src/autoagent_mcp/connector/error_handler.py
  - mcp-server/tests/test_error_recovery.py
verification:
  - 测试: adapter 返回 -32001 → MCP tool 返回结构化 error
  - 测试: adapter 进程 kill → 下一个 tool call 返回 EngineDisconnected
mode: auto-with-review
risk: low
```

---

### TASK-0120: 日志规范实现

```yaml
title: 结构化 JSON 日志 + 文件 rotate
phase: 1
engine: none
depends_on: [TASK-0117]
goal: 实现 02-mcp-server.md §六 日志规范
output:
  - mcp-server/src/autoagent_mcp/logging.py
  - mcp-server/tests/test_logging.py
verification:
  - 测试: 每个 tool call 生成 JSON 日志
  - 测试: 文件 rotate 50MB × 5
mode: auto-with-review
risk: low
```

---

### TASK-0121: 配置文件加载

```yaml
title: ~/.autoagent/config.toml 加载 + 校验
phase: 1
engine: none
depends_on: [TASK-0117]
goal: 实现 02-mcp-server.md §七 配置加载
output:
  - mcp-server/src/autoagent_mcp/config.py
  - mcp-server/tests/test_config.py
verification:
  - 测试: 默认配置加载 ok
  - 测试: 非法配置抛 ValidationError
mode: auto-with-review
risk: low
```

---

### Group F: 视觉回归实现

---

### TASK-0122: SSIM 实现

```yaml
title: scikit-image SSIM 视觉对比
phase: 1
engine: none
depends_on: [TASK-0117]
goal: 实现 SSIM diff (MVP, 不含 LPIPS)
output:
  - mcp-server/src/autoagent_mcp/vision/comparator.py
  - mcp-server/src/autoagent_mcp/vision/diff_image.py
  - mcp-server/tests/test_vision_ssim.py
verification:
  - 测试: 同图 SSIM = 1.0
  - 测试: 已知 95% similar 图 SSIM ≥ 0.95
  - LPIPS 关键字检查不存在 (MVP 不含)
mode: auto-with-review
risk: low
```

---

### TASK-0123: compare_to_baseline tool

```yaml
title: MCP tool compare_to_baseline 实现
phase: 1
engine: none
depends_on: [TASK-0122]
goal: 暴露视觉对比给 AI
output:
  - mcp-server/src/autoagent_mcp/tools/vision.py
  - mcp-server/tests/test_compare_tool.py
verification:
  - 测试: 同图返回 pass=true
  - 测试: 阈值以下返回 pass=false 且生成 diff_path
mode: auto-with-review
risk: low
```

---

### TASK-0124: take_screenshot tool 端到端

```yaml
title: MCP take_screenshot 串到 adapter
phase: 1
engine: unity
depends_on: [TASK-0110, TASK-0117]
goal: AI 端能调 take_screenshot 拿到引擎截图文件
output:
  - mcp-server/src/autoagent_mcp/tools/screenshot.py
  - mcp-server/tests/integration/test_take_screenshot.py
verification:
  - 集成测试: 起 Unity adapter mock, MCP 端调用 → 拿到 PNG 文件
mode: auto-with-review
risk: low
```

---

### TASK-0125: audit_visual_changes tool — dump diff

```yaml
title: MCP audit_visual_changes — 缓存 dump + diff visual 字段
phase: 1
engine: none
depends_on: [TASK-0117]
goal: AI 自检"我有没有不小心改了视觉"
output:
  - mcp-server/src/autoagent_mcp/tools/audit.py
  - mcp-server/src/autoagent_mcp/state/dump_cache.py
  - mcp-server/tests/test_audit_tool.py
verification:
  - 测试: 两次 dump 一致 → 无 diff
  - 测试: visual 字段变化 → 列出节点 + 字段
mode: auto-with-review
risk: low
```

---

### TASK-0126: Claude Vision 二次裁决（可选）

```yaml
title: SSIM 报警时调 Claude Vision 二次裁决
phase: 1
engine: none
depends_on: [TASK-0122, TASK-0121]
goal: 实现 06 §5.5 LLM 二次裁决
output:
  - mcp-server/src/autoagent_mcp/vision/llm_judge.py
  - mcp-server/tests/test_llm_judge.py (mock Anthropic API)
verification:
  - 测试: ssim ≥ 0.95 → 跳过 LLM
  - 测试: ssim < 0.92 → 调用 LLM 返回 verdict + reason
mode: auto-with-review
risk: medium
```

---

### Group G: AI Operating Contract 实施

---

### TASK-0127: 路径白名单 yml 完整规则

```yaml
title: scripts/ci/path_whitelist.yml 完整规则
phase: 1
engine: none
depends_on: [TASK-0003]
goal: path_whitelist.yml 完全对齐文档规则
output:
  - scripts/ci/path_whitelist.yml (完整版)
  - scripts/ci/check_changed_paths.py (扩展)
  - scripts/ci/tests/test_check_paths_full.py
verification:
  - 全部 ✅ / ❌ 路径用例覆盖
  - PR body 含 path_exception YAML 时正确豁免
mode: auto-with-review
risk: medium
```

---

### TASK-0128: 源码 diff 审计完整规则 (Unity C#)

```yaml
title: visual_write_rules.yml — Unity C# 完整禁字段
phase: 1
engine: none
depends_on: [TASK-0004]
goal: visual_write_rules.yml 覆盖 06 §2.2 全部 Unity 禁字段
output:
  - scripts/ci/visual_write_rules.yml (Unity 部分完整)
  - scripts/ci/audit_visual_writes.py (扩展)
  - scripts/ci/tests/test_audit_unity_full.py
verification:
  - pytest 全绿
  - 抓得到 image.color =, transform.position =, rt.anchoredPosition =, SetActive(false)
  - AUTOAGENT_ALLOW_VISUAL 注释豁免生效
mode: auto-with-review
risk: medium
```

---

### TASK-0129: AI agent CLI 工具

```yaml
title: autoagent CLI — start / stop / reset / status
phase: 1
engine: none
depends_on: [TASK-0121]
goal: 实现 07 §8 紧急停机 + §9 人工恢复用 CLI
output:
  - mcp-server/src/autoagent_mcp/cli.py (扩展)
verification:
  - autoagent-stop 写 STOP 文件
  - autoagent-status 显示当前 session 状态
mode: auto-with-review
risk: medium
```

---

### TASK-0130: Cost tracking + daily report

```yaml
title: Cost tracking — Anthropic API 用量计 + EOD 报告
phase: 1
engine: none
depends_on: [TASK-0120]
goal: 实现 07 §2.2 / §7.1 cost tracking
output:
  - mcp-server/src/autoagent_mcp/cost_tracker.py
  - 输出: ~/.autoagent/cost-daily.csv
verification:
  - 测试: 模拟 token 用量, cost 计算正确
  - 测试: session 上限触达 → session 停
mode: auto-with-review
risk: medium
```

---

### Group H: Login MVP 验收

---

### TASK-0131: Login fixture 完整性确认（手动）

```yaml
title: TASK-0008 的 LoginScene 完整性确认
phase: 1
engine: unity
depends_on: [TASK-0008b]
goal: 确认 LoginScene 满足 MVP 验收要求；fixture 完全不含交互控件
output:
  - 所有元素 pin ID + LogicalRole + state_sprites 完整
verification:
  - dump_tree 输出所有 pinned ID 且 LogicalRole 非空
  - dump_tree type 字段：所有非容器节点都是 Image / TMP_Text
  - behavior.attached_components 在所有节点上为空数组
mode: manual
risk: low
path_exception: ["fixtures/unity-test-project/Assets/Scenes/LoginScene.unity"]
```

---

### TASK-0132: AI Agent 实现 LoginController.cs

```yaml
title: MVP 任务 — AI 写 LoginController 实现登录交互（含 AddComponent 控件）
phase: 1
engine: unity
depends_on: [TASK-0117, TASK-0118, TASK-0119, TASK-0120, TASK-0121, TASK-0122, TASK-0123, TASK-0124, TASK-0125, TASK-0126, TASK-0127, TASK-0128, TASK-0129, TASK-0130, TASK-0131]
goal: 给 Claude Code 任务 DSL, autonomous loop 实现 login 功能
output:
  - fixtures/unity-test-project/Scripts/LoginController.cs (AI 实现)
  - fixtures/unity-test-project/Scripts/MockApi.cs
  - fixtures/unity-test-project/Scripts/Tests/LoginControllerTests.cs
  - docs/canonical-tasks/login.yaml (任务 DSL)
verification:
  - 源码 diff 审计通过（防护 0.2）
  - dump_before vs dump_after：visual 字段完全一致
  - after 中 attached_components 包含 TMP_InputField / Button
  - AI 在 ≤ 5 iterations 内完成
  - e2e: send_text → click → mock 收到 POST → welcome_text 出现
  - PR 自动 open + 全部 CI step 绿
mode: auto-with-review
risk: high
max_iterations: 5
```

---

### TASK-0133: e2e 测试 — login 流程

```yaml
title: e2e — Unity headless 跑 login 完整流程
phase: 1
engine: unity
depends_on: [TASK-0132]
goal: CI 端到端跑 login 验证
output:
  - fixtures/unity-test-project/Scripts/Tests/E2ELoginRunner.cs
  - scripts/e2e/unity_login.sh
verification:
  - bash scripts/e2e/unity_login.sh 退出码 0
  - 日志包含: send_text 成功 / click 成功 / mock API 收到 POST
mode: auto-with-review
risk: medium
```

---

### TASK-0134: 视觉回归 baseline + 比对

```yaml
title: Login 视觉回归 — baseline + compare 全流程
phase: 1
engine: unity
depends_on: [TASK-0133, TASK-0123, TASK-0132]
goal: 创建 welcome_screen baseline 并做视觉回归验证
output:
  - baselines/unity/windows/welcome_screen.png + .meta.json
verification:
  - welcome_screen.png 人工 review approve
  - SSIM ≥ 0.95 → CI green
  - 故意改 fixture 让视觉变化 → CI fail + diff 图生成
mode: auto-with-review
risk: high
max_iterations: 1
path_exception: ["baselines/unity/windows/welcome_screen.png", "baselines/unity/windows/welcome_screen.meta.json"]
```

---

### TASK-0135: Phase 1 出口 gate review（手动）

```yaml
title: Phase 1 出口 review — login MVP + 5 道防护
phase: 1
engine: unity
depends_on: [TASK-0132, TASK-0133, TASK-0134, TASK-0128]
goal: 人工签发 Phase 1 完成
output:
  - docs/phase1-gate-report.md
verification:
  - Gate 1: TASK-0132 完整 autonomous loop
  - Gate 2: 防护 0.2 拦下故意 visual 写入
  - Gate 3: 防护 0.1 拦下故意改 .unity
  - Gate 4: 防护 0.3 dump 前后 diff 验证
  - Gate 5: SSIM 视觉回归通过
  - Gate 6: 全程无人工敲键盘
  - 任意一项 fail → Phase 2 不启动
mode: manual
risk: high
```
