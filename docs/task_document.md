# AutoVisionTest — 开发任务文档 v2.0

文档日期：2026-04-18
对应产品文档：`docs/product_document.md` v2.1
目标里程碑：MVP（Phase 1）

---

## 0. 本文档的使用方法

### 0.1 面向读者

本文档是为 **AI 编程 Agent（Claude Code / Cursor 等）** 设计的任务分解清单。每个任务的颗粒度控制在"**一次对话可完成**"（约 30 分钟–2 小时人类等价工作量），单任务通常只改 1–3 个文件。

### 0.2 任务字段说明

每个任务采用统一结构：

- **ID**：`T<阶段>.<序号>`
- **依赖**：前置任务 ID 列表（空代表无依赖）
- **范围**：预计改动的文件路径（白名单）
- **交付物**：必须产出的文件，以及关键导出的类/函数签名
- **测试项**：`pytest` 用例清单，或无法自动化测试时的手动验证步骤
- **验收**：二元化 checklist，每条必须明确可判定

### 0.3 任务执行约定

- 任务必须**按依赖顺序**执行；允许并行的任务在阶段小结中列出
- 每个任务完成后**必须通过**该任务的所有验收项才能进入下一任务
- 每个任务的代码变更应形成**独立 commit**，commit message 格式：`T<id>: <任务标题>`
- 任务范围外的文件**不得修改**；若发现必须修改，先更新任务依赖关系再动手
- 所有新增代码必须有对应测试；测试覆盖率目标：核心模块（执行引擎、安全、感知）≥ 80%，其他 ≥ 60%

### 0.4 阶段与里程碑

| 阶段 | 标题 | 任务数 | 里程碑交付 |
|------|------|------|-----------|
| A | 项目骨架 | 5 | 包可安装，CLI 可启动，配置可加载，日志可输出 |
| B | 桌面控制层 | 8 | 能截图、能键鼠、能管理窗口和进程 |
| C | 视觉感知层 | 5 | OCR、SSIM、DPI 归一化、弹窗检测可用 |
| D | 模型后端 | 7 | Claude API + vLLM ShowUI 两种后端调通 |
| E | 安全防护 | 4 | 黑名单拦截 + VLM 二次确认 + 熔断 |
| F | 执行引擎 | 9 | 单步循环、终止检测、探索/回归两种模式 |
| G | 用例与调度 | 6 | 指纹、固化、失效判定、会话管理 |
| H | 报告与证据 | 4 | 结构化报告、截图投递、清理 |
| I | 接入层 | 3 | CLI / HTTP / MCP 三种接入 |
| J | MVP 验收 | 5 | 记事本 demo 闭环 + 稳定性 + grounding 基准 |

**总计：56 个任务。**

---

## 1. 项目基础信息

### 1.1 目录约定

```
AuteTest/
├── docs/                       # 产品与任务文档（现存）
├── pyproject.toml              # 包定义
├── src/autovisiontest/         # 源码根（可 pip install -e .）
│   ├── __init__.py
│   ├── cli.py                  # CLI 入口
│   ├── config/                 # 配置加载
│   ├── logging_setup.py        # structlog 初始化
│   ├── exceptions.py           # 自定义异常
│   ├── control/                # 桌面控制层 (§7)
│   ├── perception/             # 视觉感知层 (§6)
│   ├── backends/               # 模型后端抽象 (§8)
│   ├── safety/                 # 安全防护 (§9)
│   ├── engine/                 # 执行引擎 (§5)
│   ├── cases/                  # 用例体系 (§4)
│   ├── scheduler/              # 会话调度
│   ├── report/                 # 报告生成 (§11)
│   ├── interfaces/             # 接入层 (§10)
│   │   ├── cli_commands.py
│   │   ├── http_server.py
│   │   └── mcp_server.py
│   └── prompts/                # Planner/Reflector prompt 模板
├── tests/                      # 对应 src 结构
│   ├── unit/
│   ├── integration/
│   └── fixtures/               # 截图、mock 数据
├── config/                     # 运行时配置
│   └── model.yaml
├── data/                       # 运行时数据（gitignore）
│   ├── sessions/
│   ├── recordings/
│   └── evidence/
└── scripts/                    # 辅助脚本（模型启动、基准测试等）
```

### 1.2 依赖清单（pyproject.toml 预置）

| 类别 | 包 | 版本下限 |
|------|---|---------|
| 核心 | pydantic, pydantic-settings, pyyaml, structlog, click | 最新稳定 |
| 桌面控制 | pyautogui, pywin32, pygetwindow, pyperclip, mss | 最新稳定 |
| 视觉 | opencv-python, pillow, paddleocr | ≥ 2.7 (paddle) |
| 模型 | anthropic, openai, dashscope, httpx | 最新稳定 |
| HTTP | fastapi, uvicorn | 最新稳定 |
| MCP | mcp | 最新稳定 |
| 测试 | pytest, pytest-asyncio, pytest-cov, pytest-mock | 最新稳定 |

vLLM 作为**独立进程运行**，不作为 Python 依赖直接装入主环境（避免版本冲突）。

---

# 阶段 A — 项目骨架

## T A.1 项目初始化

**依赖**：—

**范围**：
- `pyproject.toml`（新建）
- `src/autovisiontest/__init__.py`（新建）
- `.gitignore`（新建或更新）
- `README.md`（更新简介 + 安装命令）

**交付物**：
- `pyproject.toml`：使用 `hatchling` 或 `setuptools` 作为构建后端，定义：
  - `name = "autovisiontest"`
  - `requires-python = ">=3.11"`
  - 完整依赖清单（见 §1.2）
  - `[project.scripts]` 注册 `autovisiontest = "autovisiontest.cli:main"`
- `src/autovisiontest/__init__.py`：导出 `__version__ = "0.1.0"`
- `.gitignore`：包含 `data/`、`__pycache__`、`*.egg-info`、`.venv`、`.pytest_cache`

**测试项**：
- 在干净 venv 下 `pip install -e .[dev]` 能成功安装
- `python -c "import autovisiontest; print(autovisiontest.__version__)"` 输出 `0.1.0`
- `autovisiontest --version` 能执行（即使只是打印版本号的桩实现）

**验收**：
- [ ] `pip install -e .` 成功
- [ ] `autovisiontest --version` 输出 `0.1.0`
- [ ] `.gitignore` 已生效（`data/` 不会被 git add）

---

## T A.2 配置系统

**依赖**：T A.1

**范围**：
- `src/autovisiontest/config/__init__.py`（新建）
- `src/autovisiontest/config/schema.py`（新建）
- `src/autovisiontest/config/loader.py`（新建）
- `config/model.yaml`（新建，示例配置）
- `tests/unit/config/test_loader.py`（新建）

**交付物**：
- `config/schema.py`：Pydantic 模型
  - `PlannerConfig`：`backend`, `model`, `api_key_env`, `max_tokens`, `temperature`, `endpoint?`
  - `ActorConfig`：`backend`, `model`, `endpoint`, `confidence_threshold`
  - `RuntimeConfig`：`max_steps: int = 30`, `max_session_duration_s: int = 600`, `step_wait_ms: int = 500`, `data_dir: Path`
  - `AppConfig`：顶层模型，组合以上
- `config/loader.py`：
  - `def load_config(path: Path | None = None) -> AppConfig`
  - 优先级：显式路径 > 环境变量 `AUTOVT_CONFIG` > `./config/model.yaml` > 包内默认
  - 支持环境变量覆盖：`AUTOVT_DATA_DIR`, `AUTOVT_PLANNER_BACKEND` 等
- `config/model.yaml` 示例内容对齐产品文档 §8.4

**测试项**：
- `test_load_default_config`：给一个最小 yaml，验证各字段默认值
- `test_env_var_override`：`AUTOVT_DATA_DIR=/tmp/foo` 覆盖成功
- `test_invalid_backend_rejected`：`backend: "nonsense"` 抛 `ValidationError`
- `test_missing_api_key_env_warning`：`backend=claude_api` 但 `api_key_env` 对应的环境变量不存在时，返回警告（不抛异常，延迟到调用时检查）

**验收**：
- [ ] `pytest tests/unit/config/` 全通过
- [ ] `autovisiontest --config config/model.yaml validate` 能打印解析后的配置（可先桩实现 validate 子命令）

---

## T A.3 日志系统

**依赖**：T A.2

**范围**：
- `src/autovisiontest/logging_setup.py`（新建）
- `tests/unit/test_logging_setup.py`（新建）

