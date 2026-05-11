# 02 - MCP Server

> 暴露给 AI Agent（Claude Code）的 Model Context Protocol 服务器。Python 实现，stdio transport。

## 一、技术栈

- **语言**：Python 3.11+
- **MCP SDK**：`mcp` (Anthropic 官方 Python SDK)
- **WebSocket 客户端**：`websockets` (asyncio-based)
- **运行模型**：单进程 + asyncio 事件循环
- **Transport**：stdio（默认，给 Claude Code 用）；HTTP/SSE（Phase 4 可选）
- **包管理**：`uv`（推荐）或 `pip`
- **配置**：`pyproject.toml` + 环境变量

## 二、架构

```
┌──────────────────────────────────────────┐
│  Claude Code (MCP Client)                │
└──────────────────────────────────────────┘
            ↓ stdio (JSON-RPC)
┌──────────────────────────────────────────┐
│  MCP Server (autoagent_mcp)              │
│  ┌────────────────────────────────────┐  │
│  │  Tool Layer (12 core + 5 aux       │  │
│  │              + 3 phase4 = 20)      │  │
│  │  dump_ui_tree / click_by_id / ...  │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Engine Connector                  │  │
│  │  WebSocket client, retry, session  │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │  Vision Module                     │  │
│  │  SSIM / LPIPS / Claude Vision      │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
            ↓ WebSocket
┌──────────────────────────────────────────┐
│  Engine Adapter (Unity / UE / Godot)     │
└──────────────────────────────────────────┘
```

## 三、MCP Tools 列表

### MCP Tool ↔ Wire Protocol Method 映射

> AI 调用的 tool 名（左列）和 Wire Protocol method（右列）是两套命名。MCP tool 名是 AI 友好（动词+对象），wire method 名是简洁（动词）。下表是唯一权威映射，避免实现 / prompt drift。
>
> **分组（口径统一）**：
> - **核心 MVP tools（12 个）** — MVP 验收必须实现，Phase 1 完成
> - **辅助 tools（5 个）** — Phase 1 完成（session 管理 + audit）
> - **Phase 4 tools（3 个）** — 反射调用类，Phase 4 末暴露
>
> Phase 1 出口标准 = 17 个 tools 全实现。99-tasks.md / 测试 verification 引用时按本分组名指代，**不再写 "all 12 tools" / "12 tools" 这种含糊措辞**。

#### 核心 MVP tools（12 个）

| MCP Tool（AI 调用） | Wire Protocol Method（Adapter 实现） | 备注 |
|---|---|---|
| `dump_ui_tree` | `dump_tree` | |
| `find_widget` | `find_widget` | |
| `get_widget` | `get_widget` | |
| `click_by_id` | `click` | |
| `send_text` | `send_text` | |
| `drag` | `drag` | |
| `scroll` | `scroll` | |
| `key_press` | `key_press` | |
| `take_screenshot` | `take_screenshot` | |
| `compare_to_baseline` | (本地) | server 端用 scikit-image 计算，不发 wire |
| `wait_for` | `wait_for` | |
| `pin_id` | `pin_id` | |

#### 辅助 tools（5 个，Phase 1 完成）

| MCP Tool | Wire Protocol Method | 备注 |
|---|---|---|
| `list_orphan_ids` | `list_orphan_ids` | |
| `audit_visual_changes` | (本地) | server 缓存 dump，diff 计算 |
| `connect_engine` | (本地) | session 管理，不发 wire 消息 |
| `disconnect` | (本地) | |
| `get_engine_info` | `get_engine_info` | |

#### Phase 4 tools（3 个）

| MCP Tool | Wire Protocol Method | 备注 |
|---|---|---|
| `invoke_method` | `invoke_method` | Phase 4 暴露 |
| `get_property` | `get_property` | Phase 4 暴露 |
| `set_property` | `set_property` | Phase 4 暴露 |

### 树查询类

#### `dump_ui_tree`
**描述**：拉取当前 UI 树。AI 通常先调用这个了解界面结构。

**Input**:
```json
{
  "include_invisible": false,
  "max_depth": -1,
  "fields": ["visual", "behavior", "meta"]
}
```

**Output**: 节点树 JSON（schema 见 01-protocol-spec.md）。

**Token 预算**：典型 50 节点 UI ~5KB / ~1500 token。超过 100 节点自动剪枝（visible only + 关键字段）。

---

#### `find_widget`
按 id / role / type / text 查找。返回匹配节点列表。

#### `get_widget`
按 ID 拿单个节点最新状态。

### 输入操作类

#### `click_by_id`
```json
{ "id": "login_button", "button": "left", "input_layer": "engine" }
```

#### `send_text`
```json
{ "id": "account_input", "text": "...", "clear_first": true }
```

#### `drag`
```json
{ "from_id": "item_001", "to_id": "slot_005" }
```

#### `scroll`
#### `key_press`

### 验证类

#### `take_screenshot`
```json
{ "scope": "fullscreen", "save_path": "..." }
```
返回路径或 base64。

