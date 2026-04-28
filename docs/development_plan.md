# AutoVisionTest 开发计划 — 闭环 MVP 收尾

文档日期：2026-04-28
对应版本：紧随 product_document v2.2
当前里程碑：Phase 1 / MVP（§2.2 记事本闭环 demo）

---

## 0. 文档目的

本文档基于一次完整的代码审计（read-only），梳理当前实现与 `product_document.md` 的差距，并按"先跑通闭环 → 再补稳定性 → 最后做工程优化"分三阶段制定开发计划。

每一项任务都给出：
- **缺口描述**：现状 vs 目标
- **影响**：阻塞哪个用户路径
- **修改位置**：具体文件与函数
- **验收标准**：怎么算做完

---

## 1. 总体差距快览

| # | 模块 | 状态 | 关键缺口 |
|---|------|------|---------|
| 1 | 断言系统（6 种） | ⚠️ 函数齐，**管线未接** | `run_assertions` 从未被调用；隐式 `no_error_dialog` 未自动加 |
| 2 | 终止条件 T1-T8 | ⚠️ 大部分 OK | T3 缺断言门禁；T7 缺截图 SSIM；T8（中途 stop）未贯通 |
| 3 | 错误弹窗检测 | ✅ 已接 T4 | 与断言里的"全屏扫词"双线，规则不一致 |
| 4 | 用例固化 | ⚠️ 流程在 | 截图路径空 → SSIM 模板失效；固化产物未写断言 |
| 5 | 回归模式 | 🔧 `NotImplementedError` | 整体未实现，第二次同目标必崩 |
| 6 | 报告系统 | ⚠️ Builder 在 | 调度器不写 `report.json`；截图 base64 因路径空而无效 |
| 7 | 接入层（CLI/HTTP/MCP） | ⚠️ 路由齐 | `get_report` 几乎总返回 404；CLI `--case` 字段名 bug |
| 8 | 调度器 | ⚠️ 异步 OK | `report_path` 永不赋值；`stop` 不能中断运行中的步循环 |
| 9 | 安全 | ⚠️ 黑名单 OK | `SecondCheck` 注入的是 `_StubChatBackend`（非真实 VLM） |
| 10 | 桌面控制 | ✅ 主体完整 | `ready_check` 未接入启动流程；T1 仅靠进程不查窗口句柄 |
| 11 | 感知层 | ✅ | — |
| 12 | 配置 / 入口 | ⚠️ | 缺 `python -m autovisiontest` 入口 |

---

## 2. Phase 1.A — 跑通闭环（必须做）

> 目标：让 `MCP start_test_session → 探索执行 → 断言 → 带截图的 report.json → AI 拿到报告` 这条主路径不再断裂。完成本阶段后，记事本 demo 的"首次成功"分支即可跑通。

### T-1.1 截图路径回填到 StepRecord

**缺口**：`step_loop._append_step()` 始终给 `before_screenshot_path` / `after_screenshot_path` 写空字符串。下游 `ReportBuilder.key_evidence.image_base64` 与 `consolidator.Expect.ssim_hash` 全部因此失效。

**修改位置**：
- `src/autovisiontest/report/evidence.py::EvidenceWriter.write_step_evidence`：返回 `(before_path, after_path)`
- `src/autovisiontest/engine/step_loop.py::StepLoop._append_step` / `run`：把返回路径存入 `StepRecord`

**验收标准**：会话结束后 `session.steps[i].after_screenshot_path` 是相对 `data_dir` 的有效路径，文件存在。

---

### T-1.2 会话结束自动写 report.json

**缺口**：`SessionScheduler._run_session()` 在 `finally` 中没有调用 `ReportBuilder` + `EvidenceWriter.write_report`，所以 `SessionRecord.report_path` 永远是空。`get_session_report` / MCP / HTTP 都拿不到报告。

**修改位置**：
- `src/autovisiontest/scheduler/session_scheduler.py::_run_session`：会话结束后构建报告、写盘、回填 `record.report_path`
- 同时把会话状态（status / termination_reason）写入 `sessions/{id}/status.json`

**验收标准**：任意一次 `start_session` 完成后，`{data_dir}/evidence/{session_id}/report.json` 存在；`get_session_report` 能读出完整 JSON。

---

### T-1.3 断言执行管线接入

**缺口**：`engine/assertions.py` 的 `run_assertions` 写好了，但**没有任何代码调用它**。即使 UI-TARS 输出 `finished()`，主循环也不会校验"文件是否真的写出来"。

