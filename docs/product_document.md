# AutoVisionTest — AI 视觉驱动的桌面应用自动化测试框架

## 产品文档 v2.2

文档日期：2026-04-28
对应里程碑：MVP（Phase 1）

---

## 0. 本文档的改动说明

**v2.0 → v2.1**：v1.0 存在若干不落地的假设：纯本地 VLM 在主流硬件上跑不动 3 秒延迟目标；三种用例类型（确定性/探索性/混合）并行推进会让 MVP 无限延期；YAML 用例需要人工编写，与"全自动闭环"目标矛盾；坐标系没有明确规则，Planner 与 Actor 无法协同。v2.0 对这些问题做了正面回答，具体决策见第 2 章。

**v2.1 → v2.2**：实现层已迁移至**单模型架构（UI-TARS-1.5-7B）**，彻底替代原 Planner + Actor + Reflector 三角色两模型方案。UI-TARS 在一次推理调用中同时输出推理链（Thought）与带像素坐标的动作（Action），消除了 Planner→Actor 两次 VLM 调用的延迟开销，也不再需要独立的 grounding 模型进程。本文档同步更新了第 3、5、6、8、12、15 章受影响的内容。

---

## 1. 产品定位与目标

### 1.1 产品定位

AutoVisionTest 是一套**纯黑盒、纯视觉**的桌面应用自动化测试框架，唯一输入是屏幕截图，唯一输出是键鼠操作。设计目标是嵌入"AI 编程闭环"：AI 写代码 → 构建 → AutoVisionTest 执行 → 结构化反馈 → AI 修复。

### 1.2 核心价值

| 价值维度 | 描述 |
|---------|------|
| **零侵入** | 不读被测应用源码，不注入 Agent，不依赖 Accessibility/UIA，不要求被测应用任何配合 |
| **AI 自主** | 测试用例由 AI 生成或 AI 探索，**不需要人工写 YAML** |
| **闭环反馈** | 失败报告结构化 + 关键截图，专为多模态 AI 编程 Agent 消费设计 |
| **可回归** | 探索性用例首次成功后自动固化为确定性回归用例，修复验证快速稳定 |

### 1.3 非目标（明确不做）

- **不做**被测应用代码插桩、不做 UIA/Accessibility 集成（哪怕可用也不用，保持纯视觉路径的一致性）
- **不做**跨平台（MVP 仅 Windows 10/11；macOS/Linux 是 Phase 3 以后的事）
- **不做**负载/性能测试（只做功能正确性验证）
- **不做**并发执行（MVP 单机串行）
- **不做**人工编写 YAML 的一等公民支持（YAML 仅作内部中间表示）

---

## 2. 核心设计决策

这一章是整份文档的**约束来源**。后续所有模块设计必须与这些决策一致。

### 2.1 决策一览

| # | 决策 | 理由 |
|---|------|------|
| D1 | **纯视觉路径**，不接入 UIA/Accessibility | 被测应用不限，统一路径更易维护；UIA 的有/无会导致行为分叉 |
| D2 | **用例由 AI 生成或 AI 探索**，不对外暴露人工 YAML 编写 | "全自动化开发"闭环的刚性要求 |
| D3 | **探索→固化→复用**：探索性用例首次成功后自动保存为确定性回归用例 | 每次探索路径不同会让"修复验证"无法稳定复跑 |
| D4 | **单模型后端**：UI-TARS-1.5-7B（或 MAI-UI）本地 vLLM，一次推理完成规划与坐标定位 | 消除 Planner→Actor 两次调用延迟；单 vLLM 进程降低部署复杂度 |
| D5 | **元素定位内嵌于模型输出**，OCR 仅用于文本断言与安全检测，模板匹配只用于断言 | UI-TARS 直接输出绝对坐标，无坐标系分歧问题 |
| D6 | **坐标系：物理像素，入口归一化**。高 DPI、多显示器在入口一次性处理 | pyautogui 在 HiDPI 下有坑，必须显式处理 |
| D7 | **冷启动 + 串行执行**：每个用例前清理残留进程 + 重启被测应用 | 消除脏状态，MVP 不追求速度 |
| D8 | **安全：关键词黑名单 + VLM 二次确认**，不做路径白名单、不做沙箱 | MVP 够用；沙箱/VM 是用户自己的事 |
| D9 | **单步延迟 < 5 秒**（从截图到动作完成） | UI-TARS-1.5-7B AWQ 单次推理的现实值（3080Ti，含图像预处理与坐标还原） |
| D10 | **MVP 手动触发**，自动触发留扩展钩子 | 手动触发更可控，闭环逻辑先跑通再谈自动化触发 |
| D11 | **MCP Server 异步模式**：提交返回 session_id，后续轮询 | 测试动辄几分钟，同步会卡住 AI 的对话 |
| D12 | **失败反馈内嵌关键截图**（base64 或 MCP resource） | 让多模态 AI Agent 能"看见" bug，而不是只读文字描述 |

### 2.2 MVP 范围与验收

**MVP 单一验收场景**：Windows 记事本闭环 demo。