**交付物**：
- `logging_setup.py`：
  - `def setup_logging(level: str = "INFO", json_output: bool = False, log_file: Path | None = None) -> None`
  - 使用 structlog，默认输出到 stderr
  - json_output=True 时输出单行 JSON（用于生产/CI）
  - 始终附加字段：`session_id`（可通过 contextvars 绑定）、`step_idx`、`module`
  - 支持日志文件轮转（10MB，保留 5 个）

**测试项**：
- `test_setup_logging_console`：捕获 stderr，验证输出格式包含预期字段
- `test_setup_logging_json`：json_output=True 时每行可被 `json.loads`
- `test_context_binding`：用 `structlog.contextvars.bind_contextvars(session_id="x")` 后，日志含 `session_id=x`

**验收**：
- [ ] `pytest tests/unit/test_logging_setup.py` 全通过
- [ ] `autovisiontest --log-level DEBUG --version` 在 stderr 看到 DEBUG 日志

---

## T A.4 异常体系

**依赖**：T A.1

**范围**：
- `src/autovisiontest/exceptions.py`（新建）
- `tests/unit/test_exceptions.py`（新建）

**交付物**：
- `exceptions.py` 定义以下异常层级：
  ```
  AutoVTError (base)
  ├── ConfigError
  ├── ControlError
  │   ├── AppLaunchError
  │   ├── AppCrashedError
  │   └── ActionExecutionError
  ├── PerceptionError
  │   ├── ScreenshotError
  │   └── OCRError
  ├── BackendError
  │   ├── ChatBackendError
  │   └── GroundingBackendError
  ├── SafetyError
  │   └── UnsafeActionError
  ├── SessionError
  │   ├── SessionNotFoundError
  │   └── SessionTimeoutError
  └── CaseError
      └── RecordingInvalidError
  ```
- 每个异常类必须可序列化为 `{"type": "...", "message": "...", "context": {...}}`（`to_dict` 方法）

**测试项**：
- `test_exception_hierarchy`：验证继承关系
- `test_to_dict`：每个异常调用 `to_dict()` 返回合法字典

**验收**：
- [ ] `pytest tests/unit/test_exceptions.py` 全通过
- [ ] 所有异常类均继承自 `AutoVTError`

---

## T A.5 CLI 骨架

**依赖**：T A.2, T A.3

**范围**：
- `src/autovisiontest/cli.py`（新建）
- `tests/unit/test_cli.py`（新建）

**交付物**：
- `cli.py`：使用 `click`，定义以下子命令（**均为桩实现**，打印"not implemented"即可，稍后在对应任务填充）：
  - `autovisiontest run --goal <str> --app <path> [--app-args <str>] [--timeout <ms>]`
  - `autovisiontest run --case <path>`
  - `autovisiontest status <session_id>`
  - `autovisiontest report <session_id> [--format json|html]`
  - `autovisiontest list-recordings`
  - `autovisiontest validate`（打印配置）
- 全局选项：`--config`, `--log-level`, `--version`
- `def main() -> int`：返回 exit code

**测试项**：
- 使用 `click.testing.CliRunner`：
  - `test_version`
  - `test_help_lists_all_subcommands`
  - `test_run_requires_goal_or_case`（`run` 不带参数应报错）
  - `test_validate_prints_config`

**验收**：
- [ ] `pytest tests/unit/test_cli.py` 全通过
- [ ] `autovisiontest --help` 列出所有子命令
- [ ] `autovisiontest run` 不带参数退出码非 0

---

## 阶段 A 里程碑验收

- [ ] 所有 5 个任务的 checklist 全部打钩
- [ ] `pytest tests/unit/` 全通过
- [ ] 在 Windows 10 和 11 各一台机器上完成 `pip install -e .` 冒烟测试
- [ ] 形成一个可工作的空骨架包，可被下游任务依赖

---

# 阶段 B — 桌面控制层

## T B.1 DPI 归一化初始化

**依赖**：T A.1

**范围**：
- `src/autovisiontest/control/dpi.py`（新建）
- `tests/unit/control/test_dpi.py`（新建）

**交付物**：
- `control/dpi.py`：
  - `def enable_dpi_awareness() -> None`：调用 `ctypes.windll.shcore.SetProcessDpiAwareness(2)`，失败降级到 `user32.SetProcessDPIAware`，再失败记录 warning
  - `def get_primary_screen_size() -> tuple[int, int]`：返回物理像素下的主屏宽高
  - `def get_dpi_scale() -> float`：返回主屏缩放因子（1.0 / 1.25 / 1.5 等）
- 模块级全局：`_DPI_AWARENESS_ENABLED = False`，确保 `enable_dpi_awareness` 幂等

**测试项**：
- `test_enable_dpi_awareness_idempotent`：连续调用两次不抛
- `test_get_primary_screen_size_returns_tuple`：返回值是 `(int, int)` 且均 > 0
- 手动验证：在 125% 缩放的显示器上，`get_dpi_scale()` 返回 1.25

**验收**：
- [ ] `pytest tests/unit/control/test_dpi.py` 全通过
- [ ] 手动验证通过（截图附于 commit）

---

## T B.2 截图采集

**依赖**：T B.1

**范围**：
- `src/autovisiontest/control/screenshot.py`（新建）
- `tests/unit/control/test_screenshot.py`（新建）

**交付物**：
- `control/screenshot.py`：
  - `def capture_primary_screen() -> bytes`：返回 PNG 字节
  - `def capture_region(x: int, y: int, w: int, h: int) -> bytes`
  - `def capture_to_ndarray() -> np.ndarray`：BGR 格式（便于 OpenCV 使用）
  - 内部使用 `mss`，模块级 `mss.mss()` 实例（复用节省开销，注意线程安全用 threading.Lock）
- 所有接口在调用前自动 `enable_dpi_awareness()`

**测试项**：
- `test_capture_primary_screen_returns_png`：返回字节以 PNG magic `\x89PNG` 开头
- `test_capture_region_size_matches`：截 100x100 区域，解码后尺寸为 100x100
- `test_capture_to_ndarray_shape`：返回 shape 形如 `(H, W, 3)`
- 性能测试（非硬性）：连续截图 100 次，平均 < 50ms

**验收**：
- [ ] `pytest tests/unit/control/test_screenshot.py` 全通过
- [ ] 性能基准记录于 `tests/benchmarks/screenshot.md`

---

## T B.3 鼠标控制原语

**依赖**：T B.1

**范围**：
- `src/autovisiontest/control/mouse.py`（新建）
- `tests/unit/control/test_mouse.py`（新建）

**交付物**：
- `control/mouse.py`：
  - `def move(x: int, y: int, duration_ms: int = 100) -> None`
  - `def click(x: int, y: int, button: Literal["left", "right", "middle"] = "left") -> None`
  - `def double_click(x: int, y: int) -> None`
  - `def right_click(x: int, y: int) -> None`
  - `def drag(from_xy: tuple[int, int], to_xy: tuple[int, int], duration_ms: int = 300) -> None`
  - `def scroll(x: int, y: int, dy: int) -> None`
- 所有坐标为物理像素，内部委托 `pyautogui`
- 调用前 `enable_dpi_awareness()`
- `pyautogui.FAILSAFE = True` 保留，允许鼠标扔到屏幕角落紧急停止

**测试项**（全部使用 `pytest-mock` mock pyautogui，不触发真实鼠标）：
- `test_click_calls_pyautogui_with_args`
- `test_double_click_uses_doubleclick`
- `test_drag_sequence`：验证 moveTo → mouseDown → moveTo → mouseUp
- `test_scroll_sign`：dy > 0 向上滚

**验收**：
- [ ] `pytest tests/unit/control/test_mouse.py` 全通过
- [ ] 手动验证：写一个 `scripts/smoke_mouse.py`，调用 `click(100, 100)` 能看到记事本菜单弹出

---

## T B.4 键盘控制原语

**依赖**：T B.1

**范围**：
- `src/autovisiontest/control/keyboard.py`（新建）
- `tests/unit/control/test_keyboard.py`（新建）

**交付物**：
- `control/keyboard.py`：
  - `def type_text(text: str, interval_ms: int = 20) -> None`：自动识别含非 ASCII 时切换到剪贴板路径（`pyperclip.copy` + Ctrl+V）
  - `def key_combo(*keys: str) -> None`：接受如 `"ctrl", "s"`，调 `pyautogui.hotkey`
  - `def press(key: str) -> None`：单键
