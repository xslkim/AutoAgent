# UI-TARS-1.5-7B-AWQ WSL2 部署手册

> 目标：在 WSL2 (Ubuntu-22.04) 里部署 **单个** vLLM 服务跑 `flin775/UI-TARS-1.5-7B-AWQ`，
> 取代原来的 Qwen2.5-VL (8000) + ShowUI-2B (8001) 双服务方案。
>
> 本文档覆盖迁移规划的 **Phase 0 + Phase 1**（P0.1、P0.2、P1.1、P1.2、P1.3）。
> 按顺序执行即可，每一步都有验收命令。

---

## 0. 目标架构

```
┌───────────────────────────────────────────────────┐
│  Windows (AutoVisionTest)                         │
│                                                   │
│  autovisiontest run ...                           │
│       │                                           │
│       └── Agent ──→ http://localhost:8000/v1      │
│                    (UI-TARS-1.5-7B-AWQ)           │
└─────────────┬─────────────────────────────────────┘
              │ localhost (shared with WSL2)
              ▼
┌───────────────────────────────────────────────────┐
│  WSL2 (Ubuntu-22.04)                              │
│                                                   │
│  vLLM Server :8000  →  UI-TARS-1.5-7B-AWQ  ~5GB   │
│                                                   │
│  GPU: NVIDIA RTX 5090 (32GB VRAM)                 │
└───────────────────────────────────────────────────┘
```

相比旧方案：
- 进程数 2 → 1
- 显存占用 ~27GB → ~8-10GB（上限，含 KV cache）
- 端口 8000+8001 → 8000

---

## 1. 前置条件（已有就跳过）

你之前跑 Qwen + ShowUI 双服务已经具备以下环境，本次直接复用：

- WSL2 + Ubuntu-22.04
- NVIDIA 驱动 + nvidia-smi 可用
- Miniconda，已有 `vllm` conda 环境（Python 3.11）
- `pip install vllm>=0.6.0` 已装好

快速验证（在 WSL 内）：

```bash
conda activate vllm
nvidia-smi | head -5
python -c "import vllm; print('vLLM', vllm.__version__)"
```

能看到 RTX 5090 + vLLM 版本号即可。

---

## 2. Phase 1.1 — 停掉旧服务

在两个原先跑 Qwen / ShowUI 的 WSL 终端里各按一次 `Ctrl+C` 停掉 vLLM。

确认 GPU 完全释放：

```bash
nvidia-smi
# 期望：没有 python 进程，显存占用接近 0
```

如果还有残留进程：

```bash
pkill -f "vllm.entrypoints.openai.api_server"
sleep 3
nvidia-smi
```

**验收**：`nvidia-smi` 里没有任何 python vLLM 进程。

---

## 3. Phase 0.1 — 下载 UI-TARS-1.5-7B-AWQ 权重

在 WSL 里（新开一个终端，或者复用停掉旧服务后的终端）：

```bash
conda activate vllm

# 国内网络建议启用镜像（和之前保持一致）
export HF_ENDPOINT=https://hf-mirror.com

# 下载 AWQ 权重（约 5GB）
huggingface-cli download flin775/UI-TARS-1.5-7B-AWQ
```

默认缓存在 `~/.cache/huggingface/hub/`，和原先的 Qwen / ShowUI 在同一位置。

**验收**：

```bash
du -sh ~/.cache/huggingface/hub/models--flin775--UI-TARS-1.5-7B-AWQ
# 期望：~5GB
```

---

## 4. Phase 0.2 + 1.2 — 启动 UI-TARS 服务

新开一个 WSL 终端（或复用下载的终端）：

```bash
conda activate vllm

python -m vllm.entrypoints.openai.api_server \
  --model flin775/UI-TARS-1.5-7B-AWQ \
  --served-model-name ui-tars-1.5-7b \
  --port 8000 \
  --host 0.0.0.0 \
  --dtype float16 \
  --quantization awq \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.45 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 5}'
```

**参数说明**：

