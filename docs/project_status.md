# AutoVisionTest 项目现状 v0.3

> 文档日期：2026-04-20
> 适用分支：`feat/uitars-and-maiui-backends` 起的 main 主干
>
> 这份文档是 `docs/product_document.md v2.1` 的**状态对账**：
> v2.1 是产品愿景与最初设计，没有废弃；但架构细节已经被实现演进改写过两次。
> 阅读建议：先看这篇了解"今天能跑到哪一步"，再回 v2.1 看"最终要做成什么样"。

---

## 0. 一句话结论

**初心没变：AI 视觉驱动的桌面应用自动化测试框架，纯黑盒纯视觉，闭环反馈给 AI 编程 Agent 消费。**
变的是"用什么模型驱动 Agent"——从 v2.1 的 **Planner+Actor+Reflector 三 Agent** 架构
改为 **UI-TARS / MAI-UI 单 GUI-Agent** 架构。业务需求和功能模块绝大多数依然有效。

---

## 1. v2.1 决策对账表

| # | v2.1 原决策 | 2026-04 现状 | 说明 |
|---|---|---|---|
| D1 | 纯视觉路径，不接 UIA/Accessibility | ✅ **保留** | `mss` 截图 + OCR，不读 UIA |
| D2 | 用例由 AI 生成/探索，不对外 YAML | ✅ **保留** | 探索性会话 + 固化到 `recordings/` |
| D3 | 探索→固化→回归复用 | 🟡 **骨架已搭**，固化链路未打通 | `cases/consolidator.py` 存在，但 `run_live_probe` 还没调它 |
| D4 | 模型后端矩阵（本地/云端/多供应商） | ⚠️ **收缩** | 只剩本地 vLLM 的 UI-TARS-1.5-7B（8000）和 MAI-UI-2B（8001）。Claude/OpenAI/Qwen-VL-Max 分支保留在 `backends/claude.py` 等文件但**已是死代码**，待清理 |
| D5 | VLM grounding 为主，OCR 为 fallback，模板匹配只做断言 | ⚠️ **改写** | GUI-agent 模型**自己出坐标**，不再需要 grounding fallback 链；OCR 只保留给断言 + 错误弹窗识别；模板匹配（SSIM）保留给回归校验 |
| D6 | 坐标系统一物理像素，入口一次性归一化 | ✅ **保留** | `control/dpi.py`、`control/screenshot.py` 落地；GUI-agent 出的坐标还做了一层反向缩放（UI-TARS：sent-image-pixel → 屏幕像素；MAI-UI：`[0,1000]` 归一化 → 屏幕像素） |
| D7 | 冷启动 + 串行执行 | ✅ **保留** | `control/process.py` 负责启动/清理 |
| D8 | 关键词黑名单 + VLM 二次确认 | ✅ **保留并扩展** | `safety/` 目录实现了 blacklist / keywords / nearby_text / second_check / guard 全栈 |
| D9 | 单步延迟 < 5s | 🟡 **分模型看**：MAI-UI-2B 125-470ms（grounding 单目标）；UI-TARS-1.5-7B 3500-5000ms。E2E 多轮历史下 MAI-UI 1100-3000ms | 指标需要按模型重新标定 |
| D10 | MVP 手动触发 | ✅ **保留** | CLI + `scripts/run_live_probe.py` |
| D11 | MCP Server 异步模式 | 🟡 **interface 存在**（`interfaces/mcp_server.py`），未接入端到端流程 | |
| D12 | 失败反馈内嵌关键截图 | 🟡 **builder 存在**（`report/builder.py` + `evidence.py`），与新 Agent 的输出字段对齐中 | |

图例：✅ 已落地 / 🟡 有骨架，需要接通 / ⚠️ 已变更，对照说明 / ❌ 已废弃

---

## 2. 已改写的核心架构

### 2.1 旧：三 Agent 协作（v2.1 §5）

```
Planner (Qwen2.5-VL-7B)  ──→  Actor (ShowUI-2B grounding)  ──→  Reflector (Planner 复用)
  每步大模型 1-2 次调用、双 vLLM 进程（8000+8001）、Planner 与 Actor 之间要同步自然语言 target_desc
```

### 2.2 新：单 GUI-Agent

```
UITarsAgent (engine/agent.py)
  │
  └── backend.decide(screenshot, goal, history)
         │
         ├── UITarsBackend  → vLLM @ :8000  UI-TARS-1.5-7B-AWQ
         └── MAIUIBackend   → vLLM @ :8001  MAI-UI-2B BF16    （通过 _DecideBackend Protocol 互换）
         │
         └── 一次调用返回  Thought + Action + 绝对像素坐标
```

对 v2.1 的具体影响：