- 非 ASCII 切换阈值：若文本含任一码点 > 127，整段走剪贴板

**测试项**：
- `test_type_ascii_uses_typewrite`：mock 验证 ASCII 文本走 `pyautogui.typewrite`
- `test_type_chinese_uses_clipboard`：mock 验证 `"你好"` 走 `pyperclip.copy` + `hotkey("ctrl", "v")`
- `test_key_combo_ctrl_s`
- `test_press_enter`

**验收**：
- [ ] `pytest tests/unit/control/test_keyboard.py` 全通过
- [ ] 手动验证：`scripts/smoke_keyboard.py` 在打开的记事本中输入 `"hello 中文"` 成功

---

## T B.5 窗口管理

**依赖**：T B.1

**范围**：
- `src/autovisiontest/control/window.py`（新建）
- `tests/unit/control/test_window.py`（新建）

**交付物**：
- `control/window.py`：
  - `@dataclass class WindowInfo: title: str, pid: int, handle: int, rect: tuple[int, int, int, int]`
  - `def list_windows() -> list[WindowInfo]`
  - `def find_window_by_title(pattern: str) -> WindowInfo | None`：支持子串匹配
  - `def find_window_by_pid(pid: int) -> WindowInfo | None`
  - `def focus(win: WindowInfo) -> bool`
  - `def wait_window(pattern: str, timeout_s: float = 30.0, poll_interval_s: float = 0.2) -> WindowInfo`：轮询直到出现或抛 `AppLaunchError`
- 使用 `pygetwindow` + `pywin32`（fallback）

**测试项**：
- `test_list_windows_returns_items`：调用后列表非空（桌面一般至少有几个窗口）
- `test_find_window_by_title_notepad`（集成测试，需要先手动开记事本）
- `test_wait_window_timeout`：等不存在的标题，`AppLaunchError` 抛出且耗时 ≈ timeout

**验收**：
- [ ] `pytest tests/unit/control/test_window.py` 全通过
- [ ] 集成测试：启动记事本 → `wait_window("记事本")` 成功返回

---

## T B.6 进程管理

**依赖**：T B.5

**范围**：
- `src/autovisiontest/control/process.py`（新建）
- `tests/unit/control/test_process.py`（新建）

**交付物**：
- `control/process.py`：
  - `@dataclass class AppHandle: pid: int, popen: subprocess.Popen, exe_name: str`
  - `def kill_processes_by_exe(exe_name: str) -> int`：调 `taskkill /IM <exe> /F`，忽略"进程不存在"，返回被 kill 的数量
  - `def launch_app(path: str, args: list[str] | None = None) -> AppHandle`
  - `def is_alive(handle: AppHandle) -> bool`：`popen.poll() is None and win32 检查窗口句柄`
  - `def close_app(handle: AppHandle, timeout_s: float = 5.0) -> None`：先发 WM_CLOSE，超时后强 kill

**测试项**：
- `test_kill_nonexistent_returns_zero`
- `test_launch_notepad`（集成）：launch → is_alive → close_app → not is_alive
- `test_is_alive_false_after_process_exits`

**验收**：
- [ ] `pytest tests/unit/control/test_process.py` 全通过
- [ ] 集成测试：启动 + 关闭记事本完整流程 OK

---

## T B.7 动作执行器

**依赖**：T B.3, T B.4

**范围**：
- `src/autovisiontest/control/executor.py`（新建）
- `src/autovisiontest/control/actions.py`（新建，定义 Action 模型）
- `tests/unit/control/test_executor.py`（新建）

**交付物**：
- `control/actions.py`：Pydantic 模型
  - `Action`：`type: Literal["click", "double_click", "right_click", "drag", "scroll", "type", "key_combo", "wait"]`, `params: dict`
  - `class ActionResult: success: bool, error: str | None, duration_ms: int`
- `control/executor.py`：
  - `class ActionExecutor`
  - `def execute(action: Action, coords: tuple[int, int] | None = None) -> ActionResult`
  - 内部按 `action.type` 分派到 `mouse`/`keyboard` 模块；NEED_TARGET 类必须传 coords
  - 失败时抛 `ActionExecutionError`，包含 action 和原始异常

**测试项**：
- `test_execute_click`（mock mouse.click，验证调用）
- `test_execute_type_without_coords_ok`
- `test_execute_click_without_coords_raises`
- `test_execute_unknown_action_type_raises`

**验收**：
- [ ] `pytest tests/unit/control/test_executor.py` 全通过

---

## T B.8 控制层集成冒烟

**依赖**：T B.2, T B.6, T B.7

**范围**：
- `tests/integration/test_control_smoke.py`（新建）

**交付物**：
- 一个端到端集成测试：
  1. `kill_processes_by_exe("notepad.exe")`
  2. `launch_app("notepad.exe")`
  3. `wait_window("记事本")`
  4. 截图 1 次
  5. 通过 executor 执行 `type_text("hello")`
  6. 再次截图
  7. OCR 目前还没实现，这里简单做 SSIM 对比两张截图应该不同
  8. `close_app(handle)`

**测试项**：
- `test_control_end_to_end_notepad_smoke`：全流程无异常

**验收**：
- [ ] 测试通过（可能需要在非无头环境运行，标记 `@pytest.mark.desktop`）
- [ ] 测试运行时间 < 15 秒

---

## 阶段 B 里程碑验收

- [ ] B.1 – B.8 任务全通过
- [ ] 控制层集成冒烟测试通过
- [ ] `scripts/demo_control.py` 能端到端：启动记事本 → 输入"hello"→ 保存对话框出现 → 关闭（不要求实际保存成功）

---

# 阶段 C — 视觉感知层

## T C.1 OCR 引擎封装

**依赖**：T A.4

**范围**：
- `src/autovisiontest/perception/ocr.py`（新建）
- `src/autovisiontest/perception/types.py`（新建，共享数据类）
- `tests/unit/perception/test_ocr.py`（新建）

**交付物**：
- `perception/types.py`：
  - `@dataclass class BoundingBox: x: int, y: int, w: int, h: int`
  - `@dataclass class OCRItem: text: str, bbox: BoundingBox, confidence: float`
  - `@dataclass class OCRResult: items: list[OCRItem], image_size: tuple[int, int]`
  - `def center(bbox: BoundingBox) -> tuple[int, int]`
  - `def find_text(result: OCRResult, query: str, fuzzy: bool = True) -> list[OCRItem]`
- `perception/ocr.py`：
  - `class OCREngine`：单例模式
  - `def __init__(lang: str = "ch", use_gpu: bool = False)`：PaddleOCR 首次调用加载模型（lazy）
  - `def recognize(image: bytes | np.ndarray) -> OCRResult`
  - 失败抛 `OCRError`

**测试项**：
- `test_ocr_recognize_simple_image`：用 fixture 图片（含"hello world"），验证能识别
- `test_find_text_exact_match`
- `test_find_text_fuzzy`：查 "helo"（拼写错）能匹配 "hello"（编辑距离 <= 1）
- `test_ocr_empty_image`：纯白图返回空列表

**fixture 准备**：
- `tests/fixtures/ocr/hello_world.png`（白底黑字 "hello world"）
- `tests/fixtures/ocr/chinese.png`（含"你好世界"）
- `tests/fixtures/ocr/empty.png`（纯白）

**验收**：
- [ ] `pytest tests/unit/perception/test_ocr.py` 全通过
- [ ] 首次调用延迟 < 10 秒（模型加载），后续 < 500ms

---

## T C.2 SSIM 相似度

**依赖**：T A.1

**范围**：
- `src/autovisiontest/perception/similarity.py`（新建）
- `tests/unit/perception/test_similarity.py`（新建）

**交付物**：
- `perception/similarity.py`：
  - `def ssim(img_a: np.ndarray, img_b: np.ndarray) -> float`：返回 [0, 1]
  - 两图尺寸不同时自动 resize 到较小尺寸
  - 支持 PNG bytes 作为输入的重载：`def ssim_bytes(a: bytes, b: bytes) -> float`

**测试项**：
- `test_ssim_identical_is_one`
- `test_ssim_different_sizes_handled`
- `test_ssim_different_images_lt_threshold`：两张完全不同截图 < 0.3

**验收**：
- [ ] `pytest tests/unit/perception/test_similarity.py` 全通过

---

## T C.3 错误弹窗检测

**依赖**：T C.1

