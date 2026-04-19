# WSL2 + vLLM 本地模型部署方案

> 目标：在 WSL2 (Ubuntu-22.04) 中部署两个 VLM 服务，供 Windows 侧 AutoVisionTest 框架通过 OpenAI 兼容 API 调用。

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  Windows (AutoVisionTest)                               │
│                                                         │
│  autovisiontest run ...                                 │
│       │                                                 │
│       ├── Planner ──→ http://localhost:8000/v1          │
│       │              (Qwen2.5-VL-7B-Instruct-AWQ)      │
│       │                                                 │
│       └── Actor   ──→ http://localhost:8001/v1          │
│                      (ShowUI-2B)                        │
└─────────────┬──────────────────────┬────────────────────┘
              │ localhost            │ localhost
              ▼                      ▼
┌─────────────────────────────────────────────────────────┐
│  WSL2 (Ubuntu-22.04)                                    │
│                                                         │
│  vLLM Server :8000  →  Qwen2.5-VL-7B (~5GB AWQ)       │
│  vLLM Server :8001  →  ShowUI-2B       (~4GB)          │
│                                                         │
│  GPU: NVIDIA RTX 5090 (32GB VRAM)                       │
│  显存预估: Planner ~18GB + Actor ~9GB ≈ 27GB           │
└─────────────────────────────────────────────────────────┘
```

**关键点**：WSL2 与 Windows 共享 `localhost`，Windows 侧的 `localhost:8000` 直接可达 WSL2 内的服务。

---

## 2. WSL2 环境准备

### 2.1 启动 WSL 并更新系统

```bash
# 在 Windows PowerShell 中
wsl -d Ubuntu-22.04

# 进入 WSL 后
sudo apt update && sudo apt upgrade -y
```

### 2.2 安装 NVIDIA GPU 驱动支持

> Windows 侧已安装 NVIDIA 驱动即可，WSL2 会自动继承。无需在 WSL 内额外安装 NVIDIA 驱动。

验证：

```bash
nvidia-smi
# 应该能看到 RTX 5090 和 CUDA 版本
```

### 2.3 安装 Miniconda

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3
eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda init bash
source ~/.bashrc
```

### 2.4 创建 Python 3.11 虚拟环境

```bash
conda create -n vllm python=3.11 -y
conda activate vllm
```

---

## 3. 安装 vLLM

```bash
pip install vllm>=0.6.0
```

> vLLM 会自动安装 PyTorch + CUDA 依赖，大约 10-15 分钟。

验证安装：

```bash
python -c "import vllm; print(f'vLLM version: {vllm.__version__}')"
```

---

## 4. 下载模型

### 方案 A：首次启动时自动下载（推荐）

vLLM 首次启动时会自动从 HuggingFace 下载模型，无需手动操作。

### 方案 B：预先下载（网络不稳定时推荐）

```bash
pip install huggingface-hub

# 下载 Planner 模型 (~5GB)
huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct-AWQ

# 下载 Actor 模型 (~4GB)
huggingface-cli download showlab/ShowUI-2B
```

> 国内网络可能需要设置 HF 镜像：
> ```bash
> export HF_ENDPOINT=https://hf-mirror.com
> ```

---

## 5. 启动服务

### 5.1 启动 Planner 服务 (Qwen2.5-VL-7B, Port 8000)

打开 **WSL 终端 1**：

```bash
conda activate vllm

python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-VL-7B-Instruct-AWQ \
  --port 8000 \
  --host 0.0.0.0 \
  --dtype auto \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.55 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 1}'
```

**参数说明**：
| 参数 | 说明 |
|------|------|
| `--port 8000` | Planner 服务端口 |
| `--host 0.0.0.0` | 允许 Windows 侧访问 |
| `--max-model-len 4096` | 上下文长度，Planner 接收截图+历史，4K 足够 |
| `--gpu-memory-utilization 0.55` | 先启动 Planner，预留 ~55% 显存（~18GB） |
| `--trust-remote-code` | Qwen 模型需要 |
| `--limit-mm-per-prompt` | 限制每次请求最多 1 张图片，防止意外 OOM |