**修改位置**：
- `src/autovisiontest/scheduler/session_scheduler.py::_run_exploratory`（或 `engine/exploratory.py::ExploratoryRunner`）：在 `StepLoop.run` 返回 PASS 后调用 `run_assertions(session.assertions, ctx)`
- ctx 至少包含：最后一帧 OCR、最后一帧截图、`chat_backend`（用于 `vlm_element_exists`）
- 任一断言失败 → `session.termination_reason = ASSERTION_FAILED`
- `session.assertion_results` 回填给 `ReportBuilder`

**验收标准**：构造一个 goal "保存 hello 到 D:\xxx.txt"，加上 `file_exists` 断言，破坏写文件逻辑后会话状态为 `FAIL: ASSERTION_FAILED`，报告里 `assertions[].result == "FAIL"`。

---

### T-1.4 隐式 no_error_dialog 断言

**缺口**：§4.4 要求所有用例**默认带一条** `no_error_dialog` 断言。当前从未自动追加。

**修改位置**：
- `src/autovisiontest/engine/exploratory.py::ExploratoryRunner.run` 入口处，或调度器创建 `SessionContext` 时
- 给 `session.assertions` 头部插入 `Assertion(type="no_error_dialog")`，避免与用户显式提供的重复

**验收标准**：单元测试构造一个会出错误弹窗的截图序列，确认会话因隐式断言失败终止。

---

### T-1.5 T3 终止条件加断言门禁

**缺口**：当前 `step_loop.run` 在 `decision.finished=True` 时直接返回 `PASS`，没有跑断言。文档 §5.3 明确"finished 且**所有断言通过**"才算 PASS。

**修改位置**：
- 与 T-1.3 共用同一处入口；finished 时跑一次断言，全过 → PASS，任一不过 → ASSERTION_FAILED

**验收标准**：UI-TARS 错判 finished 时，断言会兜底纠错，会话不会假阳性 PASS。

---

### T-1.6 RegressionRunner 最小可用版

**缺口**：`engine/regression.py::RegressionRunner.run` 直接 `raise NotImplementedError`。一旦探索成功并固化，第二次同目标会走回归路径并崩溃 → **闭环必断**。

**修改位置**：
- `src/autovisiontest/engine/regression.py::RegressionRunner`：实现一个最简版本
  - 按 `recording.steps` 顺序顺序执行 action（NEED_TARGET 直接用录像里保存的 `x/y`）
  - 跳过 SSIM 漂移校验（先做"能跑通"）
  - 复用 `ActionExecutor`、`SafetyGuard`、`Terminator`
  - 跑完跑一遍 `run_assertions`
  - 失败时直接返回 FAIL（**不**自动回退到探索 — 那是 T-2.x 的事）

**验收标准**：探索一次成功 → 自动固化 → 再次同目标调用 → 走回归路径 → 复跑成功；破坏被测应用代码后再调用 → 回归 FAIL，报告里有失败步骤截图。

---

### T-1.7 报告填全字段

**缺口**：`ReportBuilder._build_session` 不填 `trigger`、`recording_fingerprint`、`mode`；`_build_app` 不填 `pid` / `final_state`；`_build_summary` 没覆盖 `ASSERTION_FAILED` / `ERROR_DIALOG` 文案。

**修改位置**：
- `src/autovisiontest/report/builder.py`：补齐字段映射；从 `SessionContext` / `SessionRecord` 读取 trigger 与 fingerprint
- 调度器在 `start_session` 入口处把 `trigger`（cli/http/mcp）、`mode`（exploratory/regression）写入 `SessionContext`

**验收标准**：报告 JSON 与 §11.2 schema 字段一一对齐，`protocol_version: "2.0"`，`session.trigger` 准确反映入口。

---

## 3. Phase 1.B — 闭环稳定性（强烈建议做）

> 目标：让闭环不仅"能跑"，还能在反复执行、UI 变化、用户中途打断等真实场景下不出错。

### T-2.1 stop_session 协作式中断

**缺口**：`SessionScheduler.stop` 只置 `_stop_requested`，但 `step_loop.run` 内部从不检查这个标志。结果：用户点 stop 后，会话还要等当前一轮跑完才结束（可能是 30 步以后）。

**修改位置**：
- `engine/step_loop.py::StepLoop`：构造时接收一个 `stop_event: threading.Event` 或 callable
- 每次循环顶部检查；命中 → 返回 `TerminationReason.USER`
- 调度器把 stop 标志透传进来