**范围**：
- `src/autovisiontest/perception/error_dialog.py`（新建）
- `tests/unit/perception/test_error_dialog.py`（新建）

**交付物**：
- `perception/error_dialog.py`：
  - `ERROR_KEYWORDS` 常量：`["错误", "异常", "失败", "Error", "Exception", "Failed", "Warning", "警告"]`
  - `def detect_error_dialog(ocr: OCRResult) -> tuple[bool, str | None]`：返回 `(hit, matched_keyword)`
  - 判定规则：OCR 文本命中任一关键词 **且** 该文本位于屏幕上半区（y < screen_h / 2）**且** 附近（50px 内）存在"确定/OK/关闭/取消"等按钮文字
  - 阈值可配置化

**测试项**：
- `test_no_dialog_returns_false`
- `test_obvious_error_dialog_detected`：fixture 截图（错误弹窗样本）
- `test_keyword_without_button_not_dialog`：文档里仅出现"错误"字样但无按钮，不误判

**fixture 准备**：
- `tests/fixtures/dialogs/error_dialog.png`
- `tests/fixtures/dialogs/normal_document_with_error_word.png`

**验收**：
- [ ] `pytest tests/unit/perception/test_error_dialog.py` 全通过

---

## T C.4 视觉变化检测（卡死判定基础）

**依赖**：T C.2

**范围**：
- `src/autovisiontest/perception/change_detector.py`（新建）
- `tests/unit/perception/test_change_detector.py`（新建）

**交付物**：
- `perception/change_detector.py`：
  - `class ChangeDetector`
  - `def __init__(window_seconds: float = 10.0, static_threshold: float = 0.99)`
  - `def push(screenshot: np.ndarray, t: float | None = None) -> None`：添加一张截图（自动维护环形缓冲，按时间窗口剪枝）
  - `def is_static(now_t: float | None = None) -> bool`：窗口内所有相邻对的 SSIM > threshold
  - `def reset() -> None`

**测试项**：
- `test_single_frame_not_static`：只有一帧时 is_static 返回 False
- `test_identical_frames_over_window_is_static`
- `test_change_breaks_static`
- `test_reset_clears_buffer`

**验收**：
- [ ] `pytest tests/unit/perception/test_change_detector.py` 全通过

---

## T C.5 感知层门面

**依赖**：T C.1, T C.2, T C.3, T C.4

**范围**：
- `src/autovisiontest/perception/facade.py`（新建）
- `tests/unit/perception/test_facade.py`（新建）

**交付物**：
- `perception/facade.py`：
  - `@dataclass class FrameSnapshot: screenshot: np.ndarray, screenshot_png: bytes, ocr: OCRResult, timestamp: float`
  - `class Perception`
  - `def capture_snapshot() -> FrameSnapshot`：截图 + OCR 一次调用，结果缓存本次快照
  - `def detect_error_dialog(snapshot: FrameSnapshot) -> tuple[bool, str | None]`
  - `def ssim_between(a: FrameSnapshot, b: FrameSnapshot) -> float`
- 与执行引擎的唯一交互点

**测试项**：
- `test_capture_snapshot_all_fields_populated`
- `test_snapshot_timestamp_monotonic`

**验收**：
- [ ] `pytest tests/unit/perception/test_facade.py` 全通过

---

## 阶段 C 里程碑验收

- [ ] C.1 – C.5 全通过
- [ ] `scripts/demo_perception.py`：截取当前屏幕，打印 OCR 结果和是否有错误弹窗

---

# 阶段 D — 模型后端

## T D.1 Backend Protocol 定义

**依赖**：T A.4

**范围**：
- `src/autovisiontest/backends/__init__.py`（新建）
- `src/autovisiontest/backends/protocol.py`（新建）
- `src/autovisiontest/backends/types.py`（新建）

**交付物**：
- `backends/types.py`：
  - `@dataclass class Message: role: Literal["system", "user", "assistant"], content: str`
  - `@dataclass class ChatResponse: content: str, raw: dict, usage: dict | None`
  - `@dataclass class GroundingResponse: x: int, y: int, confidence: float, raw: dict`
- `backends/protocol.py`：
  - `class ChatBackend(Protocol)`：`def chat(messages, images=None, response_format="json") -> ChatResponse`
  - `class GroundingBackend(Protocol)`：`def ground(image: bytes, query: str) -> GroundingResponse`

**测试项**：
- `test_protocol_is_runtime_checkable`：装饰器 `@runtime_checkable`，`isinstance` 检查生效

**验收**：
- [ ] `pytest tests/unit/backends/test_protocol.py` 全通过

---

## T D.2 Claude Chat 后端

**依赖**：T D.1, T A.2

**范围**：
- `src/autovisiontest/backends/claude.py`（新建）
- `tests/unit/backends/test_claude.py`（新建）

**交付物**：
- `backends/claude.py`：
  - `class ClaudeChatBackend`（实现 `ChatBackend`）
  - 构造参数：`model: str`, `api_key: str`, `max_tokens: int = 2048`, `temperature: float = 0.2`
  - `chat()` 方法调用 `anthropic.Anthropic().messages.create()`
  - 图像输入按 Anthropic 格式拼装（base64 + media_type）
  - `response_format="json"` 时在 system prompt 追加 "Respond with a single JSON object. No markdown fences."
  - 错误分类：4xx → `ChatBackendError(retryable=False)`，5xx/网络 → `retryable=True`
  - 带指数退避重试（最多 3 次，1s/2s/4s）

**测试项**（mock `anthropic.Anthropic`）：
- `test_chat_basic`：验证请求构造正确
- `test_chat_with_image`：验证 image content 构造
- `test_chat_retries_on_5xx`
- `test_chat_no_retry_on_4xx`

**验收**：
- [ ] `pytest tests/unit/backends/test_claude.py` 全通过
- [ ] 手动验证：`scripts/smoke_claude.py` 发一句 "say hi" 能收到回复（需要 `ANTHROPIC_API_KEY`）

---

## T D.3 OpenAI Chat 后端

**依赖**：T D.1, T A.2

**范围**：
- `src/autovisiontest/backends/openai_backend.py`（新建）
- `tests/unit/backends/test_openai.py`（新建）

**交付物**：
- `ClassOpenAIChatBackend`（实现 `ChatBackend`）
- 支持 GPT-4o / GPT-4o-mini，图像按 OpenAI 格式
- 其他行为与 Claude 后端对齐

**测试项**：同 T D.2 的镜像

**验收**：
- [ ] 单元测试全通过
- [ ] 手动验证：`scripts/smoke_openai.py`（需要 `OPENAI_API_KEY`）

---

## T D.4 vLLM Chat 后端

**依赖**：T D.1, T A.2

**范围**：
- `src/autovisiontest/backends/vllm_chat.py`（新建）
- `tests/unit/backends/test_vllm_chat.py`（新建）
- `scripts/start_vllm_planner.sh`（新建，参考脚本）

**交付物**：
- `VLLMChatBackend`：通过 HTTP 调用 vLLM OpenAI 兼容接口
- 构造参数：`model: str`, `endpoint: str`（默认 `http://localhost:8000/v1`）, `max_tokens`, `temperature`
- 底层用 `httpx.Client`（同步，带超时 60s）
- `scripts/start_vllm_planner.sh`：启动命令示例：
  ```
  python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-VL-7B-Instruct-AWQ \
    --port 8000 --max-model-len 8192
  ```

**测试项**：
- mock `httpx.Client`，验证请求体结构
- 集成测试（标记 `@pytest.mark.vllm`）：跳过除非 `VLLM_PLANNER_URL` 环境变量设置

**验收**：
- [ ] 单元测试全通过
- [ ] 集成测试在有 vLLM 环境的机器上通过

---

## T D.5 ShowUI Grounding 后端

**依赖**：T D.1, T A.2

**范围**：
- `src/autovisiontest/backends/showui.py`（新建）
- `tests/unit/backends/test_showui.py`（新建）
- `scripts/start_vllm_actor.sh`（新建）

**交付物**：
- `ShowUIGroundingBackend`（实现 `GroundingBackend`）
- 调用本地 vLLM 加载的 ShowUI-2B
- `ground(image, query)`：构造 ShowUI 专用 prompt（参考论文格式），解析输出坐标
- 坐标解析：ShowUI 输出相对坐标（0-1），转换为绝对像素
- confidence：若模型输出包含 bbox/logprob 则使用，否则简化为 1.0 - (重复查询 N 次坐标方差 / diagonal)。MVP 先用固定 0.8（带 TODO 注释），待 prompt engineering 阶段完善