| 参数 | 说明 |
|---|---|
| `--model flin775/UI-TARS-1.5-7B-AWQ` | AWQ 4-bit 权重 |
| `--served-model-name ui-tars-1.5-7b` | 稳定的 model id，API 调用用这个名字 |
| `--port 8000 --host 0.0.0.0` | 监听 Windows 侧能访问的端口 |
| `--dtype float16` | **AWQ 必须用 float16**——vLLM 对 AWQ + `bfloat16`/`auto` 的组合会直接抛 `ValidationError`，别写 `auto` |
| `--quantization awq` | 显式告诉 vLLM 用 AWQ 路径（避免误判） |
| `--max-model-len 16384` | 足够容纳 1 张截图 + 多轮 Thought/Action 历史；UI-TARS 场景下截图 visual tokens 往往 ≥ 3000 |
| `--gpu-memory-utilization 0.45` | 32GB × 45% ≈ 14.4GB。**实测 vLLM 0.19 + 16384 上下文在 0.30 时 KV cache 分配不下**，0.45 是实测下限 |
| `--trust-remote-code` | Qwen2.5-VL 架构需要 |
| `--limit-mm-per-prompt '{"image": 5}'` | 单次请求最多 5 张图，给历史截图留空间（JSON 语法，vLLM ≥ 0.6 要求） |

启动大约 30-90 秒，看到 `Uvicorn running on http://0.0.0.0:8000` 即可。

### 显存 / 上下文权衡（重要）

`gpu-memory-utilization` 和 `max-model-len` 是**一对绑定参数**：vLLM 启动时按
`free_vram × utilization - weights` 给 KV cache 预算；预算不够就直接拒绝启动并报

```
The model's max seq len is larger than the maximum number of tokens that can be stored in KV cache
```

本机 RTX 5090（32GB）+ vLLM 0.19 + UI-TARS-1.5-7B-AWQ 的实测可用组合：

| `max-model-len` | 最低 `gpu-memory-utilization` | 备注 |
|---|---|---|
| 16384 | **0.45** | 当前推荐配置 |
| 11152 | 0.30 | 如果要把显存压到 30%，把上下文同步砍到这里 |
| 8192  | 0.25 | 调试 / 极端省显存时 |

启动失败时看 vLLM 日志尾部给出的 `can store at most XXXXX tokens` 估算，按这个数反向决定 `--max-model-len`。

### 其它常见启动错误

- `ValidationError: dtype='bfloat16' ... 'awq'` → 把 `--dtype` 改成 `float16`（见上表）
- `CUDA out of memory` → 把 `--gpu-memory-utilization` 往下调一档；如果 16384 太贪，按上表把 `--max-model-len` 也同步降
- `Qwen2_5_VL` 找不到 → `pip install -U transformers`
- `limit-mm-per-prompt` 语法报错 → 旧版 vLLM 用 `'image=5'` 字符串；新版（≥0.6）必须用上面的 JSON
- `AWQ` 相关其它报错 → 先不加 `--quantization awq`，让 vLLM 从 config 自动推断

---

## 5. Phase 1.3 — 验收 probe

### 5.1 健康检查（WSL 内）

另开一个 WSL 终端：

```bash
curl -s http://localhost:8000/v1/models | python -m json.tool
```

期望看到 `"id": "ui-tars-1.5-7b"`。

### 5.2 Windows 侧可达性

在 Windows PowerShell：

```powershell
Invoke-RestMethod -Uri http://localhost:8000/v1/models | ConvertTo-Json
```

能看到相同 id 即 WSL-Windows 网络通路正常。

### 5.3 端到端 Thought+Action probe

**这一步验证模型真的能按 UI-TARS 格式输出**。我会在 Windows 侧放一个小脚本
`scripts/probe_uitars.py`（见任务 P2.4 交付物），你跑一下它，看 raw response 是否有：

```
Thought: 当前画面上...我需要点击...
Action: click(point='<point>512 720</point>')
```