**验收标准**：会话执行中调用 stop，2 个 step_wait_ms 内会话结束，报告 `termination_reason == USER`。

---

### T-2.2 SecondCheck 接入真实 chat backend

**缺口**：`exploratory.py` 给 `SecondCheck` 注入的是 `_StubChatBackend`，黑名单命中时永远不会"放行"，但反过来也意味着 VLM 二次确认完全是假的。

**修改位置**：
- 复用 `UITarsBackend`（或封装一个轻量 chat wrapper），让 `SecondCheck` 用同一个 vLLM 端点
- prompt 用 §9.2 的固定模板，`temperature=0.0`，`max_tokens=128`
- 注意：UI-TARS 不是通用 chat 模型，可能需要单独跑一次"yes/no" prompt

**验收标准**：黑名单命中 → SecondCheck 调用真实模型 → 返回 safe/unsafe → 行为符合 §9.2。

---

### T-2.3 安全 override 计数语义修正

**缺口**：`safety/guard.py` 里 `SecondCheck.confirm` 拿到结果后**无论** safe 还是 unsafe **都递增** `safety_overrides`。文档 §9.2 的"每会话 3 次上限"显然指**放行成功**才算一次。

**修改位置**：
- `src/autovisiontest/safety/guard.py`：仅在 `verdict == safe` 时递增 `safety_overrides`

**验收标准**：连续 5 次 unsafe + 1 次 safe → safety_overrides = 1，仍可继续；连续 3 次 safe → 第 4 次直接 blocked。

---

### T-2.4 UI 大改自动回退到探索（§5.4）

**缺口**：文档要求回归过程中"连续 2 步预期截图与实际截图 SSIM < 0.5 → 判定 UI 大改 → 回退到探索"。当前 `_invalidate_and_reexplore` 骨架在调度器里有，但 `recording_invalid` 标志从未被置位。

**修改位置**：
- `engine/regression.py::RegressionRunner`：每步执行前 / 后比对当前截图与 `step.expect.ssim_hash`
- 连续 2 步 SSIM < 0.5 → 设置 `session.recording_invalid = True` 并提前返回
- 调度器看到 `recording_invalid` → 删除该 recording → 改走 exploratory 重跑

**验收标准**：手动改 recording 中某步的 ssim_hash → 回归触发 invalidate → 自动转探索 → 重新固化。

---

### T-2.5 启动流程接入 ready_check

**缺口**：`control/window.py::wait_window` 已实现，但 `exploratory.py` 在 launch_app 后只 `time.sleep(startup_wait_ms)`，没有真正等"窗口标题包含关键字"。

**修改位置**：
- `engine/exploratory.py::ExploratoryRunner.run`：launch 后调用 `wait_window(title_contains=app.ready_check.value, timeout=30)`
- ready_check 失败 → `LAUNCH_FAILED`

**验收标准**：被测应用启动慢时不会过早开始截图；启动失败时会话快速失败。

---

### T-2.6 T1 崩溃检测增强

**缺口**：当前 T1 只查 `is_alive(handle)`（基于 tasklist）。文档要求"目标进程不存在 **或** 主窗口句柄失效"。

**修改位置**：
- `control/process.py`：新增 `is_main_window_alive(pid)` 用 pywin32 / pygetwindow
- `engine/terminator.py::_check_crashed`：两个条件都查

**验收标准**：被测应用进程还在但主窗口被 X 关掉 → 触发 CRASH 终止。

---

### T-2.7 T7 加截图 SSIM 检查

**缺口**：当前"重复无进展"只看 `(action_type, params, target_desc)` 三元组。文档要求**再加一条** "截图 SSIM > 0.95"。

**修改位置**：
- `engine/terminator.py::_check_no_progress`：除了三元组相同外，还要比较最近 3 个 StepRecord 的 after_screenshot SSIM

**验收标准**：UI-TARS 同一动作但每次实际产生不同 UI 反馈时，不再误报无进展。

---

### T-2.8 EvidenceCleaner 失败会话识别修复

**缺口**：`report/cleaner.py::_is_failed_session` 查 `evidence/{id}/status.json`，但 `session_store` 写到 `sessions/{id}/status.json`。永远找不到 status，所有"失败保留 30 天"逻辑失效。

**修改位置**：
- `report/cleaner.py`：改去 `sessions/{id}/status.json` 读，或注入 `SessionStore`

**验收标准**：跑一次失败会话，7 天后磁盘清理只清成功的，failed 留 30 天。