1. AI 编程 Agent 收到任务："在记事本中写入指定文字并保存到指定路径"
2. Agent 写实现代码（例如一个调用记事本的 Python 脚本，或一段 AutoHotkey）
3. Agent 通过 MCP 调用 AutoVisionTest，传入自然语言目标："打开记事本，输入 'hello world'，保存到 C:\TestSandbox\out.txt"
4. AutoVisionTest 执行探索，成功后返回结构化报告 + 把成功轨迹固化为 `recordings/notepad_save.json`
5. 人为破坏实现代码（例如把保存按钮的热键错成 Ctrl+X）
6. Agent 再次触发测试，AutoVisionTest 用固化的回归用例复跑，失败 → 返回带截图的失败报告
7. Agent 根据报告自主修复代码
8. 再次触发，PASS

MVP 达成这个闭环即验收。不要求"任意应用"上工作，但**架构必须是通用的**，不能对记事本做硬编码。

---

## 3. 系统架构

### 3.1 进程与组件

```
┌─────────────────────────────────────────────────────────────┐
│ AI 编程 Agent (Claude Code / Cursor / 自定义)                │
└────────────┬───────────────────────────────┬────────────────┘
             │ MCP / HTTP / CLI              │ 读取报告
             ▼                               │
┌─────────────────────────────────────────────────────────────┐
│ AutoVisionTest 主进程                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 接入层                                                │   │
│  │   MCP Server  │  FastAPI HTTP  │  CLI                │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 会话调度器 (SessionScheduler)                         │   │
│  │   - 会话生命周期 (start/status/report/stop)          │   │
│  │   - 用例路由 (回归用例 vs 探索用例)                   │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 执行引擎 (StepLoop)                                   │   │
│  │   UITarsAgent — 每步单次调用，输出 Thought + Action   │   │
│  └───┬───────────────┬──────────────────┬───────────────┘   │
│      ▼               ▼                  ▼                   │
│  ┌────────┐    ┌────────────┐    ┌──────────────┐           │
│  │ 感知层  │    │ 模型后端    │    │ 桌面控制层    │           │
│  │ (§6)   │    │ 抽象 (§8)  │    │ (§7)         │           │
│  └────────┘    └──────┬─────┘    └──────────────┘           │
│                       │                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 安全拦截器 (SafetyGuard, §9) — 作用于所有动作出口       │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ▼
               ┌─────────────────┐
               │ 本地 vLLM 服务   │
               │ (独立进程)       │
               │ UI-TARS-1.5-7B  │
               │ 端口 8000        │
               └─────────────────┘
```

### 3.2 关键进程划分

- **主进程**：AutoVisionTest 框架本体（Python），常驻。
- **本地 vLLM 服务**：独立进程，运行 UI-TARS-1.5-7B（或 MAI-UI），通过 OpenAI 兼容 HTTP 接口调用。模型加载成本只付一次，主进程崩溃不影响模型。单一进程取代了原来的 `vllm-planner`（端口 8000）+ `vllm-actor`（端口 8001）双进程方案。
- **被测应用**：独立进程，由 SessionScheduler 冷启动管理。

---

## 4. 测试用例体系

### 4.1 两种用例，一个生命周期

v1.0 的三分法（确定性/探索性/混合）收敛为两种：

| 类型 | 何时产生 | 特点 |
|------|---------|------|
| **探索性用例（Exploratory）** | AI 或人类给出自然语言目标，由 Planner 动态展开 | 路径不稳定，耗时长，首次发现问题用 |
| **回归用例（Regression）** | 探索性用例首次成功后**自动固化** | 路径固定，快速可复跑，修复验证用 |

两者底层都是同一个 YAML/JSON 结构（见 §4.3），只是 `type` 字段和执行策略不同。**用户不需要关心这个结构**——AI 生成，框架保存。

### 4.2 生命周期

```
用户/AI 编程 Agent
      │ 给出自然语言目标 "验证登录功能"
      ▼
┌──────────────────┐
│  会话调度器        │
│  查 recordings/   │  ── 存在且有效 ──►  走回归模式（快）
│  对应回归用例      │
└────────┬─────────┘
         │ 不存在或已失效
         ▼
   探索模式（Planner 动态展开）
         │
         ├── 失败 ──► 返回失败报告（不固化）
         │
         └── 成功 ──► 自动固化到 recordings/<fingerprint>.json
                    │
                    ▼
              下次同目标优先走回归模式
```

**固化时机**：探索成功（UITarsAgent 返回 `finished=True` 且所有断言通过）后，把完整操作序列 + 每步截图 + 断言结果一起序列化。

**回归用例失效判定**：回归执行过程中，若**连续 2 步**的预期截图与实际截图 SSIM < 0.5，或 VLM grounding 找不到预期元素 → 判定"UI 大改，回归用例失效" → **自动回退到探索模式**并重新固化。

**用例指纹（fingerprint）**：`sha256(app_path + normalized_goal + app_version)`。`normalized_goal` 是对自然语言目标做小写化、去标点、去停用词后的结果。同一应用同一目标同一版本，指纹相同。

### 4.3 内部数据结构

**对外不暴露**，仅作为框架内部落盘格式与 UITarsAgent 交互的中间表示。

