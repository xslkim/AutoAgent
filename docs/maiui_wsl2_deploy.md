# MAI-UI-2B BF16 WSL2 部署手册

> 文档版本：v1.1（2026-04-20）
>
> 适用状态：MAI-UI-2B 是 AutoVisionTest 当前的**唯一 GUI-Agent 后端**，
> UI-TARS-1.5-7B-AWQ 已停用。
>
> 关联代码：`src/autovisiontest/backends/maiui.py` /
> `src/autovisiontest/engine/agent.py` / `config/model.yaml`

---

## 0. 架构概览

```
┌─────────────────────────────────────────────────────┐
│  Windows 10/11                                       │
│                                                      │
│  autovisiontest run ...                              │
│       │                                              │
│       └── UITarsAgent (MAIUIBackend)                 │
│                │                                     │
│                └──→ http://localhost:8001/v1         │
└────────────────────────────┬────────────────────────┘
                             │ localhost (WSL2 mirrored)
                             ▼
┌─────────────────────────────────────────────────────┐
│  WSL2 (Ubuntu-22.04)                                 │
│                                                      │
│  vLLM Server :8001  →  Tongyi-MAI/MAI-UI-2B          │
│  conda env: vllm-maiui                               │
│  dtype: bfloat16   VRAM: ~8GB (含 KV cache)          │
│                                                      │
│  GPU: NVIDIA RTX 5090 (32GB VRAM)                    │
└─────────────────────────────────────────────────────┘
```

关键点：

| 项 | 值 |
|---|---|
| 模型 | `Tongyi-MAI/MAI-UI-2B`（Qwen3-VL 架构，BF16，无量化） |
| 端口 | **8001**（和 Windows 侧 `MAIUIBackend` 硬编码一致） |
| conda 环境 | `vllm-maiui`（与旧 UI-TARS 环境隔离） |
| 坐标系 | 模型输出 `[0, 1000]` 归一化坐标，backend 自动反算回屏幕像素 |
| 单步延迟 | E2E 实测 **125–470 ms**（grounding 单目标）；多轮历史 1–3 s |

---

## 1. 前置条件

- WSL2 + Ubuntu-22.04
- NVIDIA 驱动可用：`nvidia-smi` 能看到 RTX 5090
- Miniconda 已装（`~/miniconda3` 或 `~/anaconda3`）

快速验证：

```bash
nvidia-smi | head -5
# 期望：RTX 5090，32GB，进程列表空（没有跑着的 vLLM）
```

如果还有旧服务（UI-TARS 或其他）占着 GPU，先停掉：

```bash
pkill -f "vllm.entrypoints.openai.api_server"
sleep 3 && nvidia-smi
```

---

## 2. 创建专用 conda 环境

MAI-UI-2B 官方要求 `vllm >= 0.11.0` + `transformers >= 4.57.0`（Qwen3-VL 架构需要），与旧 vLLM 依赖不兼容，因此单独建 env：

```bash
conda create -n vllm-maiui python=3.11 -y
conda activate vllm-maiui

# 国内网络可加清华源加速
# pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

pip install "vllm==0.11.0" "transformers>=4.57.0"
```

验收：

```bash
python -c "import vllm, transformers; print('vllm', vllm.__version__); print('transformers', transformers.__version__)"
# 期望：vllm 0.11.0   transformers >= 4.57.0
```

> ⚠️ 如果 `pip install vllm==0.11.0` 卡在编译 flash-attn / xformers，
> 先确认 `nvcc --version >= 12.1`。

---

## 3. 下载模型权重

```bash
conda activate vllm-maiui

# 国内网络启用镜像
export HF_ENDPOINT=https://hf-mirror.com

# BF16 权重，约 5GB（4 个 safetensors 分片）
huggingface-cli download Tongyi-MAI/MAI-UI-2B
```

验收：

```bash
du -sh ~/.cache/huggingface/hub/models--Tongyi-MAI--MAI-UI-2B
# 期望：~5GB
```

---

## 4. 启动服务

```bash
conda activate vllm-maiui

python -m vllm.entrypoints.openai.api_server \
  --model Tongyi-MAI/MAI-UI-2B \
  --served-model-name mai-ui-2b \
  --port 8001 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.40 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 5}'
```

### 参数说明

| 参数 | 说明 |
|---|---|
| `--served-model-name mai-ui-2b` | Windows 侧 `MAIUIBackend` 和 `run_live_probe.py` 都用这个名字 |
| `--port 8001` | 和 `src/autovisiontest/backends/maiui.py` 的默认 endpoint 保持一致 |
| `--host 0.0.0.0` | Windows 才能通过 WSL2 loopback 访问到 |
| `--dtype bfloat16` | 2B 模型不量化，直接 BF16；RTX 5090 原生支持 |
| `--max-model-len 16384` | 容纳 1 张截图（~3000 vision tokens）+ 最多 5 轮历史图 |
| `--gpu-memory-utilization 0.40` | 32GB × 40% ≈ 12.8GB；权重 5GB + KV cache 有充裕缓冲 |
| `--trust-remote-code` | Qwen3-VL 自定义 modeling 需要 |
| `--limit-mm-per-prompt '{"image": 5}'` | 单次请求最多 5 张图（匹配 `build_messages` 的 `history_images=3` 上限） |