| v2.1 章节 | 新架构下的替代 |
|---|---|
| §5.1 三 Agent 职责 | 合并为 `engine/agent.py::UITarsAgent`，单次 `decide()` |
| §5.2 单步主循环"Planner+Reflector 合并 / Actor grounding" | `engine/step_loop.py::StepLoop.run()` — 每步一次 `agent.decide()`，无 grounding 二次调用 |
| §6.3 元素定位 fallback 链（VLM → OCR → Planner 重试） | **不再存在**。GUI-agent 模型直接出坐标；grounding 失败直接计 `TARGET_NOT_FOUND` |
| §8 ChatBackend + GroundingBackend 双 Protocol | 合并为 `engine/agent.py::_DecideBackend` 单 Protocol |
| §8.5 双 vLLM 进程（planner:8000 + actor:8001） | 只需要**一个** vLLM 进程；MAI-UI 作为对比后端时才起到 8001（二选一，不并跑） |

### 2.3 未变的子系统（v2.1 里依然对得上）

- **感知层**（`perception/`）：截图、OCR、SSIM、错误弹窗识别、change detector
- **桌面控制层**（`control/`）：mss 截图、DPI、pyautogui 封装、process 启停、window 聚焦
- **安全层**（`safety/`）：黑名单 + VLM 二次确认 + 全局熔断
- **接入层**（`interfaces/`）：CLI / HTTP / MCP 三路骨架
- **会话调度器**（`scheduler/`）：会话生命周期 + 用例路由
- **报告层**（`report/`）：builder、evidence、cleaner
- **用例层**（`cases/`）：fingerprint、store、consolidator、schema —— 回归固化的支架

---

## 3. 当前能力清单

### 3.1 已验证能跑通

| 能力 | 验证方式 | 状态 |
|---|---|---|
| UI-TARS 1.5-7B-AWQ 部署（WSL2 + vLLM）| `docs/uitars_wsl2_deploy.md` + `scripts/probe_uitars.py` | ✅ |
| MAI-UI-2B BF16 部署（WSL2 + vLLM）| `docs/maiui_wsl2_deploy.md` + `scripts/probe_maiui.py` | ✅ |
| UI-TARS grounding（start_box / bbox / pixel 方言）| `scripts/_smoke_uitars_parser.py` 21 例全过 | ✅ |
| MAI-UI grounding（`[0,1000]` 归一化坐标）| `scripts/probe_maiui_matrix.py` 计算器 6 目标全中 | ✅ |
| 单 Agent 主循环 | `src/autovisiontest/engine/step_loop.py` | ✅ |
| Windows 计算器 E2E（8 × 7 = 56，attach 模式）| `scripts/run_live_probe.py --backend maiui` | ✅ |
| 多轮历史的因果消息排序 | `backends/uitars.py::build_messages` 修复后 MAI-UI 不再重复 step-0 思考 | ✅ |
| Agent Protocol 解耦 | `engine/agent.py::_DecideBackend` — 换后端只改 factory | ✅ |

### 3.2 有代码但未打通端到端