```yaml
# recordings/<fingerprint>.json 的 YAML 视图
test_case:
  fingerprint: "a1b2c3..."
  type: "regression"         # exploratory | regression
  goal: "打开记事本,输入hello world,保存到C:\\TestSandbox\\out.txt"
  app:
    path: "C:\\Windows\\System32\\notepad.exe"
    startup_wait_ms: 2000
    ready_check:
      type: "window_title_contains"
      value: "记事本"

  steps:
    - idx: 1
      action: "key_combo"
      keys: ["ctrl", "n"]
      expect:
        screenshot_hash: "sha256:..."   # 用于 SSIM 相似度比对
        vlm_elements: ["空白文档编辑区"]  # VLM grounding 预期发现的元素
    - idx: 2
      action: "type"
      text: "hello world"
      expect:
        ocr_contains: ["hello world"]
    # ...

  assertions:
    - type: "ocr_contains"
      text: "hello world"
    - type: "file_exists"
      path: "C:\\TestSandbox\\out.txt"
    - type: "file_contains"
      path: "C:\\TestSandbox\\out.txt"
      text: "hello world"

  metadata:
    created_at: "2026-04-18T10:00:00Z"
    original_exploration_session_id: "ts-20260418-001"
    success_count: 3
    last_success_at: "2026-04-18T11:30:00Z"
```

### 4.4 断言类型（MVP）

| 断言 | 描述 | 感知层 | 备注 |
|------|------|--------|------|
| `ocr_contains` | 屏幕包含指定文字 | OCR | 主力断言，最稳定 |
| `vlm_element_exists` | 给定自然语言描述的元素存在 | VLM | 需要 VLM 调用，慢但灵活 |
| `no_error_dialog` | 无错误弹窗（OCR 检测常见错误标题） | OCR | 隐式加在所有用例上 |
| `file_exists` | 文件存在 | 文件系统 | 非视觉断言，直接走 OS |
| `file_contains` | 文件内容包含指定文本 | 文件系统 | 读文件验证输出，MVP 必备 |
| `screenshot_similar` | 当前区域截图与模板 SSIM > 阈值 | 模板匹配 | 仅用于"视觉回归" |

v1.0 里 `visual_region_changed` / `ai_judge` 等 MVP 不做。

---

## 5. 测试执行引擎

### 5.1 单 Agent 架构

原 Planner + Actor + Reflector 三角色已合并为**单一 UITarsAgent**，由 UI-TARS-1.5-7B 模型驱动。

| 职责 | 实现方式 |
|------|---------|
| **规划（原 Planner）** | UI-TARS 的 `Thought` 字段：自由文本推理链，描述当前状态判断和下一步意图 |
| **定位（原 Actor）** | UI-TARS 的 `Action` 字段：直接输出带绝对像素坐标的动作原语（`click(start_box='(x,y)')`等），无需单独调用 grounding 模型 |
| **反思（原 Reflector）** | 滚动历史（最近 N 步的截图 + Thought + Action 序列）以多轮对话形式回传给模型，模型根据前后截图的变化隐式完成反思 |

**每步调用次数：1 次**（单 vLLM 请求），相比原方案（Planner/Reflector 合并 1 次 + Actor 1 次 = 2 次）减少 50% 的网络往返。

| 参数 | 说明 |
|------|------|
| `model` | `ui-tars-1.5-7b`（AWQ 量化）或 `maiui_local`（MAI-UI） |
| `history_images` | 回传最近几步截图（默认 3），平衡上下文长度与延迟 |
| `language` | `Chinese`（Thought 语言，须与训练分布匹配） |
| `temperature` | `0.0`（贪婪解码，UI-TARS 专为确定性推理训练） |

### 5.2 单步主循环

```
┌─────────────────────────────────────────────────────────┐
│ step_idx = 0                                            │
│ agent_history = []   # rolling (thought, action, img)  │
│ while True:                                             │
│   1. snapshot = perception.capture_snapshot()           │
│      - screenshot_png                                   │
│      - ocr_result (异步,本步内缓存复用)                  │
│   2. 终止检查 terminator.check(session, snapshot)       │
│      → 命中任一 T1..T8 则返回对应 TerminationReason     │
│   3. 单次 Agent 调用:                                   │
│        decision = agent.decide(session, snapshot)       │
│        输出 AgentDecision {                             │
│          thought: "推理链文本",                          │
│          action: {type, params},                        │
│          coords: (x, y) | None,    ← 已是屏幕物理像素    │
│          end_coords: (x2,y2)|None, ← drag 终点          │
│          finished: bool,                                │
│          finished_content: str                          │
│        }                                                │
│   4. 如果 decision.finished: break 成功 (PASS)          │
│   5. 如果 coords 缺失且动作需要坐标(NEED_TARGET):        │
│        记录失败步；连续 3 次 → TARGET_NOT_FOUND          │
│   6. 安全拦截 safety_guard.check(action, coords, ocr)   │
│        命中黑名单 → VLM 二次确认(§9.2)                   │
│        二次确认仍危险 → 中止,上报 ABORT:UNSAFE           │
│   7. executor.execute(action, coords)                   │
│   8. 等待 wait_ms (默认 500ms)                          │
│   9. 采集 after_screenshot; 写 evidence                 │
│   10. session.steps.append(StepRecord)                  │
│   11. step_idx += 1                                     │
└─────────────────────────────────────────────────────────┘
```

