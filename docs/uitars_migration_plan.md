# UI-TARS-1.5-7B 迁移规划

> 目标：把 AutoVisionTest 从"Qwen2.5-VL-7B (planner) + ShowUI-2B (actor)"的双模型架构
> 切换到"UI-TARS-1.5-7B (planner + actor 合一)"的单模型架构，让 Planner 天然具备
> GUI agent 的"观察—思考—行动"能力，摆脱"念剧本"式的僵化行为。

---

## 0. 背景

当前架构的两个痛点：

1. **Planner 是通用 VLM，缺 GUI 语义先验**
   - 现用 `Qwen/Qwen2.5-VL-7B-Instruct-AWQ`，它能看图能推理，但没针对 GUI 任务做过专门训练
   - 表现：完全按 GOAL 里的步骤顺序执行，即便屏幕上目标窗口已经打开，它也不会"跳过"
     已完成的子目标，呈现"念剧本"的僵化模式

2. **Grounding 模型过时**
   - `showlab/ShowUI-2B` 发布于 2024-11，基于更老的 Qwen2-VL-2B
   - ScreenSpot-Pro 近乎零分，复杂界面（比如被 IDE 占据大半屏）中定位能力差

---

## 1. 决策（已与用户对齐）

| 项 | 选择 | 备注 |
|---|---|---|
| 模型 | `flin775/UI-TARS-1.5-7B-AWQ` | 4-bit AWQ，~5GB VRAM，推理快 |
| 架构 | **合并 Planner + Actor** 为单次调用 | UI-TARS 一次输出 Thought+Action+absolute coords |
| 旧代码 | **直接删除**（ShowUI backend、Qwen planner 专用分支） | 项目还在迭代期，不留烂摊子 |
| 旧服务 | **都停掉**，UI-TARS 单服务占 8000 | 不搞 A/B 并存 |
| 测试 | 先冒烟，单元测试后补 | 优先跑通端到端 |
| GOAL 形态 | **3-4 步骨架**（不写具体 UI 元素名） | 给模型自主决策空间 |

---

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────┐
│  Windows (AutoVisionTest)                               │
│                                                         │
│  autovisiontest run ...                                 │
│       │                                                 │
│       └── UITarsAgent ──→ http://localhost:8000/v1      │
│              (单次调用直接拿到 Thought + Action + (x,y))│
└─────────────┬───────────────────────────────────────────┘
              │ localhost
              ▼
┌─────────────────────────────────────────────────────────┐
│  WSL2 (Ubuntu-22.04)                                    │
│                                                         │
│  vLLM Server :8000  →  UI-TARS-1.5-7B-AWQ (~5GB)        │
│                                                         │
│  GPU: NVIDIA RTX 5090 (32GB VRAM)                       │
└─────────────────────────────────────────────────────────┘
```

相比现状：
- 端口从 8000+8001 减到 8000
- 显存占用从 ~27GB 降到 ~5-8GB
- 每步推理从 2 次（Planner→Actor）减到 1 次

---

## 3. UI-TARS 核心规范（参考）

### 3.1 官方 COMPUTER_USE 提示模板

```
You are a GUI agent. You are given a task and your action history, with screenshots.
You need to perform the next action to complete the task.

## Output Format
Thought: ...
Action: ...

## Action Space
click(point='<point>x1 y1</point>')
left_double(point='<point>x1 y1</point>')
right_single(point='<point>x1 y1</point>')
drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
hotkey(key='ctrl c')        # lowercase, space-separated, max 3 keys
type(content='xxx')          # escape \', \", \n; end with \n to submit
scroll(point='<point>x1 y1</point>', direction='down or up or right or left')
wait()                       # sleep 5s then screenshot
finished(content='xxx')      # task done

## Note
- Use {language} in Thought.
- Write a small plan and summarize next action (with target) in one sentence in Thought.

