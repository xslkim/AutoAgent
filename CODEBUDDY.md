# CODEBUDDY.md

This file provides guidance to CodeBuddy when working with code in this repository.

## Project Overview

AutoVisionTest — AI 视觉驱动的桌面应用纯黑盒自动化测试框架。唯一输入是屏幕截图，唯一输出是键鼠操作。设计目标：嵌入"AI 编程闭环"——AI 写代码 → 构建 → AutoVisionTest 执行 → 结构化反馈 → AI 修复。

## Architecture

### Core Modules

```
src/autovisiontest/
├── cli.py                  # CLI 入口 (click)
├── config/                 # 配置加载 (Pydantic Settings + YAML)
├── logging_setup.py        # structlog 初始化
├── exceptions.py           # 自定义异常层级
├── control/                # 桌面控制层
│   ├── dpi.py              #   DPI 归一化初始化
│   ├── screenshot.py       #   截图采集 (mss)
│   ├── mouse.py            #   鼠标控制原语 (pyautogui)
│   ├── keyboard.py         #   键盘控制原语 (pyautogui + pyperclip)
│   ├── window.py           #   窗口管理 (pygetwindow + pywin32)
│   ├── process.py          #   进程管理 (subprocess + taskkill)
│   ├── actions.py          #   Action/ActionResult Pydantic 模型
│   └── executor.py         #   动作执行器 (分派到 mouse/keyboard)
├── perception/             # 视觉感知层
│   ├── types.py            #   BoundingBox/OCRItem/OCRResult 数据类
│   ├── ocr.py              #   PaddleOCR 引擎封装
│   ├── similarity.py       #   SSIM 相似度计算 (OpenCV)
│   ├── error_dialog.py     #   错误弹窗检测 (OCR + 关键词)
│   ├── change_detector.py  #   视觉变化/卡死检测 (环形缓冲 + SSIM)
│   └── facade.py           #   感知层门面 (截图+OCR一次调用)
├── backends/               # 模型后端抽象
│   ├── protocol.py         #   ChatBackend / GroundingBackend Protocol
│   ├── types.py            #   Message/ChatResponse/GroundingResponse 数据类
│   ├── claude.py           #   Claude API Chat 后端
│   ├── openai_backend.py   #   OpenAI API Chat 后端
│   ├── vllm_chat.py        #   vLLM 本地 Chat 后端 (OpenAI 兼容)
│   ├── showui.py           #   ShowUI-2B Grounding 后端
│   └── factory.py          #   后端工厂 (按配置分派)
├── safety/                 # 安全防护
│   ├── keywords.py         #   黑名单关键词常量
│   ├── blacklist.py        #   黑名单匹配器
│   ├── nearby_text.py      #   目标附近 OCR 文字抓取
│   ├── second_check.py     #   VLM 二次确认
│   └── guard.py            #   SafetyGuard 总入口
├── engine/                 # 测试执行引擎
│   ├── models.py           #   核心数据模型 (StepRecord/SessionContext/...)
│   ├── planner.py          #   Planner 调用封装
│   ├── actor.py            #   Actor 调用与 fallback 链
│   ├── assertions.py       #   断言器 (ocr/file/screenshot/vlm)
│   ├── terminator.py       #   终止条件检查 (T1-T8)
│   ├── step_loop.py        #   单步主循环
│   ├── exploratory.py      #   探索模式执行器
│   └── regression.py       #   回归模式执行器
├── cases/                  # 用例体系
│   ├── schema.py           #   TestCase Pydantic 模型
│   ├── fingerprint.py      #   用例指纹计算 (sha256)
│   ├── store.py            #   用例存取 (RecordingStore)
│   └── consolidator.py     #   用例固化器 (探索→回归)
├── scheduler/              # 会话调度
│   ├── session_scheduler.py #  SessionScheduler (探索/回归路由)
│   └── session_store.py    #   会话状态持久化
├── report/                 # 报告与证据
│   ├── schema.py           #   Report Pydantic 模型 (protocol v2.0)
│   ├── evidence.py         #   EvidenceWriter (截图+OCR落盘)
│   ├── builder.py          #   ReportBuilder (构造+截图投递策略)
│   └── cleaner.py          #   EvidenceCleaner (后台清理)
├── interfaces/             # 接入层
│   ├── cli_commands.py     #   CLI 子命令实装
│   ├── http_server.py      #   FastAPI HTTP 服务
│   └── mcp_server.py       #   MCP Server (stdio/http)
└── prompts/                # Planner/Reflector prompt 模板
    ├── planner.py          #   prompt 构造 + 响应解析
    └── planner_system.txt  #   系统提示模板
```

### Visual Perception (Key Design)

纯黑盒 — 不注入代码、不依赖 Accessibility/UIA。四层感知协作：

- **截图** (`mss`)：所有感知与决策的输入，每步循环开始 + 每次动作后
- **OCR** (`PaddleOCR`)：文字识别、OCR 断言、VLM grounding 失败时的 fallback 定位、错误弹窗检测
- **VLM Grounding** (`ShowUI-2B` / `OS-Atlas-2B`)：元素定位，输入自然语言描述 → 输出坐标
- **模板匹配** (`OpenCV SSIM`)：截图相似度计算（终止条件、回归校验、视觉断言）

### Test Execution Engine (Three Agents)