说明：
- **步 1 的 OCR 结果在本步内复用**：终止检查（错误弹窗）、安全拦截（黑名单匹配）、断言判定 都读同一份缓存，避免重复调用。
- **步 3 是唯一的模型调用**：UI-TARS 在一次推理中同时完成原 Planner（意图规划）、Actor（坐标定位）、Reflector（基于历史截图的隐式反思）三个职责。`coords` 已由 backend 完成坐标系还原（从 sent-image 像素 → 原始屏幕像素），步骤循环无需再做换算。
- **步 6 的安全拦截**见 §9，对 NO_TARGET 动作（如 `type` 的文本内容）同样检查。

### 5.3 终止条件

按优先级从高到低：

| # | 条件 | 检测方法 | 结果 |
|---|------|---------|------|
| T1 | **应用崩溃** | 目标进程不存在 或 主窗口句柄失效 | FAIL: CRASH |
| T2 | **命中安全黑名单** | SafetyGuard 拦截 | ABORT: UNSAFE |
| T3 | **Agent 判定成功** | UITarsAgent 返回 `finished=True`（`finished()` 动作）且所有断言通过 | PASS |
| T4 | **错误弹窗** | OCR 检测到"错误/Error/异常"等关键词 + 弹窗窗口特征 | FAIL: ERROR_DIALOG |
| T5 | **最大步数** | step_idx >= max_steps（默认 30） | FAIL: MAX_STEPS |
| T6 | **卡死** | 连续 10 秒 SSIM(last, current) > 0.99 且已尝试过动作 | FAIL: STUCK |
| T7 | **重复动作无进展** | 连续 3 步相同 action_type + 相同 target_desc + 截图 SSIM > 0.95 | FAIL: NO_PROGRESS |
| T8 | **人工终止** | 收到 stop 信号 | ABORT: USER |

### 5.4 回归模式执行

与探索模式共用主循环，但有两点差异：

1. **Agent 不走 VLM 推理**：直接读取 `recordings/*.json` 的 `steps`，按 idx 顺序吐出预录动作，跳过 `UITarsAgent.decide()` 调用。
2. **每步都做预期校验**：执行前比对当前截图与 `expect.screenshot_hash` 的 SSIM，若连续 2 步 SSIM < 0.5 → 判定 UI 大改 → 中止回归 → 回落到探索模式（见 §4.2）。

### 5.5 动作分类

| 类别 | 动作 | 是否需要 target_desc / grounding |
|------|------|------|
| **NEED_TARGET** | `click` / `double_click` / `right_click` / `drag`（起点）/ `scroll`（指定位置） | 是 |
| **NO_TARGET** | `type` / `key_combo` / `wait` / `scroll`（全局滚动） | 否 |
| **META** | `launch_app` / `close_app` / `focus_window` | 否 |

`drag` 的终点若是相对于起点的位移，走 NEED_TARGET（起点定位）；若终点也是元素，两次 grounding。MVP 只支持第一种以降低复杂度。

### 5.6 bug_hints 的产出

`bug_hints` 由上层逻辑根据终止原因汇总产出（UI-TARS 本身不单独输出 hint 字段，hint 从 `Thought` 字段和终止状态中提取）：

- 终止条件 T4（错误弹窗）、T5（最大步数）、T6（卡死）、T7（无进展）触发时，从最近几步的 `thought` 文本中提取失败描述
- 探索结束（PASS 或 FAIL）时，对整体轨迹给一次总结

每条 hint 字段：`{description, confidence, related_hypothesis[]}`。提取逻辑应约束"若无法给出置信度 > 0.4 的 hint 则返回空数组，宁缺毋滥"。

---

## 6. 视觉感知与坐标系

### 6.1 感知层分工

| 层 | 用途 | 何时调用 |
|---|------|---------|
| **截图** | 所有感知与决策的输入 | 每步循环开始 + 每次动作后 |
| **OCR (PaddleOCR)** | 文字识别、OCR 断言、错误弹窗检测、安全黑名单文字匹配 | 每步 1 次（异步，本步内缓存复用） |
| **VLM 坐标定位（UITarsAgent）** | 元素定位，内嵌于单次推理输出，直接返回绝对像素坐标 | 每步 1 次（与规划合并，无独立 grounding 调用） |
| **模板匹配 (OpenCV SSIM)** | 截图相似度计算（终止条件、回归校验、视觉断言） | 终止检查 + 回归校验 |

### 6.2 坐标系规则（强约束）

**所有内部坐标统一用"主屏左上角为原点的物理像素"**。

- 入口处（截图采集时）做一次 DPI 归一化：读取 `GetDpiForMonitor`，记录缩放因子，后续所有截图都缩放到"逻辑像素 = 物理像素"的状态。
- 多显示器：MVP 只支持**主屏**。多屏是 Phase 2。
- `pyautogui` 在调用前 `ctypes.windll.shcore.SetProcessDpiAwareness(2)`，避免坐标偏移。
- 被测应用的 `region` 相对坐标（若回归用例里保存了）在使用时乘以当前截图尺寸还原为物理像素。

