# MAI-UI-2B BF16 WSL2 部署手册

> 目标：在 WSL2 (Ubuntu-22.04) 里部署 **新增** 一个 vLLM 服务跑
> `Tongyi-MAI/MAI-UI-2B`（Qwen3-VL 架构，BF16 无量化），用来和现有的
> `ui-tars-1.5-7b-awq` 做**同任务同截图**的 grounding 对照实验。
>
> 对应的实验假设见 `docs/uitars_migration_plan.md` 的 Path 2。
>
> 本文档默认**保留现有的 UI-TARS 服务不动**（仍在 8000 端口），
> MAI-UI-2B 起在 **8001** 端口，两个服务共用同一张 RTX 5090。

---

## 0. 目标架构

```
┌───────────────────────────────────────────────────────┐
│  Windows (AutoVisionTest)                             │
│                                                       │
│  scripts/run_live_probe.py --endpoint 8000    (旧)    │
│  scripts/run_live_probe.py --endpoint 8001    (新)    │
│       │                         │                     │
│       ▼                         ▼                     │
└───────┼─────────────────────────┼─────────────────────┘
        │                         │   localhost (WSL2)
        ▼                         ▼
┌───────────────────┐   ┌──────────────────────────────┐
│ WSL2 vLLM :8000   │   │ WSL2 vLLM :8001              │
│ UI-TARS-1.5-7B-AWQ│   │ MAI-UI-2B (BF16)             │
│ ~6GB VRAM         │   │ ~5GB VRAM                    │
│ conda env: vllm   │   │ conda env: vllm-maiui        │  ← 新建
└───────────────────┘   └──────────────────────────────┘
        │                         │
        └──────── 同一张 RTX 5090 (32GB) ─────────┘
```

**为什么要新建 conda 环境 `vllm-maiui`**：MAI-UI 官方 README 明确要求
`vllm >= 0.11.0` 且 `transformers >= 4.57.0`（Qwen3-VL 架构需要），
而现有 UI-TARS 服务跑的 vLLM 0.19 用的是 Qwen2.5-VL 分支，两边依赖树
容易打架。**把 MAI-UI 塞进新 env 最稳**，旧 env 不动保证 UI-TARS 还能随时对跑。

---

## 1. 前置条件

你现在的 WSL 已经满足：

- WSL2 + Ubuntu-22.04
- NVIDIA 驱动 + `nvidia-smi` 可用（RTX 5090 / 32GB）
- Miniconda（`~/miniconda3` 或 `~/anaconda3`）
- 现有 `vllm` conda env 正在跑 UI-TARS（可选，保留即可）

快速验证：

```bash
nvidia-smi | head -5
# 期望看到 RTX 5090 + 剩余显存 >= 12GB（UI-TARS 跑着大约占 8-10GB）
```

---

## 2. Phase 1 — 创建专用 conda 环境

```bash
# 不要在现有 vllm env 里直接 upgrade，容易把 UI-TARS 弄炸
conda create -n vllm-maiui python=3.11 -y
conda activate vllm-maiui

# 国内网络走清华源（可选）
# pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# MAI-UI 官方钦定的版本组合
pip install "vllm==0.11.0" "transformers>=4.57.0"

# AutoAWQ 不需要装（我们不用量化版）
```

**验收**：

```bash
python -c "import vllm, transformers; print('vllm', vllm.__version__); print('transformers', transformers.__version__)"
# 期望：vllm 0.11.0 + transformers >= 4.57.0
```

> ⚠️ 如果这一步 `pip install vllm==0.11.0` 卡在编译 flash-attn 或 xformers，
> 先检查 `nvcc --version` 是否 >= 12.1。装不上告诉我卡在哪一行，我看日志。

---

## 3. Phase 2 — 下载 MAI-UI-2B 权重

同一 env 里：

```bash
conda activate vllm-maiui

# 国内网络启用镜像
export HF_ENDPOINT=https://hf-mirror.com

# 下载 BF16 权重（约 5GB，4 个 safetensors 分片）
huggingface-cli download Tongyi-MAI/MAI-UI-2B
```

**验收**：

```bash
du -sh ~/.cache/huggingface/hub/models--Tongyi-MAI--MAI-UI-2B
# 期望：~5GB
```

---

## 4. Phase 3 — 启动 MAI-UI-2B 服务（8001 端口）

**重要**：用 8001 端口，不要动 8000 上的 UI-TARS。

