# AutoVisionTest

> **AI 视觉驱动的桌面应用自动化测试框架**，专为 AI 编程 Agent 闭环开发设计。

AI 写代码 → 构建 → AutoVisionTest 执行视觉测试 → 结构化反馈（含截图）→ AI 修复 → 循环。

---

## 目录

1. [核心理念：闭环开发](#1-核心理念闭环开发)
2. [前置条件](#2-前置条件)
3. [快速启动](#3-快速启动)
4. [AI Agent 集成（MCP 接口）](#4-ai-agent-集成mcp-接口)
5. [闭环开发完整流程](#5-闭环开发完整流程)
6. [报告格式与 AI 反馈](#6-报告格式与-ai-反馈)
7. [HTTP API 接口](#7-http-api-接口)
8. [CLI 接口](#8-cli-接口)
9. [配置参考](#9-配置参考)
10. [目录结构](#10-目录结构)
11. [FAQ](#11-faq)

---

## 1. 核心理念：闭环开发

传统自动化测试依赖人工维护测试脚本，AI 编程时代这个环节成为瓶颈。AutoVisionTest 解决这个问题：

```
┌─────────────────────────────────────────────────────────┐
│                   AI 编程闭环                            │
│                                                         │
│   AI Agent                                              │
│   (Cursor / Claude Code / 自定义)                        │
│       │                                                 │
│       │ 1. 写代码、构建                                   │
│       │                                                 │
│       │ 2. 调用 MCP 触发测试                              │
│       ▼                                                 │
│   AutoVisionTest ──────────────────────────────────┐    │
│       │ 纯视觉执行（截图→VLM→键鼠操作）                │    │
│       ▼                                            │    │
│   被测桌面应用                                      │    │
│       │                                            │    │
│       │ 3. 返回结构化报告 + 失败截图                 │    │
│       └────────────────────────────────────────────┘    │
│       │                                                 │
│       │ 4. AI 读报告，自主修复代码                        │
│       └─────────────────────────────────────────────┐   │
│                      循环直到 PASS                   │   │
└──────────────────────────────────────────────────────┘   │
```

**关键特性：**

| 特性 | 说明 |
|------|------|
| **零侵入** | 不读源码、不注入 Agent、不依赖 Accessibility/UIA，唯一输入是屏幕截图 |
| **自然语言目标** | 测试目标用自然语言描述，AI 或人类都能直接写 |
| **探索 → 固化 → 回归** | 首次探索成功后自动生成回归用例，之后每次测试走确定性回放，快速稳定 |
| **结构化反馈** | 失败报告 JSON 格式，内嵌关键截图（base64），多模态 AI Agent 可直接消费 |
| **单模型推理** | UI-TARS-1.5-7B 一次推理同时输出思考链 + 绝对像素坐标动作，单步延迟 3-4 秒 |
| **多后端支持** | 本地 vLLM（UI-TARS / MAI-UI）或云端 API（Claude / OpenAI）均可作为推理后端 |
| **安全防护** | 内置黑名单 + VLM 二次确认，防止误操作系统文件或凭据 |

---

## 2. 前置条件

### 2.1 系统要求

- **OS**：Windows 10 / 11（桌面控制依赖 Windows API）
- **GPU**：NVIDIA RTX 3080Ti 12GB 或更高（运行本地 VLM，使用云端 API 时可不需要）
- **WSL2**：Ubuntu 22.04（运行 vLLM 服务，使用云端 API 时可不需要）
- **Python**：3.11+（Windows 主进程）

### 2.2 安装 AutoVisionTest

```powershell
# 克隆仓库
git clone <repo_url> D:\AutoAgent
cd D:\AutoAgent

# 基础安装（含开发依赖）
pip install -e ".[dev]"

# 按需安装可选功能
pip install -e ".[http]"   # HTTP API 服务（FastAPI + uvicorn）
pip install -e ".[mcp]"    # MCP 接口（供 Cursor / Claude Code 接入）
pip install -e ".[cloud]"  # 云端 API 后端（OpenAI / Claude）

# 一键安装全部
pip install -e ".[dev,http,mcp,cloud]"
```

### 2.3 部署推理后端

#### 选项 A：本地 UI-TARS（推荐，无需网络）

在 WSL2 内启动 vLLM 服务（首次加载约 2-3 分钟）：

```bash
conda activate vllm

vllm serve flin775/UI-TARS-1.5-7B-AWQ \
    --served-model-name ui-tars-1.5-7b \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.85
```

验证服务就绪：

```bash
curl http://localhost:8000/v1/models | python3 -m json.tool
```

详细部署步骤见 [docs/uitars_wsl2_deploy.md](docs/uitars_wsl2_deploy.md)。

#### 选项 B：本地 MAI-UI

```bash
vllm serve <mai-ui-model> \
    --served-model-name mai-ui \
    --host 0.0.0.0 \
    --port 8001
```

#### 选项 C：云端 API（Claude / OpenAI）

无需本地 GPU，在 `config/model.yaml` 中配置对应后端即可（见 [第 9 节](#9-配置参考)）。

### 2.4 配置文件

编辑 `config/model.yaml`（默认配置已可用）：

```yaml
agent:
  backend: "uitars_local"
  model: "ui-tars-1.5-7b"
  endpoint: "http://localhost:8000/v1"   # WSL2 vLLM 服务
  max_tokens: 512
  temperature: 0.0
  language: "Chinese"
  history_images: 3
  timeout_s: 60.0

runtime:
  max_steps: 50
  max_session_duration_s: 600
  step_wait_ms: 500
  data_dir: "./data"
```

也可通过环境变量覆盖配置（见 [第 9.3 节](#93-环境变量覆盖)）。

---

## 3. 快速启动

### 3.1 CLI 方式（验证环境）

```powershell
# 验证当前配置是否有效
python -m autovisiontest validate

# 启动一个探索性测试会话（阻塞直到完成）
python -m autovisiontest run \
    --goal "打开记事本，输入 hello world，保存到 C:\TestSandbox\out.txt" \
    --app "C:\Windows\System32\notepad.exe"
```

成功后会在 `./data/sessions/<session_id>/` 下生成报告和截图，
并在 `./data/recordings/` 下生成回归用例。

### 3.2 MCP 方式（接入 AI Agent，推荐）

启动 MCP Server（stdio 模式，供 Cursor/Claude Code 接入）：

```powershell
python -m autovisiontest mcp
```

或 HTTP/SSE 模式（供自定义 Agent 接入）：

```powershell
python -m autovisiontest mcp --http :8090
```

### 3.3 HTTP API 方式

启动 REST API 服务：

```powershell
python -m autovisiontest serve --port 8080
```

---

## 4. AI Agent 集成（MCP 接口）

MCP（Model Context Protocol）是接入 AI Agent 的**首选方式**，Cursor、Claude Code 等工具原生支持。

### 4.1 Cursor 配置

在 Cursor 的 MCP 设置中添加：

```json
{
  "mcpServers": {
    "autovisiontest": {
      "command": "python",
      "args": ["-m", "autovisiontest", "mcp"],
      "cwd": "D:\\AutoAgent"
    }
  }
}
```

重启 Cursor 后，AI Agent 即可调用以下 6 个工具。

### 4.2 MCP 工具清单

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `start_test_session` | 启动测试会话（异步，立即返回 session_id） | `goal`, `app_path`, `app_args` |
| `get_session_status` | 查询会话状态与进度 | `session_id` |
| `get_session_report` | 获取完整测试报告（含截图） | `session_id` |
| `stop_session` | 停止运行中的会话 | `session_id` |
| `list_recordings` | 列出所有已固化的回归用例 | — |
| `invalidate_recording` | 删除一条回归用例（强制下次走探索） | `fingerprint` |

### 4.3 MCP 工具使用示例

**启动测试：**

```
工具：start_test_session
参数：
  goal: "验证文件保存功能：打开记事本，输入 'test content'，保存到 C:\TestSandbox\out.txt，确认文件存在"
  app_path: "C:\Windows\System32\notepad.exe"
  app_args: ""

返回：{"session_id": "sess_a1b2c3d4"}
```

**轮询状态（每 5 秒轮询一次，通常 1-3 分钟完成）：**

```
工具：get_session_status
参数：session_id: "sess_a1b2c3d4"

返回：{
  "session_id": "sess_a1b2c3d4",
  "status": "RUNNING",       // PENDING | RUNNING | COMPLETED | FAILED | STOPPED
  "mode": "exploratory",     // 首次：探索；之后：regression
  "progress": 0.4,
  "current_step": "Step 7/50: 点击保存按钮"
}
```

**获取报告（仅 COMPLETED/FAILED 后有效）：**

```
工具：get_session_report
参数：session_id: "sess_a1b2c3d4"
```

---

## 5. 闭环开发完整流程

以下是 AI Agent（如 Cursor）接入 AutoVisionTest 实现闭环的标准流程。

### 5.1 流程图

```
AI Agent 收到开发任务
         │
         ▼
   写实现代码 + 构建
         │
         ▼
   调用 start_test_session                ◄──────────────────┐
         │                                                   │
         ▼                                                   │
   轮询 get_session_status                                   │
         │                                                   │
    RUNNING？──等待 5 秒──┐                                   │
         │               │                                   │
    完成？◄───────────────┘                                   │
         │                                                   │
         ├── COMPLETED ──► get_session_report ──► 读"PASS"  │
         │                    报告              ──► 任务完成  │
         │                                                   │
         └── FAILED ──────► get_session_report               │
                              读失败截图 + 错误描述            │
                              读 bug_hints 分析根因            │
                              修复代码 + 重新构建 ─────────────┘
```

### 5.2 探索 → 固化 → 回归

**第一次测试（探索模式）：**

AutoVisionTest 调用 VLM 模型，自主决策每一步操作，直到完成目标或达到终止条件。

- 成功后：自动将完整操作序列保存为 `data/recordings/<fingerprint>.json`
- 下次同目标测试：自动走**回归模式**（回放固化步骤），速度提升 3-5 倍

**修复验证场景：**

```
1. 首次探索成功 → 生成回归用例
2. 代码改动破坏功能
3. Agent 触发测试 → 自动走回归模式
4. 回归失败 → 返回失败截图 + bug_hints
5. Agent 修复代码
6. 再次测试 → PASS
```

**强制重新探索（当 UI 大改时）：**

```
工具：invalidate_recording
参数：fingerprint: "a1b2c3..."   // 从 list_recordings 获取

下次测试将重新走探索模式，生成新的回归用例
```

### 5.3 AI Agent Prompt 模板

在 Cursor 或 Claude Code 的系统提示中加入以下说明，让 AI Agent 知道如何使用 AutoVisionTest：

```
你有访问 AutoVisionTest 的 MCP 工具权限，可以对 Windows 桌面应用做视觉自动化测试。

测试流程：
1. 用 start_test_session 启动测试，记录 session_id
2. 每 5-10 秒调用 get_session_status 轮询，直到 status 不为 RUNNING
3. 用 get_session_report 获取报告
4. 如果 result.status == "PASS"，测试通过
5. 如果 result.status == "FAIL"，读取 result.failure_reason、steps[].screenshot_after
   （截图为 base64 PNG，可直接查看）以及 bug_hints 字段中的 AI 根因分析

注意：
- 首次测试走探索模式（较慢，1-3 分钟）；之后走回归模式（较快，30-60 秒）
- 报告中的截图直接内嵌在 JSON 里，用于帮助你定位视觉 bug
- bug_hints 是框架根据失败模式自动生成的根因假设，可作为修复起点
- 如果连续失败 3 次，考虑调用 invalidate_recording 删除旧回归用例，强制重新探索
```

---

## 6. 报告格式与 AI 反馈

测试完成后，`get_session_report` 返回结构化 JSON，专为 AI 消费设计。

### 6.1 报告结构

```json
{
  "meta": {
    "version": "2.0",
    "generated_at": "2026-04-29T10:23:45Z"
  },
  "session": {
    "id": "sess_a1b2c3d4",
    "goal": "打开记事本，输入 hello world，保存到 C:\\TestSandbox\\out.txt",
    "mode": "exploratory",
    "trigger": "mcp",
    "app": {
      "path": "C:\\Windows\\System32\\notepad.exe",
      "pid": 12345
    }
  },
  "result": {
    "status": "PASS",              // PASS | FAIL
    "termination_reason": "PASS",  // 见终止原因说明
    "total_steps": 8,
    "duration_s": 45.2
  },
  "summary": "完成目标：打开记事本 → 输入文字 → Ctrl+S 保存 → 确认文件存在",
  "failure_reason": null,          // FAIL 时有内容，包含具体失败原因
  "bug_hints": [                   // AI 自动生成的根因假设（FAIL 时）
    {
      "hypothesis": "保存对话框未弹出，可能是快捷键 Ctrl+S 未触达目标窗口",
      "confidence": 0.85
    }
  ],
  "steps": [
    {
      "step_idx": 1,
      "thought": "当前屏幕显示桌面，需要打开记事本。点击搜索栏输入 notepad。",
      "action": {"type": "click", "params": {"x": 960, "y": 1060}},
      "assertion_results": [],
      "screenshot_before": "<base64 PNG>",
      "screenshot_after": "<base64 PNG>"
    }
  ],
  "assertions": [
    {
      "type": "file_exists",
      "params": {"path": "C:\\TestSandbox\\out.txt"},
      "passed": true,
      "message": "文件存在"
    }
  ]
}
```

### 6.2 终止原因说明

| termination_reason | 含义 | AI Agent 处理建议 |
|--------------------|------|-------------------|
| `PASS` | 所有步骤完成且断言通过 | 任务成功 |
| `ASSERTION_FAILED` | 步骤执行完但断言失败 | 查看 assertions 数组定位具体失败的断言 |
| `CRASH` | 被测应用崩溃 | 检查代码是否有未处理异常 |
| `ERROR_DIALOG` | 检测到错误弹窗 | 查看失败截图，定位 UI 错误 |
| `MAX_STEPS` | 超过最大步数（默认 50 步）未完成 | 目标可能太复杂，拆分为子目标 |
| `STUCK` | 连续多步屏幕无变化（SSIM ≥ 0.99） | 被测应用可能卡住，查看截图 |
| `NO_PROGRESS` | 连续 3+ 步执行了完全相同的动作 | 检查 UI 交互逻辑是否正确 |
| `TARGET_NOT_FOUND` | 回归模式下找不到预期 UI 元素 | UI 可能有较大变化，调用 invalidate_recording 重新探索 |
| `UNSAFE` | 动作被安全防护拦截 | 检查操作是否触及黑名单路径或凭据 |
| `USER` | 手动停止 | — |

### 6.3 失败场景示例

**断言失败（文件未生成）：**

```json
{
  "result": {
    "status": "FAIL",
    "termination_reason": "ASSERTION_FAILED"
  },
  "failure_reason": "断言 file_exists 失败：路径 C:\\TestSandbox\\out.txt 不存在",
  "bug_hints": [
    {
      "hypothesis": "保存路径不存在或快捷键 Ctrl+S 未生效",
      "confidence": 0.80
    }
  ],
  "assertions": [
    {
      "type": "file_exists",
      "params": {"path": "C:\\TestSandbox\\out.txt"},
      "passed": false,
      "message": "文件不存在"
    }
  ]
}
```

AI Agent 读到后，结合 `bug_hints` 和末尾步骤截图，发现保存对话框未弹出，定位到代码里 `Ctrl+S` 快捷键发送目标窗口错误，修复后重测。

---

## 7. HTTP API 接口

适合自定义 Agent 或 CI 流水线集成。需先安装 `http` 可选依赖：`pip install -e ".[http]"`。

启动服务：

```powershell
python -m autovisiontest serve --port 8080 --config config/model.yaml
```

### 7.1 接口列表

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/v1/sessions` | 创建并启动测试会话 |
| `GET` | `/v1/sessions/{id}/status` | 查询会话状态 |
| `GET` | `/v1/sessions/{id}/report` | 获取测试报告 |
| `POST` | `/v1/sessions/{id}/stop` | 停止会话 |
| `GET` | `/v1/recordings` | 列出回归用例 |
| `DELETE` | `/v1/recordings/{fingerprint}` | 删除回归用例 |

### 7.2 使用示例

```bash
# 启动测试
curl -X POST http://localhost:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "打开记事本，输入 hello world，保存",
    "app_path": "C:\\Windows\\System32\\notepad.exe"
  }'

# 返回：{"session_id": "sess_a1b2c3d4"}

# 轮询状态
curl http://localhost:8080/v1/sessions/sess_a1b2c3d4/status

# 获取报告
curl http://localhost:8080/v1/sessions/sess_a1b2c3d4/report > report.json
```

### 7.3 CI/CD 集成示例

```python
import time
import requests

BASE = "http://localhost:8080"

def run_test(goal: str, app_path: str) -> dict:
    # 启动测试
    resp = requests.post(f"{BASE}/v1/sessions", json={
        "goal": goal,
        "app_path": app_path,
    })
    session_id = resp.json()["session_id"]

    # 轮询直到完成
    while True:
        status = requests.get(f"{BASE}/v1/sessions/{session_id}/status").json()
        if status["status"] in ("COMPLETED", "FAILED", "STOPPED"):
            break
        time.sleep(5)

    # 获取报告
    report = requests.get(f"{BASE}/v1/sessions/{session_id}/report").json()
    return report


if __name__ == "__main__":
    report = run_test(
        goal="验证记事本文件保存功能",
        app_path=r"C:\Windows\System32\notepad.exe",
    )
    if report["result"]["status"] == "PASS":
        print("✓ 测试通过")
    else:
        print(f"✗ 测试失败: {report['failure_reason']}")
        for hint in report.get("bug_hints", []):
            print(f"  假设（置信度 {hint['confidence']:.0%}）：{hint['hypothesis']}")
        exit(1)
```

---

## 8. CLI 接口

适合本地快速验证和调试。

```powershell
# 验证当前配置（检查模型端点、数据目录等）
python -m autovisiontest validate

# 基本用法：探索性测试
python -m autovisiontest run \
    --goal "打开记事本，输入 hello world，保存到 C:\TestSandbox\out.txt" \
    --app "C:\Windows\System32\notepad.exe"

# 从已固化的用例文件运行（回归模式）
python -m autovisiontest run --case data/recordings/abc123.json

# Attach 模式（不自动启动应用，对已打开的应用做测试）
python -m autovisiontest run \
    --goal "在当前打开的记事本中输入 hello" \
    --no-launch

# 指定配置文件
python -m autovisiontest run \
    --goal "..." \
    --app "..." \
    --config config/model.yaml

# 查询会话状态
python -m autovisiontest status sess_a1b2c3d4

# 获取完整测试报告（JSON 格式输出到 stdout）
python -m autovisiontest report sess_a1b2c3d4

# 列出所有已固化的回归用例
python -m autovisiontest list-recordings

# 查看帮助
python -m autovisiontest --help
python -m autovisiontest run --help
```

**全局选项：**

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--config PATH` | `./config/model.yaml` | 配置文件路径 |
| `--log-level` | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |

---

## 9. 配置参考

### 9.1 `config/model.yaml` 完整选项

```yaml
agent:
  backend: "uitars_local"           # 见后端说明
  model: "ui-tars-1.5-7b"          # vLLM --served-model-name
  endpoint: "http://localhost:8000/v1"
  max_tokens: 512
  temperature: 0.0                   # 保持 0.0 确保确定性
  language: "Chinese"               # 模型 Thought 输出语言
  history_images: 3                 # 传给模型的历史截图数量
  timeout_s: 60.0                   # 单次推理超时

runtime:
  max_steps: 50                     # 单次会话最大操作步数
  max_session_duration_s: 600       # 单次会话最大时长（秒）
  step_wait_ms: 500                 # 每步操作后等待时间
  data_dir: "./data"                # 数据目录（报告、录制、截图）
```

### 9.2 后端选项

| backend 值 | 后端实现 | 说明 |
|------------|---------|------|
| `uitars_local` | `UITarsBackend` | UI-TARS-1.5-7B，通过本地 vLLM 提供；图像预缩放到 1344×1344 token 空间；输出绝对像素坐标 |
| `maiui_local` | `MAIUIBackend` | MAI-UI（Qwen3-VL based），通过本地 vLLM 提供；使用 [0,1000] 归一化坐标；PNG 自动压缩为 JPEG 降低带宽 |
| `openai` | `OpenAIChatBackend` | GPT-4o / GPT-4o-mini；自动重试（3 次，指数退避）；需安装 `cloud` 依赖 |
| `claude` | `ClaudeChatBackend` | Claude API；需安装 `cloud` 依赖及配置 `ANTHROPIC_API_KEY` |
| `vllm_chat` | `VLLMChatBackend` | 通用 OpenAI 兼容 vLLM 接入，适合自托管其他模型 |

**MAI-UI 配置示例：**

```yaml
agent:
  backend: "maiui_local"
  model: "mai-ui"
  endpoint: "http://localhost:8001/v1"
  max_tokens: 512
  temperature: 0.0
  language: "Chinese"
  history_images: 3
  timeout_s: 60.0
```

**云端 Claude 配置示例：**

```yaml
agent:
  backend: "claude"
  model: "claude-sonnet-4-6"
  endpoint: ""           # 使用官方 API，留空
  max_tokens: 1024
  temperature: 0.0
  language: "Chinese"
  history_images: 2
  timeout_s: 30.0
```

### 9.3 环境变量覆盖

无需修改配置文件，直接通过环境变量覆盖：

| 环境变量 | 对应配置项 | 示例 |
|---------|-----------|------|
| `AUTOVT_CONFIG` | 配置文件路径 | `AUTOVT_CONFIG=config/prod.yaml` |
| `AUTOVT_DATA_DIR` | `runtime.data_dir` | `AUTOVT_DATA_DIR=D:\TestData` |
| `AUTOVT_AGENT_ENDPOINT` | `agent.endpoint` | `AUTOVT_AGENT_ENDPOINT=http://10.11.0.85:28801/v1` |

### 9.4 硬件与模型选择

| GPU | 推荐模型 | 后端 | 预估单步延迟 |
|-----|---------|------|-------------|
| RTX 3080Ti 12GB | UI-TARS-1.5-7B AWQ | `uitars_local` | 3-4 秒 |
| RTX 3090 24GB | UI-TARS-1.5-7B FP16 | `uitars_local` | 2-3 秒 |
| RTX 5090 32GB | UI-TARS-1.5-7B FP16 | `uitars_local` | 1-2 秒 |
| RTX 3090/5090 | MAI-UI | `maiui_local` | 2-3 秒 |
| 无 GPU | GPT-4o / Claude | `openai` / `claude` | 5-10 秒（网络依赖）|

---

## 10. 目录结构

```
AutoAgent/
├── config/
│   └── model.yaml                  # 模型与运行时配置
├── data/                           # 运行时数据（gitignore）
│   ├── sessions/                   # 会话元数据 + 测试证据（每会话一目录）
│   │   └── <session_id>/
│   │       ├── report.json         # 完整测试报告
│   │       └── step_*.png          # 每步截图（before/after）
│   └── recordings/                 # 固化的回归用例
│       └── <fingerprint>.json
├── docs/
│   ├── product_document.md         # 产品设计文档
│   └── uitars_wsl2_deploy.md       # WSL2 部署手册
├── examples/
│   └── cases/
│       └── calculator_5x7.py       # 示例测试用例（Python 格式）
└── src/autovisiontest/
    ├── backends/                   # 模型推理后端（UITars / MAIUI / Claude / OpenAI / vLLM）
    ├── cases/                      # 测试用例定义、加载、存储、固化
    ├── config/                     # 配置 schema 与加载器
    ├── control/                    # 桌面控制（鼠标、键盘、截图、进程、窗口）
    ├── engine/                     # 执行引擎（主循环、模型适配、终止逻辑、断言）
    ├── interfaces/
    │   ├── mcp_server.py           # MCP Server（Cursor/Claude Code 接入点）
    │   ├── http_server.py          # REST API Server（FastAPI）
    │   └── cli_commands.py         # CLI 命令实现
    ├── perception/                 # 视觉感知（OCR、变化检测、错误弹窗识别）
    ├── prompts/                    # Prompt 模板
    ├── report/                     # 报告生成（schema、builder、证据写入）
    ├── safety/                     # 安全防护（黑名单、VLM 二次确认）
    ├── scheduler/                  # 会话生命周期管理
    ├── cli.py                      # CLI 入口（Click）
    └── exceptions.py               # 错误层次结构
```

---

## 11. FAQ

**Q: 首次测试很慢（超过 5 分钟），正常吗？**

首次是探索模式，VLM 需要逐步探索 UI，通常 50 步以内完成（约 2-4 分钟，取决于目标复杂度）。探索成功后自动固化，之后回归模式只需 30-60 秒。

**Q: 测试失败后，AI Agent 需要做什么？**

1. 调用 `get_session_report` 获取报告
2. 查看 `result.failure_reason` 了解失败原因
3. 查看 `bug_hints` 数组中 AI 自动生成的根因假设
4. 查看 `steps` 数组末尾的 `screenshot_after`（base64 截图）直接看到失败时的屏幕状态
5. 查看 `assertions` 数组了解哪个断言失败
6. 根据以上信息定位代码问题，修复后重新触发测试

**Q: 如何让 AI Agent 自动触发测试？**

在 Cursor 的 Agent 规则（`.cursor/rules/`）或对话系统提示中加入约定：每次代码变更后调用 `start_test_session`，完成后读报告。具体见 [第 5.3 节](#53-ai-agent-prompt-模板)。

**Q: 回归用例什么时候会失效？**

当被测应用 UI 发生较大变化（连续多步 VLM 找不到预期元素，termination_reason 为 `TARGET_NOT_FOUND`）时，AutoVisionTest 会自动标记回归用例失效，并退回探索模式重新录制。也可手动调用 `invalidate_recording` 强制失效。

**Q: 支持哪些断言类型？**

| 断言类型 | 说明 |
|---------|------|
| `no_error_dialog` | 没有错误弹窗（默认隐式加入） |
| `ocr_contains` | 屏幕文字包含指定内容（PaddleOCR） |
| `file_exists` | 指定文件存在 |
| `process_running` | 指定进程仍在运行 |
| `screenshot_similar` | 屏幕与模板截图相似（SSIM） |

**Q: 如何在 CI/CD 中集成？**

启动 HTTP API 服务后，用 Python/Shell 脚本调用 REST API 即可。参考 [第 7.3 节](#73-cicd-集成示例) 的 Python 示例。构建失败（exit code 1）时 CI 自动报错，报告存储在 `data/sessions/` 供事后分析。

**Q: vLLM 服务在 WSL2 里，Windows 主进程能访问吗？**

可以。WSL2 与 Windows 共享 `localhost`，Windows 进程可以直接访问 `http://localhost:8000`。`config/model.yaml` 中 `endpoint: "http://localhost:8000/v1"` 即使用此路径。

**Q: 不想用本地 GPU，能用云端 API 吗？**

可以。安装 `cloud` 可选依赖（`pip install -e ".[cloud]"`），在配置文件中将 `backend` 设为 `openai` 或 `claude`，填写对应 API Key 的环境变量，即可使用 GPT-4o 或 Claude 作为推理后端，无需本地 GPU。

**Q: 安全防护如何工作？**

每次动作执行前，`SafetyGuard` 会先做黑名单关键词匹配（系统文件路径、凭据模式等），命中后调用 VLM 二次确认（结合 OCR 上下文判断是否真正危险）。若确认危险，动作被拦截，会话以 `UNSAFE` 终止。