### 6.3 元素定位策略

单模型架构下，UI-TARS 在一次推理中**直接输出绝对像素坐标**，不存在独立的 grounding 模型调用，因此原四级 fallback 链（VLM grounding → OCR 匹配 → Planner 重试 → 失败上报）已简化：

1. **UITarsAgent.decide()** 返回 `AgentDecision.coords`：模型自行完成图像理解与坐标定位，结果已还原到屏幕物理像素空间（backend 内部处理 sent-image 缩放比例）。
2. 若 `coords` 为 `None`（parse_error 或模型未输出坐标的动作）：**记录失败步，在下一步将截图 + 历史重新投喂给模型**，隐式触发模型自我修正。
3. 连续 3 步 `coords` 缺失且动作属于 NEED_TARGET：上报 `FAIL: TARGET_NOT_FOUND`。

**OCR 在定位中的角色**：OCR 仍保留用于错误弹窗检测、安全拦截（黑名单文字匹配）和文本类断言（`ocr_contains`），但**不再作为坐标定位的 fallback**。

### 6.4 截图性能

- MVP 用 `mss` 库做截图（比 `pyautogui.screenshot` 快一个数量级）。
- 送 VLM 前压缩到短边 1080px，JPEG quality 85。
- OCR 用原分辨率（精度优先）。

---

## 7. 桌面控制层

### 7.1 动作原语

| 动作 | 参数 | 实现 |
|------|------|------|
| `move` | `x, y` | pyautogui.moveTo (加 0.1s 缓动) |
| `click` | `x, y, button=left` | pyautogui.click |
| `double_click` | `x, y` | pyautogui.doubleClick |
| `right_click` | `x, y` | pyautogui.rightClick |
| `drag` | `from, to` | pyautogui.moveTo + mouseDown + moveTo + mouseUp |
| `scroll` | `x, y, dy` | pyautogui.scroll |
| `type` | `text` | pyautogui.typewrite（ASCII） / pyperclip + Ctrl+V（非 ASCII，含中文） |
| `key_combo` | `keys[]` | pyautogui.hotkey |
| `wait` | `ms` | time.sleep |

**注**：`type` 对中文必须走剪贴板路径，pyautogui.typewrite 不支持 Unicode。

### 7.2 窗口/进程管理

- **启动被测应用**：`subprocess.Popen(app_path)`，等待 `ready_check` 通过（默认主窗口标题包含关键字，超时 30s）。
- **冷启动清理**：启动前 `taskkill /IM <exe_name> /F`，忽略"进程不存在"错误。
- **窗口聚焦**：`pygetwindow` 找到目标窗口，`activate()`。
- **崩溃检测**：每步循环检查 `Popen.poll()` 和主窗口句柄，任一失效 → T1。

---

## 8. 模型后端抽象

### 8.1 统一接口

单模型架构只需一个 Protocol：

```python
class _DecideBackend(Protocol):
    """任何能驱动 UITarsAgent 的后端都满足此结构类型。
    UITarsBackend 和 MAIUIBackend 均实现此接口，区别仅在坐标系处理。
    """
    def decide(
        self,
        image_png: bytes,
        goal: str,
        history: list[HistoryStep] | None = None,
    ) -> UITarsDecision:
        """一次推理，返回 Thought + Action（含绝对屏幕坐标）。"""
        ...
```

`UITarsAgent` 通过 `_DecideBackend` 注入后端；`StepLoop` 只与 `Agent` Protocol 交互，对具体模型完全透明。

### 8.2 后端矩阵

| 后端标识 | 模型 | 坐标系 | 硬件 | 备注 |
|---------|------|--------|------|------|
| `uitars_local` | UI-TARS-1.5-7B（AWQ/INT4） | sent-image 像素，backend 内自动还原 | 3080Ti 12GB / 3090 / 5090 | **MVP 默认**，vLLM 独立进程，单端口 8000 |
| `maiui_local` | MAI-UI（Tongyi-MAI，Qwen3-VL 基座） | `[0, 1000]` 归一化虚拟画布 | 3090 / 5090 | 同一 vLLM 进程，换 `model` 参数即可 |

**注**：原 `claude_api` / `openai_api` / `qwen_api` 云端 Planner 后端已不在单模型架构中使用；云端 API 在需要时仍可用于外部评估或报告生成，但不参与主循环推理。

### 8.3 推荐配置

| 硬件 | 推荐后端 | 模型 | 预估单步延迟 |
|------|---------|------|-------------|
| 3080Ti 12GB | `uitars_local` | UI-TARS-1.5-7B AWQ | 3-4 秒 |
| 3090 24GB | `uitars_local` | UI-TARS-1.5-7B FP16 | 2-3 秒 |
| 5090 32GB | `uitars_local` | UI-TARS-1.5-7B FP16 | 1-2 秒 |
| 3090 / 5090 | `maiui_local` | MAI-UI | 2-3 秒 |

