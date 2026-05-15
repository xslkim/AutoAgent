# protocol/ — Wire Protocol JSON Schema

机器可校验版本的 [docs/01-protocol-spec.md](../docs/01-protocol-spec.md)。Phase 0 后期所有 adapter 实现 / MCP server / e2e 测试都拿这里的 schema 做静态校验。

## 文件结构

| 文件 | $id | 内容 |
|---|---|---|
| `schema/node.json` | `https://autoagent.dev/schema/v0.1/node.json` | 单个 UI 节点（visual/behavior/meta/engine_extras 分组） |
| `schema/methods.json` | `https://autoagent.dev/schema/v0.1/methods.json` | 18 个 wire method 的 JSON-RPC request 包络 + 每方法 params/result（在 `$defs.methods` 下） |
| `schema/events.json` | `https://autoagent.dev/schema/v0.1/events.json` | 6 种事件 notification |
| `schema/errors.json` | `https://autoagent.dev/schema/v0.1/errors.json` | 错误码 + 名称 enum |

全部用 JSON Schema **Draft 2020-12**。

## 跨文件 $ref

`methods.json` 多处 `$ref` 到 `node.json`（如 `dump_tree.result.nodes[]`）。校验时需要把两个 schema 一起喂给 `referencing` registry：

```python
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).parent / "schema"

def load(name):
    return json.loads((SCHEMA_DIR / name).read_text())

node_schema = load("node.json")
methods_schema = load("methods.json")

registry = Registry().with_resources([
    (node_schema["$id"], Resource(contents=node_schema, specification=DRAFT202012)),
    (methods_schema["$id"], Resource(contents=methods_schema, specification=DRAFT202012)),
])

validator = Draft202012Validator(methods_schema, registry=registry)
validator.validate({
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "dump_tree",
    "params": {"root_id": None}
})
```

## 测试

```bash
pytest protocol/tests/ -v
```

测试覆盖：

1. 4 个 schema 文件本身是合法 Draft 2020-12（meta-schema 校验）
2. 一个 sample Node 通过 `node.json`
3. 一个 sample `dump_tree` request 通过 `methods.json`
4. 一个 sample `event.scene_changed` notification 通过 `events.json`
5. 一个 sample error 通过 `errors.json`

## 依赖

- `jsonschema >= 4.18`（自带 `referencing` 支持，Draft 2020-12 必需）
- `pytest`

## 版本

- **v0.1**：当前。Phase 0 PoC 完成后会出 v0.2，schema 锁定（详见 [docs/01-protocol-spec.md](../docs/01-protocol-spec.md) §一）。
- v0.1 → v0.2 升级时，`$id` 里的 `v0.1` 替换为 `v0.2`，旧 schema 文件保留以支持版本协商。

## 与 docs/01 的关系

`docs/01-protocol-spec.md` 是**唯一权威源**——人读的规范、约定、跨引擎差异说明都在那里。本目录是该规范的**机器可校验形式**，覆盖不到的高层不变量（如"任务 DSL 引用的节点必须 `stable_id_source ∈ {pinned, auto}`"）由应用层强制。