启动 30–90 秒后看到：

```
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

即服务就绪。

### 显存配置参考

| 场景 | `--gpu-memory-utilization` | `--max-model-len` | VRAM 估算 |
|---|---|---|---|
| **生产推荐** | 0.40 | 16384 | ~13GB |
| 省显存（调试） | 0.25 | 8192 | ~8GB |

如果启动报 `cannot store at most XXXXX tokens in KV cache`，按日志里的 `can store at most` 值反向调低 `--max-model-len`。

### 常见启动错误

| 错误信息 | 解决办法 |
|---|---|
| `Qwen3VLForConditionalGeneration not found` | `transformers` 版本太低，`pip install -U transformers` |
| `CUDA out of memory` | 把 `--gpu-memory-utilization` 降到 0.30 并同步降 `--max-model-len` |
| `ValueError: bfloat16 is not supported` | 极少见；退回 `--dtype float16` |
| `vllm version must be 0.11.0` | Qwen3-VL 对 vLLM 版本敏感，确保是 0.11.0，不要用更早或更新版本 |

---

## 5. 健康检查

### 5.1 WSL 内验证

```bash
curl -s http://localhost:8001/v1/models | python -m json.tool
```

期望：

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

### 5.3 基础推理验证

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

能返回非空 `content` 即链路通。

---

## 6. 一键启动脚本

```bash
cat > ~/start_maiui.sh <<'EOF'
#!/bin/bash
# 启动 AutoVisionTest GUI-Agent 服务（MAI-UI-2B BF16）
# 对应 docs/maiui_wsl2_deploy.md

set -euo pipefail

export HF_ENDPOINT=https://hf-mirror.com   # 国内网络；海外注释掉此行

echo "=== Starting MAI-UI-2B on :8001 ==="
exec python -m vllm.entrypoints.openai.api_server \
  --model Tongyi-MAI/MAI-UI-2B \
  --served-model-name mai-ui-2b \
  --port 8001 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.40 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 5}'
EOF

chmod +x ~/start_maiui.sh
```

以后直接：

```bash
conda activate vllm-maiui && ~/start_maiui.sh
```

---

## 7. 运行时观测

```bash
# 显存占用
watch -n 2 nvidia-smi

# 请求速率 / 队列 / 延迟
curl -s http://localhost:8001/metrics | grep -E "vllm:(request_|avg_|running)"
```

实测延迟参考（RTX 5090，单张 1920×1080 截图）：

| 场景 | latency |
|---|---|
| grounding 单目标（计算器按钮） | 125–470 ms |
| E2E 多轮（含 3 张历史图） | 1–3 s |
| calculator 8×7=56 全程 10 步 | ~15 s total |

---

## 8. Windows 侧使用

服务起来后，Windows 侧不需要任何额外配置，框架默认就用 MAI-UI 后端。

### 直接 E2E 运行

```powershell
cd E:\AutoAgent
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"

# 倒计时 20s 后自动开始，先 Win+D 清空桌面
python scripts\run_live_probe.py --backend maiui --max-steps 15 --goal "你的测试目标"
```

### 切回 UI-TARS（如需对比）

如果需要重新跑 UI-TARS 做对比，参见 `docs/uitars_wsl2_deploy.md`。
两个服务可以同时在线（总显存 < 25GB），但日常只需要 MAI-UI。

---

## 9. 常见问题

| 症状 | 排查 |
|---|---|
| Windows 侧 `localhost:8001` 连不上 | 确认启动命令有 `--host 0.0.0.0`；WSL2 建议用 mirrored 网络模式（Windows 11 默认） |
| `Qwen3VL` 未识别 | `pip install -U transformers`（需要 ≥ 4.57.0） |
| `import mai_grounding_agent failed` | 不需要装该包，AutoVisionTest 走 OpenAI 兼容 API，不用官方 cookbook |
| 模型返回坐标偏差很大 | 正常，MAI-UI-2B 输出的是 `[0, 1000]` 归一化坐标，由 `_make_norm1000_transform` 自动反算；如果偏差系统性偏移，检查 `orig_w` / `orig_h` 是否取到了原始截图尺寸（不是压缩后的） |
| `Thought` 在多步后不变 | `build_messages` 的消息顺序问题（已修复）：需要 `screenshot → assistant_turn` 的因果顺序，不能颠倒 |

---

## 10. 版本历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-04-20 | 初版，定位为"UI-TARS 对照实验"，含双服务并跑说明 |
| v1.1 | 2026-04-20 | MAI-UI-2B 成为唯一生产后端；移除 UI-TARS 并存相关内容；`--gpu-memory-utilization` 从 0.25 调至 0.40（单服务模式）；补充 E2E 实测延迟数据 |