**MVP 默认**：`uitars_local` + UI-TARS-1.5-7B AWQ（3080Ti，单 vLLM 进程）。相比原"Planner 云端 + Actor 本地"方案，消除了云端 API 的网络延迟与费用。

### 8.4 配置文件

`config/model.yaml`：

```yaml
# AutoVisionTest Configuration — 单模型 UI-TARS Agent
# 一个 vLLM 服务承载全部推理，无需额外 actor 进程。

agent:
  backend: "uitars_local"              # uitars_local | maiui_local
  model: "ui-tars-1.5-7b"             # vLLM --served-model-name
  endpoint: "http://localhost:8000/v1" # 单 vLLM 服务（WSL2 或本机）
  max_tokens: 512
  temperature: 0.0                     # 确定性解码，UI-TARS 训练分布
  language: "Chinese"                  # Thought 语言
  history_images: 3                    # 回传最近几步截图
  timeout_s: 60.0

runtime:
  max_steps: 50
  max_session_duration_s: 600
  step_wait_ms: 500
  data_dir: "./data"
```

旧版 `planner` / `actor` 两段式配置如存在于 YAML 中会被 `load_config` 忽略（`model_config = {"extra": "ignore"}`）。

### 8.5 本地进程布局

单模型架构只需**一个 vLLM 进程**：

| 进程 | 端口 | 模型 | 显存估算 (3080Ti) |
|------|------|------|------------------|
| `vllm-uitars` | 8000 | UI-TARS-1.5-7B AWQ | ~8-10 GB |

相比原双进程方案（`vllm-planner` 6-7 GB + `vllm-actor` 5 GB ≈ 11-12 GB），单进程显存占用更低，在 3080Ti 12GB 上有充足余量。

**WSL2 部署**：vLLM 进程运行于 WSL2，主进程（Windows Python）通过 `http://localhost:8000/v1` 访问，详见部署文档。

---

## 9. 安全防护

### 9.1 关键词黑名单

MVP 硬编码中英文黑名单：

```
删除 / 永久删除 / 清空 / 清除 / 重置 / 格式化 / 卸载 / 抹掉 / 擦除 / 恢复出厂
Delete / Remove / Erase / Format / Uninstall / Reset / Wipe / Factory
```

**匹配范围**（按动作类型区分）：

| 动作 | 匹配对象 | 说明 |
|------|---------|------|
| `click` / `double_click` / `right_click` | 通过 grounding 得到的目标坐标附近（半径 30px）的 OCR 文字 | 最常见的误操作入口 |
| `type` | 待输入的文本本身 | 防止 Planner 让应用执行 `del /s /q C:\` 一类命令行输入 |
| `key_combo` | 组合键语义（查表：`alt+f4` / `ctrl+shift+del` 等危险组合） | 小白名单内的危险组合键 |
| `drag` / `scroll` / `wait` | 不检查 | 本身不造成破坏性操作 |

### 9.2 VLM 二次确认

命中黑名单时**不立即中止**，先向 UITarsAgent（或独立 VLM 二次确认调用）发问：

> "即将对文字为 '{text}' 的元素执行 {action}，在当前测试目标 '{goal}' 下，这是否是预期且安全的操作？只回答 'safe' 或 'unsafe'，并给一句理由。"

- 回答 `safe` → 放行，**并在 session 日志中记录一条 `SAFETY_OVERRIDE`**
- 回答 `unsafe` 或解析失败 → 中止，`ABORT: UNSAFE`

二次确认最多每会话 3 次，超过则后续任何命中都直接中止（防止模型被诱导连续放行）。

### 9.3 全局熔断

- 单个会话最大动作数：30（可配置）
- 单个会话最大时长：10 分钟（可配置）
- 达到上限 → 强制中止

### 9.4 超出 MVP 范围

- 路径白名单：不做。用户自己决定被测应用操作的目录。
- VM/Sandbox：不做。建议用户在 Windows Sandbox 或 VMware snapshot 中运行高风险测试，这是用户侧的部署选择。

---

## 10. 接入层

三种接入方式**复用同一个核心引擎**，差异仅在协议。

### 10.1 CLI

```
autovisiontest run --goal "打开记事本,输入hello,保存到D:\a.txt" --app "notepad.exe"
autovisiontest run --case recordings/notepad_save.json
autovisiontest status <session_id>
autovisiontest report <session_id> [--format json|html]
autovisiontest list-recordings
```

### 10.2 HTTP (FastAPI)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/sessions` | 提交测试，body: `{goal, app_path, app_args?, timeout_ms?}`，返回 `{session_id}` |
| GET | `/v1/sessions/{id}/status` | 返回 `{status: pending|running|success|failed|aborted, progress, current_step}` |
| GET | `/v1/sessions/{id}/report` | 完成后返回结构化报告（见 §11） |
| POST | `/v1/sessions/{id}/stop` | 中止会话 |
| GET | `/v1/recordings` | 列出所有回归用例 |
| DELETE | `/v1/recordings/{fingerprint}` | 删除回归用例（强制下次重新探索） |

异步模式，提交立即返回。

### 10.3 MCP Server

暴露给 Claude Code / Cursor 的 tool：

