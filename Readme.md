# AutoVisionTest

AI 视觉驱动的桌面应用纯黑盒自动化测试框架。

## 概述

AutoVisionTest 通过本地部署的视觉语言模型（VLM）理解屏幕内容，模拟键鼠操作执行测试，测试结果结构化反馈给 AI 编程 Agent，形成 **"编码 → 测试 → 反馈 → 修复"闭环**。

核心特点：
- **零侵入**：纯视觉黑盒，不读被测应用源码，不注入 Agent，不依赖 Accessibility/UIA
- **AI 自主**：测试用例由 AI 生成或 AI 探索，无需人工编写 YAML
- **闭环反馈**：失败报告结构化 + 关键截图，专为多模态 AI Agent 消费设计
- **可回归**：探索性用例首次成功后自动固化为确定性回归用例

## 快速开始

```bash
# 安装
pip install -e .[dev]

# CLI 运行探索性测试
autovisiontest run --goal "打开记事本,输入hello,保存到D:\a.txt" --app "notepad.exe"

# 启动 HTTP API
autovisiontest serve --port 8080

# 启动 MCP Server (供 Claude Code / Cursor 调用)
autovisiontest mcp
```

## 文档

| 文档 | 说明 |
|------|------|
| [docs/product_document.md](docs/product_document.md) | 产品文档 v2.1 — 架构、设计决策、MVP 验收场景 |
| [docs/task_document.md](docs/task_document.md) | 任务文档 v2.0 — 56 个原子任务分解 |
| [docs/dev_workflow.md](docs/dev_workflow.md) | 开发流程 v1.0 — 双 Agent 协作工作流 |

## 技术栈

- Python 3.11+ / Pydantic / structlog / click
- PaddleOCR / OpenCV / mss (视觉感知)
- pyautogui / pywin32 / pygetwindow / pyperclip (桌面控制)
- vLLM / ShowUI-2B / Qwen2.5-VL / Claude API / GPT-4o (模型后端)
- FastAPI / mcp Python SDK (接入层)

## 许可

MIT