等待看到 `Uvicorn running on http://0.0.0.0:8000` 即启动成功。

### 5.2 启动 Actor 服务 (ShowUI-2B, Port 8001)

> **重要**：必须在 Planner 完全加载后再启动 Actor，否则会抢显存。

打开 **WSL 终端 2**：

```bash
conda activate vllm

python -m vllm.entrypoints.openai.api_server \
  --model showlab/ShowUI-2B \
  --port 8001 \
  --host 0.0.0.0 \
  --dtype auto \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.28 \
  --trust-remote-code \
  --enforce-eager \
  --limit-mm-per-prompt '{"image": 1}'
```

**参数说明**：
| 参数 | 说明 |
|------|------|
| `--port 8001` | Actor 服务端口 |
| `--max-model-len 8192` | **必须 8192**。4K 屏幕截图压缩到 640 短边后仍有 ~3700 visual tokens，2048 远不够 |
| `--gpu-memory-utilization 0.28` | 同卡双开时，Actor 只能用剩余显存（约 28%，~9GB） |
| `--enforce-eager` | **必须加**。同卡第二个 vLLM 在 max-model-len 8192 下会触发 CUDA graph profiling 断言失败，enager 模式可绕过 |
| `--limit-mm-per-prompt '{"image": 1}'` | 限制每次请求最多 1 张图片（vLLM ≥ 0.19.x 需用 JSON 格式） |

### 5.3 显存分配策略

> **核心约束**：两个 vLLM 实例在同一张 RTX 5090 (32GB) 上，后启动的只能使用剩余显存。

| 启动顺序 | 服务 | GPU 利用率 | 实际占用 | 说明 |
|----------|------|-----------|---------|------|
| 1st | Planner (Qwen2.5-VL-7B-AWQ) | 55% (~18GB) | ~5GB | 必须先启动 |
| 2nd | Actor (ShowUI-2B) | 28% (~9GB) | ~4GB | 用剩余显存 |
| — | **合计** | 83% (~27GB) | ~9GB | 有余量给 KV Cache |

**为什么 Actor 不能用 40%？** Planner 加载后虽只占 ~5GB，但 vLLM 的 KV Cache 内存池会预分配到 `gpu-memory-utilization` 指定的比例。剩余可分配的显存约 ~9GB（28% of 32GB），刚好够 Actor 使用。

---

## 6. 验证服务

### 6.1 在 WSL 内验证

```bash
# 验证 Planner
curl -s http://localhost:8000/v1/models | python -m json.tool

# 验证 Actor
curl -s http://localhost:8001/v1/models | python -m json.tool
```

应分别返回 `Qwen/Qwen2.5-VL-7B-Instruct-AWQ` (max_model_len: 4096) 和 `showlab/ShowUI-2B` (max_model_len: 8192)。

### 6.2 在 Windows PowerShell 中验证

```powershell
# 验证 Planner
Invoke-RestMethod -Uri http://localhost:8000/v1/models

# 验证 Actor
Invoke-RestMethod -Uri http://localhost:8001/v1/models
```

### 6.3 端到端功能测试

```bash
# 在 Windows 侧运行
cd E:\AutoAgent
python scripts/test_backends.py
```

预期输出：
```
=== Testing Planner (Qwen2.5-VL-7B) ===
Planner response: {"greeting": "...", "status": "ok"}
Planner OK!

=== Testing Actor (ShowUI-2B) ===
Screenshot captured: ... bytes
Grounding result: x=..., y=..., confidence=0.80
Actor OK!

=== All backend tests passed! ===
```

---

## 7. 项目配置

当前 `config/model.yaml` 已配置好：

```yaml
planner:
  backend: "vllm_local"
  model: "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
  endpoint: "http://localhost:8000/v1"

actor:
  backend: "showui_local"
  model: "showlab/ShowUI-2B"
  endpoint: "http://localhost:8001/v1"
```

无需额外修改，直接可用。

---

## 8. 一键启动脚本

创建 `~/start_vllm.sh`：