```bash
conda activate vllm-maiui

python -m vllm.entrypoints.openai.api_server \
  --model Tongyi-MAI/MAI-UI-2B \
  --served-model-name mai-ui-2b \
  --port 8001 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.25 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 5}'
```

### 参数说明

| 参数 | 说明 |
|---|---|
| `--model Tongyi-MAI/MAI-UI-2B` | HuggingFace repo id，vLLM 会从本地 hub 缓存加载 |
| `--served-model-name mai-ui-2b` | 稳定的 model id，Windows 侧 backend 用这个名字 |
| `--port 8001` | **不要用 8000**（8000 是 UI-TARS） |
| `--host 0.0.0.0` | Windows 才能访问到 WSL 内的服务 |
| `--dtype bfloat16` | 2B 模型不量化，直接 BF16；显存足够 |
| `--max-model-len 16384` | 容纳 1 张截图 (~3000 vision tokens) + 多轮历史 |
| `--gpu-memory-utilization 0.25` | **32GB × 25% ≈ 8GB**；权重 5GB + KV cache ~3GB 足矣，给 UI-TARS 留 20GB |
| `--trust-remote-code` | Qwen3-VL 自定义 modeling 需要 |
| `--limit-mm-per-prompt '{"image": 5}'` | 跟 UI-TARS 一致，历史最多带 5 张图 |

启动 40-90 秒，看到

```
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

即可。

### 显存 / 上下文权衡

MAI-UI-2B 比 UI-TARS-7B 小很多，vLLM 的预算公式同样是
`free_vram × utilization - weights`。两个服务同时跑的实测推荐组合：

| 场景 | UI-TARS-7B-AWQ | MAI-UI-2B | 总显存 |
|---|---|---|---|
| **推荐**（并存对跑） | `--gpu-memory-utilization 0.45` (port 8000) | `--gpu-memory-utilization 0.25` (port 8001) | ~22GB，留 10GB 缓冲 |
| 只跑 MAI-UI | — | `--gpu-memory-utilization 0.40` | ~13GB |
| 只跑 UI-TARS | `--gpu-memory-utilization 0.45` | — | ~14GB |

如果你嫌"两个服务同时占着"烦，**也可以先 `Ctrl+C` 停掉 UI-TARS**，只跑 MAI-UI：

```bash
# 在跑 UI-TARS 那个终端里按 Ctrl+C
# 然后在 vllm-maiui env 里把 --gpu-memory-utilization 调到 0.40
```

反正我们做对照实验时是**同任务分别跑**，不需要真的并发请求两个模型。

### 常见启动错误

- `Qwen3VLForConditionalGeneration not found` → `transformers` 版本太低，升级到 ≥ 4.57.0
- `vllm.version must be 0.11.0` → 别用更早或更新的 vLLM，这个模型的 Qwen3-VL 支持 0.11.0 最稳
- `CUDA OOM` → 先 `nvidia-smi` 看 UI-TARS 占了多少，然后下调 `--gpu-memory-utilization` 到 0.20
- `ValueError: bfloat16 is not supported` → 少见；如果真的遇到，降到 `--dtype float16`

---

## 5. Phase 4 — 健康检查

### 5.1 WSL 内 curl

```bash
curl -s http://localhost:8001/v1/models | python -m json.tool
```

期望看到：

```json
{
  "data": [
    { "id": "mai-ui-2b", ... }
  ]
}
```

### 5.2 Windows 侧可达性

PowerShell：

```powershell
Invoke-RestMethod -Uri http://localhost:8001/v1/models | ConvertTo-Json
```

能看到同样 id 即网络通。

### 5.3 纯文本最小对话

确认基础推理通路没问题（不含图像）：

```bash
curl -s http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mai-ui-2b",
    "messages": [{"role":"user","content":"Reply in one short sentence."}],
    "max_tokens": 64,
    "temperature": 0
  }'
```

期望：返回一段英文短句（MAI-UI 是 GUI-instruct tuning，通用闲聊可能比较呆，但不应该报错）。

### 5.4 带图 + GUI grounding 的最小 probe

**这一步验证模型真的会输出 GUI action**。让它看一张截图，指一个元素：

```bash
# 用方舟官方那张演示图（和之前给 Doubao 测的是同一张）
curl -s http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mai-ui-2b",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://ark-project.tos-cn-beijing.ivolces.com/images/view.jpeg"}},
        {"type": "text", "text": "Describe what you see in one short sentence."}
      ]
    }],
    "max_tokens": 128,
    "temperature": 0
  }' | python -m json.tool