**测试项**：
- mock vLLM，验证 prompt 构造 + 坐标解析
- `test_ground_parses_relative_coords`
- `test_ground_out_of_bounds_clamped`

**验收**：
- [ ] 单元测试全通过
- [ ] 集成测试：`ground` 调用 fixture 图片的"保存按钮"能返回坐标

---

## T D.6 后端工厂

**依赖**：T D.2, T D.3, T D.4, T D.5

**范围**：
- `src/autovisiontest/backends/factory.py`（新建）
- `tests/unit/backends/test_factory.py`（新建）

**交付物**：
- `backends/factory.py`：
  - `def create_chat_backend(config: PlannerConfig) -> ChatBackend`
  - `def create_grounding_backend(config: ActorConfig) -> GroundingBackend`
  - 按 `config.backend` 字段分派；未知后端抛 `ConfigError`

**测试项**：
- `test_create_claude_backend`
- `test_create_openai_backend`
- `test_unknown_backend_raises`

**验收**：
- [ ] `pytest tests/unit/backends/test_factory.py` 全通过

---

## T D.7 后端集成冒烟

**依赖**：T D.6

**范围**：
- `tests/integration/test_backends_smoke.py`（新建）
- `scripts/benchmark_backends.py`（新建）

**交付物**：
- 一个跳过默认、显式开启的集成测试：端到端调一次 Claude + 一次 ShowUI，校验返回结构
- 基准脚本打印延迟

**验收**：
- [ ] 在至少一台配置齐全（有 API key + vLLM 启动）的机器上集成测试通过
- [ ] 基准数据记录于 `tests/benchmarks/backends.md`

---

## 阶段 D 里程碑验收

- [ ] D.1 – D.7 全通过
- [ ] Claude + ShowUI 两条链路在集成测试中调通

---

# 阶段 E — 安全防护

## T E.1 黑名单匹配器

**依赖**：T C.1

**范围**：
- `src/autovisiontest/safety/blacklist.py`（新建）
- `src/autovisiontest/safety/keywords.py`（新建）
- `tests/unit/safety/test_blacklist.py`（新建）

**交付物**：
- `safety/keywords.py`：
  - `CLICK_KEYWORDS = ["删除", "永久删除", "清空", "清除", "重置", "格式化", "卸载", "抹掉", "擦除", "恢复出厂", "Delete", "Remove", "Erase", "Format", "Uninstall", "Reset", "Wipe", "Factory"]`
  - `KEY_COMBO_BLACKLIST = [("alt", "f4"), ("ctrl", "shift", "del"), ("win", "l"), ("win", "r"), ("win", "e")]`
  - `TYPE_CONTENT_PATTERNS = [r"\bdel\s+/[sq]", r"\bformat\s+[a-z]:", r"\brm\s+-rf", r"\brmdir\s+/s"]`
- `safety/blacklist.py`：
  - `def click_hits_blacklist(ocr_texts_near_target: list[str]) -> tuple[bool, str | None]`
  - `def type_hits_blacklist(text: str) -> tuple[bool, str | None]`
  - `def key_combo_hits_blacklist(keys: tuple[str, ...]) -> tuple[bool, str | None]`

**测试项**：
- `test_click_delete_button_hit`
- `test_click_safe_button_miss`
- `test_type_rm_rf_hit`
- `test_type_normal_text_miss`
- `test_alt_f4_hit`

**验收**：
- [ ] `pytest tests/unit/safety/test_blacklist.py` 全通过

---

## T E.2 目标附近 OCR 文字抓取

**依赖**：T C.1

**范围**：
- `src/autovisiontest/safety/nearby_text.py`（新建）
- `tests/unit/safety/test_nearby_text.py`（新建）

**交付物**：
- `def find_nearby_texts(ocr: OCRResult, x: int, y: int, radius_px: int = 30) -> list[str]`：返回中心点距 (x, y) 在 radius 内的 OCR 文本

**测试项**：
- `test_nearby_within_radius_returned`
- `test_nearby_outside_not_returned`
- `test_empty_ocr_returns_empty_list`

**验收**：
- [ ] 单元测试全通过

---

## T E.3 VLM 二次确认

**依赖**：T E.1, T D.6

**范围**：
- `src/autovisiontest/safety/second_check.py`（新建）
- `tests/unit/safety/test_second_check.py`（新建）

**交付物**：
- `class SecondCheck`
- 构造参数：`chat_backend: ChatBackend`, `max_overrides_per_session: int = 3`
- `def confirm(action: Action, hit_reason: str, goal: str, session_ctx: dict) -> Literal["safe", "unsafe"]`
- 超过 `max_overrides_per_session` 次放行后，同一会话所有后续命中一律返回 `"unsafe"`（不再问 VLM）
- 每次调用无论结果都记录到 `session_ctx["safety_overrides"]`

**测试项**：
- `test_safe_response_parsed`
- `test_unsafe_response_parsed`
- `test_exceeds_limit_auto_unsafe`
- `test_malformed_response_defaults_unsafe`

**验收**：
- [ ] 单元测试全通过

---

## T E.4 SafetyGuard 总入口

**依赖**：T E.1, T E.2, T E.3

**范围**：
- `src/autovisiontest/safety/guard.py`（新建）
- `tests/unit/safety/test_guard.py`（新建）

**交付物**：
- `class SafetyGuard`
- 构造参数：`second_check: SecondCheck`, `max_session_actions: int = 30`, `max_session_duration_s: int = 600`
- `def check(action: Action, coords: tuple[int, int] | None, ocr: OCRResult, goal: str, session_ctx: dict) -> SafetyVerdict`
  - `SafetyVerdict`: `Literal["pass", "blocked", "timeout"]` + `reason: str`
- 检查顺序：
  1. 动作数超限 → blocked: "MAX_ACTIONS"
  2. 时长超限 → blocked: "MAX_DURATION"
  3. 动作类型命中黑名单 → SecondCheck → blocked 或 pass
  4. 默认 pass

**测试项**：
- `test_within_limits_passes`
- `test_max_actions_blocks`
- `test_click_dangerous_then_unsafe_blocks`
- `test_click_dangerous_then_safe_passes`

**验收**：
- [ ] 单元测试全通过

---

## 阶段 E 里程碑验收

- [ ] E.1 – E.4 全通过
- [ ] `SafetyGuard` 可被后续执行引擎直接调用

---

# 阶段 F — 执行引擎

## T F.1 核心数据模型

**依赖**：T A.4, T B.7

**范围**：
- `src/autovisiontest/engine/models.py`（新建）
- `tests/unit/engine/test_models.py`（新建）

**交付物**：
- Pydantic 模型：
  - `StepRecord`：`idx, timestamp, planner_intent, actor_target_desc, action, grounding_confidence, before_screenshot_path, after_screenshot_path, reflection`
  - `Assertion`：`type, params, result, detail`
  - `TerminationReason`：枚举 `CRASH/UNSAFE/PASS/ERROR_DIALOG/MAX_STEPS/STUCK/NO_PROGRESS/USER/TARGET_NOT_FOUND/ASSERTION_FAILED`
  - `SessionContext`：持有 session_id、goal、mode、history、steps、assertions、safety_overrides、bug_hints
- 所有时间字段 UTC ISO 8601

**测试项**：
- `test_models_serialize_roundtrip`
- `test_termination_reason_enum`

**验收**：
- [ ] 单元测试全通过

---

## T F.2 Planner Prompt 模板

**依赖**：T F.1

**范围**：
- `src/autovisiontest/prompts/planner.py`（新建）
- `src/autovisiontest/prompts/planner_system.txt`（新建）
- `tests/unit/prompts/test_planner.py`（新建）

**交付物**：
- `prompts/planner_system.txt`：系统提示，必须包含：
  - 角色定义
  - 可用动作类型（9 种）及哪些需要 target_desc
  - 响应 JSON schema 定义
  - "若上一步失败或卡住，给出 bug_hints；信心 < 0.4 时宁缺毋滥"
- `prompts/planner.py`：
  - `def build_planner_messages(goal: str, history: list[StepRecord], last_reflection: str | None, ocr_summary: str) -> list[Message]`
  - `def parse_planner_response(raw: str) -> PlannerDecision`
  - `PlannerDecision`：`reflection, done, bug_hints, next_intent, target_desc, action`
