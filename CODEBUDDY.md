# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## Project Overview

AutoVisionTest — AI视觉驱动的桌面应用纯黑盒自动化测试框架。通过本地部署的视觉语言模型（VLM）理解屏幕内容，模拟键鼠操作执行测试，测试结果结构化反馈给AI编程Agent，形成"编码→测试→反馈→修复"闭环。

## Architecture

### Core Modules

```
autovisiontest/
├── scheduler/        # 测试管理器 - 接收测试请求、调度用例、管理生命周期
├── parser/           # 场景解析器 - 将测试描述(YAML/JSON/自然语言)转为可执行步骤
├── engine/           # 测试执行引擎 - 三Agent循环(规划→执行→反思)
│   ├── planner/      #   规划Agent - 分析截图、确定下一步操作
│   ├── actor/        #   执行Agent - 执行键鼠操作
│   └── reflector/    #   反思Agent - 验证结果、判断目标达成
├── perception/       # 视觉感知层 - 三级识别策略
│   ├── pixel/        #   L1像素级 - SSIM/SIFT截图对比
│   ├── ocr/          #   L2 OCR级 - PaddleOCR文字识别
│   └── vlm/          #   L3模型级 - ShowUI/Qwen2-VL视觉理解
├── control/          # 桌面控制层 - 鼠标、键盘、窗口管理(Win32 API)
├── reporter/         # 测试报告生成器 - 结构化反馈协议(JSON)
├── environment/      # 环境管理 - 应用启停、状态快照、数据回滚
└── inference/        # 本地AI推理服务 - vLLM/llama.cpp模型常驻推理
```

### Three-Level Visual Perception (Key Design Decision)

This is pure black-box testing — no code injection or accessibility API dependency. Three perception levels work together:
- **L1 (Pixel)**: Screenshot diff via SSIM/SIFT — detects visual changes only, zero dependencies
- **L2 (OCR)**: PaddleOCR — reads text on screen for element location and assertion
- **L3 (VLM)**: Visual Language Model (ShowUI-2B/Qwen2-VL-2B) — full screen understanding and action decision

Accessibility API (Windows UI Automation) is an optional enhancement when available, never a requirement.

### Test Case Types

- **Deterministic**: Fixed action sequence + precise assertions (YAML defined) — for regression tests
- **Exploratory**: Natural language goal, AI autonomous navigation — for smoke/exploratory tests  
- **Hybrid**: Key steps fixed + AI fills intermediate steps — for complex flows

### Termination Conditions (Prevents Infinite Loops)

Execution loop MUST check these in order: goal achieved → assertion passed → max_steps exceeded → repeated action detected (3x same action, no state change) → error dialog → app crash → manual stop.

### Feedback Protocol

Test results output as structured JSON containing: session info, test case metadata, pass/fail status with failure step/reason, screenshot evidence per step, full action trace with coordinates, coverage stats (elements interacted vs detected), and AI-generated bug hints with confidence scores. This JSON is consumed by AI coding agents.

## Reference Open-Source Projects

| Project | What to Learn From |
|---------|-------------------|
| **ScreenAgent** | "Plan-Execute-Reflect" loop design, reflection mechanism |
| **ShowUI-Aloha** | Lightweight 2B VLM model for local deployment, learning from human demonstrations |
| **Cradle** | General computer control — keyboard/mouse action space design, desktop control layer |
| **UFO** | Dual-agent architecture (AppAgent planner + ActAgent executor), Windows OS integration |

## Tech Stack

- Python 3.10+, vLLM/llama.cpp for local inference, ShowUI-2B/Qwen2-VL-2B-Instruct as VLM
- PaddleOCR for text recognition, OpenCV for image comparison
- pyautogui + Win32 API (ctypes/pywin32) for desktop control
- PyYAML for test case config, FastAPI for external API, structlog for logging

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run single test
pytest tests/test_perception.py -k "test_ocr_detect" -v

# Run full test suite
pytest tests/ -v

# Lint
ruff check src/ tests/

# Start local VLM inference service
python -m autovisiontest.inference.server --model showui-2b --gpu 0

# Run framework CLI
python -m autovisiontest run --config test_config.yaml

# Generate test report
python -m autovisiontest report --session ts-20260417-001
```

## Key Constraints

- **Pure black-box**: Never inject code into or modify the AUT. Visual perception must work without accessibility APIs.
- **Local AI only**: VLM must run on local GPU. No cloud API calls for screen understanding. Minimum 8GB VRAM for 2B model.
- **Single-step latency < 3s**: VLM stays resident in GPU memory. Screenshot compression + async inference to keep per-step time under 3 seconds.
- **Structured feedback**: All test results must conform to the JSON feedback protocol so AI coding agents can parse them programmatically.
