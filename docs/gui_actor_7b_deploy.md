# GUI-Actor-7B 部署手册

> 模型：`microsoft/GUI-Actor-7B-Qwen2.5-VL`  
> 参考论文：[GUI-Actor: Coordinate-Free Visual Grounding for GUI Agents](https://arxiv.org/abs/2506.03143)  
> GitHub：https://github.com/microsoft/GUI-Actor

---

## 0. 与 UI-TARS 的关键差异

在部署前必须理解 GUI-Actor 的架构与 UI-TARS 有本质区别，这直接影响集成方式。

### 坐标输出方式不同

| 项目 | UI-TARS-1.5-7B | GUI-Actor-7B |
|------|----------------|--------------|
| 输出方式 | 文本生成坐标 | Attention-based `<ACTOR>` token |
| 坐标格式 | `click(start_box='(680,584)')` | 归一化浮点 `[px, py] ∈ [0,1]` |
| 解析方式 | 正则解析文本 | 读取 attention map 的加权中心 |
| vLLM 标准 API | ✅ 直接兼容 | ⚠️ 需要 `--trust-remote-code` 加载自定义推理头 |

### 精度优势来源

GUI-Actor 论文指出 UI-TARS 类文本坐标方案的三个缺陷：

1. **空间语义对齐弱**：坐标数字与视觉 patch 没有直接绑定
2. **监督信号模糊**：同一按钮有多个合法坐标表示
3. **粒度不匹配**：视觉 patch 是 28×28px，坐标是像素级

GUI-Actor 用 Attention Head 直接对视觉 patch 打分，绕过了上述问题。ScreenSpot-Pro 精度 44.6%，而 UI-TARS-1.5-7B 约 28%。

---

## 1. 硬件要求

### 最低配置

| 组件 | 要求 | 说明 |
|------|------|------|
| GPU VRAM | **16 GB** | BF16 模型本体 ~14.5 GB，推理时 KV-cache + 激活值需额外约 1.5 GB |
| 系统内存 | 32 GB | 模型加载时 CPU 侧缓冲 |
| 磁盘 | 30 GB | 模型权重 ~15 GB，vLLM 环境 ~8 GB，缓存余量 |

### 当前环境

```
GPU: RTX 4060 Ti 16 GB
显存占用（参考）:
  - 模型 BF16:    ~14.5 GB
  - KV-cache:     ~1.2 GB（max-model-len=2048 时）
  - 运行时缓冲:    ~0.3 GB
  - 合计:         ~16 GB  ← 极限，建议 max-model-len 不超过 2048
```

> ⚠️ **没有官方 AWQ 量化版本。** 社区暂无发布，若 16 GB 不够用，需自行量化或降低 max-model-len。

---

## 2. 环境准备（WSL2 Ubuntu 22.04）

```bash
# 与 UI-TARS 部署共用同一套 Python/CUDA 环境即可
# 确认 CUDA 版本
nvidia-smi
nvcc --version   # 要求 CUDA 12.1+

# 确认 vLLM 版本（要求 0.6.0+，建议最新）
pip show vllm
# 如需升级：
pip install -U vllm
```

---

## 3. 下载模型

```bash
# 方式一：huggingface-cli（推荐，支持断点续传）
pip install huggingface_hub
huggingface-cli download microsoft/GUI-Actor-7B-Qwen2.5-VL \
  --local-dir ~/models/GUI-Actor-7B \
  --local-dir-use-symlinks False

# 方式二：git lfs（需要科学上网）
git lfs install
git clone https://huggingface.co/microsoft/GUI-Actor-7B-Qwen2.5-VL \
  ~/models/GUI-Actor-7B
```

下载完成后验证文件数量（应有 4 个 safetensors 分片）：

```bash
ls ~/models/GUI-Actor-7B/*.safetensors | wc -l
# 期望输出: 4
```

---

## 4. 启动 vLLM 服务

### 4.1 启动命令

```bash
python -m vllm.entrypoints.openai.api_server \
  --model ~/models/GUI-Actor-7B \
  --served-model-name gui-actor-7b \
  --trust-remote-code \
  --dtype bfloat16 \
  --max-model-len 2048 \
  --gpu-memory-utilization 0.92 \
  --limit-mm-per-prompt image=1 \
  --port 28801
```

### 4.2 关键参数说明

| 参数 | 值 | 原因 |
|------|----|------|
| `--trust-remote-code` | 必填 | 加载 GUI-Actor 自定义推理头（`<ACTOR>` token 的 attention 权重） |
| `--dtype bfloat16` | 必填 | 模型训练精度，不能用 float16 |
| `--max-model-len 2048` | 16 GB 显存限制 | 降低 KV-cache 占用，避免 OOM |
| `--gpu-memory-utilization 0.92` | RTX 4060 Ti 限制 | 留 ~1.3 GB 给系统和 CUDA 运行时 |
| `--limit-mm-per-prompt image=1` | 推荐 | 每次只处理单张截图，节省显存 |
| `--served-model-name gui-actor-7b` | 自定义 | 与 config/model.yaml 中的 model 字段对应 |

### 4.3 验证服务启动

```bash
curl http://localhost:28801/v1/models
# 期望返回包含 "gui-actor-7b" 的 JSON
```

---

## 5. 集成到 AutoVisionTest

> ⚠️ **GUI-Actor 不能直接替换 UI-TARS**，原因：坐标输出格式不同。

### 5.1 坐标格式对比

**UI-TARS 输出（当前解析器支持）：**
```
Thought: 我需要点击数字键5...
Action: click(start_box='(680,584)')
```

**GUI-Actor 通过 vLLM 标准 API 的输出：**
```python
pred["topk_points"][0]  # → [0.497, 0.762]  归一化坐标
```
映射到屏幕：`x = round(0.497 * 1920) = 954`，`y = round(0.762 * 1080) = 823`

### 5.2 需要新增的后端适配器

在 `src/autovisiontest/backends/` 下新增 `gui_actor.py`，处理归一化坐标解析。核心逻辑：

```python
# 归一化坐标 → 屏幕坐标
def _norm_to_screen(px: float, py: float, orig_w: int, orig_h: int):
    x = max(0, min(orig_w - 1, round(px * orig_w)))
    y = max(0, min(orig_h - 1, round(py * orig_h)))
    return x, y
```

### 5.3 config/model.yaml 切换配置

```yaml
agent:
  backend: "gui_actor"                        # 新后端标识
  model: "gui-actor-7b"
  endpoint: "http://10.11.0.123:28801/v1"
  max_tokens: 512
  temperature: 0.0
  language: "Chinese"
  history_images: 3
  timeout_s: 60.0
```

---

## 6. 精度验证

使用项目内置的验证脚本对比两个模型：

```bash
cd C:\d\AutoAgent

# 用 computer_720.png 对比 GUI-Actor vs UI-TARS
python base_test/calc_precision.py base_test/computer_720.png

# 用原始 1080P 截图对比
python base_test/calc_precision.py data/20260506_163541/step_0_before.png
```

结果保存在 `base_test/calc_precision_result.png`，可视化对比 5 个按键的点击精度。

---

## 7. 常见问题

### OOM（显存不足）

```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

解决方案（按优先级）：
1. 降低 `--max-model-len 1024`
2. 降低 `--gpu-memory-utilization 0.88`
3. 关闭其他占用 GPU 的进程：`fuser -v /dev/nvidia0`

### trust-remote-code 警告

```
WARNING: trust-remote-code is enabled...
```

正常现象，GUI-Actor 需要加载自定义 attention head 代码，信任微软官方仓库是安全的。

### 模型输出坐标为空

检查 vLLM 是否正确加载了自定义推理代码：

```bash
# 查看启动日志中是否有
grep "custom model" vllm.log
# 或检查模型配置
curl http://localhost:28801/v1/models | python -m json.tool
```

---

## 8. 与 UI-TARS-1.5-7B-AWQ 对比

| 项目 | UI-TARS-1.5-7B-AWQ | GUI-Actor-7B BF16 |
|------|--------------------|-------------------|
| ScreenSpot-Pro | ~28% | **44.6%** |
| VRAM 占用 | ~5 GB（AWQ 4-bit） | ~15.7 GB（BF16） |
| 16 GB 可用性 | ✅ 充裕 | ⚠️ 极限 |
| 量化版本 | ✅ 官方 AWQ | ❌ 暂无 |
| 代码兼容性 | ✅ 直接替换 | ❌ 需新增后端 |
| 全桌面 1080P 精度 | 中（缩放后 ~1344×756） | 较好（patch 级 attention） |

**结论**：精度提升明显（+60%），但集成成本高、显存紧张。建议：
- 先用 `calc_precision.py` 验证精度提升是否值得
- 确认值得后再开发 `gui_actor.py` 后端适配器