- 解析容错：剥 markdown fence、允许尾随文本、抛 `ChatBackendError` 如完全无法 JSON

**测试项**：
- `test_build_messages_includes_goal`
- `test_parse_valid_response`
- `test_parse_with_markdown_fence`
- `test_parse_invalid_raises`

**验收**：
- [ ] 单元测试全通过
- [ ] `prompts/planner_system.txt` 经人工 review（commit message 标注 "reviewed"）

---

## T F.3 Planner 调用封装

**依赖**：T D.1, T F.2

**范围**：
- `src/autovisiontest/engine/planner.py`（新建）
- `tests/unit/engine/test_planner.py`（新建）

**交付物**：
- `class Planner`
- 构造参数：`chat_backend: ChatBackend`
- `def decide(session: SessionContext, snapshot: FrameSnapshot) -> PlannerDecision`
  - 内部：构造 messages → 调 chat → 解析响应 → 返回
  - history 超过 N 步（可配置，默认 10）时截断，保留最早 2 步 + 最近 8 步
- `def summarize_on_terminate(session: SessionContext, reason: TerminationReason) -> list[BugHint]`：终止时的总结调用

**测试项**：
- `test_decide_happy_path`（mock backend）
- `test_decide_history_truncation`

**验收**：
- [ ] 单元测试全通过

---

## T F.4 Actor 调用与 fallback 链

**依赖**：T D.5, T C.1

**范围**：
- `src/autovisiontest/engine/actor.py`（新建）
- `tests/unit/engine/test_actor.py`（新建)

**交付物**：
- `class Actor`
- 构造参数：`grounding_backend: GroundingBackend`, `confidence_threshold: float = 0.6`, `max_planner_retries: int = 2`
- `def locate(snapshot: FrameSnapshot, target_desc: str, on_retry: Callable | None = None) -> LocateResult`
  - 1. 调 grounding → 若 confidence ≥ threshold 返回
  - 2. OCR fallback：如 `target_desc` 含引号字符串，OCR 查找中心点
  - 3. 若两者都失败，调 `on_retry`（由 engine 提供，让 Planner 重试）最多 `max_planner_retries` 次
  - 4. 仍失败返回 `LocateResult(success=False, ...)`
- `LocateResult`：`success: bool, x: int | None, y: int | None, source: "grounding"|"ocr"|"retry", confidence: float`

**测试项**：
- `test_locate_grounding_success`
- `test_locate_grounding_low_conf_ocr_fallback_success`
- `test_locate_all_methods_fail`
- `test_locate_ocr_fallback_needs_quoted_text`

**验收**：
- [ ] 单元测试全通过

---

## T F.5 断言器

**依赖**：T C.1, T F.1

**范围**：
- `src/autovisiontest/engine/assertions.py`（新建）
- `tests/unit/engine/test_assertions.py`（新建）

**交付物**：
- `engine/assertions.py`：每种断言一个函数
  - `def assert_ocr_contains(ocr: OCRResult, text: str) -> AssertionResult`
  - `def assert_no_error_dialog(ocr: OCRResult) -> AssertionResult`
  - `def assert_file_exists(path: str) -> AssertionResult`
  - `def assert_file_contains(path: str, text: str) -> AssertionResult`
  - `def assert_screenshot_similar(current: np.ndarray, template: np.ndarray, threshold: float = 0.9) -> AssertionResult`
  - `def assert_vlm_element_exists(chat: ChatBackend, image: bytes, element_desc: str) -> AssertionResult`
- `def run_assertions(assertions: list[Assertion], ctx: dict) -> list[AssertionResult]`：调度

**测试项**：
- 每种断言至少 2 个测试（成功 + 失败）

**验收**：
- [ ] 单元测试全通过

---

## T F.6 终止条件检查

**依赖**：T C.3, T C.4, T B.6, T F.1

**范围**：
- `src/autovisiontest/engine/terminator.py`（新建）
- `tests/unit/engine/test_terminator.py`（新建）

**交付物**：
- `class Terminator`
- 构造参数：`app_handle: AppHandle`, `max_steps: int = 30`, `change_detector: ChangeDetector`
- `def check(session: SessionContext, snapshot: FrameSnapshot, ocr: OCRResult) -> TerminationReason | None`
- 按 §5.3 的优先级顺序检查 T1-T8（T2/T3/T8 在别处触发，此处检查 T1/T4/T5/T6/T7）

**测试项**：
- `test_crash_detected`
- `test_max_steps_triggered`
- `test_error_dialog_triggered`
- `test_stuck_triggered`
- `test_no_progress_triggered`
- `test_normal_returns_none`

**验收**：
- [ ] 单元测试全通过

---

## T F.7 单步主循环

**依赖**：T F.3, T F.4, T F.5, T F.6, T E.4, T B.7, T C.5

**范围**：
- `src/autovisiontest/engine/step_loop.py`（新建）
- `tests/unit/engine/test_step_loop.py`（新建）

**交付物**：
- `class StepLoop`
- 构造参数：Planner, Actor, Terminator, SafetyGuard, ActionExecutor, Perception, evidence_writer
- `def run(session: SessionContext) -> TerminationReason`：主循环实现（§5.2）
- 每步：截图+OCR → Terminator.check → Planner.decide → Actor.locate（如需）→ SafetyGuard.check → Executor.execute → 等待 → 写 evidence → 更新 session

**测试项**：
- 重度 mock 各组件：
  - `test_run_happy_path_pass`：Planner 两步后返回 done=True
  - `test_run_crash_terminates`
  - `test_run_max_steps_terminates`
  - `test_run_safety_blocks`

**验收**：
- [ ] 单元测试全通过

---

## T F.8 探索模式执行器

**依赖**：T F.7

**范围**：
- `src/autovisiontest/engine/exploratory.py`（新建）
- `tests/unit/engine/test_exploratory.py`（新建）

**交付物**：
- `class ExploratoryRunner`
- `def run(goal: str, app_path: str, app_args: list[str] | None = None) -> SessionContext`
  - 启动被测应用 → 创建 StepLoop → run → 关闭应用 → 返回 session

**测试项**：
- mock 整条链路，验证 app 启停和 session 填充
- `test_run_cleans_up_on_exception`

**验收**：
- [ ] 单元测试全通过

---

## T F.9 回归模式执行器

**依赖**：T F.7, T G.3（可先桩）

**范围**：
- `src/autovisiontest/engine/regression.py`（新建）
- `tests/unit/engine/test_regression.py`（新建）

**交付物**：
- `class RegressionRunner`
- 加载 recording → 用"脚本 Planner"驱动（按 steps 顺序吐）→ StepLoop 复用
- 每步做 SSIM 预期校验，连续 2 步 < 0.5 → 标记 `recording_invalid=True` 并返回
- `def run(recording_path: Path) -> SessionContext`

**测试项**：
- `test_run_regression_pass`
- `test_run_regression_invalidation_on_ui_drift`

**验收**：
- [ ] 单元测试全通过

---

## 阶段 F 里程碑验收

- [ ] F.1 – F.9 全通过
- [ ] `scripts/demo_exploratory.py`：跑一个简单目标（"打开记事本"）能走完主循环（可能失败但不崩溃）

---

# 阶段 G — 用例与调度

## T G.1 用例 Schema

**依赖**：T F.1

**范围**：
- `src/autovisiontest/cases/schema.py`（新建）
- `tests/unit/cases/test_schema.py`（新建）

**交付物**：
- Pydantic 模型：`TestCase`, `AppConfig`, `Step`, `Expect`, `CaseMetadata`（对应产品文档 §4.3）
- JSON 落盘格式，YAML 也能加载（Pydantic 自带 dict 互转）

**测试项**：
- `test_schema_roundtrip_json`
- `test_schema_roundtrip_yaml`
- `test_schema_validation_errors`

**验收**：
- [ ] 单元测试全通过

---

## T G.2 指纹计算

**依赖**：T G.1

**范围**：
- `src/autovisiontest/cases/fingerprint.py`（新建）
- `tests/unit/cases/test_fingerprint.py`（新建）

**交付物**：
- `def normalize_goal(goal: str) -> str`：小写 + 去标点 + 按空格拆词 + 去停用词（中文用简单字符分、英文常见停用词表）
- `def compute_app_version(app_path: str) -> str`：优先 PE 元数据 `FileVersion`，失败 fallback 到 exe 文件 SHA-256 前 12 位
- `def compute_fingerprint(app_path: str, goal: str) -> str`：`sha256(app_path + normalize_goal(goal) + compute_app_version(app_path))`，取前 16 位

