# AutoVisionTest — AI 视觉驱动的桌面应用自动化测试框架

## 产品文档 v2.1

文档日期：2026-04-18
对应里程碑：MVP（Phase 1）

---

## 0. 本文档的改动说明（相对 v1.0）

v1.0 存在若干不落地的假设：纯本地 VLM 在主流硬件上跑不动 3 秒延迟目标；三种用例类型（确定性/探索性/混合）并行推进会让 MVP 无限延期；YAML 用例需要人工编写，与"全自动闭环"目标矛盾；坐标系没有明确规则，Planner 与 Actor 无法协同。v2.0 对这些问题做了正面回答，具体决策见第 2 章。

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
| D4 | **模型后端可配置**：本地 vLLM / 本地 llama.cpp / 云端 API（Claude、GPT-4o、Qwen-VL-Max） | 支持 3080Ti/3090/5090/云端多种部署，兼顾成本与能力 |
| D5 | **元素定位统一走 VLM grounding**，OCR 作为 fallback，模板匹配只用于断言 | 消除 Planner 与 Actor 的坐标系分歧 |
| D6 | **坐标系：物理像素，入口归一化**。高 DPI、多显示器在入口一次性处理 | pyautogui 在 HiDPI 下有坑，必须显式处理 |
| D7 | **冷启动 + 串行执行**：每个用例前清理残留进程 + 重启被测应用 | 消除脏状态，MVP 不追求速度 |
| D8 | **安全：关键词黑名单 + VLM 二次确认**，不做路径白名单、不做沙箱 | MVP 够用；沙箱/VM 是用户自己的事 |
| D9 | **单步延迟 < 5 秒**（从截图到动作完成） | 本地 7B-INT4 规划 + ShowUI grounding 串行的现实值 |
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
│  │ 执行引擎 (ExecutionEngine)                            │   │
│  │   Planner ↔ Actor ↔ Reflector  (see §5)              │   │
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
          ┌─────────────┴──────────────┐
          ▼                            ▼
  ┌───────────────┐            ┌───────────────┐
  │ 本地 VLM 服务  │            │  云端 VLM API  │
  │ (独立进程)     │            │  (可选)        │
  │ vLLM / llama  │            │  Claude / GPT  │
  └───────────────┘            └───────────────┘