| Tool | 说明 |
|------|------|
| `start_test_session(goal: str, app_path: str, app_args?: str, timeout_ms?: int) -> {session_id}` | 启动测试 |
| `get_session_status(session_id: str) -> {status, progress, current_step_description}` | 轮询状态 |
| `get_session_report(session_id: str) -> Report` | 拉完整报告（含关键截图，作为 MCP resource） |
| `stop_session(session_id: str) -> {}` | 中止 |
| `list_recordings() -> [recording_summary]` | 列出回归用例 |
| `invalidate_recording(fingerprint: str) -> {}` | 使回归用例失效（下次重探索） |

**异步约定**：`start_test_session` 立即返回，Claude/Cursor 用 `get_session_status` 轮询（或在收到 push 通知时拉取，见 §10.4）。

### 10.4 扩展钩子：全自动触发（Phase 2）

MVP 暂不实现，但预留接口：

- 文件监听（`watchdog`）：指定目录有构建产物变化 → 自动触发关联用例
- Git hook：`post-commit` / `post-merge` 触发
- HTTP Webhook：CI 流水线调用

---

## 11. 测试反馈协议

### 11.1 核心原则

反馈是给**多模态 AI 编程 Agent** 消费的，不是给人看的。所以：

- 关键失败步骤的截图必须能被 AI 直接看到（base64 或 MCP resource URI）
- 文字描述要能在不看截图的情况下也能大致理解问题（为了文本模型降级兼容）
- 给出 `bug_hint` 以降低 AI 的分析成本，但标注置信度，避免 AI 盲信

### 11.2 报告 schema

```json
{
  "protocol_version": "2.0",
  "session": {
    "id": "ts-20260418-001",
    "trigger": "mcp",
    "mode": "regression",
    "recording_fingerprint": "a1b2c3...",
    "start_time": "2026-04-18T10:00:00Z",
    "end_time": "2026-04-18T10:02:30Z",
    "duration_ms": 150000
  },
  "goal": "打开记事本,输入hello world,保存到C:\\TestSandbox\\out.txt",
  "app": {
    "path": "C:\\Windows\\System32\\notepad.exe",
    "pid": 12345,
    "final_state": "exited_normally"
  },
  "result": {
    "status": "FAIL",
    "termination_reason": "ASSERTION_FAILED",
    "summary": "保存步骤执行后,文件 C:\\TestSandbox\\out.txt 不存在",
    "failed_step_idx": 5
  },
  "steps": [
    {
      "idx": 1,
      "timestamp": "2026-04-18T10:00:05Z",
      "planner_intent": "点击'文件'菜单",
      "actor_target_desc": "文件菜单,左上角",
      "action": {"type": "click", "x": 32, "y": 45},
      "grounding_confidence": 0.92,
      "before_screenshot": "evidence/step1_before.png",
      "after_screenshot": "evidence/step1_after.png",
      "reflection": "菜单展开成功"
    }
    // ...
  ],
  "assertions": [
    {"type": "file_exists", "path": "C:\\TestSandbox\\out.txt", "result": "FAIL", "detail": "文件不存在"}
  ],
  "key_evidence": {
    "failed_step_screenshot": {
      "step_idx": 5,
      "description": "点击保存后的屏幕",
      "image_base64": "...",
      "image_path": "evidence/step5_after.png"
    },
    "error_context_screenshots": [
      {"step_idx": 4, "image_base64": "..."},
      {"step_idx": 5, "image_base64": "..."}
    ]
  },
  "bug_hints": [
    {
      "description": "从截图看,保存对话框出现后被自动关闭,但文件未生成。可能是保存路径校验失败或权限问题。",
      "confidence": 0.7,
      "related_hypothesis": ["路径参数解析错误", "文件写入权限问题", "保存按钮热键被错误绑定"]
    }
  ]
}
```

### 11.3 截图投递策略

- **成功报告**：仅返回第一步和最后一步截图（节省体积）
- **失败报告**：返回失败步骤前后各 2 步的截图（共最多 5 张），保证 AI 能看到失败上下文
- 通过 MCP 的 resource 机制投递时，优先走 resource URI 而不是 base64（减少 token 消耗）

### 11.4 Evidence 存储与清理

- 存储根目录：`{data_dir}/evidence/{session_id}/`
  - `step_<idx>_before.png` / `step_<idx>_after.png`
  - `ocr_<idx>.json`（每步 OCR 结果缓存）
  - `report.json`（最终报告）
- `data_dir` 默认 `./data`，可通过环境变量 `AUTOVT_DATA_DIR` 覆盖
- **保留策略**：
  - 默认保留最近 50 个 session 或最近 7 天（以早到为准）
  - 所有 FAILED/ABORTED 会话无视时长保留 30 天
  - 后台任务每小时清理一次
- 回归用例 `recordings/` 目录**永久保留**，不受清理策略影响

---

## 12. 环境与硬件

### 12.1 支持矩阵

| 硬件 | 后端 | 模型 | 单步延迟 | 状态 |
|------|------|------|---------|------|
| 3080Ti 12GB | `uitars_local` | UI-TARS-1.5-7B AWQ | 3-4s | **MVP 开发主力** |
| 3090 24GB | `uitars_local` | UI-TARS-1.5-7B FP16 | 2-3s | Phase 2 验证 |
| 5090 32GB | `uitars_local` | UI-TARS-1.5-7B FP16 | 1-2s | Phase 2 验证 |
| 3090 / 5090 | `maiui_local` | MAI-UI | 2-3s | Phase 2 备选 |