**测试项**：
- `test_normalize_goal_stable`
- `test_compute_app_version_notepad`
- `test_fingerprint_stable_across_calls`
- `test_fingerprint_changes_on_different_goal`

**验收**：
- [ ] 单元测试全通过

---

## T G.3 用例存取

**依赖**：T G.1, T G.2

**范围**：
- `src/autovisiontest/cases/store.py`（新建）
- `tests/unit/cases/test_store.py`（新建）

**交付物**：
- `class RecordingStore`
- 构造参数：`data_dir: Path`
- `def save(case: TestCase) -> Path`：写 `{data_dir}/recordings/{fingerprint}.json`
- `def load(fingerprint: str) -> TestCase | None`
- `def list_all() -> list[TestCase]`
- `def delete(fingerprint: str) -> bool`
- `def find_for_goal(app_path: str, goal: str) -> TestCase | None`

**测试项**：
- `test_save_and_load`
- `test_list_all`
- `test_delete`
- `test_find_for_goal_matches`

**验收**：
- [ ] 单元测试全通过

---

## T G.4 用例固化器

**依赖**：T G.3, T F.8

**范围**：
- `src/autovisiontest/cases/consolidator.py`（新建）
- `tests/unit/cases/test_consolidator.py`（新建）

**交付物**：
- `def consolidate(session: SessionContext, store: RecordingStore) -> TestCase`：
  - 从探索成功的 session 里抽出 steps（去除 reflection、retry）
  - 计算 expect 字段：每步截图 SSIM hash + 关键 OCR 文字
  - 构造 TestCase → store.save

**测试项**：
- `test_consolidate_from_session`
- `test_consolidate_ignores_failed_session`

**验收**：
- [ ] 单元测试全通过

---

## T G.5 会话调度器

**依赖**：T F.8, T F.9, T G.3, T G.4

**范围**：
- `src/autovisiontest/scheduler/session_scheduler.py`（新建）
- `src/autovisiontest/scheduler/session_store.py`（新建）
- `tests/unit/scheduler/test_session_scheduler.py`（新建）

**交付物**：
- `class SessionScheduler`
- `def start_session(goal, app_path, app_args=None, timeout_ms=None) -> str`：
  - 查 store 是否已有回归用例 → 有则走回归，无则走探索
  - 异步执行（后台线程），返回 session_id
- `def get_status(session_id) -> SessionStatus`
- `def get_report(session_id) -> Report | None`（阶段 H 完成后填充）
- `def stop(session_id) -> bool`
- 内部用 `concurrent.futures.ThreadPoolExecutor(max_workers=1)`（MVP 串行）
- 会话状态持久化到 `{data_dir}/sessions/{session_id}/status.json`

**测试项**：
- `test_start_returns_session_id`
- `test_get_status_pending_then_running_then_completed`
- `test_stop_cancels_session`
- `test_regression_preferred_over_exploration_when_recording_exists`

**验收**：
- [ ] 单元测试全通过

---

## T G.6 UI 大改 → 回退探索

**依赖**：T G.5, T F.9

**范围**：
- 修改 `scheduler/session_scheduler.py`
- `tests/unit/scheduler/test_fallback_to_exploration.py`（新建）

**交付物**：
- 在 `SessionScheduler` 内：回归执行返回 `recording_invalid=True` 时，自动启动探索模式的补偿会话，并在成功后替换旧 recording
- 新方法：`def invalidate_recording(fingerprint: str) -> bool`（暴露给外部 API）

**测试项**：
- `test_invalid_recording_triggers_exploration`
- `test_new_exploration_overwrites_old`
- `test_manual_invalidate_deletes`

**验收**：
- [ ] 单元测试全通过

---

## 阶段 G 里程碑验收

- [ ] G.1 – G.6 全通过
- [ ] `scripts/demo_scheduler.py`：手工启动一次探索 → 固化 → 再次跑回归 → 观察第二次走回归路径（通过日志验证）

---

# 阶段 H — 报告与证据

## T H.1 Report Schema

**依赖**：T F.1

**范围**：
- `src/autovisiontest/report/schema.py`（新建）
- `tests/unit/report/test_schema.py`（新建）

**交付物**：
- 按产品文档 §11.2 的 JSON schema 定义 Pydantic 模型
- `protocol_version = "2.0"` 常量

**测试项**：
- `test_report_schema_roundtrip`
- `test_report_protocol_version_stable`

**验收**：
- [ ] 单元测试全通过

---

## T H.2 Evidence 存储

**依赖**：T A.2

**范围**：
- `src/autovisiontest/report/evidence.py`（新建）
- `tests/unit/report/test_evidence.py`（新建）

**交付物**：
- `class EvidenceWriter`
- 构造参数：`session_id: str`, `data_dir: Path`
- `def write_step(idx: int, before: bytes, after: bytes, ocr: OCRResult) -> dict[str, Path]`
- `def write_report(report: Report) -> Path`
- 目录：`{data_dir}/evidence/{session_id}/`

**测试项**：
- `test_write_step_creates_files`
- `test_write_report_json`

**验收**：
- [ ] 单元测试全通过

---

## T H.3 Report 构造器

**依赖**：T H.1, T H.2, T F.1

**范围**：
- `src/autovisiontest/report/builder.py`（新建）
- `tests/unit/report/test_builder.py`（新建）

**交付物**：
- `class ReportBuilder`
- `def build(session: SessionContext, evidence_dir: Path, include_base64: bool = True) -> Report`：
  - 按截图投递策略（§11.3）选择 key_evidence
  - 成功仅首尾、失败取失败点前后各 2 步
  - `include_base64=False` 时仅填路径，由 MCP resource 负责投递
- `def to_json(report: Report, pretty: bool = True) -> str`
- `def to_html(report: Report) -> str`（简易可选，MVP 可桩实现）

**测试项**：
- `test_build_success_report_minimal_evidence`
- `test_build_failure_report_context_screenshots`
- `test_to_json_roundtrip`

**验收**：
- [ ] 单元测试全通过

---

## T H.4 Evidence 清理后台任务

**依赖**：T H.2

**范围**：
- `src/autovisiontest/report/cleaner.py`（新建）
- `tests/unit/report/test_cleaner.py`（新建）

**交付物**：
- `class EvidenceCleaner`
- 构造参数：`data_dir, keep_recent_sessions=50, keep_days=7, keep_failed_days=30`
- `def cleanup() -> CleanupStats`：按 §11.4 规则扫描并删除
- 线程启动入口 `def start_background(interval_s: int = 3600) -> Thread`

**测试项**：
- `test_cleanup_by_count`
- `test_cleanup_preserves_recent`
- `test_cleanup_preserves_failed_longer`
- `test_recordings_never_deleted`

**验收**：
- [ ] 单元测试全通过

---

## 阶段 H 里程碑验收

- [ ] H.1 – H.4 全通过
- [ ] `scripts/demo_report.py`：造一个假 session → 生成 report.json → 打开查看字段完整

---

# 阶段 I — 接入层

## T I.1 CLI 实装

**依赖**：T G.5, T H.3

**范围**：
- `src/autovisiontest/cli.py`（修改，填充阶段 A 的桩）
- `src/autovisiontest/interfaces/cli_commands.py`（新建）
- `tests/unit/interfaces/test_cli_commands.py`（新建）

**交付物**：
- 实装所有 CLI 子命令：
  - `run`: 启动会话，阻塞等待完成，打印 status 和报告路径
  - `status <sid>`: 打印当前状态
  - `report <sid>`: 打印 JSON 或 HTML
  - `list-recordings`: 打印表格
  - `validate`: 打印配置
- 退出码约定：0=PASS / 1=FAIL / 2=ABORT / 3=内部错误

**测试项**：
- `test_run_success_returns_0`（mock scheduler）
- `test_run_fail_returns_1`
- `test_report_prints_json`
- `test_list_recordings_empty_dir`

**验收**：
- [ ] 单元测试全通过
- [ ] `autovisiontest run --goal "..."`  可用（与假 scheduler 集成）

---

## T I.2 HTTP API (FastAPI)

**依赖**：T G.5, T H.3

**范围**：
- `src/autovisiontest/interfaces/http_server.py`（新建）
- `tests/integration/interfaces/test_http_server.py`（新建）

