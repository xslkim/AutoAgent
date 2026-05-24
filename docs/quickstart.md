# AutoAgent Quickstart

5 分钟上手，将 AI 驱动的 UI 自动化添加到你的 Unity / Unreal / Godot 项目。

## 前提条件

- **Unity** 2021.3+ / **Unreal** 5.x / **Godot** 4.x
- **Python** 3.12+
- **Claude Code** 或兼容 MCP 的 AI agent
- (可选) Windows/macOS/Linux OS 级输入需要对应平台

## 1. 安装 Adapter

### Unity

以本地 UPM 包方式添加：

```json
// Packages/manifest.json
{
  "dependencies": {
    "com.autoagent.runtime": "file:../../adapters/unity"
  }
}
```

打开 Unity，等待包解析完成。`Assets/AutoAgent/` 目录下的 Runtime 代码会自动编译。

### 安装 MCP Server

```bash
cd mcp-server
pip install -e ".[dev]"
```

## 2. 配置

```bash
# 创建配置文件
mkdir -p ~/.autoagent

cat > ~/.autoagent/config.toml << 'EOF'
[server]
host = "127.0.0.1"
port = 27842

[logging]
file = "~/.autoagent/logs/mcp-server.log"
level = "INFO"
EOF
```

## 3. 启动

### 启动 Engine

```bash
# Unity: 打开 fixtures/unity-test-project 并进入 Play Mode
# 或使用命令行:
unity -projectPath fixtures/unity-test-project -executeMethod AutoAgent.CIBuild.EnterPlayMode
```

### 启动 MCP Server

```bash
cd mcp-server
python -m autoagent_mcp.server
```

## 4. 第一个任务：点击按钮

```
1. Agent 调用 dump_tree → 获取 UI 树和节点 ID
2. Agent 找到目标节点的 id (如 "btn_login")
3. Agent 调用 click(id="btn_login") → 触发点击
```

### MCP 工具速查

| 工具 | 说明 |
|---|---|
| `dump_tree` | 导出 UI 节点树 |
| `dump_tree_delta` | 增量查询（只返回变化的节点） |
| `click(id, button, input_layer)` | 点击节点 |
| `drag(from_id, to_id, duration_ms)` | 拖拽 |
| `scroll(id, direction, amount)` | 滚动 |
| `key_press(id, key, input_layer)` | 按键 |
| `send_text(id, text)` | 输入文本 |
| `take_screenshot` | 截图 |
| `compare_to_baseline(id)` | SSIM 视觉对比 |
| `compare_lpips_to_baseline(id)` | LPIPS 感知对比 |
| `claude_judge_screenshot(id, question)` | Claude Vision 裁决 |
| `invoke_method(id, method, args)` | 调用组件方法 |
| `get_property(id, property)` | 读取属性 |
| `set_property(id, property, value)` | 写入属性 |

## 5. OS 级输入

默认使用引擎事件层 (`input_layer="engine"`)。切换到 OS 级输入可直接操控系统光标：

```python
# Windows: Win32 SendInput
await click(id="btn", input_layer="os")

# macOS: CGEventPost (需要辅助功能权限)
await click(id="btn", input_layer="os")

# Linux: X11 XTest
await click(id="btn", input_layer="os")
```

## 6. AI Agent 自治循环

```bash
# 配置 AI agent 环境
cp .env.agent.example .env.agent
# 编辑 .env.agent: 填入 API key 和 MCP server 地址

# 启动自治 agent
python scripts/agent/run_task.py --task docs/canonical-tasks/login.yaml
```

Agent 会自动：
1. 读取任务 DSL
2. 调用 dump_tree 获取 UI 结构
3. 编写引擎代码
4. 运行测试
5. 截图对比
6. 判断完成或继续迭代

## 7. CI 集成

```yaml
# .github/workflows/unity-pr.yml 示例
- name: Run Unity tests
  run: |
    unity -runTests -batchmode -projectPath fixtures/unity-test-project \
      -testPlatform PlayMode -testResults results.xml
```

## 8. 视觉回归

```bash
# 建立 baseline
python scripts/e2e/capture_baseline.py --engine unity --scene poc_playground

# 对比当前截图与 baseline（CI 脚本）
python scripts/ci/check_visual_baseline.py --baseline baselines/unity/windows/poc_playground.png
```

## 下一步

- 完整协议规范: [docs/01-protocol-spec.md](01-protocol-spec.md)
- 各引擎 adapter 设计: [docs/03-adapter-unity.md](03-adapter-unity.md) / [04](04-adapter-unreal.md) / [05](05-adapter-godot.md)
- 美术保真防护: [docs/06-visual-regression.md](06-visual-regression.md)
- 升级指南: [docs/migration/v0.x-to-v1.0.md](migration/v0.x-to-v1.0.md)