```bash
#!/bin/bash
# 启动 AutoVisionTest VLM 服务（单卡双实例）
# RTX 5090 32GB — Planner 55%, Actor 28%

export HF_ENDPOINT=https://hf-mirror.com  # 国内镜像，按需启用

echo "=== Starting Planner (Qwen2.5-VL-7B) on :8000 ==="
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-VL-7B-Instruct-AWQ \
  --port 8000 \
  --host 0.0.0.0 \
  --dtype auto \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.55 \
  --trust-remote-code \
  --limit-mm-per-prompt '{"image": 1}' &

PLANNER_PID=$!
echo "Planner PID: $PLANNER_PID"

echo "=== Waiting 30s for Planner to load model... ==="
sleep 30

echo "=== Starting Actor (ShowUI-2B) on :8001 ==="
python -m vllm.entrypoints.openai.api_server \
  --model showlab/ShowUI-2B \
  --port 8001 \
  --host 0.0.0.0 \
  --dtype auto \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.28 \
  --trust-remote-code \
  --enforce-eager \
  --limit-mm-per-prompt '{"image": 1}' &

ACTOR_PID=$!
echo "Actor PID: $ACTOR_PID"

echo ""
echo "=== Both services starting ==="
echo "Planner PID: $PLANNER_PID (port 8000, max_model_len 4096)"
echo "Actor PID:   $ACTOR_PID   (port 8001, max_model_len 8192)"
echo ""
echo "Press Ctrl+C to stop both services"

trap "kill $PLANNER_PID $ACTOR_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
```

使用方式：

```bash
conda activate vllm
chmod +x ~/start_vllm.sh
~/start_vllm.sh
```

---

## 9. 踩坑记录

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Actor 400 Bad Request: `Input length exceeds max context length` | 4K 屏幕截图 token 数远超 `--max-model-len 2048` | 将 Actor 的 `--max-model-len` 改为 **8192**，同时框架侧压缩截图到 640px 短边 |
| `--limit-mm-per-prompt image=1` 报错 `Value image=1 cannot be converted` | vLLM ≥ 0.19.x 要求 JSON 格式 | 改为 `--limit-mm-per-prompt '{"image": 1}'` |
| Actor 无法启动: `Free memory ... less than desired` | Planner 已占用显存，Actor 预留池不够 | 降低 Actor 的 `--gpu-memory-utilization` 到 **0.28** |
| Actor 触发 CUDA graph profiling 断言 | 同卡双实例 + 大 max-model-len 冲突 | 加 `--enforce-eager` 禁用 CUDA graph |
| ShowUI 返回单引号 JSON `{'x': 0.5}` | 模型输出不规范 | 框架侧 `_parse_coordinates` 自动将单引号替换为双引号 |

---

## 10. 故障排查

| 问题 | 解决方案 |
|------|---------|
| `nvidia-smi` 失败 | 确认 Windows NVIDIA 驱动已安装且为最新版 |
| 模型下载慢/超时 | 设置 `export HF_ENDPOINT=https://hf-mirror.com` |
| CUDA out of memory | 先确认 Planner 是否已完全加载，再调低 Actor 的 `--gpu-memory-utilization` |
| Windows 无法访问 WSL 端口 | 确认 WSL2 版本 ≥ 0.67.6（支持 localhost 转发）。检查 `wsl --version` |
| vLLM 安装失败 | 确认 WSL2 Ubuntu 版本 ≥ 22.04，glibc ≥ 2.35 |
| Qwen 模型 trust-remote-code 报错 | 确认加了 `--trust-remote-code` 参数 |
| Actor 启动时 profiling 断言 | 加 `--enforce-eager` 参数 |

---

## 11. 部署完成检查清单

部署完成后，在 Windows PowerShell 中逐项确认：

```powershell
# 1. Planner 服务可达，max_model_len = 4096
(Invoke-RestMethod http://localhost:8000/v1/models).data

# 2. Actor 服务可达，max_model_len = 8192
(Invoke-RestMethod http://localhost:8001/v1/models).data

# 3. 项目配置加载正常
autovisiontest validate

# 4. 端到端测试
python E:\AutoAgent\scripts\test_backends.py

# 5. 试运行
autovisiontest run --goal "打开记事本,输入hello" --app "notepad.exe"
```