#### `compare_to_baseline`
```json
{
  "current_path": "screenshots/current.png",
  "baseline_path": "baselines/login.png",
  "method": "ssim" | "lpips" | "both",
  "threshold": { "ssim": 0.95, "lpips": 0.10 }
}
```
返回：`{ "pass": true, "ssim": 0.97, "lpips": 0.05, "diff_path": "..." }`

#### `wait_for`
等待 widget 出现 / 消失 / 文本变化。

### Meta 管理类

#### `pin_id`
钉一个 stable ID 到节点。

#### `list_orphan_ids`
找出失踪的 ID（上轮见过、本轮找不到）。

#### `audit_visual_changes`
对比上次 dump 和这次 dump，列出 visual 字段的变化（用于 AI 自检：我有没有不小心碰了视觉）。

### Session 类

#### `connect_engine`
```json
{ "engine": "unity" | "unreal" | "godot", "host": "127.0.0.1", "port": 27842 }
```
建立 WebSocket 连接。

#### `disconnect`
#### `get_engine_info`

## 四、Session 与连接管理

### 单连接模型（Phase 1-3）

- MCP Server 同时只连一个引擎实例
- `connect_engine` 替换当前连接
- 自动重连：连接断开 → 1s/2s/4s 退避 → 最多 5 次

### 多连接模型（Phase 4 引入）

- 同时连多个引擎实例（用于跨引擎对比测试）
- 每个 tool 加可选 `engine_session` 参数

## 五、错误处理

| 场景 | 行为 |
|---|---|
| Adapter 返回 error | 直接透传给 AI（保留 error code + message） |
| WebSocket 连接失败 | 自动重试，超过 5 次返回 ConnectionError |
| Tool 参数 schema 错误 | MCP SDK 自动校验，返回结构化错误 |
| Adapter 超时（默认 5s） | 返回 TimeoutError，附最近一次成功响应时间 |
| Adapter 进程崩溃 | 返回 EngineDisconnected，提示 AI 重启引擎 |

## 六、日志规范

### 日志级别
- `DEBUG`：每个 tool 调用的入参 / 出参
- `INFO`：连接建立 / 断开 / 主要操作
- `WARN`：重试 / 降级
- `ERROR`：失败

### 日志输出
- stderr（stdio transport，stdout 给 MCP 用）
- 同时写文件 `~/.autoagent/mcp-server.log`，rotate 50MB × 5

### 结构化日志
```json
{
  "ts": "2026-05-09T10:23:45Z",
  "level": "INFO",
  "event": "tool.invoked",
  "tool": "click_by_id",
  "params": {"id": "login_button"},
  "result": {"success": true},
  "duration_ms": 23
}
```

AI Agent 可以通过 `read_log` tool 主动读日志（Phase 4 加）。

## 七、配置文件

`~/.autoagent/config.toml`：

```toml
[mcp_server]
log_level = "INFO"
log_file = "~/.autoagent/mcp-server.log"

[engine]
default_host = "127.0.0.1"
default_port = 27842
connect_timeout_ms = 5000
operation_timeout_ms = 5000
heartbeat_interval_ms = 30000

[vision]
ssim_threshold = 0.95
ssim_warn_threshold = 0.92        # 触发 LLM 二次裁决
lpips_enabled = false              # MVP 仅 SSIM；Phase 4 启用 LPIPS（依赖 PyTorch ~500MB）
lpips_threshold = 0.10             # 仅 lpips_enabled=true 时生效
lpips_subprocess = true            # 子进程化以隔离 PyTorch 内存
baseline_dir = "./baselines"
diff_dir = "./diffs"

[claude_vision]
enabled = false
api_key_env = "ANTHROPIC_API_KEY"
model = "claude-opus-4-7"
max_diff_per_session = 20          # 防 token 爆炸
```

## 八、入口与启动

### Claude Code 配置
`.mcp.json`（项目根 or 全局）：

```json
{
  "mcpServers": {
    "autoagent": {
      "command": "uv",
      "args": ["run", "autoagent-mcp"],
      "cwd": "D:/AutoAgent/mcp-server"
    }
  }
}
```

### CLI 命令

```bash
# 启动服务（stdio mode，由 Claude Code 调用）
autoagent-mcp

# 调试模式（HTTP transport for testing）
autoagent-mcp --transport http --port 8765

# 健康检查
autoagent-mcp ping --host 127.0.0.1 --port 27842
```

## 九、测试策略

- **单元测试**：每个 tool 用 mock WebSocket server 测（pytest）
- **集成测试**：起一个 fake adapter（Python WebSocket server，mock 协议），跑全套 MCP tools
- **e2e 测试**：起真实 Unity adapter，跑 login MVP

CI：每 PR 跑 unit + integration；e2e 在 Unity / Godot CI 里跑。

## 十、性能 & 资源

- 启动时间 < 2s（不含 vision 模块加载）
- 单 tool 调用 overhead < 10ms（本地 WebSocket）
- 内存常驻 < 100MB
- vision 模块按需加载，**MVP 仅 SSIM**（pure NumPy / scikit-image，~5MB 内存）
- LPIPS（PyTorch ~500MB）作为可选 extras（`pip install autoagent-mcp[lpips]`），**Phase 4 才引入**；启用时强制子进程化（`lpips_subprocess = true`）避免污染主 server 内存