## User Instruction
{instruction}
```

### 3.2 坐标约定
- `<point>x y</point>`，绝对像素坐标（相对于输入图像）
- 注意：UI-TARS 对图像有 max_pixels 限制（与 Qwen2.5-VL 同），长边过大会内部缩放，
  解析坐标时可能需要除以缩放比还原回原始屏幕分辨率

### 3.3 与当前 action 词汇的对应

| 当前 `control/actions.py` | UI-TARS | 差异 |
|---|---|---|
| `click` | `click` | ✓ 一致 |
| `double_click` | `left_double` | 改名 |
| `right_click` | `right_single` | 改名 |
| `drag` | `drag` | ✓ |
| `scroll` | `scroll` | ✓ |
| `type` | `type` | ✓（params 从 `text` 改 `content`） |
| `key_combo` | `hotkey` | 改名，参数从 list 改 space-separated 字符串 |
| `wait` | `wait` | ✓ |
| — | `finished` | 新增，替代 `done=true` 语义 |

---

## 4. 任务列表（按执行顺序）

> 每一项都是独立可 commit 的小步。按顺序做，做完一项勾一项。

### Phase 0 — 准备

- [ ] **P0.1** 在 WSL2 里拉取 `flin775/UI-TARS-1.5-7B-AWQ` 权重，确认磁盘够用（~5GB）
- [ ] **P0.2** 在 WSL2 里用 vLLM 裸启动 UI-TARS 一次，确认模型能加载、可以 `/v1/models` 返回
  - 验收：`curl http://localhost:8000/v1/models` 返回 UI-TARS 的 id

### Phase 1 — 部署切换

- [ ] **P1.1** 停掉 WSL2 里旧的两个 vLLM 服务（Qwen planner 8000、ShowUI actor 8001）
- [ ] **P1.2** 起 UI-TARS 服务到 8000，写成可重复的启动脚本（含推荐的 vLLM 参数：
  `--max-model-len`、`--limit-mm-per-prompt image=N`、`--gpu-memory-utilization`）
- [ ] **P1.3** 写一个 10 行的 Python probe：发一张桌面截图 + 一句中文指令，
  打印 raw response，肉眼确认有 `Thought: ... Action: click(point=...)` 结构
  - 验收：probe 能成功返回 Thought+Action

### Phase 2 — Backend 层

- [ ] **P2.1** 新建 `src/autovisiontest/backends/uitars.py`：
  - 构造 COMPUTER_USE prompt（填 `{language}`、`{instruction}`）
  - 支持 action history 注入（多轮 messages）
  - 解析 response 中的 `Thought: ... Action: <fn>(...)` 
  - 把 `<point>x y</point>` 还原成原图绝对像素坐标（考虑 max_pixels 缩放）
  - 返回统一的结构 `UITarsDecision { thought, action_name, action_args, point_xy }`
- [ ] **P2.2** 在 `backends/factory.py` 注册新的 backend 类型（例如 `uitars_local`）
- [ ] **P2.3** 更新 `config/model.yaml` 和 `config/loader.py`：简化为单模型配置
  ```yaml
  agent:
    backend: "uitars_local"
    model: "flin775/UI-TARS-1.5-7B-AWQ"
    endpoint: "http://localhost:8000/v1"
    language: "Chinese"      # UI-TARS thought language
  runtime:
    max_steps: 50
    ...
  ```
- [ ] **P2.4** 写 `scripts/probe_uitars.py` 冒烟脚本，读一张 PNG、一条 GOAL，打印决策
  - 验收：脚本能解析出正确的 action 名和坐标

### Phase 3 — Engine 合并

- [ ] **P3.1** 新建/改写 `engine/agent.py`（代替原 Planner + Actor 的分工）
  - 单次调用 UI-TARS backend 拿到 thought + action + 绝对坐标
  - 返回 `AgentDecision { thought, action, finished, finished_content }`
- [ ] **P3.2** 简化/移除 `engine/actor.py`（grounding 已内含在 agent 里）
- [ ] **P3.3** 改 `engine/step_loop.py`：
  - 去掉单独的 Actor 调用
  - 用新的 `AgentDecision` 驱动
  - `finished` action 等价于原来的 `done=true`，触发 PASS
- [ ] **P3.4** `control/actions.py` 添加 UI-TARS 风格的 action 名（`left_double` /
  `right_single` / `hotkey` / `finished`），保留执行逻辑
- [ ] **P3.5** `control/executor.py` 适配新的参数名（`type.content` 替代 `type.text`、
  `hotkey.key` 字符串 split 替代 `key_combo.keys` list）

### Phase 4 — 提示词 & GOAL 简化