---

### T-2.9 CLI `--case` 字段名 bug

**缺口**：`cli_commands.py` 走 `case.app_config.path`，但 `cases/schema.AppConfig` 字段名是 `app_path` / `app_args`。直接报 AttributeError。

**修改位置**：
- `src/autovisiontest/interfaces/cli_commands.py::run`：改成正确字段名

**验收标准**：`autovisiontest run --case recordings/<f>.json` 能跑通回归。

---

### T-2.10 HTTP /v1/sessions/{id}/status 字段补齐

**缺口**：文档 §10.2 要求 status 返回 `progress` 和 `current_step`，当前只返 status 字符串。

**修改位置**：
- `interfaces/http_server.py`：从 `SessionContext.step_count` / `max_steps` 推 progress；`current_step` 取最后一步的 thought

**验收标准**：轮询期间 progress 单调增长。

---

## 4. Phase 1.C — 工程优化（可选，验收前补）

### T-3.1 `python -m autovisiontest` 入口

新增 `src/autovisiontest/__main__.py`，调用 `from autovisiontest.cli import main; main()`。让用户即使没装 entry_point 也能跑。

### T-3.2 固化产物中保存断言

`cases/consolidator.py::consolidate` 把 `session.assertions` 也写入 TestCase。回归时读取并执行同样的断言。

### T-3.3 normalized_goal 中文停用词

`cases/fingerprint.py::normalize_goal` 加一个 ~50 词的中文停用词表（"的、了、在、把、和"等）。否则同义微调会重新触发探索。

### T-3.4 错误弹窗规则统一

把 `engine/assertions.assert_no_error_dialog`（全屏扫词）和 `perception/error_dialog.detect_error_dialog`（上半屏 + 邻近按钮）合并，避免两处规则不同步。建议：assertion 复用 `detect_error_dialog`。

### T-3.5 报告 final_state 与 PID

调度器记录 `Popen.pid` 和退出码，报告 `app.pid` / `app.final_state` 不再是空字符串。

### T-3.6 单元测试补齐

按修改顺序补 pytest：
- `tests/unit/scheduler/test_report_persistence.py`：覆盖 T-1.2
- `tests/unit/engine/test_assertions_integration.py`：覆盖 T-1.3 / T-1.4 / T-1.5
- `tests/unit/engine/test_regression_runner.py`：覆盖 T-1.6
- `tests/e2e/test_notepad_closed_loop.py`：完整 §2.2 场景

---

## 5. 验收：Phase 1.A 完成后能做什么

完成 §2 后，记事本 demo 的"首次成功 + 自动固化 + 再次复跑成功"两条路径已通；"破坏 → 失败报告"路径在 T-1.6 之后通。

完成 §3 后，记事本 demo 的"反复 20 次稳定性 ≥ 90%"指标可以开始测了。

完成 §4 后，可以正式进入"任意 Windows 应用 demo"的 Phase 2 验证。

---

## 6. 任务依赖关系（建议执行顺序）

```
T-1.1 (截图路径回填)  ──┐
                        ├──► T-1.2 (写 report.json)
                        │
T-1.3 (断言管线) ──┬────┴──► T-1.7 (报告字段补齐)
T-1.4 (隐式断言)  ─┤
T-1.5 (T3 门禁)   ─┘
                        
T-1.6 (回归最简版) ──── 需要 T-1.1 / T-1.3 已完成

──────── Phase 1.A 完成（闭环跑通）────────

T-2.1 (stop 协作式)
T-2.2 (SecondCheck VLM)  ──── 可选并行
T-2.3 (override 语义)
T-2.4 (UI 大改回退) ──── 需要 T-1.6 完成
T-2.5 / T-2.6 / T-2.7 / T-2.8 / T-2.9 / T-2.10 ──── 独立任务，并行

──────── Phase 1.B 完成（稳定性）────────

T-3.x 全部独立，按需做
```

---

## 7. 不做（明确不在 MVP 范围）

为防止范围蔓延，以下事项**Phase 1 不做**：
- 多显示器支持
- 全自动触发（文件监听 / Git hook / Webhook）
- 并发执行
- 多应用泛化（除记事本外）
- 纯本地 Planner / 云端 API 多后端切换
- 用例库 UI

这些列在 product_document §15.2 / §15.3 的 Phase 2 / Phase 3。

---

*开发计划结束。每完成一个任务请在对应行打勾并附上 PR/commit 引用。*