这种结构的字符串。如果有，**Phase 0/1 收工**。

> 脚本还没写好前，可以先用 curl 快速自测：
>
> ```bash
> # 在 WSL 或 Windows 任意侧都行
> curl -s http://localhost:8000/v1/chat/completions \
>   -H "Content-Type: application/json" \
>   -d '{
>     "model": "ui-tars-1.5-7b",
>     "messages": [{"role":"user","content":"Hello, respond in one short sentence."}],
>     "max_tokens": 64
>   }'
> ```
>
> 能返回一段英文回答即服务 OK。**注意这个测试不含图像，只验证基础对话通路**。
> 完整的 image + UI-TARS 格式验证要用 `probe_uitars.py`。

---

## 6. 一键启动脚本

为了以后方便，把启动命令存成 `~/start_uitars.sh`：

```bash
cat > ~/start_uitars.sh <<'EOF'
#!/bin/bash
# 启动 AutoVisionTest 单模型 UI-TARS 服务
# 对应 docs/uitars_wsl2_deploy.md

set -euo pipefail

# 国内网络启用 HF 镜像；海外直接注释掉此行
export HF_ENDPOINT=https://hf-mirror.com

echo "=== Starting UI-TARS-1.5-7B-AWQ on :8000 ==="
exec python -m vllm.entrypoints.openai.api_server \
  --model flin775/UI-TARS-1.5-7B-AWQ \
  --served-model-name ui-tars-1.5-7b \
  --port 8000 \
  --host 0.0.0.0 \
  --dtype float16 \
  --quantization awq \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.45 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 5}'
EOF

chmod +x ~/start_uitars.sh
```

以后直接：

```bash
conda activate vllm && ~/start_uitars.sh
```

---

## 7. 运行时观测

服务稳定后，偶尔用这两条命令盯一下资源：

```bash
# 显存
watch -n 2 nvidia-smi

# 请求速率 / 延迟（vLLM 自带 metrics）
curl -s http://localhost:8000/metrics | grep -E "vllm:(request_|avg_|running)"
```

UI-TARS 7B AWQ 在 RTX 5090 上单张截图单轮推理应该在 1-3 秒量级。

---

## 8. 常见问题

| 症状 | 排查 |
|---|---|
| Windows 侧 `localhost:8000` 连不上 | 确认 WSL 里起服务用了 `--host 0.0.0.0`；Windows 防火墙一般不拦 localhost |
| 显存 OOM | 按第 4 节"显存/上下文权衡"表重配 `--gpu-memory-utilization` + `--max-model-len` |
| 图片 token 太多超上下文 | 调大 `--max-model-len`；Windows 侧发图前的尺寸压缩已在 `backends/uitars.py::_resize_for_uitars` 内部完成 |
| AWQ dtype 报错 | `--dtype float16`（**不能**用 `auto` 或 `bfloat16`） |
| 启动慢 | 首次启动 vLLM 会做 CUDA graph capture + warmup，30-90 秒正常 |
| `Qwen2_5_VL` 找不到 | 更新 `transformers` 到最新：`pip install -U transformers` |
| 中文输入乱码 | 检查 WSL/SSH 终端 locale：`export LANG=en_US.UTF-8` |

---

## 9. 完成标准

全部通过即可把本手册对应的 TODO 项标完：

- [ ] `nvidia-smi` 里没有旧 Qwen / ShowUI vLLM 进程
- [ ] `du -sh ~/.cache/huggingface/hub/models--flin775--UI-TARS-1.5-7B-AWQ` 显示 ~5GB
- [ ] `curl http://localhost:8000/v1/models` 返回 `ui-tars-1.5-7b`
- [ ] Windows 侧 `Invoke-RestMethod` 能拿到同样的结果
- [ ] 简单的非图片 chat 请求能正常 echo

做完告诉我一声，我这边把 `probe_uitars.py` 送上，做一次真实图像 + UI-TARS 格式的收尾验证，然后进入 Phase 2+。
