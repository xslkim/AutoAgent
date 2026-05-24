# AutoAgent v1.0 — 项目状态与使用说明

> 最后更新: 2026-05-24 | 296 commits | 93/93 任务完成

## 项目概述

多引擎（Unity / Unreal / Godot）AI Agent 驱动的 UI 开发框架。AI 通过 MCP 协议操控游戏引擎，实现 UI 开发的完整闭环：接任务 → 写代码 → 自动运行 → 视觉对比 → 迭代。

## 当前版本: v1.0

### 三引擎 Adapter

| 引擎 | 语言 | OS 输入 | 主要文件 |
|------|------|---------|---------|
| **Unity** | C# | Win32 SendInput / macOS CGEventPost / Linux XTest | `adapters/unity/Assets/AutoAgent/Runtime/` |
| **Unreal** | C++ | Win32 SendInput / macOS CGEventPost / Linux XTest | `adapters/unreal/Source/AutoAgent/` |
| **Godot** | GDScript | DisplayServer 光标位移 + InputEvent 注入 | `adapters/godot/addons/autoagent/` |

### MCP Server (Python)

WebSocket JSON-RPC 协议，工具列表：

| 类别 | 工具 |
|------|------|
| 节点查询 | `dump_tree`, `dump_tree_delta`, `find_widget`, `get_widget` |
| 输入 | `click`, `drag`, `scroll`, `key_press`, `send_text` |
| 视觉 | `take_screenshot`, `compare_to_baseline`, `compare_lpips_to_baseline`, `claude_judge_screenshot` |
| 反射 | `invoke_method`, `get_property`, `set_property` |

### 五道美术保真防护

0. 源码层审计（路径白名单 + visual-write 扫描）
1. 协议层 Schema 权限分离
2. ID 稳定性（pinned / auto）
3. 视觉回归（SSIM + Claude Vision + LPIPS）
4. 资源 GUID 追踪

### CI / 自动化

| Workflow | 触发 | Runner |
|----------|------|--------|
| Source audit | PR + push main | GitHub Ubuntu |
| Unity PR | PR | Self-hosted Windows (F5090) |
| UE PR lint | PR | GitHub Ubuntu |
| Godot PR | PR | GitHub Ubuntu |
| UE nightly | Schedule | Self-hosted Windows |

---

## 快速开始

### 1. 安装 MCP Server

```bash
cd mcp-server
pip install -e ".[dev]"
```

### 2. 配置

```bash
mkdir -p ~/.autoagent
cat > ~/.autoagent/config.toml << 'EOF'
[engine]
host = "localhost"
port = 27842

[vision]
ssim_threshold = 0.95
lpips_threshold = 0.1
EOF
```

### 3. 启动引擎 + Server

```bash
# Unity: 打开 fixtures/unity-test-project 并进入 Play Mode
# 或UE: 打开 fixtures/unreal-test-project 并 PIE
# 或Godot: 打开 fixtures/godot-test-project 并运行

# MCP Server
cd mcp-server
python -m autoagent_mcp.server
```

### 4. AI Agent 自治循环

```bash
cp .env.agent.example .env.agent
# 编辑 .env.agent 填入 API key

python scripts/agent/runner.py --task docs/canonical-tasks/login_mvp.yaml
```

### 5. OS 级输入

```python
# 绕过引擎事件系统，直接操控系统光标
await click(id="btn", input_layer="os")       # 三平台支持
await key_press(id="field", key="Enter", input_layer="os")
```

### 6. 运行测试

```bash
# Python 测试
pytest scripts/ci/tests/ mcp-server/tests/

# Unity (需要本地 Unity Editor)
# Test Runner → PlayMode → Run All

# Godot (headless)
godot --headless --path fixtures/godot-test-project \
  res://addons/autoagent/tests/headless_input_test.tscn
```

### 7. 发布

```bash
bash scripts/release.sh patch   # v1.0.0 → v1.0.1
bash scripts/release.sh minor   # v1.0.0 → v1.1.0
```

---

## 项目结构

```
AutoAgent/
  ARCHITECTURE.md           # 架构决策摘要
  CHANGELOG.md              # v1.0.0 完整 changelog
  STATUS.md                 # 本文件
  docs/                     # 详细设计文档 (00-10 系列)
    tasks.md                # 任务清单索引
    tasks-phase{0-4}.md     # 分 Phase 任务明细
    quickstart.md           # 5 分钟上手指南
    migration/              # 升级指南
  adapters/                 # 三引擎适配器
    unity/                  #  Unity C# adapter
    unreal/                 #  UE C++ adapter
    godot/                  #  Godot GDScript adapter
  mcp-server/               #  MCP Server (Python)
  protocol/                 #  协议 schema
  scripts/                  #  CI / e2e / agent / release
  tests/                    #  集成 / stress tests
  fixtures/                 #  三引擎静态测试项目
  baselines/                #  视觉回归基线截图
  state/                    #  任务状态跟踪 + cost tracking
  .github/workflows/        #  CI workflows
```

## Phase 4 任务总览

| Task | 内容 | PR |
|------|------|----|
| 0115 | invoke/get/set_property | #121 |
| 0400 | Win32 SendInput | #125 |
| 0401 | macOS CGEventPost | #126 |
| 0402 | Linux XTest | #126 |
| 0403 | LPIPS subprocess | #122 |
| 0404 | Claude Vision 裁决 | #123 |
| 0405C | MCP delta cache | #124 |
| 0405 | Adapter TreeCache + wire delta | #130 |
| 0406 | Fast hash + 预分配 + stress test | #131 |
| 0407 | Stress test 13 cases | #131 |
| 0408 | CHANGELOG + migration + quickstart | #127 |
| 0409 | 文档 review | #128 |
| UE+Godot OS | UE C++ OS 三平台 + Godot GDScript OS 层 | #132 |