**交付物**：
- FastAPI app，路由按产品文档 §10.2
- POST `/v1/sessions`: 返回 `{session_id}`
- GET `/v1/sessions/{id}/status`
- GET `/v1/sessions/{id}/report`
- POST `/v1/sessions/{id}/stop`
- GET `/v1/recordings`
- DELETE `/v1/recordings/{fingerprint}`
- OpenAPI schema 自动生成
- 入口：`autovisiontest serve --port 8080`

**测试项**（使用 `TestClient`）：
- `test_create_session`
- `test_get_status_not_found_404`
- `test_stop_session`
- `test_list_recordings`

**验收**：
- [ ] 集成测试全通过
- [ ] `autovisiontest serve` 启动后 `/docs` Swagger 可访问

---

## T I.3 MCP Server

**依赖**：T G.5, T H.3

**范围**：
- `src/autovisiontest/interfaces/mcp_server.py`（新建）
- `tests/integration/interfaces/test_mcp_server.py`（新建）

**交付物**：
- 基于 `mcp` Python SDK，实现产品文档 §10.3 列出的 6 个 tool
- 报告截图作为 MCP `resource` 投递（URI 形如 `autovt://evidence/{session_id}/step_5_after.png`）
- 入口：`autovisiontest mcp`（stdio 模式）或 `autovisiontest mcp --http :8090`

**测试项**：
- `test_list_tools`
- `test_start_test_session_returns_id`
- `test_get_session_report_includes_resources`

**验收**：
- [ ] 集成测试全通过
- [ ] 手动验证：在 Claude Code 中以 MCP 连接该 server，能调用 `start_test_session`

---

## 阶段 I 里程碑验收

- [ ] I.1 – I.3 全通过
- [ ] CLI / HTTP / MCP 三种接入独立可用

---

# 阶段 J — MVP 验收

## T J.1 记事本 demo - 探索模式

**依赖**：所有 F/G/H/I 完成

**范围**：
- `tests/e2e/test_notepad_exploration.py`（新建）
- `docs/demo/notepad.md`（新建，demo 指南）

**交付物**：
- E2E 测试：
  1. 清理 `C:\TestSandbox\`
  2. 调 `scheduler.start_session(goal="打开记事本,输入hello world,保存到C:\\TestSandbox\\out.txt", app_path="C:\\Windows\\System32\\notepad.exe")`
  3. 等待完成（最长 5 分钟）
  4. 验证 result.status == "PASS"
  5. 验证 `C:\TestSandbox\out.txt` 存在且内容为 "hello world"
  6. 验证 `recordings/` 新生成了一个 fingerprint 文件

**测试项**：
- `test_notepad_exploration_end_to_end`

**验收**：
- [ ] 测试连续跑 3 次，至少 2 次通过（探索模式不稳定可接受）
- [ ] 失败的那次有完整报告

---

## T J.2 记事本 demo - 回归复跑

**依赖**：T J.1

**范围**：
- `tests/e2e/test_notepad_regression.py`（新建）

**交付物**：
- E2E 测试：
  1. 确保 T J.1 已固化 recording
  2. 删除 out.txt
  3. 再次 `start_session` 同样目标
  4. 验证：日志显示进入回归模式（非探索）
  5. 验证：总耗时 < 60 秒
  6. 验证：result.status == "PASS"

**测试项**：
- `test_notepad_regression_fast_replay`

**验收**：
- [ ] 连续 10 次，成功率 ≥ 90%（回归模式要稳）
- [ ] 平均耗时 < 60 秒

---

## T J.3 故意破坏场景

**依赖**：T J.2

**范围**：
- `tests/e2e/test_notepad_broken_fix.py`（新建）
- `scripts/demo/notepad_target_broken.py`（新建，被测脚本示例）
- `scripts/demo/notepad_target_ok.py`（新建）

**交付物**：
- E2E 测试：
  1. 使用"破坏版"被测脚本（例如通过 AutoHotkey 写错保存快捷键）
  2. 跑回归
  3. 验证：result.status == "FAIL"
  4. 验证：report.key_evidence 含至少 3 张截图
  5. 验证：report.bug_hints 非空
  6. 替换为"正确版"脚本
  7. 再跑回归
  8. 验证：result.status == "PASS"

**测试项**：
- `test_broken_fix_cycle`

**验收**：
- [ ] 测试通过
- [ ] 失败报告中截图能清晰看出"保存对话框未出现"或类似现象

---

## T J.4 稳定性基准

**依赖**：T J.2

**范围**：
- `scripts/benchmarks/notepad_stability.py`（新建）
- `tests/benchmarks/notepad_stability.md`（新建，结果记录）

**交付物**：
- 脚本连续跑 20 次回归模式
- 输出：成功率、平均/中位/P95 耗时、失败截图

**测试项**：
- 手动执行脚本

**验收**：
- [ ] 成功率 ≥ 90%
- [ ] 结果提交至 `tests/benchmarks/notepad_stability.md`

---

## T J.5 Grounding 准确率基准

**依赖**：所有 D 阶段任务

**范围**：
- `tests/benchmarks/grounding/` 目录（新建）
  - `targets.yaml`：20 个元素的真值边界框
  - 对应截图
- `scripts/benchmarks/grounding_accuracy.py`（新建）
- `tests/benchmarks/grounding_accuracy.md`（结果记录）

**交付物**：
- 基准集：记事本 10 个元素 + 计算器 10 个元素（按钮/菜单/输入框混合）
- 每个元素手工标注 BoundingBox
- 脚本：对每个元素调 `ground(image, query)`，统计命中率

**测试项**：
- 手动运行脚本

**验收**：
- [ ] Grounding 命中率 ≥ 85%
- [ ] 结果和失败样例记录至 md

---

## 阶段 J 里程碑验收（= MVP 总验收）

- [ ] J.1 – J.5 全通过
- [ ] 产品文档 §2.2 所述的 8 步闭环能完整演示一次
- [ ] `docs/demo/notepad.md` 可让新用户在干净环境复现 MVP

---

# 附录 A：并行执行建议

某些阶段内任务可并行：

| 阶段 | 并行组 |
|------|--------|
| B | {B.2, B.3, B.4} 并行（都依赖 B.1），B.5/B.6 随后 |
| C | C.1 / C.2 可并行；C.3 依赖 C.1；C.4 依赖 C.2 |
| D | D.2 / D.3 / D.4 / D.5 可并行（都依赖 D.1） |
| E | E.1 / E.2 可并行 |
| F | F.2 / F.5 / F.6 可并行（F.1 之后） |
| G | G.2 / G.3 可并行（G.1 之后） |
| H | H.1 / H.2 可并行 |
| I | I.1 / I.2 / I.3 可并行 |

跨阶段原则上串行，但允许下阶段的"无依赖准备工作"（例如 fixture 收集）提前。

---

# 附录 B：风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| ShowUI 在现实屏幕上 grounding 精度 < 85% | 中 | 高 | Phase 2 切换 OS-Atlas-2B；同时在 Planner 中补充坐标修正 few-shot |
| Claude API 响应时间波动大 | 中 | 中 | 加缓存（相同 goal+screenshot hash 复用）；超时从 60s 提到 90s |
| vLLM 在 3080Ti 上 OOM | 中 | 中 | 预先量化到 AWQ INT4；启动脚本添加 `--gpu-memory-utilization 0.85` |
| PaddleOCR 中文识别误识字符相似字 | 中 | 中 | 断言用 `fuzzy=True`（编辑距离 ≤ 1）；关键词也按相似变体扩展 |
| pyautogui 被安全软件拦截 | 低 | 高 | 部署文档说明加白名单；提供基于 `SendInput` 的备选实现作为 Phase 2 |
| Windows 缩放不为 100% 时坐标偏移 | 中 | 高 | T B.1 强制 PerMonitorV2；在 QA 环境覆盖 100%/125%/150% 三档 |
| MCP 协议 resource 投递在 Claude Code 中兼容性 | 低 | 中 | fallback 用 base64 直接嵌入；由配置切换 |

---

# 附录 C：后续阶段（非 MVP）预告

Phase 2（此文档不展开）：
- 纯本地 Planner 端到端验证
- 5 种异构应用 demo
- 全自动触发（watchdog + Git hook）
- 多显示器
- 回归用例版本管理
- Planner prompt 的评估集与持续优化

Phase 3：
- 跨平台
- 并发执行与资源调度
- 用例库 UI
- Web Dashboard

---

*任务文档结束。每个任务按 §0.3 约定独立 commit，完成 checklist 方可进入下一任务。*