| 子系统 | 代码位置 | 缺什么 |
|---|---|---|
| **探索成功→自动固化** | `cases/consolidator.py` + `cases/store.py` | `run_live_probe` / `StepLoop` 在 `PASS` 时没调 `consolidator`；recordings/*.json 还没落过盘 |
| **回归模式执行** | `engine/regression.py` | 依赖 recordings 存在；recordings 没固化 → 回归路径跑不起来 |
| **断言系统** | `engine/assertions.py` | `ocr_contains` / `file_exists` / `file_contains` / `screenshot_similar` 需要与 `StepLoop` 终止判定联动 |
| **HTTP 接入**（`POST /v1/sessions` 等） | `interfaces/http_server.py` | 与新 Agent 的 `SessionContext` 对接的胶水代码未写 |
| **MCP 接入** | `interfaces/mcp_server.py` | 同上 |
| **报告 v2.0 schema**（`key_evidence` / `bug_hints` / `steps[].before_screenshot`） | `report/builder.py` + `report/schema.py` | Agent 目前产出的 thought/action/coords 需要映射到 v2.1 §11.2 的 JSON schema |
| **终止条件 T1/T4/T6/T8** | `engine/terminator.py` | 代码里 T7 no-progress 已修（`P6.1`），T1 进程崩溃 / T4 错误弹窗 / T6 卡死判定待补 |

### 3.3 还没开始的（v2.1 承诺但当前空缺）

- **自动化触发**（v2.1 §10.4 Phase 2）——文件监听、git hook、webhook
- **多显示器支持**（v2.1 §12.2 Phase 2）
- **多应用泛化**（v2.1 §15.2 Phase 2）——除了记事本/计算器之外的浏览器、Office、Electron、WPF
- **用例指纹持久化 + 版本失效判定**（v2.1 §4.2）

---

## 4. 距离 MVP 验收（v2.1 §2.2 记事本 demo 闭环）还差什么

v2.1 的 MVP 单一验收场景：**AI Agent 通过 MCP 调 AutoVisionTest 跑记事本写文件 → 成功后固化 → 破坏代码 → 回归跑失败，带截图报告 → Agent 修代码 → 再跑 PASS。**

对账今天的位置：

| 验收步骤 | 当前状态 | 缺什么 |
|---|---|---|
| 1. AI Agent 通过 MCP 提交测试 | ❌ MCP server 还没接到新 Agent | 写 `mcp_server` 到 `SessionScheduler` 的胶水 |
| 2. 探索性执行"打开记事本 → 输入 → 保存" | 🟡 计算器 E2E 已通，记事本还没直接验证过 | 跑 `scripts/run_live_probe.py` 记事本场景（MAI-UI 应该更稳） |
| 3. 成功后自动固化为回归用例 | ❌ 固化链路未接入 | 把 `cases/consolidator.py` 接到 `StepLoop.run()` 的 PASS 分支 |
| 4. 修改代码重测，回归模式复跑 | ❌ | 依赖 3 |
| 5. 失败时返回结构化报告 + 关键截图（base64 / MCP resource） | 🟡 `report/builder.py` 有骨架 | 把 Agent 的 `thought` / `action` / `coords` / `before_screenshot` 映射到 v2.1 §11.2 schema |
| 6. AI Agent 看报告修代码 | N/A（这一步是用户侧 AI 自主做的） | |
| 7. 再次触发，PASS | ❌ | 依赖 1/3/4/5 |

**结论：核心链路上 70% 的模块代码已经在，剩下的是"接线工作"——把已有的 `consolidator` / `assertions` / `mcp_server` / `report.builder` 串到新 Agent 的输出上。**

---

## 5. 推荐的下一步优先级

按"打通 MVP 闭环"的最短路径排：

### P1 — 记事本 E2E 跑通（验证 MAI-UI 在非计算器场景下也稳）
1. 用 `scripts/run_live_probe.py --backend maiui` 跑一个简短记事本 GOAL
   （"打开记事本，输入"今天天气真好"，Ctrl+S 保存到桌面"）
2. 目标：≤ 15 步跑完，`finished` action 触发 PASS
3. 失败的话按 `docs/uitars_migration_plan.md` §7 风险表调优（history_images、prompt 语言、温度）

### P2 — 接通"探索→固化"链路
1. `StepLoop.run()` 收到 `TerminationReason.PASS` 时调 `cases/consolidator.py::consolidate`
2. 落盘到 `recordings/<fingerprint>.json`，schema 用 v2.1 §4.3 那套（或简化版）
3. 验证：记事本 E2E 成功后 `recordings/` 下多一个文件

### P3 — 回归模式跑通
1. `engine/regression.py` 读 recordings，直接按 `steps[]` 回放 action，不调 Agent
2. 每步做 SSIM 校验，连续 2 步 < 0.5 则回退探索
3. 验证：改动 UI（例如把记事本主题切换）后回归失败，自动回落探索

### P4 — MCP 接入 + 报告 schema 对齐
1. `interfaces/mcp_server.py` 暴露 5 个 tool（v2.1 §10.3），对接 `SessionScheduler`
2. 失败报告里把关键截图以 MCP resource URI（优先）或 base64 方式投出
3. 用 Claude Code / Cursor 的 MCP 客户端实测一次远程触发

### P5 — 清理 + 补测
1. 删掉 `backends/{claude.py,openai_backend.py,vllm_chat.py,protocol.py}` 死代码（确认无引用后）
2. 补 `tests/unit/backends/test_uitars.py`、`test_maiui.py`
3. 补 `tests/unit/engine/test_step_loop.py`（对接新 Agent 协议，替代被删掉的旧 test）
4. `docs/product_document.md` 的第 5/8 章小幅改写，把"三 Agent / 双 backend"部分替换为"单 Agent / _DecideBackend Protocol"

---

## 6. 如何读这两份文档

- **愿景与为什么**：读 `docs/product_document.md v2.1`（尤其是 §1 定位、§2 决策、§2.2 MVP、§4 用例体系、§11 反馈协议）
- **今天在哪**：读这份 `project_status.md`
- **模型部署**：
  - UI-TARS：`docs/uitars_wsl2_deploy.md`
  - MAI-UI-2B：`docs/maiui_wsl2_deploy.md`
- **模型迁移决策过程**：`docs/uitars_migration_plan.md`（已完成的 Phase 0-7 记录）

---

*文档结束。当子系统接入状态发生变化时（例如 P2 完成后），更新 §3.2 / §4 的对应行即可，无需重写全文。*