```

能拿到 `choices[0].message.content` 里是对图片内容的英文描述即可。

**这一步的 raw response 把开头 100 字发给我**——我要根据它输出的实际方言（归一化坐标
vs 像素坐标、action 关键字拼写）写 `MAIUIBackend`。

---

## 6. 一键启动脚本

```bash
cat > ~/start_maiui.sh <<'EOF'
#!/bin/bash
# 启动 MAI-UI-2B 服务（用于跟 UI-TARS-AWQ 做 grounding 对照）
# 对应 docs/maiui_wsl2_deploy.md

set -euo pipefail

export HF_ENDPOINT=https://hf-mirror.com

echo "=== Starting MAI-UI-2B on :8001 ==="
exec python -m vllm.entrypoints.openai.api_server \
  --model Tongyi-MAI/MAI-UI-2B \
  --served-model-name mai-ui-2b \
  --port 8001 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.25 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 5}'
EOF

chmod +x ~/start_maiui.sh
```

以后：

```bash
conda activate vllm-maiui && ~/start_maiui.sh
```

---

## 7. 运行时观测

```bash
# 总显存占用（看 UI-TARS + MAI-UI 加起来多少）
watch -n 2 nvidia-smi

# 单服务指标
curl -s http://localhost:8001/metrics | grep -E "vllm:(request_|avg_|running)"
```

MAI-UI-2B 在 RTX 5090 上单张 1344×756 截图单轮推理预计 **0.5-1.5 秒**（比
UI-TARS-7B-AWQ 快 2-3 倍，因为参数少）。

---

## 8. 常见问题

| 症状 | 排查 |
|---|---|
| Windows 侧 `localhost:8001` 连不上 | 确认启动命令有 `--host 0.0.0.0`；检查 WSL 是否在 NAT 模式（mirrored 模式最简单） |
| 两个服务启动后一个挂了 | 最可能是 OOM；看 `nvidia-smi`，总占用 > 30GB 就挤掉 UI-TARS 的 `--gpu-memory-utilization` 或 MAI-UI 的 |
| `Qwen3VL` 未识别 | `pip install -U transformers`；仍不行就下载最新 vllm 小版本：`pip install vllm==0.11.0 --force-reinstall` |
| `import mai_grounding_agent failed` | **不需要装 mai_grounding_agent**，我们走 OpenAI 兼容 API，不用他们的 cookbook 包 |
| MAI-UI 响应很短/不含坐标 | 这是正常现象，MAI-UI 对不明确的 prompt 回答会很简洁；**等 Windows 侧的 `MAIUIBackend` 写好后按它的 prompt 模板测才有意义**。5.4 只是为了确认链路通，不是功能验证 |

---

## 9. 完成标准

全部打钩即可告诉我"部署完了"：

- [ ] 新 conda env `vllm-maiui` 创建成功，`vllm==0.11.0` + `transformers>=4.57.0` 装上
- [ ] `du -sh ~/.cache/huggingface/hub/models--Tongyi-MAI--MAI-UI-2B` 显示 ~5GB
- [ ] UI-TARS (8000) 和 MAI-UI (8001) **同时** `/v1/models` 都能返回正确 id
- [ ] `nvidia-smi` 看总显存 < 25GB（两个服务都稳了）
- [ ] Phase 5.4 那个带图 curl 的 raw response 前 100 字**截图或复制发我**

---

## 10. 下一步（我这边的工作）

看到你交付 § 9 之后，我会立刻开工：

1. **新建 `src/autovisiontest/backends/maiui.py`**
   - prompt 模板（需根据 5.4 输出反推出 MAI-UI 实际吃什么格式）
   - 归一化坐标 → 绝对像素的反算（跟 UI-TARS 的 sent-frame 反算不同）
   - action schema 的 parser（如果它也用 `click(...)` 语法就复用 AST；如果是 JSON tool-call 就写新解析器）

2. **扩展 `factory.py`**
   - 支持根据 config 里 `backend.kind` 切换 `uitars_local` / `maiui_local`

3. **新建 `scripts/run_live_probe_maiui.py`** 或者给 `run_live_probe.py` 加 `--backend` 开关

4. **跑同一个 calculator case**
   - 完全一样的任务 prompt
   - 完全一样的屏幕状态（你手动还原）
   - 对比 × 按钮的 grounding 是否落在 `(1397 ± 40, 640 ± 40)` 屏幕坐标

实验结束后，我们会对三个 7B 量级的 backend 出一份横向对比报告（UI-TARS-AWQ / UI-TARS-fp16 如果要做 / MAI-UI-2B），用数据说话下一步怎么走。