### 12.2 被测环境

- OS：Windows 10 (≥ 19045) / Windows 11
- 主屏分辨率：MVP 推荐 1920×1080，2K/4K 需手动验证 DPI 处理
- 多显示器：MVP 不支持，Phase 2

### 12.3 主机硬件基线

| 项 | MVP 最低 | 推荐 |
|---|---------|------|
| CPU | 6 核现代 x86 | 8 核以上 |
| RAM | 16 GB | 32 GB |
| 磁盘 | 50 GB 可用（模型 + 证据） | 200 GB SSD |
| GPU | 3080Ti 12GB（运行 UI-TARS-1.5-7B AWQ，显存 ~10 GB） | 3090 / 5090 |
| 网络 | 本地 vLLM（WSL2）无需公网；如需访问云端报告接口则需稳定公网 | 千兆 |

---

## 13. 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.11 |
| VLM 推理（本地） | vLLM | ≥ 0.6 |
| VLM 推理（云端） | anthropic SDK / openai SDK / dashscope SDK | — |
| OCR | PaddleOCR | ≥ 2.7 |
| 图像 | OpenCV-python / Pillow / mss | — |
| 桌面控制 | pyautogui + pywin32 + pygetwindow + pyperclip | — |
| HTTP | FastAPI + uvicorn | — |
| MCP | `mcp` Python SDK | — |
| 配置 | Pydantic Settings + YAML | — |
| 日志 | structlog | — |
| 测试 | pytest + pytest-asyncio | — |

---

## 14. 性能与质量指标

| 指标 | MVP 目标 | 测量条件与方法 |
|------|---------|---------|
| 单步延迟 | < 5 秒 | UI-TARS-1.5-7B AWQ via 本地 vLLM，3080Ti，取 20 次中位数 |
| 模型冷启动 | < 60 秒 | UI-TARS-1.5-7B AWQ via vLLM，从进程启动到首次推理调用返回 |
| 记事本 demo 端到端 | < 60 秒 | 从 MCP `start_test_session` 到 `get_session_report` 可取 |
| 记事本 demo 稳定性 | 连续 20 次成功率 ≥ 90% | 固化为回归用例后，连续跑 20 次 |
| VLM grounding 准确率 | ≥ 85% | 方法见下 |
| 误操作率 | < 5% | 以上范围内，统计触发了但不应触发的 click/type |

**Grounding 准确率测量方法**：
- 构建一个固定的 grounding 基准集：记事本 + 计算器上共 20 个目标元素（按钮、菜单项、输入框），每个手工标注边界框（真值）
- 每次测试对每个元素跑 1 次 grounding，输出 `(x, y)`
- 若 `(x, y)` 落在真值边界框内 → 记为正确
- 准确率 = 正确数 / 20

v1.0 的"视觉识别准确率 > 90%"这种笼统指标被砍掉，换成可测量的场景指标。

---

## 15. 分阶段路线

### 15.1 Phase 1 — MVP（当前目标）

**目标**：记事本 demo 闭环跑通（见 §2.2）。

**交付**：
- CLI + HTTP + MCP 三种接入
- 探索性执行 + 成功固化 + 回归复跑
- **单模型 UITarsAgent**（UI-TARS-1.5-7B via 本地 vLLM）
- 关键词黑名单安全防护
- 结构化报告 + 截图证据

**不包括**：云端 API Planner、多应用泛化验证、全自动触发、多显示器、并发。

### 15.2 Phase 2 — 泛化与自动化

- 备选模型验证（MAI-UI on 3090，与 UI-TARS 横向对比）
- 至少 5 个异构应用（浏览器、Office、Electron、WPF、Win32）的 demo 覆盖
- 全自动触发（文件监听 + Git hook）
- 多显示器支持
- 回归用例的版本管理与 UI 大改自动重探索

### 15.3 Phase 3 — 生产就绪

- macOS / Linux 支持
- 并发执行（多实例 + 资源调度）
- 用例库 UI（查看、编辑、重放）
- 性能测试维度（非目标中有提到不做"负载/性能"，这里仅指测试执行本身的性能监控）

---

## 16. 开放问题（待后续决策）

- **UI-TARS system prompt 调优**：`COMPUTER_USE_DOUBAO` 模板已固定，但 goal 措辞、history 长度对成功率影响显著，需要在 MVP 开发初期做一轮系统测试。
- **回归用例指纹的 `app_version` 如何获取**：对有版本号的应用可用 PE 元数据，对其他应用可能需要哈希可执行文件。MVP 可以先用 exe 哈希。
- **pywin32 在部分安全软件下会被拦截**：需要在部署文档中说明，不纳入代码。
- **MCP 的 push 通知**在当前 MCP 协议下支持程度不一，MVP 先按轮询实现，Phase 2 再评估。

---

*文档结束。任何章节有异议请提出，将在 v2.1 中修订。*