- [ ] **P4.1** 删除 `src/autovisiontest/prompts/planner_system.txt`（UI-TARS 自带模板）
- [ ] **P4.2** 把 `prompts/planner.py` 瘦身成只做：
  - 构造 UI-TARS 用户消息（instruction + history screenshots）
  - 不再构造复杂 JSON schema 指令
- [ ] **P4.3** 改 `run_notepad_test.py` 的 GOAL 为 3-4 句骨架，例如：
  ```
  打开记事本应用。在记事本中输入"今天天气真好"。把文件保存到桌面。关闭记事本。
  ```
  不再写"第一步点搜索按钮、第二步..."这种具体步骤

### Phase 5 — 旧代码清理

- [ ] **P5.1** 删除 `src/autovisiontest/backends/showui.py`
- [ ] **P5.2** 删除 `tests/unit/backends/test_showui.py`
- [ ] **P5.3** `backends/factory.py` 移除 `showui_local` / `vllm_chat`（作为 planner）的分支
- [ ] **P5.4** 清理临时文件：`diag_desktop.png`、`last_run.log`、老 evidence 数据
- [ ] **P5.5** `config/loader.py` 清掉对 `planner` / `actor` 两段 yaml 的解析，改为 `agent`

### Phase 6 — 顺手修的小 bug

- [ ] **P6.1** `engine/terminator.py::_check_no_progress`：比较键加入 `target_desc`（或
  UI-TARS 场景下的 `thought` hash），避免不同目标的连续 click 被误判 NO_PROGRESS

### Phase 7 — 冒烟 & 调优

- [ ] **P7.1** 单 grounding probe：桌面截图 + "点击任务栏搜索按钮"，肉眼确认坐标落在任务栏
- [ ] **P7.2** 端到端 attach 模式 notepad 测试（简短 GOAL），看能否一次跑通
- [ ] **P7.3** 根据失败截图迭代：可能需要调整 prompt 的 `{language}` / 温度 /
  action history 长度

### Phase 8 — 收尾（允许延后）

- [ ] **P8.1** 补 `tests/unit/backends/test_uitars.py`（prompt 构造 + response parse 单测）
- [ ] **P8.2** 更新 `Readme.md` 架构图 & 模型说明
- [ ] **P8.3** 更新 `docs/product_document.md` 相关章节
- [ ] **P8.4** 更新 `docs/wsl2_vllm_deploy.md` 为单服务部署文档

---

## 5. 验收目标

完成全部 Phase 1–7 后：

1. **能跑通**：attach 模式下，GOAL 仅写"打开记事本，输入..., 保存，关闭"四句话，
   端到端完成并被判 PASS
2. **步数合理**：从当前桌面（Cursor IDE 占屏）完成整个任务 ≤ 20 步
3. **智能体征**：日志里能看到 UI-TARS 的 `Thought:` 反映"观察—思考—行动"链路，
   不是机械念剧本
4. **部署简化**：WSL2 里只有一个 vLLM 进程跑 UI-TARS，显存占用 ≤ 8GB

---

## 6. 风险与未知

| 风险 | 缓解 |
|---|---|
| UI-TARS 输出 `<point>x y</point>` 的坐标系与我们的屏幕像素映射关系待实证 | P1.3 probe 时用一张已知元素位置的截图对拍，校准缩放公式 |
| vLLM 对 UI-TARS AWQ 的 chat template 兼容性 | P0.2 加载时观察是否需要显式传 `--chat-template` |
| 中文语言 `{language}=Chinese` 对精度是否有影响 | 默认先用 Chinese；如效果差，回退 English thought + 中文 instruction |
| UI-TARS 对多轮 screenshot history 的 token 消耗 | 初版只传最近 3 张历史图；超限再优化 |
| 旧代码删除后如果要回退？| 依赖 git；如需正式 A/B，再拉分支处理，默认不在同一棵主干里共存 |

---

## 7. 参考

- UI-TARS paper: arXiv 2501.12326
- UI-TARS repo: https://github.com/bytedance/UI-TARS
- AWQ 权重: https://huggingface.co/flin775/UI-TARS-1.5-7B-AWQ
- 官方 prompt: `codes/ui_tars/prompt.py::COMPUTER_USE_DOUBAO`
- ScreenSpot-Pro benchmark: UI-TARS-1.5-7B 49.6%（vs ShowUI-2B ≈ 0%）