| Agent | 模型 | 职责 |
|-------|------|------|
| **Planner** | 大模型 (本地 Qwen2.5-VL 或云端 Claude/GPT-4o) | 分析截图 + 历史动作，输出下一步意图和目标描述 |
| **Actor** | 小模型 (ShowUI-2B / OS-Atlas-2B) | 根据 Planner 给的元素描述，grounding 输出具体坐标 |
| **Reflector** | 与 Planner 共享模型 | 验证上一步结果、判断目标达成、产出 bug_hints |

Planner 与 Reflector 共享对话上下文（一次调用完成规划+反思），Actor 独立调用。

### Test Case Types

两种用例，一个生命周期：

- **探索性 (Exploratory)**：AI 或人类给出自然语言目标，Planner 动态展开。路径不稳定，首次发现问题用。
- **回归 (Regression)**：探索性用例首次成功后**自动固化**。路径固定，快速可复跑，修复验证用。

### Termination Conditions (Prevents Infinite Loops)

按优先级：应用崩溃(T1) → 安全拦截(T2) → Reflector判定成功(T3) → 错误弹窗(T4) → 最大步数(T5) → 卡死(T6) → 重复动作无进展(T7) → 人工终止(T8)。

### Feedback Protocol

测试结果输出为结构化 JSON (protocol_version: "2.0")，包含：session 信息、目标、应用状态、结果状态+终止原因、每步动作轨迹（含坐标+grounding confidence+反思）、断言结果、关键失败截图（base64 或 MCP resource）、AI 生成的 bug_hints（含置信度）。专为多模态 AI 编程 Agent 消费设计。

## Key Design Decisions (D1-D12)

| # | 决策 | 约束 |
|---|------|------|
| D1 | 纯视觉路径，不接入 UIA | 不允许代码中出现 UIA 依赖 |
| D2 | 用例由 AI 生成或 AI 探索 | 不对外暴露人工 YAML 编写接口 |
| D3 | 探索→固化→复用 | 成功后必须自动保存为回归用例 |
| D4 | 模型后端可配置 | 本地 vLLM / 本地 llama.cpp / 云端 API |
| D5 | 元素定位统一走 VLM grounding | OCR 仅作 fallback |
| D6 | 坐标系：物理像素，入口归一化 | DPI 处理必须在入口一次性完成 |
| D7 | 冷启动 + 串行执行 | 每个用例前清理残留进程+重启被测应用 |
| D8 | 安全：关键词黑名单 + VLM 二次确认 | 不做路径白名单、不做沙箱 |
| D9 | 单步延迟 < 5 秒 | VLM 常驻 GPU，截图压缩+异步推理 |
| D10 | MVP 手动触发 | 自动触发留扩展钩子 |
| D11 | MCP Server 异步模式 | 提交返回 session_id，后续轮询 |
| D12 | 失败反馈内嵌关键截图 | 让 AI 能"看见" bug |

## Tech Stack

- Python 3.11+
- vLLM (≥ 0.6) / llama.cpp 用于本地推理；anthropic / openai / dashscope SDK 用于云端
- ShowUI-2B / OS-Atlas-2B 作为 Actor grounding 模型；Qwen2.5-VL-7B/32B 或 Claude/GPT-4o 作为 Planner
- PaddleOCR (≥ 2.7) 用于文字识别，OpenCV 用于图像对比
- pyautogui + pywin32 + pygetwindow + pyperclip + mss 用于桌面控制
- Pydantic Settings + YAML 用于配置，structlog 用于日志
- FastAPI + uvicorn 用于 HTTP，mcp Python SDK 用于 MCP Server，click 用于 CLI
- pytest + pytest-asyncio + pytest-mock + pytest-cov 用于测试

## Development Commands

```bash
# Install dependencies
pip install -e .[dev]

# Run single test
pytest tests/unit/perception/test_ocr.py -k "test_ocr_detect" -v

# Run full test suite
pytest tests/ -v

# Lint
ruff check src/ tests/

# Start local VLM inference service (planner)
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-VL-7B-Instruct-AWQ --port 8000

# Start local VLM inference service (actor/grounding)
python -m vllm.entrypoints.openai.api_server --model showlab/ShowUI-2B --port 8001

# Run framework CLI
autovisiontest run --goal "打开记事本,输入hello,保存到D:\a.txt" --app "notepad.exe"

# Start HTTP server
autovisiontest serve --port 8080

# Start MCP server
autovisiontest mcp

# Generate test report
autovisiontest report <session_id> --format json
```

## Key Constraints

- **Pure black-box**: 不读被测应用源码，不注入 Agent，不依赖 Accessibility/UIA。所有感知必须基于截图。
- **Model backend configurable**: VLM 可本地可云端。Actor grounding 建议本地。Minimum 8GB VRAM for 2B model；Planner 用云端时无本地 GPU 要求。
- **Single-step latency < 5s**: VLM 常驻 GPU 内存。截图压缩（短边1080px, JPEG Q85）+ 异步推理。
- **Structured feedback**: 所有测试结果必须符合 protocol v2.0 JSON schema，使 AI 编程 Agent 可编程消费。
- **Safety first**: 关键词黑名单 + VLM 二次确认 + 熔断（30步/10分钟上限），不允许绕过。

## Dual-Agent Development Workflow

本项目使用 Dev Agent + Test Agent 双 Agent 协作开发，详见 `docs/dev_workflow.md`。

核心规则：
- Dev 写生产代码 + 基础测试；Test 做独立验收 + 补充 edge case 测试
- 通过 `.agent/handoffs/` 和 `.agent/reviews/` 文件异步通信
- 同一任务最多 3 轮 review，超过自动升级给人类
- 所有决定落盘为文件 + Git commit