```

### 3.2 关键进程划分

- **主进程**：AutoVisionTest 框架本体（Python），常驻。
- **本地 VLM 服务**：独立进程，通过 OpenAI 兼容 HTTP 接口调用。这样模型加载成本只付一次，且主进程崩溃不影响模型。
- **云端 VLM**：不需要本地进程，HTTP 直连。
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

**固化时机**：探索成功（Reflector 判定目标达成 + 所有断言通过）后，把完整操作序列 + 每步截图的 grounding 结果 + Reflector 的断言结果一起序列化。

**回归用例失效判定**：回归执行过程中，若**连续 2 步**的预期截图与实际截图 SSIM < 0.5，或 VLM grounding 找不到预期元素 → 判定"UI 大改，回归用例失效" → **自动回退到探索模式**并重新固化。

**用例指纹（fingerprint）**：`sha256(app_path + normalized_goal + app_version)`。`normalized_goal` 是对自然语言目标做小写化、去标点、去停用词后的结果。同一应用同一目标同一版本，指纹相同。

### 4.3 内部数据结构

**对外不暴露**，仅作为框架内部落盘格式与 Planner/Actor 交互的中间表示。

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

### 5.1 三 Agent 职责

| Agent | 模型 | 输入 | 输出 | 调用频次 |
|-------|------|------|------|---------|
| **Planner** | 大模型（本地 7B-INT4 或云端 Claude/GPT-4o） | 当前截图 + 目标 + 历史动作 + 上一步反思 | 下一步的**自然语言意图** + 目标元素描述 | 每步 1 次 |
| **Actor** | 小模型（本地 ShowUI-2B 或 OS-Atlas-2B） | 当前截图 + Planner 给的元素描述 | 具体坐标 + 键鼠原语 | 每步 1 次 |
| **Reflector** | 与 Planner 同一个模型（复用会话） | 动作前后截图 + Planner 的预期 | 是否达成、是否继续、是否命中终止 | 每步 1 次 |

**合并优化**：Planner 与 Reflector 可以共享一个对话上下文（同一个模型 API 调用），这样可以把"规划 + 上一步反思"合成一次调用，**把每步的大模型调用数从 2 降到 1**。Actor 必须独立调用（模型不同）。

### 5.2 单步主循环

```
┌─────────────────────────────────────────────────────────┐
│ step_idx = 0                                            │
│ history = []                                            │
│ while True:                                             │
│   1. screenshot = capture()                             │
│   2. ocr_result = ocr(screenshot)  # 缓存,本步多处复用  │
│   3. 终止检查 terminate_conditions_met(                 │
│         screenshot, ocr_result, history, app_state      │
│      ) → 命中任一 T1..T8 则结束                          │
│   4. Planner+Reflector 合并调用:                        │
│        输入: goal, screenshot, history, last_expect     │
│        输出: {                                          │
│          reflection: "上一步成功/失败/其他",             │
│          done: bool,                                    │
│          bug_hints: [...] (失败/卡住时产出),             │
│          next_intent: "点击'保存'按钮",                  │
│          target_desc: "保存按钮,通常在菜单栏" | null,    │
│          action: {type: "click|type|...", params: {}}   │
│        }                                                │
│   5. 如果 done=True: break 成功                         │
│   6. 动作分派 (§5.5):                                    │
│      - 需要 grounding 的动作(NEED_TARGET)               │
│          → Actor grounding → OCR fallback(§6.3)         │
│          → 得到 (x, y)                                  │
│      - 不需要 grounding 的动作(NO_TARGET)               │
│          → 直接使用 action.params                       │
│   7. 安全拦截 SafetyGuard.check(action, ocr_result)     │
│        命中黑名单 → VLM 二次确认(§9.2)                   │
│        二次确认仍危险 → 中止,上报 ABORT:UNSAFE           │
│   8. desktop_control.execute(action)                    │
│   9. 等待 wait_ms (默认 500ms,可动态调整)                │
│   10. history.append({step_idx, action, result})        │
│   11. step_idx += 1                                     │
└─────────────────────────────────────────────────────────┘
```

说明：
- **步 2 的 OCR 结果在本步内复用**：终止检查（错误弹窗）、安全拦截（黑名单匹配）、grounding fallback、断言判定 都读同一份缓存，避免重复调用。
- **步 4 的 `target_desc`** 对 NO_TARGET 类动作设为 `null`。Planner 必须在 prompt 中被告知哪些动作不需要目标。
- **步 7 的安全拦截**见 §9，对 NO_TARGET 动作也要检查（例如 `type` 的文本内容）。

### 5.3 终止条件

按优先级从高到低：

| # | 条件 | 检测方法 | 结果 |
|---|------|---------|------|
| T1 | **应用崩溃** | 目标进程不存在 或 主窗口句柄失效 | FAIL: CRASH |
| T2 | **命中安全黑名单** | SafetyGuard 拦截 | ABORT: UNSAFE |
| T3 | **Reflector 判定成功** | Planner 返回 `done=true` 且所有断言通过 | PASS |
| T4 | **错误弹窗** | OCR 检测到"错误/Error/异常"等关键词 + 弹窗窗口特征 | FAIL: ERROR_DIALOG |
| T5 | **最大步数** | step_idx >= max_steps（默认 30） | FAIL: MAX_STEPS |
| T6 | **卡死** | 连续 10 秒 SSIM(last, current) > 0.99 且已尝试过动作 | FAIL: STUCK |
| T7 | **重复动作无进展** | 连续 3 步相同 action_type + 相同 target_desc + 截图 SSIM > 0.95 | FAIL: NO_PROGRESS |
| T8 | **人工终止** | 收到 stop 信号 | ABORT: USER |

### 5.4 回归模式执行

与探索模式共用主循环，但有两点差异：

1. **Planner 不用大模型**：直接读取 `recordings/*.json` 的 `steps`，按 idx 顺序吐出 `next_intent`。
2. **每步都做预期校验**：执行前比对当前截图与 `expect.screenshot_hash` 的 SSIM，若连续 2 步 SSIM < 0.5 → 判定 UI 大改 → 中止回归 → 回落到探索模式（见 §4.2）。

### 5.5 动作分类

| 类别 | 动作 | 是否需要 target_desc / grounding |
|------|------|------|
| **NEED_TARGET** | `click` / `double_click` / `right_click` / `drag`（起点）/ `scroll`（指定位置） | 是 |
| **NO_TARGET** | `type` / `key_combo` / `wait` / `scroll`（全局滚动） | 否 |
| **META** | `launch_app` / `close_app` / `focus_window` | 否 |

`drag` 的终点若是相对于起点的位移，走 NEED_TARGET（起点定位）；若终点也是元素，两次 grounding。MVP 只支持第一种以降低复杂度。

### 5.6 bug_hints 的产出

`bug_hints` 由 Planner/Reflector 在以下时机生成：

- Reflector 判定**上一步失败**（预期元素未出现、意外弹窗、OCR 期望文字未出现）
- 终止条件 T4（错误弹窗）、T5（最大步数）、T6（卡死）、T7（无进展）触发时
- 探索结束（PASS 或 FAIL）时，对整体轨迹给一次总结

每条 hint 字段：`{description, confidence, related_hypothesis[]}`。Planner 的 system prompt 中应包含"若无法给出置信度 > 0.4 的 hint 则返回空数组，宁缺毋滥"的约束。

---

## 6. 视觉感知与坐标系

### 6.1 感知层分工

| 层 | 用途 | 何时调用 |
|---|------|---------|
| **截图** | 所有感知与决策的输入 | 每步循环开始 + 每次动作后 |
| **OCR (PaddleOCR)** | 文字识别、OCR 断言、VLM grounding 失败时的 fallback 定位、错误弹窗检测 | 每步 1 次（异步，不阻塞 Planner） |
| **VLM grounding (Actor)** | 元素定位，输入自然语言描述 → 输出坐标 | 每个需要定位的动作前 1 次 |
| **模板匹配 (OpenCV SSIM)** | 截图相似度计算（终止条件、回归校验、视觉断言） | 终止检查 + 回归校验 |

### 6.2 坐标系规则（强约束）

**所有内部坐标统一用"主屏左上角为原点的物理像素"**。

- 入口处（截图采集时）做一次 DPI 归一化：读取 `GetDpiForMonitor`，记录缩放因子，后续所有截图都缩放到"逻辑像素 = 物理像素"的状态。
- 多显示器：MVP 只支持**主屏**。多屏是 Phase 2。
- `pyautogui` 在调用前 `ctypes.windll.shcore.SetProcessDpiAwareness(2)`，避免坐标偏移。
- 被测应用的 `region` 相对坐标（若回归用例里保存了）在使用时乘以当前截图尺寸还原为物理像素。

### 6.3 元素定位的 fallback 链

Actor 执行定位时，按顺序尝试：

1. **VLM grounding**（ShowUI-2B / OS-Atlas-2B）：输入 `target_desc`，输出 `(x, y, confidence)`。
2. 若 `confidence < 0.6`：**OCR 文字匹配**。若 `target_desc` 里带引号字符串（例如 `"保存"`按钮），直接 OCR 找这个文字的中心点。
3. 若 OCR 也失败：**让 Planner 重试**（给它看当前截图 + "上一步定位失败"反馈），最多 2 次。
4. 仍失败：上报 `FAIL: TARGET_NOT_FOUND`。

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

拆分为两个独立 Protocol，避免规划模型被迫实现 grounding：

```python
class ChatBackend(Protocol):
    """用于 Planner/Reflector。云端 API 和本地通用 VLM 都实现此接口。"""
    def chat(
        self,
        messages: list[Message],
        images: list[bytes] | None = None,
        response_format: Literal["text", "json"] = "json",
    ) -> ChatResponse: ...

class GroundingBackend(Protocol):
    """用于 Actor。仅专门的 grounding 模型实现。"""
    def ground(self, image: bytes, query: str) -> GroundingResponse:
        # returns (x, y, confidence: 0..1)
        ...
```

Planner 通过 `ChatBackend` 注入；Actor 通过 `GroundingBackend` 注入。两者是独立的依赖，可分别配置后端。

### 8.2 后端矩阵

| 后端 | 角色 | 模型 | 硬件 | 备注 |
|------|------|------|------|------|
| `local_vllm` | Planner/Reflector | Qwen2.5-VL-7B-INT4 | 3080Ti / 3090 | vLLM 独立进程，OpenAI 兼容 API |
| `local_vllm` | Planner/Reflector | Qwen2.5-VL-32B-INT4 | 5090 | 同上 |
| `local_vllm` | Actor | ShowUI-2B / OS-Atlas-2B | 所有 | 与规划模型共存 GPU（3080Ti 需注意显存） |
| `claude_api` | Planner/Reflector | claude-opus-4-7 / claude-sonnet-4-6 | 云端 | Actor 仍用本地 grounding |
| `openai_api` | Planner/Reflector | gpt-4o / gpt-4o-mini | 云端 | 同上 |
| `qwen_api` | Planner/Reflector | qwen-vl-max | 云端 | 同上 |

**注**：Actor（grounding）**必须本地**，因为云端通用 VLM 对 GUI 坐标的精度明显低于专门的 grounding 模型。

### 8.3 推荐配置

| 硬件 | 推荐配置 | 预估单步延迟 |
|------|---------|-------------|
| 3080Ti 12GB | Planner=Claude API, Actor=ShowUI-2B 本地 | 2-3 秒 |
| 3080Ti 12GB（纯本地） | Planner=Qwen2.5-VL-7B-INT4, Actor=ShowUI-2B | 4-5 秒（贴边） |
| 3090 24GB | Planner=Qwen2.5-VL-7B FP16, Actor=ShowUI-2B | 3-4 秒 |
| 5090 32GB | Planner=Qwen2.5-VL-32B-INT4, Actor=OS-Atlas-2B | 3-4 秒 |

**MVP 默认**：Planner = Claude API（开发期稳定性优先），Actor = ShowUI-2B 本地。纯本地配置作为 Phase 2 验证项。

### 8.4 配置文件

`config/model.yaml`：

```yaml
planner:
  backend: "claude_api"   # local_vllm | claude_api | openai_api | qwen_api
  model: "claude-opus-4-7"
  api_key_env: "ANTHROPIC_API_KEY"
  max_tokens: 2048
  temperature: 0.2

actor:
  backend: "local_vllm"
  model: "showlab/ShowUI-2B"
  endpoint: "http://localhost:8001/v1"
  confidence_threshold: 0.6
```

### 8.5 本地进程布局

当 Planner 和 Actor 都用本地模型时，**启动两个独立的 vLLM 进程**（不共享）：

| 进程 | 端口 | 模型 | 显存估算 (3080Ti) |
|------|------|------|------|
| `vllm-planner` | 8000 | Qwen2.5-VL-7B-INT4 | ~6-7 GB |
| `vllm-actor` | 8001 | ShowUI-2B FP16 | ~5 GB |

选择两进程的理由：
- vLLM 单进程的多模型支持不稳定，且模型切换会引起调度抖动
- 两个模型请求频次完全不同（Planner 每步 1 次长上下文，Actor 每步 1 次短上下文），独立进程各自调参更容易
- 进程隔离，一个模型崩溃不影响另一个

3080Ti 12GB 同时跑两个本地进程贴边，**若不够**：退化为"Planner 云端 + Actor 本地"。配置文件按第 8.3 节表格切换。

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

命中黑名单时**不立即中止**，先向 Planner 发问：

> "即将对文字为 '{text}' 的元素执行 {action}，在当前测试目标 '{goal}' 下，这是否是预期且安全的操作？只回答 'safe' 或 'unsafe'，并给一句理由。"

- 回答 `safe` → 放行，**并在 session 日志中记录一条 `SAFETY_OVERRIDE`**
- 回答 `unsafe` 或解析失败 → 中止，`ABORT: UNSAFE`

二次确认最多每会话 3 次，超过则后续任何命中都直接中止（防止 Planner 被诱导连续放行）。

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

| 硬件 | 模型配置 | 单步延迟 | 状态 |
|------|---------|---------|------|
| 3080Ti 12GB | Claude API + ShowUI-2B | 2-3s | **MVP 开发主力** |
| 3080Ti 12GB | Qwen2.5-VL-7B-INT4 + ShowUI-2B | 4-5s | Phase 2 纯本地验证 |
| 3090 24GB | Qwen2.5-VL-7B FP16 + ShowUI-2B | 3-4s | Phase 2 |
| 5090 32GB | Qwen2.5-VL-32B-INT4 + OS-Atlas-2B | 3-4s | Phase 2 |

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
| GPU | 3080Ti 12GB（Planner 走云端时）/ 见 §12.1 矩阵 | 3090 / 5090 |
| 网络 | Planner 走云端时需稳定公网 | 千兆 |

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
| 单步延迟 | < 5 秒 | Claude API Planner + 本地 Actor，千兆网，取 20 次中位数 |
| 模型冷启动 | < 60 秒 | ShowUI-2B via vLLM，从进程启动到首次 ground 调用返回 |
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
- Claude API Planner + ShowUI-2B Actor
- 关键词黑名单安全防护
- 结构化报告 + 截图证据

**不包括**：纯本地 Planner、多应用泛化验证、全自动触发、多显示器、并发。

### 15.2 Phase 2 — 泛化与自动化

- 纯本地 Planner 验证（Qwen2.5-VL-7B-INT4 on 3080Ti）
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

- **Planner prompt 模板**需要在 MVP 开发初期先做一轮 prompt engineering，目前只有骨架。
- **回归用例指纹的 `app_version` 如何获取**：对有版本号的应用可用 PE 元数据，对其他应用可能需要哈希可执行文件。MVP 可以先用 exe 哈希。
- **pywin32 在部分安全软件下会被拦截**：需要在部署文档中说明，不纳入代码。
- **MCP 的 push 通知**在当前 MCP 协议下支持程度不一，MVP 先按轮询实现，Phase 2 再评估。

---

*文档结束。任何章节有异议请提出，将在 v2.1 中修订。*
