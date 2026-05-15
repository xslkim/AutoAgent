# mcp-server/ — AutoAgent MCP Server (Phase 0 stub)

把 docs/01-protocol-spec.md 的 17 个 wire methods 暴露为 MCP tools，给 Claude Code 调。Phase 0 stub 阶段直接返回 mock 数据；Phase 1 接 WebSocket 真实进 engine adapter。

## Install (uv)

```bash
cd mcp-server
uv sync
```

无 uv 时可用 pip：

```bash
cd mcp-server
pip install -e .[dev]
```

## 启动 / 测试

```bash
autoagent-mcp --help          # 帮助
autoagent-mcp --list-tools    # 列出 17 个 tool 名（不启动 server）
autoagent-mcp                 # 启动 stdio MCP server（被 Claude Code spawn 时用）

pytest tests/ -v              # 测试
```

## Claude Code 集成

repo 根 `.mcp.json`：

```json
{
  "mcpServers": {
    "autoagent": {
      "command": "autoagent-mcp",
      "args": []
    }
  }
}
```

启动 Claude Code 后 `/mcp` 应看到 17 个 tool 注册成功。

## 17 个 Tool

按 [docs/01-protocol-spec.md](../docs/01-protocol-spec.md) §四 章节分组：

| 章节 | Tools |
|---|---|
| 4.1 树查询 | `dump_tree`, `find_widget`, `get_widget` |
| 4.2 输入操作 | `click`, `send_text`, `drag`, `scroll`, `key_press` |
| 4.3 截图与等待 | `take_screenshot`, `wait_for` |
| 4.4 反射调用 | `invoke_method`, `get_property`, `set_property` |
| 4.5 ID 管理 | `pin_id`, `list_orphan_ids` |
| 4.6 Session | `ping`, `get_engine_info` |

`negotiate_version` 是 wire-internal 握手（[docs/01 §七](../docs/01-protocol-spec.md)），**不暴露**给 AI——AI 看不到也不应该调用。

## 目录结构

```
mcp-server/
├── pyproject.toml
├── README.md
├── src/
│   └── autoagent_mcp/
│       ├── __init__.py          # 包标记 + __version__
│       ├── server.py            # FastMCP 实例构造 + stdio 启动
│       ├── cli.py               # argparse CLI 入口（--help / --list-tools）
│       └── tools/
│           └── __init__.py      # 17 个 tool stub + register_all()
└── tests/
    └── test_server_starts.py
```

## Phase 0 → Phase 1 演进

当前 stub：tool 接收正确 params 形状，返回 mock 数据。

Phase 1 时 stub 替换为：

1. 连接到 engine adapter 的 WebSocket（`ws://127.0.0.1:27842`，subprotocol `autoagent.v1`）
2. 走 `negotiate_version` 握手
3. 把 tool 调用转成 JSON-RPC `Request`，发到 adapter
4. 等 `Response`，把 `result` 直接返回；error 转 `McpError`
5. 参数和返回值都过 `protocol/schema/*.json` 校验

## 版本

`autoagent-mcp 0.1.0`（与 wire protocol v0.1 对齐）。
