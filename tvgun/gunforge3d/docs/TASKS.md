# GunForge3D 开发任务

版本：v0.5 · 2026-11-16 · 四份文档联合评审修订（见PLAN §11）；v0.5 是交付执行前的复核，只补执行规则（落点见附录 C），任务范围和验收数值不变。方案见 [PLAN.md](PLAN.md)。本文是执行者（AI 编码模型）的工作说明，按 T00 → T20 顺序执行。

## 0. 执行规则（每个任务都适用）

### 0.1 环境

- 开发机的硬件、工具路径和已验证的范围见 [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)，开工前按其中第 5 节的命令复查一遍。
- 仓库根：开发机上是 `E:\tvgun`。本工程根：`E:\tvgun\gunforge3d`。Godot 工程根：`E:\tvgun\gunforge3d\game`。若实际检出路径不同，以实际路径为准，下文的 `E:\tvgun` 相应替换；脚本和代码里不得硬编码仓库盘符，一律用相对路径或 `$PSScriptRoot`。除特别说明外，本文的命令都在仓库根执行。
- Godot：`D:\gunforge_cache\tools\godot-4.6.3\Godot_v4.6.3-stable_win64_console.exe`（下文记为 `$GODOT`，PowerShell 中用调用运算符 `&` 执行）。如环境变量 `GODOT_BIN` 已设置则优先用它。**不要下载或安装任何引擎、插件或素材。**
- 语言只用 GDScript。除脚本、着色器和 JSON 外不需要其他工具链。

### 0.2 边界

- 只能新建或修改 `gunforge3d/` 下的文件，以及 T00 指定的仓库根文件 `play_3d.cmd`。
- **不得修改、移动或引用** `gunforge/`、`android/`、`art2d/`、`scripts/`、`docs/`、`test_res/` 和仓库根的其他文件。可以阅读它们作参考，但不得 `preload` 或复制整段代码。
- 不引入外部素材（模型、贴图、音频、字体）。所有画面用 Godot 内置图元和代码生成，所有声音用代码合成，文字用引擎默认字体。
- 不使用 Godot 物理引擎做玩法判定（不用 `RayCast3D`、`Area3D`、`intersect_ray`）。命中一律走 `sim/geom.gd`。

### 0.3 代码约定

- 缩进用 Tab。函数参数、返回值和成员变量写类型标注。
- **不要使用 `class_name`。** 跨文件引用一律 `const Foo = preload("res://sim/foo.gd")`。原因：用 `--script` 直接运行时全局类缓存可能不存在。
- `sim/` 下的脚本一律 `extends RefCounted`，不得依赖场景树、`Engine`、`Time`、`OS` 或全局随机函数。随机数只用 `SimWorld.rng` 的实例方法；`FileAccess` 仅限关卡加载。具体扫描规则见 T03。
- `sim/` 里的时间一律是整数 tick（60 tick = 1 秒）。JSON 里的秒在加载时用 `roundi(seconds * 60)` 换算。
- `JSON.parse_string` 把所有数字读成 float。用作下标、计数、tick 的值要 `int()`。
- Godot 会为每个脚本和着色器生成 `.uid` 文件，一并提交。`game/.godot/` 不提交。
- 只在逻辑不明显处写注释，注释用英文。面向玩家的文字用中文。
- 不要为没有要求的功能写代码。不要添加配置开关来绕过验收。

### 0.4 测试

- 测试入口：`& $GODOT --headless --path gunforge3d/game --script res://tests/run_all.gd`。退出码 0 为全部通过。可加 `-- --only=<名字片段>` 只跑部分。
- 每个任务都要为新增逻辑写测试，放在 `game/tests/test_<主题>.gd`。任务里列出的"必测"是下限。
- 测试必须真实断言行为。禁止为了通过而放宽断言、跳过用例或在被测代码里识别测试环境。
- 继承 `SceneTree` 的脚本在 `_initialize()` 开头，根节点尚未进入场景树。需要节点时先 `await process_frame`。
- 涉及画面的任务还要截图自检：按任务给出的方式生成 PNG，自己查看图片，确认与描述相符后再提交。截图存到 `gunforge3d/reports/captures/`（已被忽略，不入库）。截图需要非无头模式，会短暂弹出窗口，属正常。
- 需要真实渲染的检查（截图、限亮测量、性能）无法在无头模式运行，不放进 `run_all`，按任务说明用窗口模式单独执行并把结果记入 PROGRESS。
- 启动窗口的自动化命令要设超时（建议 120 秒，整关回放 600 秒）。超时视为失败并排查原因，不要无限等待。
- 每个任务结束前跑一遍全量测试，之前任务的测试不得失败。

### 0.5 提交与进度

- 每个任务完成且全量测试通过后提交一次：`git add gunforge3d play_3d.cmd`，提交信息 `gunforge3d: Txx <英文摘要>`。提交到 `main`，**不 push**，不改 git 配置，不改历史。
- 提交前更新 `gunforge3d/docs/PROGRESS.md`：任务号、状态、测试数量、截图或指标摘要、偏离本文之处及原因。
- 遇到本文与实际冲突、或验收无法达到时：不要绕过。在 PROGRESS.md 记录问题与已尝试的做法，停下来向用户说明。

### 0.6 通用数据约定

- 坐标系：+X 右，+Y 上，前进方向 −Z。单位米。角度在 JSON 中用度。
- 向量写 `[x, y, z]`，颜色写 `"#rrggbb"`。
- 规范坐标：1920×1080。内容区是规范坐标 `[72,72]–[1848,1008]`，大小 1776×936。"内容像素"指以内容区左上为原点、1776×936 的坐标。
- 安全框：内容区四边各内缩 60 内容像素，即内容像素 `[60,60]–[1716,876]`。运行时的可见性判定（T10）和校验器（T17）用同一个定义。
- 相机：垂直视场默认 60°，宽高比固定 1776/936，近裁 0.1，远裁 200。
- 实体 id：关卡数据里定义的实体（spawn、props、debug_actors）直接用数据中的字符串 id，Boss 用 `<段 id>:boss`；运行期生成的实体（投射物、拾取物、Boss 放出的小怪）用 `<类型>#<序号>`，序号取自 Sim 的下一实体序号。所有实体另带单调递增的生成序号，排序和平局处理一律按生成序号，不按 id。事件、令牌、`captor` 引用和机器人候选里的 id 都是这个 id。

### 0.7 每个任务的开工与收工

- 建议每个任务用一次新的会话。不论是否新会话，开工先读：§0 全文、当前任务全文、`PROGRESS.md`、附录 A 和 B；任务引用了 PLAN 的小节时读那一节。不要凭上一个任务的记忆工作。
- 开工时 `git status` 应当干净，全量测试应当通过（T00 除外）。不是这样就先查明原因并记入 PROGRESS，不要在坏的基线上叠加新代码。
- 只做当前任务。发现以前任务的缺陷时，可以做修复它所需的最小改动并补测试，在 PROGRESS 里写明；不要顺手重构，也不要提前实现后面任务的内容。
- 交付项多的任务（T10、T13、T16、T18、T19）按交付项的编号逐项实现，每完成一项就写它的测试并运行，不要全部写完再一起测。
- 收工的顺序：全量测试 → 截图自检 → 更新 PROGRESS → 提交。验收里有任何一项没达到，就不把任务标成完成，按 §0.5 处理。

---

## T00 工程脚手架

**目标**：建立可运行、可测试的空工程。

**交付**

1. `gunforge3d/game/project.godot`：名称 `GunForge3D`，主场景 `res://main.tscn`，特性 `"4.6", "Forward Plus"`，窗口 1280×720、可缩放，stretch 模式 `disabled`，默认清屏色黑。
2. `game/main.tscn` 与 `game/main.gd`：一个 `Node` 根节点。暂时只显示黑色窗口。
3. 目录 `shell/ sim/ sim/behaviors/ view/ hud/ audio/ dev/ data/levels/ tests/fixtures/`。空目录放 `.gitkeep`。
4. 测试框架：
   - `tests/harness.gd`（`extends RefCounted`）：`check(cond: bool, label: String)`、`check_eq(a, b, label)`、`check_near(a: float, b: float, eps: float, label)`。记录通过数与失败标签，失败时打印标签和实际值。
   - `tests/run_all.gd`（`extends SceneTree`）：`await process_frame` 后枚举 `res://tests/` 下的 `test_*.gd`，按文件名排序，逐个 `load().new()` 并调用 `run(t, tree)`（`t` 是 harness 实例，`tree` 是 SceneTree；调用一律加 `await`）。支持 `-- --only=<片段>`。结束时打印一行 JSON `{"passed":n,"failed":[...]}`，全部通过 `quit(0)`，否则 `quit(1)`。
   - `tests/test_smoke.gd`：断言 `1 + 1 == 2`，并断言 `res://project.godot` 存在。
5. `gunforge3d/run.ps1`：参数 `-Test`、`-Godot <路径>`，其余参数透传给游戏（放在 `--` 之后）。
   - 查找顺序：`-Godot` → `$env:GODOT_BIN` → `D:\gunforge_cache\tools\godot-4.6.3\Godot_v4.6.3-stable_win64_console.exe` → 仓库同级 `..\gunforge_cache\tools\godot-4.6.3\...` → PATH 中的 `godot`。找不到时报错并说明如何设置。
   - 所有路径基于 `$PSScriptRoot`，不依赖调用方 cwd。启动前，若 `game/.godot/` 不存在，先执行一次 `--headless --path <game绝对路径> --import`，失败时明确报错。
   - `-Test` 运行全量测试并返回其退出码。
   - 开发机的默认 Shell 是 PowerShell 7，而 `.cmd` 里的 `powershell` 命令启动的是系统自带的 Windows PowerShell 5.1。`run.ps1` 和 `tools/` 下的脚本要在两者里都能运行：脚本文件只用 ASCII 字符（5.1 会把不带 BOM 的 UTF-8 当成本地编码，中文会乱码甚至解析失败），不用 7 才有的语法（如 `&&`、三元运算符）。
6. `E:\tvgun\play_3d.cmd`：调用 `gunforge3d\run.ps1`，写法参照根目录的 `play_paper_lantern.cmd`（该文件不存在时用 `powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gunforge3d\run.ps1" %*`）；用 `%*` 完整透传参数，验证带空格的路径。
7. `gunforge3d/.gitignore`：`game/.godot/`、`reports/captures/`、`*.tmp`。
8. `gunforge3d/README.md`：如何启动、如何测试、目录说明、与 2D 工程的关系（各 1–3 句）。
9. `gunforge3d/docs/PROGRESS.md`：进度表初稿。

**验收**

- 全量测试命令退出码 0，输出 `"passed"` 不小于 2。
- `& $GODOT --path gunforge3d/game --quit-after 30` 能启动并正常退出，无脚本错误。

---

## T01 画面壳与坐标映射

**目标**：TVGun 布局的窗口壳，以及窗口、规范、内容三种坐标的互换。

**交付**

1. `shell/screen_layout.gd`（`extends RefCounted`，纯计算）：
   - 常量 `NORM := Vector2(1920, 1080)`；成员 `white := 24.0`、`dark := 48.0`、`outer := 0.022`、`profile := "monitor"`、`calibration := Transform2D.IDENTITY`。
   - `configure(profile_name: String)`：`"monitor"` → outer 0.022，`"tv"` → 0.045。
   - `frame_rect(window: Vector2) -> Rect2`：规范框在窗口中的矩形。`fit = min(w/1920, h/1080) * (1 - 2*outer)`，居中。
   - `content_rect(window: Vector2) -> Rect2`：内容区在窗口中的矩形（规范框四边各内缩 `(white+dark)*scale`）。
   - `content_size() -> Vector2`：`(1776, 936)`。
   - `window_to_norm(p, window)`、`norm_to_window(p, window)`。
   - `norm_to_content(p: Vector2) -> Vector2`：`calibration * p - (72, 72)`。`content_to_norm` 为其逆。
   - `is_offscreen(p_norm) -> bool`：校准后的点不在 `[0,1920]×[0,1080]` 内。
   - `in_content(p_norm) -> bool`：校准后的点在内容区内。
2. `shell/shell.gd` + `shell/shell.tscn`（`Control`，铺满窗口）：
   - 自绘：全窗黑底；规范框位置画纯白矩形；其内缩 `white` 处画纯黑矩形（暗带与内容底色）。
   - 子节点 `SubViewport`（名为 `Content`）：`own_world_3d = true`，`render_target_update_mode = UPDATE_ALWAYS`，固定为 1776×936，由 TextureRect 等比缩放到实际内容区；逻辑相机与渲染始终使用同一宽高比。3D 场景与 HUD 以后都挂在它下面。
   - 子节点 `TextureRect`：显示 `Content` 的贴图，位置与大小等于 `content_rect`，使用限亮着色器。
   - 窗口尺寸变化时重算全部矩形。
   - F11 切换全屏，F3 在 monitor/tv 档之间切换。
3. `shell/luma_cap.gdshader`（`canvas_item`）：`uniform float cap = 0.75`。按 `Y = dot(rgb, vec3(0.2126, 0.7152, 0.0722))` 计算，`Y > cap` 时 `rgb *= cap / Y`。
4. `main.tscn` 实例化 Shell。临时往 `Content` 里放一个测试 3D 场景（地面、一个盒子、一盏平行光、相机），以确认 3D 能显示。该临时场景在 T05 删除。
5. 临时命令行参数 `--shot=<绝对路径.png>`：启动 30 帧后保存整窗截图并退出（T07 换成正式接口后删除）。

**必测**（`tests/test_screen_layout.gd`）

- 1920×1080 窗口、outer=0：`frame_rect` 为 `(0,0,1920,1080)`，`content_rect` 为 `(72,72,1776,936)`。
- 1280×720 窗口、monitor 档：规范框居中，宽高比 16:9，左右留边各为窗口宽的 2.2%。
- `window_to_norm` 与 `norm_to_window` 在 3 种窗口尺寸（含非 16:9 的 1600×1200）下往返误差 < 1e-3。
- `norm_to_content((72,72)) == (0,0)`，`norm_to_content((1848,1008)) == (1776,936)`。
- `is_offscreen((-1,500))` 为真，`is_offscreen((10,10))` 为假；`in_content((10,10))` 为假，`in_content((960,540))` 为真。

**截图自检**：用 `--shot` 截图。确认：外圈黑边、一圈白框、白框内一圈黑带、中间是 3D 画面，四边对称。

---

## T02 输入抽象与鼠标输入源

**目标**：与手机协议一致的输入事件层，首版只接鼠标。

**交付**

1. `shell/input_events.gd`：事件名常量 `AIM`、`SHOT`、`RELOAD`、`START`、`COIN`、`EXIT`，以及构造函数，如 `shot(x, y) -> Dictionary`（`{"event":"SHOT","x":..,"y":..}`）。x、y 是规范坐标。
2. `shell/input_source.gd`（基类，`extends RefCounted`）：`poll() -> Array[Dictionary]` 返回自上次调用以来的事件；`aim() -> Dictionary` 返回 `{"x","y","valid"}`。
3. `shell/mouse_source.gd`：Shell 把 `InputEvent` 转给它的 `handle(event: InputEvent, layout, window_size: Vector2)`。
   - 鼠标移动 → 更新 aim（规范坐标，valid 恒为 true）。
   - 左键按下 → SHOT，坐标为按下瞬间的规范坐标。
   - 右键按下或 R → RELOAD。Enter 或小键盘 Enter → START。数字 5 → COIN。Esc → EXIT。
   - 只响应按下沿，忽略按键重复（`echo`）。
4. `shell/input_router.gd`：持有当前输入源，`collect() -> Array[Dictionary]` 返回给 Sim 的输入。
   - SHOT 且 `layout.is_offscreen` → 转成 `RELOAD`。
   - 其余 SHOT 转成 `{"event":"SHOT","x":cx,"y":cy,"in_content":bool}`，`cx, cy` 是内容像素。
   - AIM 不进入 Sim，只供 HUD 读取。EXIT 不进入 Sim，交给 Shell 处理暂停。
5. Shell 隐藏系统鼠标指针，暂停时恢复显示。

**必测**（`tests/test_input.gd`）：用手工构造的 `InputEventMouseButton`、`InputEventMouseMotion`、`InputEventKey` 喂给 `mouse_source`。

- 1920×1080、outer=0 时点击窗口 `(960,540)` → SHOT，规范坐标 `(960,540)`；路由后内容像素 `(888,468)`，`in_content` 为真。
- 点击 `(10,10)`（白边内）和 `(30,30)`（暗带内）→ 都是 SHOT 且 `in_content` 为假。
- monitor 档下点击窗口 `(2,2)`（外黑边）→ 路由后为 RELOAD。
- R、右键 → RELOAD；Enter → START；5 → COIN；Esc → EXIT，且 EXIT 不出现在 `collect()` 的结果里。
- 带 `echo = true` 的按键不产生事件。

---

## T03 Sim 核心与主循环

**目标**：确定性的逻辑世界骨架，并接入主循环。

**交付**

1. `sim/fixed_clock.gd`：`hz := 60`、`debt := 0.0`。`advance(seconds: float) -> int` 返回本帧应执行的步数。单帧上限 8 步，超出时只执行 8 步并把 debt 清零，防止卡顿后暴走。
2. `sim/sim_world.gd`：
   - 成员：`tick: int`、`rng: RandomNumberGenerator`、`phase: String`（`"title"`、`"playing"`、`"continue"`、`"results"`）、`events: Array[Dictionary]`（本 tick 产生的事件，每步开头清空）。
   - `setup(level: Dictionary, rules: Dictionary, archetypes: Dictionary)`：用 `level.seed` 初始化 rng，进入 `"title"`。
   - `step(inputs: Array)`：处理输入，推进一 tick。本任务只处理：`"title"` 阶段收到 START 或 SHOT → 进入 `"playing"` 并发事件 `phase_change`。
   - `emit(type: String, data := {})`：往 `events` 追加 `{"type": type, ...data}`。
   - `snapshot() -> Dictionary`：完整状态。后续任务新增的每个子系统都必须把自己的状态并入。`rng.seed` 与 `rng.state` 是 64 位整数，存为十进制字符串。实体数组按稳定生成序号排列；快照包含下一实体序号、检查点（不递归包含自身）、延迟队列、统计和全部玩法计时器，不含本 tick 的输出 events、渲染节点、Shell 时钟或调试配置。确定性承诺限于同一 Godot 4.6.3 Windows 构建和相同模拟代码/数据。
   - `state_hash() -> String`：`JSON.stringify(snapshot(), "", true, true).sha256_text()`。第四个参数 `full_precision = true` 必须开启，否则相差极小的浮点状态会得到相同的哈希。
   - **每 tick 的执行顺序**（后续任务往对应步骤里加内容，不得调换顺序）：
     1. 清空 `events`，按当前 tick 兑现已到期的玩家冷却/换弹（如 reload_done），再接收输入。
     2. 按数组顺序处理输入。SHOT 针对上一 tick 结束时的状态求交；不做渲染插值，窗口输入在下一次推进的第一步消费，命中与死亡立即生效。
     3. 推进轨道与相机。
     4. 导演：波次与生成。
     5. 角色行为，按生成顺序。已死亡的角色不执行，所以预警最后一 tick 被击杀的敌人不会造成伤害。
     6. 投射物。
     7. 道具、拾取物与延迟效果（如油桶连锁）。
     8. 更新玩家计时器的只读剩余值（换弹、射击冷却、无敌）；到期兑现统一在第1步。计时器在设置当 tick 不递减：第 k tick 开始的 N tick 冷却在第 k+N tick 输入前到期。优先用绝对到期 tick 表示；行为/投射物的 N tick 也遵循相同边界，生成当 tick 不消耗一整步时间。
     9. 清场判定、段切换、阶段切换。
     10. `tick += 1`。输入记录中的 tick 是本次 step 入口值；final_tick 是已完成的步数。若输入导致阶段切换，本 tick 不再消费其余玩法输入或执行旧阶段逻辑。若生命归零，立即停止本 tick 后续伤害和清场判定。results → title 执行 setup 后立即返回，不再自增，以满足初始哈希测试。
3. `data/rules.json`：按 PLAN §4.2 与 §4.6 的初值写全：生命、弹匣、换弹时间、射击间隔、无敌时间、续关倒计时、各项分值、连击上限与步进、`assist_px: 0`、`luma_cap: 0.75`。
4. `data/levels/empty.json`：`{"format":"gunforge3d-level-v1","id":"empty","title":"空","seed":1,"geometry":[],"rail":[]}`。
5. `main.gd`：加载 rules、archetypes（文件不存在时用 `{}`，T09 补上）和关卡。每帧 `clock.advance(delta)`；第一步带上 `input_router.collect()` 的输入，其余步输入为空（窗口回放例外：每一步按该 tick 注入回放输入）。0 步帧保留输入队列；同 tick 按采集顺序排序。失焦/暂停丢弃暂停期间的玩法输入，恢复时清零时钟 debt；每步之后调用 `_dispatch(sim.events)`（View、HUD、Audio 以后接在这里）。命令行参数 `--level=<res 路径或绝对路径>`，默认 `res://data/levels/empty.json`。

**必测**（`tests/test_sim_core.gd`）

- `advance(1.0/60)` 返回 1；`advance(0.5)` 返回 8 且 debt 归零；60 次 `advance(1.0/120)` 合计 30 步。
- 两个 SimWorld 以相同输入序列跑 600 tick，`state_hash()` 相同。
- 哈希对状态敏感：一个 SimWorld 在第 10 tick 收到 START，另一个始终没有收到，跑到第 60 tick 时先断言两者 `phase` 不同，再断言哈希不同。（不同的输入不保证产生不同的状态。不要为了让哈希不同而把输入历史存进状态。）
- 哈希精度：手工构造两个只在某个浮点字段上相差 1e-15 的 snapshot 字典，按 `state_hash` 的序列化方式得到的哈希不同。
- title 阶段收到 START → phase 为 `"playing"`，当 tick 的 events 含 `phase_change`。
- 扫描 `res://sim/` 下所有 `.gd`：使用能识别字符串与注释的轻量词法扫描，禁止场景树依赖和 `Engine.`、`Time.`、`OS.`、`get_tree(`、`class_name`；禁止无接收者的全局随机调用（randf、randi、randf_range、randi_range、randfn、randomize、seed）。只允许 `SimWorld.rng` 或显式指向它的局部变量调用随机方法。测试覆盖全局调用被拒绝、实例调用被接受、字符串/注释/带空白的调用不误判。
- 同 tick 阶段切换：title 阶段在同一 tick 送入 START 和 SHOT，只产生一次 `phase_change`。射击冷却和换弹的计时边界本任务还没有可测的功能，放在 T08 测。

---

## T04 几何求交库

**目标**：射击判定用的射线求交，纯数学。

**交付**：`sim/geom.gd`，全部为静态函数。命中返回 `{"t": float, "normal": Vector3}`，未命中返回 `{}`。`dir` 为单位向量，`t` 是沿它的距离，只接受 `t >= 0`。射线起点在形状内部时视为命中，`t = 0`，法线取 `-dir`。

- `ray_sphere(origin, dir, center, radius)`。
- `ray_capsule(origin, dir, a, b, radius)`：a、b 是轴线两端的球心。
- `ray_obb(origin, dir, xform: Transform3D, half: Vector3)`：盒子以 `xform` 为中心和朝向。把射线变换到局部后做 slab 求交，法线变回世界。
- `ray_cylinder(origin, dir, xform: Transform3D, radius, half_height)`：局部 Y 轴为轴线的有盖圆柱。
- `ray_shape(origin, dir, shape: Dictionary)`：按 `shape.type` 分发。字段：sphere `{center, radius}`；capsule `{a, b, radius}`；box `{xform, half}`；cylinder `{xform, radius, half_height}`。
- `point_in_shape(p: Vector3, shape: Dictionary) -> bool`。
- `distance_to_shape(p: Vector3, shape: Dictionary) -> float`：点到形状表面的距离，内部为 0（校验器用）。
- `segment_blocked(from: Vector3, to: Vector3, shapes: Array) -> bool`：线段是否被任一形状挡住。

**必测**（`tests/test_geom.gd`，每种形状至少 6 例）

- 正中命中的 t 与法线（误差 < 1e-4）；擦边外侧未命中；背向未命中；起点在内部 t = 0。
- 胶囊：命中圆柱段、命中两端球冠、从端点外沿轴线射入。
- OBB：绕 Y 旋转 45° 后的命中面与法线；非均匀半尺寸。
- 圆柱：命中侧面、命中顶盖、命中底盖；从上方斜射、落在盖半径之外且未及侧面的不命中。
- 一致性：固定种子生成 200 条射线，对同一形状，`ray_shape` 的 t 与"沿射线每 0.001 采样 `point_in_shape` 得到的首个入点"相差 < 0.01。四种形状各做一组。
- `segment_blocked`：被挡、未挡、形状在线段延长线上（不算挡）三种情况。

---

## T05 关卡格式、加载与白模视图

**目标**：定义关卡 JSON 的静态部分，加载它，并把白模搭出来。

**关卡格式 `gunforge3d-level-v1`**（本任务实现 geometry、markers、environment、lights；rail 在 T06，spawns 在 T10，props 在 T12）

```json
{
  "format": "gunforge3d-level-v1",
  "id": "warehouse_raid",
  "title": "仓库突入",
  "seed": 20261115,
  "par_score": 30000,
  "environment": {
    "sky": "#20242b", "ambient": "#8a93a3", "ambient_energy": 0.6,
    "sun": {"dir_deg": [-50, 35, 0], "color": "#fff1dd", "energy": 1.1, "shadows": true},
    "fog": {"color": "#20242b", "density": 0.01}
  },
  "materials": {
    "floor": {"color": "#5a5f66"},
    "wall": {"color": "#767c85"},
    "metal": {"color": "#4a5058", "metallic": 0.6, "roughness": 0.5}
  },
  "geometry": [
    {"id": "alley_floor", "shape": "box", "pos": [0, -0.1, -10], "size": [8, 0.2, 24],
     "rot_deg": [0, 0, 0], "material": "floor", "solid": true}
  ],
  "lights": [
    {"type": "omni", "pos": [0, 4, -20], "color": "#ffd9a0", "energy": 2.0, "range": 12}
  ],
  "markers": {"a1_crate_l": {"pos": [-2.2, 0, -14], "yaw": 0}},
  "props": [],
  "rail": []
}
```

- `geometry[].shape`：`box`（`size` 为全尺寸）、`cylinder`（`radius`、`height`）、`sphere`（`radius`）、`capsule`（`radius`、`height` 为总高）。`pos` 是中心。`rot_deg` 可省略。`solid` 默认 true，决定是否挡子弹。`material` 必须存在于 `materials`。
- `markers`：具名点，供出生点、路径、站位引用。`yaw` 可省略。
- `environment`、`lights`、`markers`、`props`、`par_score` 可省略，取合理默认值。

**交付**

1. `sim/level_loader.gd`：`load_file(path) -> Dictionary`，返回 `{"ok": bool, "level": Dictionary, "errors": Array[String]}`。
   - 结构检查：format 正确、必填字段、id 唯一、material 引用存在、shape 合法、数值有限且尺寸为正。
   - 生成运行期数据：`level.blockers: Array`，即所有 solid 几何对应的 `geom` shape 字典。
   - 计算 `level.sha256`，供回放使用：取文件文本，先把 CRLF 归一为 LF，再算 SHA-256。git 的换行转换会让同一文件在不同检出下字节不同，不归一的话入库的回放夹具换一台机器就会被拒绝。rules、archetypes 的哈希和 T16 的 `sim_revision` 同样处理。
2. `sim_world.setup` 保存 `blockers`。
3. `view/world_view.gd`（`Node3D`）：`build(level)`。
   - 按 geometry 生成 `MeshInstance3D`（`BoxMesh`、`CylinderMesh`、`SphereMesh`、`CapsuleMesh`），材质用 `StandardMaterial3D`，同名材质共用一个实例。
   - 按 environment 生成 `WorldEnvironment`（纯色背景、环境光、雾、SSAO）和带阴影的 `DirectionalLight3D`。
   - 按 lights 生成 `OmniLight3D`。
4. `view/game_view.gd`（`Node3D`，挂在 Shell 的 `Content` 下）：包含 `world_view` 和一个 `Camera3D`（fov 60，`keep_aspect = KEEP_HEIGHT`）。本任务相机固定在 `(0, 1.6, 0)` 看向 −Z。删除 T01 的临时测试场景。
5. `tests/fixtures/box_room.json`：一个宽 10、高 4、长 20 的房间（地面、两侧墙、尽头墙，沿 −Z 延伸），3 个高低不同的箱子、1 根圆柱、2 个 marker。后续任务的测试都可用它。

**必测**（`tests/test_level_loader.gd`）

- `box_room.json` 加载成功，`blockers` 数量等于 solid 几何数量。
- 分别构造 format 错误、重复 id、未知 material、负尺寸、未知 shape —— 各自 `ok == false` 且 errors 含可读原因。
- 从 `(0, 1.6, 0)` 向 −Z 的射线，对 `blockers` 逐个 `ray_shape`，最近命中是尽头墙，t 与手算距离一致。
- `world_view.build` 之后 `MeshInstance3D` 数量等于 geometry 数量（需要 `tree`：把节点加到 `tree.root` 后断言，结束时 `queue_free`）。

**截图自检**：`--level=res://tests/fixtures/box_room.json --shot=...`。能看出房间纵深、箱子有阴影、不同材质可分辨、画面无过曝。

---

## T06 轨道相机

**目标**：镜头按关卡数据沿轨道运动。Sim 相机是唯一事实来源。

**格式**：`rail` 是段的有序数组。

```json
[
  {"id": "s0_intro", "type": "move", "duration": 4.0, "ease": "smooth",
   "camera": [
     {"t": 0.0, "pos": [0, 1.6, 0],  "look": [0, 1.5, -10]},
     {"t": 4.0, "pos": [0, 1.6, -6], "look": [0, 1.4, -16]}
   ]},
  {"id": "s1_alley", "type": "hold", "timeout": 45.0,
   "camera": [{"t": 3.0, "pos": [0.3, 1.6, -6], "look": [0.5, 1.4, -16]}]}
]
```

- `type`：`move` 到 `duration` 结束。`hold` 由导演决定何时结束（T10）；本任务里先在 `timeout` 到时结束。
- `camera` 关键帧的 `t` 是段内秒数。每段在 `t = 0` 处有一个隐含关键帧，等于上一段结束时的姿态；第一段必须显式给出 `t = 0`。关键帧可带 `fov`（默认 60）。
- 位置：关键帧之间用 Catmull-Rom（首尾端点重复）。`look` 目标点与 `fov` 线性插值。
- `ease`：`"linear"`（默认）或 `"smooth"`（仅move）。对每两个相邻关键帧之间的局部归一化时间做 smoothstep，再用于位置/look/fov插值，保证中间关键帧时刻仍命中给定姿态。
- 最后一个关键帧之后保持不动。hold 段可以没有关键帧；有关键帧时，正常清场离段不得早于最后关键帧（先清场则停止新攻击并等镜头走完），以保证下一段缓存的起始姿态连续。关键帧t不得超过duration/timeout。hold 的关键帧只用来让镜头到位（最后一个 t 建议 ≤ 3 秒），不要用关键帧做持续漂移，否则该段无法早于最后关键帧结束。
- 持续漂移用 hold 段的可选字段 `"drift": {"amp": [0.4, 0, 0], "period": 8.0}`：最后一个关键帧之后，相机位置叠加 `w · amp · sin(2π·τ/period)`，`amp` 是世界坐标下的米，τ 是最后关键帧之后的秒数，`look` 目标不变。权重 `w` 保证离段时相机回到关键帧终点姿态，取三项的最小值，每项都钳制在 0–1：`漂移已进行的 tick / 60`（淡入）；`(timeout tick − seg_tick) / 60`（超时前淡出）；清场后的 `(离段 tick − seg_tick) / 60`（清场淡出，未清场时这一项为 1；离段 tick 由 T10 的导演给出）。`w` 是 seg_tick 和离段 tick 的纯函数，不需要另存状态。限制：`amp` 长度 ≤ 1.0 米，`period` ≥ 4 秒，只允许出现在 hold 段。
- 最后一段结束后发 `rail_end` 事件。rail 为空的关卡（只用于结构夹具）进入 playing 后相机固定在 `(0, 1.6, 0)` 看向 −Z，不发 `rail_end`，不会自行结束。

**交付**

1. `sim/rail.gd`：`setup(segments)`；`pose_at(segment_index: int, seg_tick: int, exit_tick: int = -1) -> Dictionary`（`{"pos", "look", "fov"}`）。`exit_tick` 是已确定的离段 tick，只用于漂移权重，未清场时传 −1。内部缓存每段的起始姿态（不含漂移）。
2. `sim/camera_rig.gd`：由姿态计算 `transform: Transform3D`（`looking_at`，上方向 +Y）与 `fov`。提供：
   - `screen_ray(content_px: Vector2) -> Dictionary`：`{"origin", "dir"}`。`ndc = px / (1776, 936) * 2 - 1`，`dir = basis * Vector3(ndc.x * tan(fov/2) * aspect, -ndc.y * tan(fov/2), -1)` 归一化，`aspect = 1776/936`。
   - `project(world: Vector3) -> Dictionary`：`{"px": Vector2, "depth": float, "in_front": bool}`，是 `screen_ray` 的逆。
   - `px_per_meter(depth: float) -> float`：`936 / (2 * depth * tan(fov/2))`。
3. `sim_world`：playing 阶段每 tick 推进 `seg_index`、`seg_tick`，更新 `camera`。段切换时发 `segment_enter {id, index}`。新增 `seek(segment_id)`：直接跳到该段开头并重置该段状态（开发用）。snapshot 包含段索引与段内 tick。
4. `view/game_view.gd`：每帧把 Sim 相机的 transform 和 fov 拷给 `Camera3D`。title 阶段显示第一段 `t = 0` 的姿态。
5. 关卡加载器校验 rail：id 唯一、type 合法、move 有正的 duration、hold 有正的 timeout、关键帧 t 非负且递增、第一段有 `t = 0`、`pos` 与 `look` 不重合且视线不与上方向平行，fov在(0,180)内，关键帧不超过段的时限，`drift` 只在 hold 段且满足上面的限制；空rail只供结构夹具，playable须非空。
6. 给 `box_room.json` 加 3 段轨道：move 4 秒前进 → hold（timeout 3 秒）→ move 3 秒并向右转。

**必测**（`tests/test_rail.gd`）

- 关键帧时刻的姿态等于关键帧值。段间连续：上一段最后一个 tick 与下一段第 0 tick 的 `pos` 距离 < 0.05。
- `smooth` 段首尾两个 tick 的位移都小于中段单 tick 位移的 20%。
- `project(origin + dir * 5)` 的 `px` 与传入 `screen_ray` 的像素一致（多点、多姿态，误差 < 0.01 像素）。
- 相机后方的点 `in_front` 为假。
- 把 `Camera3D` 加到尺寸 1776×936 的 `SubViewport`（需 `tree`，并等一帧），其 `project_ray_normal(px)` 与 `screen_ray(px).dir` 在 5 个像素点上的差 < 1e-4。
- 跑完三段后收到 `rail_end`。`seek` 到第二段后段索引与相机姿态正确。
- 漂移：给一个 hold 段加 `drift`（amp `[0.4,0,0]`、period 4、timeout 10）。段中相机相对关键帧终点的最大偏移不小于 0.35 米、不超过 0.4 米（容差 1e-6）；`seg_tick` 等于 timeout 对应的 tick 时偏移 < 1e-6；传入 `exit_tick` 后，`seg_tick` 等于它时偏移同样 < 1e-6；下一段第 0 tick 与上一段最后一个 tick 的 `pos` 距离 < 0.05。

---

## T07 调试接口与截图

**目标**：让后续任务能自动驱动游戏、截图、自检。

**交付**

1. 命令行参数（`main.gd` 解析 `OS.get_cmdline_user_args()`）：
   - `--level=<路径>`
   - `--segment=<段 id>`：启动后直接进入 playing 并 seek 到该段
   - `--fixed`：启动即冻结，只能由调试接口或脚本推进
   - `--mute`、`--profile=monitor|tv`、`--window=<宽>x<高>`
   - `--script-run=<json 路径>`：按脚本自动执行（见第 3 点）
2. `dev/dev_server.gd`：只监听 `127.0.0.1` 的 TCP，端口默认 19020，可用 `--dev-port=<端口>` 或构造参数改。端口被占用时打印一条警告并继续运行（不启用调试接口），不要崩溃。每行一个 JSON 请求，每行一个 JSON 回应。仅在 `OS.is_debug_build()` 时启用。命令：
   - `{"cmd":"state"}` → tick、phase、段、相机、玩家、各实体摘要、`hash`
   - `{"cmd":"freeze","on":true}`
   - `{"cmd":"step","n":60}`：冻结时推进 n tick，回应最新 state
   - `{"cmd":"input","event":"SHOT","x":888,"y":468}`：x、y 为内容像素，注入到下一 tick。也接受 RELOAD、START、COIN
   - `{"cmd":"seek","segment":"s1_alley"}`
   - `{"cmd":"set","key":"invincible","value":true}`：key 可为 `invincible`、`timescale`、`god_ammo`
   - `{"cmd":"capture","path":"<绝对路径.png>","what":"window"}`：`what` 为 `window` 或 `content`，等下一帧绘制完再保存
   - `{"cmd":"quit"}`
   - 调试开关（invincible 等）不属于 Sim 状态。
   - `main.gd` 维护一个 `session_clean` 标记。使用过 `--segment`、`seek`、`set`、`step`、`freeze`、`--force` 或 `--fixed` 中的任何一个，本次运行即标记为不干净，之后不写回放（T16）。经调试接口或脚本注入的 `input` 走正常输入通道，不影响该标记。所有内容坐标 SHOT 缺省 in_content 时由 1776×936 边界推导；记录进入 Sim 的完整事件。
3. `--script-run` 的脚本：`{"steps":[{"wait":120},{"input":{"event":"SHOT","x":888,"y":468}},{"seek":"s1"},{"set":{"key":"invincible","value":true}},{"capture":"<路径>","what":"content"},{"quit":true}]}`。`wait` 单位是 tick。这是截图自检的主要方式，不需要另开 TCP 客户端。
4. `gunforge3d/tools/capture.ps1`：参数 `-Level`、`-Segment`、`-Wait <tick>`、`-Out <png>`、`-What window|content`，生成临时脚本并调用游戏完成一次截图。
5. 删除 T01 的临时 `--shot` 参数。

**必测**（`tests/test_dev.gd`）

- 脚本解析：合法脚本得到步骤数组；未知步骤类型报错。
- 在测试里创建 `dev_server`（Sim 用 `box_room`，端口用 19021，避免与正在运行的游戏抢 19020），用 `StreamPeerTCP` 连接它，测试手动调用服务器的 `poll()`：`state` 得到含 `tick` 的回应；`freeze` 后 `step 10` 使 tick 增加 10；`input START` 使 phase 变为 playing；`seek` 后段索引改变。

**截图自检**：用 `capture.ps1` 对 `box_room` 的三段各截一张，确认镜头位置随段变化。

---

## T08 射击核心

**目标**：开枪、弹药、换弹，以及打在世界上的反馈。

**交付**

1. `sim/player.gd`：`life`、`ammo`、`reload_ticks_left`、`fire_cooldown`、`invuln_ticks`、`shots_fired`、`shots_hit`。数值来自 rules。
2. `sim/shooting.gd`：`resolve(world, content_px) -> Dictionary`。
   - 用 `camera.screen_ray` 取射线，对所有候选形状求最近命中。候选顺序固定；t 完全相同按 kind、id、part 的字典序打破平局。
   - 候选由 `world.collect_targets() -> Array` 收集，每项 `{"shape", "kind", "id", "part", "zone"}`。`id` 是实体 id，`part` 是部件名（没有部件的实体为空串）。本任务只有世界 `blockers`（kind `"world"`，id 为几何 id），后续任务追加角色部件、投射物、道具、拾取物。
   - 返回 `{"kind": "world"|"none"|..., "pos", "normal", "t", "id", "part", "zone"}`。被命中的是哪个实体的哪个部件，一律由求交结果携带，后续代码不得根据命中位置反推。
   - `assist_px > 0` 时，非世界目标的球与胶囊半径增加 `assist_px / px_per_meter(depth)`。首版为 0，但代码路径要有并有测试。
3. `sim_world.step` 处理输入（仅 playing 阶段）：
   - SHOT：换弹中或射击冷却中 → 忽略。`ammo == 0` → 事件 `dry_fire`。否则 `ammo -= 1`、`shots_fired += 1`、事件 `shot_fired {px}`；`in_content` 为真时 resolve，命中世界发 `impact_world {pos, normal}`，什么都没中发 `shot_miss`；`in_content` 为假时发 `shot_miss`。
   - RELOAD：`ammo < 弹匣容量` 且不在换弹中 → 开始换弹，事件 `reload_start`；计时结束 `ammo = 容量`，事件 `reload_done`。
4. `view/fx.gd`（`Node3D`）：按事件生成短命特效。特效用自己的 `RandomNumberGenerator`。
   - `shot_fired`：从镜头右下方到命中点（或射线 60 米处）的细弹道线（0.06 秒），以及镜头右下方一个 0.05 秒的小 `OmniLight3D` 闪光。
   - `impact_world`：命中点一个深色小圆片弹孔（贴合法线，保留 10 秒，最多 64 个，超出回收最旧的；用薄圆片 `MeshInstance3D` 实现，沿法线抬高约 1 厘米防止闪烁，不用 `Decal` 节点，Compatibility 渲染器不支持它，后续美术阶段会用到该渲染器），加 6–10 个向法线半球飞散并受重力下落的小方块碎屑（0.5 秒）。
5. `hud/hud.gd`（`Control`，挂在 `Content` 下，绘制在 3D 之上）：
   - `Content` 固定为 1776×936，HUD 直接用内容像素布局，不做额外缩放；整体缩放由 Shell 的 TextureRect 完成。
   - 准星：跟随 `input_router` 的 aim（转成内容像素）。十字加圆环，开枪时短暂扩张。aim 在内容区外时不显示。
   - 右下弹药：8 个子弹图标（自绘矩形），已用的变暗。弹匣空时屏幕中下方闪烁"换弹！（右键 / R）"。换弹中显示进度条。
6. `main.gd` 的 `_dispatch` 把事件分发给 `fx` 和 `hud`。

**必测**（`tests/test_shooting.gd`，用 `box_room`）

- 对准尽头墙开枪：事件含 `shot_fired` 和 `impact_world`，`pos` 在墙面上，弹药减 1。
- 连开 8 枪（间隔满足冷却）后第 9 枪为 `dry_fire`，弹药不为负。
- 间隔小于射击冷却的第二枪被忽略（弹药只减 1）。
- 换弹期间开枪被忽略；到时弹药回满；满弹时 RELOAD 无效果。
- `in_content == false` 的 SHOT 扣弹但没有 `impact_world`。
- 朝没有几何的方向开枪得到 `shot_miss`。
- title 阶段的 SHOT 不扣弹。title 阶段同一 tick 的 START 和 SHOT：进入 playing，弹药仍是满的。
- 计时边界（规则见 T03 第 8 步）：第 k tick 开枪后，第 k+5 tick 的 SHOT 被忽略，第 k+6 tick 的可以开枪（0.1 秒 = 6 tick）。第 k tick 开始换弹，第 k+47 tick 的 SHOT 被忽略，第 k+48 tick 的 SHOT 能打出（0.8 秒 = 48 tick），且该 tick 的事件里 `reload_done` 在 `shot_fired` 之前。
- `assist_px`：构造一个球形非世界目标，射线从其外侧 3 像素处擦过。`assist_px = 0` 不中，`assist_px = 5` 命中。

**截图自检**：脚本在 `box_room` 中对墙和箱子开 5 枪后截图，能看到弹孔贴花、弹药图标减少。

---

## T09 角色、部件与姿态

**目标**：由图元拼成的人形角色，部件级命中，受伤与死亡。行为在 T10。

**交付**

1. `data/archetypes.json`。本任务写 `dummy`（站立不动的靶人，`behavior: "none"`）和 `gunner` 的身体定义：

```json
{
  "gunner": {
    "body": "humanoid", "team": "enemy", "hp": 2, "behavior": "gunner",
    "colors": {"torso": "#b5483f", "head": "#d9a441", "limb": "#8c3a33", "gear": "#3a3d42"},
    "params": {}
  }
}
```

2. `sim/pose_lib.gd`：
   - `HUMANOID` 部件表。根在脚底中心，局部 +Z 为角色的正面：

     | 部件 | 形状 | 局部中心 | zone |
     |---|---|---|---|
     | head | sphere r=0.17 | (0, 1.60, 0) | weak |
     | torso | box 0.46×0.62×0.26 | (0, 1.12, 0) | body |
     | leg_l / leg_r | capsule r=0.09，总高 0.82 | (∓0.12, 0.41, 0) | body |
     | arm_l / arm_r | capsule r=0.07，总高 0.60 | (∓0.31, 1.15, 0) | body |
     | gun | box 0.08×0.10×0.40 | (0.31, 1.20, 0.28) | none（不参与命中） |

   - `part_shapes(body: String, pose: String, pose_t: float, root: Transform3D, extra := {}) -> Array`：每个部件返回 `{"name", "zone", "shape": <geom shape，世界坐标>, "xform": Transform3D, "mesh": {"type", ...尺寸}, "color_key"}`。Sim 用 `shape` 判定，View 用 `xform` 与 `mesh` 渲染。**两者必须来自这同一个函数**，这是"所见即所中"的保证。
   - 姿态（`pose_t` 为进入该姿态后的秒数）：
     - `idle`：直立，躯干轻微起伏（y ±0.01，周期 2 秒）。
     - `run`：腿前后摆（±35°，周期 0.5 秒），手臂反向摆，整体上下 ±0.04。
     - `crouch`：整体下沉 0.75 米并前倾 15°（躲在掩体后）。
     - `aim`：直立，右臂与枪前伸指向正面。
     - `flinch`：上身后仰 20°，0.4 秒内回正。
     - `die`：0.5 秒内绕脚底向后倒 85°，之后保持。
     - `hands_up`：双臂上举（人质）。`cower`：下沉 0.6 米，双臂抱头（人质）。
     - `held`：被挟持的人质。整体下沉 0.30 米（头部中心高 1.30，头顶 1.47），双臂垂在身后，不上举。这样身后挟持者的头（中心高 1.60）能从人质头顶上方露出。
     - `strike`：右臂上举后向前劈下。`throw`：右臂后引再前挥。两者都以 `extra.progress`（0–1）驱动，不用 `pose_t`。
3. `sim/actor.gd`：`id`、`archetype`、`team`、`pos: Vector3`、`yaw: float`、`pose`、`pose_tick`、`hp`、`alive`、`state`、`state_tick`、`despawn_ticks`、`params`、`mem: Dictionary`（行为的私有状态）。方法 `root_transform()`、`shapes()`、`snapshot()`。
4. `sim_world`：
   - `actors: Array`；`spawn_actor(spec) -> Actor`，事件 `actor_spawn {id, archetype, pos}`。
   - `collect_targets` 加入存活角色中 zone 不为 `none` 的部件。
   - `apply_hit(actor, part, zone, pos)`：`weak` 伤害等于当前 hp；`body` 伤害 1；`armor` 无伤害并发 `armor_hit {id, part, pos}`。非装甲命中发 `hit_actor {id, part, zone, pos, killed}` 且仅在直接SHOT路径 `shots_hit += 1`（爆炸/脚本伤害不增加）。`part` 一路传到行为的 `on_hit`（T19 的 Boss 依赖它区分左右导弹舱与核心）。
   - 死亡：`alive = false`、姿态 `die`、事件 `actor_die {id, zone}`，1.5 秒后移除并发 `actor_remove {id}`。死亡的角色不再参与命中。
5. `view/actor_view.gd` 与 `view/actors_view.gd`：每个角色一个 `Node3D`，按部件生成 `MeshInstance3D`，每帧从 Sim 读部件变换。受击时全身 0.08 秒提亮。死亡的最后 0.5 秒透明淡出。按 `actor_spawn`、`actor_remove` 增删。
6. `fx`：`hit_actor` 在命中点喷出该部件颜色的碎屑；`weak` 命中额外一圈放射状亮黄火花；`armor_hit` 为冷色火星。
7. 关卡顶层支持 `"debug_actors": [{"id", "archetype", "marker" 或 "pos", "yaw", "pose"}]`，进入 playing 时直接生成，供测试与截图。给 `box_room.json` 放 2 个 `dummy`：一个完全露出，一个站在箱子后只露上半身。

**必测**（`tests/test_actors.gd`）

- 一致性：5 个姿态各取 3 个时刻，`part_shapes` 返回的 `shape` 中心（球心、盒中心、胶囊 a 与 b 的中点）与 `xform.origin` 一致。
- 对准 dummy 头部中心的投影像素开枪 → `hit_actor`，part 为 `head`，zone 为 weak，killed 为真。打左臂时 part 为 `arm_l`。
- 打躯干两枪才死；第一枪后 `alive` 为真。
- 箱子后的 dummy：瞄其腿部位置开枪，命中的是世界，角色不掉血。
- `crouch` 姿态下头部中心比 `idle` 低 0.6 米以上。
- 死亡 1.5 秒后角色从 `actors` 移除；死亡期间再射同一位置不产生 `hit_actor`。
- 2 枪命中 1 枪落空 → `shots_fired == 3`、`shots_hit == 2`。

**截图自检**：`box_room` 中两个 dummy 可辨认为人形，头部颜色醒目。再截一张击中后的倒地。

---

## T10 导演、射手与受伤

**目标**：数据驱动的出怪与波次、攻击令牌、第一种敌人行为、玩家受伤。到此可以玩到第一个完整战斗点。

**格式**：段内新增字段。

```json
{"id": "s1_alley", "type": "hold", "timeout": 45, "tokens": 2,
 "spawns": [
   {"id": "s1_g1", "archetype": "gunner", "wave": 0, "at": 0.5,
    "from": "a1_door", "to": "a1_crate_l", "enter": "run",
    "required": true, "params": {"windup": 1.8, "first_delay": 1.0}}
 ],
 "waves": [{"wave": 1, "when_remaining": 0, "delay": 0.8, "tokens": 2}],
 "cues": [{"at": 0.0, "type": "caption", "text": "射击头部可一枪毙命", "duration": 3.0}]
}
```

- `spawns[].wave` 默认 0；`at` 是相对该波开始的秒数。`from`、`to` 引用 marker；可用 `path: ["m1", "m2"]` 给出途经点。
- `enter`：`"run"`（从 from 经 path 跑到 to）、`"popup"`（直接出现在 to，处于隐藏姿态）、`"side"`（从 from 侧移到 to，面朝相机）。
- `required` 对敌人默认true，决定是否计入清场；人质强制false。`params` 覆盖原型参数。spawn.id 在全关唯一，wave索引连续，at≥0且不得超出所属段时限；held captor须同波同时或先生成，不允许未解析引用。
- `waves` 可省略。第 0 波在段开始时启动。第 n 波在第 n−1 波的 spawn 全部生成、且其中 required 的存活数 ≤ `when_remaining`（默认 0）之后再过 `delay`（默认 0.5 秒）启动。`tokens` 若给出，从该波开始覆盖段的令牌数。
- hold 段结束：所有波已启动并生成完毕，且所有 required 敌人死亡 → 事件 `segment_clear`，达到 `max(清场tick+60, 最后相机关键帧tick)` 后进入下一段。清场后取消本段全部剩余攻击、清除投射物，非required敌人逃离。到 `timeout` 仍未清场 → 存活敌人进入 `flee`，事件 `segment_timeout`，进入下一段。带 `drift` 的段清场时把离段 tick 传给 `rail.pose_at`，漂移在离段等待内淡出（T06），离段时相机回到基准姿态。没有任何 required 敌人、也没有入段 carry 敌人和 Boss 的 hold 段（只会出现在结构夹具里）不算清场，等到 `timeout` 结束，不发 `segment_clear`。
- move 段：所有 spawn 视为第 0 波，按 `at` 生成。段结束时仍存活的敌人，spawn 上有 `"carry": true` 的带入下一段并计入其清场，其余进入 `flee`。
- `cues`：本任务只实现 `caption {text, duration}`。

**交付**

1. `sim/director.gd`：管理当前段的波次、生成、清场、超时与令牌。snapshot 完整。
   - **令牌规则**：导演记录每个令牌的持有者（角色 id 或投射物 id）。`request_token(owner_id) -> bool`；`release_token(owner_id, cooldown_ticks)` 是幂等的，持有者没有令牌时什么也不做；冷却结束后该令牌才可再被申请。`transfer_token(from_id, to_id)` 用于投掷兵把令牌交给投射物。
   - 持有者以任何方式结束攻击都必须释放：攻击结算、被打断、死亡、逃跑、被移除。导演在角色或投射物被移除时兜底调用一次 `release_token`。换段与续关时清空全部令牌与冷却。换段先清除旧投射物与待爆炸队列，取消所有旧预警；carry 角色保留 hp/位置并回到其非攻击待机状态（gunner 为 hidden，thrower 为 idle，rusher 追赶，shield 为 advance），重新等待首次攻击延迟后申请新段令牌。令牌数降低时不回收正在使用的令牌，但在占用数加冷却数低于新上限前禁止新申请。
   - `world.threat_visible(actor) -> bool`：取当前攻击姿态可伤害部件的中心（人形至少头、躯干、腿；Boss 见 T19），至少一个位于相机前方、内容安全框内，且对全部候选形状求交的首个命中是该角色的非装甲部件。人质、其他角色、盾和道具均可阻挡。隐藏状态用即将进入的攻击姿态预检，不能因 crouch 被挡而永远不探身。
2. `sim/behaviors/registry.gd`（行为名 → 脚本）与 `sim/behaviors/gunner.gd`。行为脚本只有静态函数，状态都存在 actor 上：`enter(world, actor)`、`tick(world, actor)`、`on_hit(world, actor, part, zone)`、`on_death(world, actor)`。
3. 射手状态机。参数与默认值：`windup` 1.6、`hide` 1.2、`first_delay` 0.8、`expose_lead` 0.3、`cooldown` 1.0、`speed` 4.0（米/秒）、`use_cover` true。
   - `entering`：沿 from → path → to 以 `speed` 移动，姿态 `run`，朝向移动方向。`popup` 直接到位。
   - `hidden`：姿态 `crouch`（`use_cover` 为 false 时 `idle`），持续 `hide`（首次为 `first_delay`）。之后申请令牌，拿不到则每 0.2 秒重试。
   - `windup`：拿到令牌，转为 `aim` 并面向相机，事件 `attack_windup {id, ticks}`。持续 `expose_lead + windup`。
   - **预警要求连续可见**：进入 windup 时须通过可见性预检。之后每 tick 按当前姿态检查；失去可见性即把剩余预警重置为完整时长并发一次 `attack_hold {id}`，可见恢复时发 `attack_resume {id, ticks}` 并从完整时长重新计时。不能累积碎片化可见时间。连续4秒不可见则取消攻击、释放令牌（0.6秒冷却）并回到非攻击等待状态。冲锋兵、投掷兵、盾兵同样执行。预警及攻击在该状态已至少显示一个 tick 后才能结算。
   - `fire`：事件 `attack_fire {id}`，调用 `world.damage_player(1, actor)`，**立即**释放令牌（冷却 0.6 秒）。然后保持 `aim` 共 `cooldown` 秒，回到 `hidden`。
   - `on_hit`（未死）：若在 `windup`，事件 `attack_cancel {id}`。无论处于哪个状态都调用一次 `release_token`（幂等）。进入 `flinch` 0.4 秒后回到 `hidden`。
   - `on_death`：若持有令牌立即释放（0.6秒冷却）；若在 `windup`，发 `attack_cancel`。
   - `flee`：朝 from 跑，到达或 2 秒后移除，不再攻击，仍可被击中。
   - 不移动时角色始终面向相机的水平方向。
4. `world.damage_player(amount, source)`：无敌中 → 忽略。否则 `life -= amount`，设置无敌时间，事件 `player_hurt {life, source_id}`。`life <= 0` → phase 变为 `"continue"`，事件 `player_down`（续关流程在 T13，本任务里 `continue` 阶段不做任何事）。
5. 调试开关 `invincible`：`damage_player` 不扣血，但仍发 `player_hurt`。
6. HUD：
   - 左下生命：5 个图标。受伤时丢失的那格闪烁。
   - 预警圈：监听 `attack_windup`、`attack_hold`、`attack_resume`、`attack_cancel`、`attack_fire`、`actor_die`；剩余 tick 读取 Sim，不能用渲染时间独立倒数。圆心为该角色躯干中心的投影（每帧用 Sim 相机重新投影）。半径从 90 内容像素线性收缩到 26，颜色由黄渐变到红，最后 0.3 秒快速闪烁。圆心画一个小感叹号。
   - 受伤：全屏红色暗角 0.5 秒（峰值不透明度 0.45）。
   - 字幕：屏幕上方居中，半透明黑底。
7. View：受伤时仅让边缘暗角、弹药图标和非瞄准装饰轻震（≤6 内容像素、0.15 秒）。Camera3D、活体部件、准星和预警圈不叠加独立位移。
8. `tests/fixtures/arena_gunner.json`：一个小场地，一段 hold，两波共 4 个射手，2 个掩体箱。所有 `arena_*` 夹具到 T17 都要通过 playable 校验，现在就按那里的约束摆：敌人站位距相机 5–11 米、暴露时头部在安全框内且不被遮挡、相机离 solid 表面 ≥ 0.25 米、hold 的 timeout ≤ 90 秒。

**必测**（`tests/test_director.gd`、`tests/test_gunner.gd`）

- 无输入运行 `arena_gunner`：第一个 `attack_windup` 之后 `expose_lead + windup` 秒出现 `attack_fire` 和 `player_hurt`，生命减 1。
- 无敌时间内的第二次 `attack_fire` 不扣血。
- 令牌：`tokens` 为 1、3 个射手，逐 tick 断言处于 `windup` 的不超过 1 个。
- 在 `windup` 期间打其躯干：出现 `attack_cancel`，该次不出现 `attack_fire`，随后另一个射手能进入 windup。
- `windup` 期间爆头：`attack_cancel` 加 `actor_die`，玩家不掉血。
- 第 1 波在第 0 波 required 全灭后才生成；全部击杀后出现 `segment_clear` 并进入下一段。
- `timeout` 为 5 秒且不开枪：出现 `segment_timeout`，敌人进入 flee 并被移除。
- 在箱子后 `hidden` 的射手：朝它站立时头部的位置开枪打不中它；`windup` 时可以打中头。
- move 段里 `carry: true` 的敌人进入下一段后仍存活并计入清场。
- 令牌不泄漏：`tokens` 为 1、2 个射手。第一个开火后，在它的 `cooldown` 期间打它躯干一枪（不致死）；之后第二个射手仍能进入 windup。再测：持有令牌的射手在 windup 中进入 flee（段超时），令牌被释放。
- 可见性：把一个射手的站位放在一堵墙后（完全不可见）。预检失败不申请令牌；将已开始预警的射手遮住则重置预警，4 秒后取消并释放令牌。把站位放在画面外同理；0.2 秒可见/0.2 秒不可见反复切换时不得累计到开火。
- 同 tick 顺序：在 windup 的最后一个 tick 送入致命的 SHOT，玩家不掉血。
- 带 `drift` 的 hold 段在漂移中途清场：离段前最后一个 tick，相机位置与该段关键帧终点的距离 < 0.02 米；下一段第 0 tick 的位置等于关键帧终点。
- 同一输入序列两次运行哈希一致。

**截图自检**：`arena_gunner` 中预警圈的黄色大圈与红色小圈各一张，受伤暗角一张。

**人工试玩点**：提供 `play_3d.cmd --level=res://tests/fixtures/arena_gunner.json`，请用户留意瞄准、预警和节奏，记录到 PROGRESS。继续可独立完成的后续任务；除非用户明确要求等待，不以尚无试玩反馈阻断开发。T15 再提供一次反馈预览，T20 的人工判断单独标为待确认。

---

## T11 冲锋兵、投掷兵与投射物、盾兵

**目标**：补齐三种敌人。

**交付**

1. `archetypes.json` 增加 `rusher`、`thrower`、`shield`。三者与射手一眼可分：冲锋兵躯干 `#8e4a9c`，投掷兵 `#c9762c`，盾兵躯干 `#6b4a3a`、盾 `#4a5058`。
2. `sim/behaviors/rusher.gd`。参数：`speed` 5.5、`hp` 3、`melee_range` 2.2、`windup` 0.7、`interval` 1.5、`slow_time` 0.5、`slow_factor` 0.4。
   - 沿 from → path 跑，之后直奔"相机位置水平前方 `melee_range` 米处的地面点"。该目标每 tick 按当前相机重算，镜头移动时它会追。
   - 到位后申请令牌 → `windup`（姿态 `strike`，progress 0→0.6；事件 `attack_windup`）→ 劈下（progress →1），`damage_player(1)`，事件 `attack_fire` → 归还令牌（冷却 0.6 秒）→ 等 `interval` 再来。
   - 受击（未死）：`slow_time` 内速度乘 `slow_factor`。若在 windup，本次攻击的 windup 重新计时（每次攻击最多重置 1 次）。
3. `sim/projectile.gd` 与 `world.projectiles`：`id`、`pos`、`vel`、`gravity`、`radius`（判定 0.30）、`owner_id`、`ticks_left`、`damage`、`token_owner`。
   - 抛物线：给定起点、终点（发射瞬间相机位置下方 0.2 米）与飞行时间，解出初速度。`gravity = 0` 时为直线。
   - 到期攻击采用街机威胁计时语义：飞行结束 → `damage_player`，事件 `projectile_hit_player {id}`；不另做与移动相机的物理接触判定。HUD 明确表示剩余威胁时间，不能因终点与当前相机不同而提前消失。换段/续关/Boss 击毁时无伤清除。
   - `collect_targets` 加入球形目标（kind `"projectile"`）。被击中 → 移除，事件 `projectile_destroyed {id, pos}`，`shots_hit += 1`。
   - 生成时事件 `projectile_spawn {id, ticks}`。
4. `sim/behaviors/thrower.gd`。参数：`windup` 1.0、`flight` 1.6、`interval` 2.5、`hp` 2。
   - 到位后站立（`idle`）。申请令牌 → `throw` 姿态持续 `windup`（事件 `attack_windup`）→ 从右手位置生成投射物，事件 `attack_fire`。
   - 投出时用 `transfer_token` 把令牌交给投射物。投射物结束（被击落、命中或被清除）时释放。投掷兵此后死亡不影响这个令牌。飞行中不再申请令牌；结束后等待 interval 再预警。所有释放使用 0.6 秒冷却；删除兜底不延长已有冷却。
   - `windup` 期间受击：发 `attack_cancel`、归还令牌，`flinch` 0.4 秒后等待 interval。
5. `sim/behaviors/shield.gd`。参数：`speed` 1.2、`hp` 3、`windup` 1.2、`interval` 3.0、`stop_range` 4.0。
   - 身体：humanoid 追加部件 `shield`，box 0.70×1.20×0.08，zone `armor`。举盾时中心 (0, 1.23, 0.38)；放下时中心 (−0.55, 1.23, 0.10)。盾覆盖 0.63–1.83 米高度，挡住躯干和头；下沿离地 0.63 米，腿始终可打。下沿不能再低：相机在 1.6 米高、4 米外看腿部中心（0.41 米）的视线，在盾面处高约 0.54 米，下沿低于这个值时瞄腿中心会打在盾上。
   - `advance`：举盾，姿态 `run`（慢速）走向相机，到 `stop_range` 停下。每 `interval` 申请令牌 → `windup`：放下盾，姿态 `aim`，暴露躯干和头，事件 `attack_windup` → 到时 `damage_player(1)`、发 `attack_fire`、释放令牌（冷却 0.6 秒）→ 重新举盾。
   - windup 期间受击（未死）：发 `attack_cancel`、释放令牌（冷却 0.6 秒）并举盾。
6. View 与 HUD：投射物为深色球加一圈红色环，拖短尾迹。HUD 在飞行中的投射物上画跟随的红色菱形标记，剩余 < 0.5 秒时闪烁。`projectile_destroyed` 有小爆点特效。
7. 夹具 `arena_mixed.json`：三段 hold，分别只有冲锋兵、投掷兵、盾兵；再加一段镜头移动的 move，其中有 1 个冲锋兵。

**必测**（`tests/test_enemies.gd`）

- 冲锋兵：不开枪时到达并造成伤害；3 枪身体击杀；受击后 0.5 秒内的位移小于未受击时的 60%；在 move 段里仍能追到近战距离。
- 投掷兵：`windup` 后生成投射物；`flight` 秒后命中玩家；按其投影位置开枪可击落且玩家不掉血；击落后令牌归还。投射物飞行途中击杀投掷兵：令牌仍由投射物持有，投射物结束后才释放，且只释放一次。
- 投射物轨迹：终点与目标点距离 < 0.05 米，最高点高于起点与终点。
- 盾兵：相机高 1.6 米，距离 4 米和 10 米各测一次。举盾时瞄躯干与头部中心 → `armor_hit`，不掉血，`shots_hit` 不增加；瞄任一条腿的中心 → `hit_actor`，part 为该腿，掉血；`windup` 时可爆头。
- 三个 hold 段都能被"威胁一出现就击杀"的测试脚本无伤通过（测试里直接读 Sim 状态算瞄点）。

**截图自检**：三种敌人各一张，投射物飞行中一张。确认三者可区分，盾清楚可见。

---

## T12 人质、可破坏物与拾取

**交付**

1. `archetypes.json` 增加 `hostage`：躯干 `#3f8fb5`、头 `#e8e2d0`，team `hostage`，无 gun 部件，所有部件 zone 为 `hostage`。
2. `sim/behaviors/hostage.gd`，由 spawn 的 `params.mode` 决定：
   - `"cower"`：在 `to` 处保持 `cower`，直到段结束。
   - `"run_across"`：`hands_up` 姿态从 from 跑到 to（`speed` 3.0），到达后获救并移除。
   - `"held"`：`params.captor` 指向同段某敌人的 id。人质站在挟持者与相机之间：挟持者位置朝相机水平方向 0.35 米处，不侧偏，姿态 `held`（见 T09），始终面向相机。挟持者不移动、不蹲下（其 `use_cover` 被强制为 false），头部从人质头顶上方露出，躯干被人质挡住。
   - 被击中：事件 `hostage_hit {id, pos}`；`life -= 1`（无视无敌时间，也不刷新无敌时间；生命归零照常进入 `continue`）；人质 `die` 并移除；不计 `shots_hit`。
   - 获救：`cower` 在段清场时；`run_across` 到达终点时；`held` 在挟持者死亡时。事件 `hostage_rescued {id, pos}`，`life = min(life + 1, 上限)`。
   - 人质不计入清场。段超时时未获救的人质无奖励地移除。
3. 关卡顶层 `props`：`{"id", "type": "barrel"|"crate", "pos", "yaw", "segment": "<段 id，可省略>", "contains": "medkit"|"medal"|null}`。`pos` 是底面中心。带 `segment` 的道具从进入该段起才存在。
   - `barrel`：cylinder r=0.3、h=0.9，颜色 `#c8622a`，中部一圈深色箍。1 枪引爆：事件 `explosion {pos, radius}`。半径 3.5 米内（按角色根位置上方 1 米处计算）的敌人受 5 点伤害（击杀 zone 记为 `explosion`）；人质按被击中处理；其他油桶延迟 0.15 秒连锁；投射物被摧毁。不伤玩家。
   - `crate`：box 0.7×0.7×0.7，颜色 `#a58a5c`。2 枪击碎（事件 `prop_hit`、`prop_break {id, pos}`）。`contains` 非空时在其中心上方 0.5 米生成拾取物。
   - 存在的道具挡子弹（kind `"prop"`），击毁后不再阻挡。命中道具计 `shots_hit`。
4. `sim/pickup.gd`：`type`、`pos`、`ticks_left`（6 秒）。判定球半径 0.35。射击收集：`medkit` → 生命 +1（已满时改为加分，T13 接入）；`medal` → 加分（T13）。收集的一枪计 `shots_hit += 1`。事件 `pickup_spawn`、`pickup_collect {id, type, pos}`、`pickup_expire`。
5. View：
   - 道具与拾取物。拾取物缓慢旋转并上下浮动，浮动中心由Sim根据出生tick确定（shape与View共用），最后2秒仅材质闪烁，不改变命中体。医疗包为白盒加绿十字，奖章为金色扁圆柱。
   - 爆炸：膨胀并淡出的橙色球壳、碎屑、0.2 秒的 `OmniLight3D`。注意不要大面积顶到限亮上限。
   - 人质受击：蓝色碎屑，屏幕中央"误伤！"0.8 秒。人质获救：其位置上方"获救 +1"。
6. 夹具 `arena_hostage.json`：三段，分别是 `held`、`run_across` 加敌人、`cower` 加油桶旁的 2 个敌人和 1 个含医疗包的箱子。

**必测**（`tests/test_hostage_props.gd`）

- 打中人质：生命 −1，`hostage_hit`，`shots_hit` 不增加，人质被移除。无敌时间内打中人质仍然扣血。
- `held`：相机在距离 5、8、11 米，且相对挟持者头部高度为 −0.5、0、+2 米共 9 种位置下，瞄挟持者头部中心都先命中挟持者的头，瞄挟持者躯干中心都先命中人质。相机再左右平移 ±0.5 米各测一次。
- 击杀挟持者后 `hostage_rescued`，生命 +1 且不超上限。
- `run_across` 到达终点获救；`cower` 在清场时获救；人质存活不阻止清场；超时的人质不获救。
- 油桶：引爆后半径内 2 个敌人死亡，半径外 1 个不受影响；半径内的人质死亡并扣血；相邻油桶连锁；半径内的投射物被摧毁。
- 箱子 2 枪碎并生成拾取物；射击拾取物后生命 +1；6 秒不收集则消失。
- 箱子击碎前挡住其后方目标，击碎后可以打到。

**截图自检**：挟持场景一张（确认头部中心及足够的可瞄区域露在人质上方）、爆炸一张、拾取物一张。

---

## T13 游戏流程、计分与结算

**交付**

1. `sim/scoring.gd`，按 PLAN §4.6，分值全部取自 rules。
   - 每次加分发事件 `score {amount, total, pos, label}`。`pos` 可为空。label 如 `"HEADSHOT"`、`"RESCUE"`、`"NO DAMAGE"`。
   - 连击：命中敌人、投射物、道具、拾取物 → +1。`shot_miss`、`impact_world`、`armor_hit`、`player_hurt`、`hostage_hit` → 清零；清零前连击 ≥ 5 时发 `combo_break {combo}`。
   - 倍率 `1 + min(combo, 20) * 0.05`，作用于命中分与击杀分，不作用于奖励类（救人质、无伤、结算）。先给连击 +1，再用新的连击数算倍率。例：连击为 0 时爆头击杀一个射手，连击变 1，得分 `(50 + 100 + 100) × 1.05 = 262`（向下取整）。
   - 油桶炸死的普通敌人按稳定生成序号各得击杀分、各给连击+1；引爆的一枪只计一次道具命中/shot_hit。爆炸不会对Boss机体套用普通5点伤害；Boss只接受弱点部件的直接射击。连锁按生成序号处理，不重复触发已引爆的油桶。
   - `shots_hit` 的口径：命中敌人非装甲部件、投射物、道具、拾取物各计 1；命中装甲、世界、人质不计。命中率 = `shots_hit / shots_fired`，取值 0–1，`shots_fired` 为 0 时记 0。
   - 结算奖励：命中率奖励 = `roundi(命中率 × 2000)`；生命奖励 = 剩余生命 × 300。只在 `cleared` 为真时发放。
   - 生命已满时拾取医疗包 → +300 分。
   - 误伤人质 → −500 分（总分不低于 0），事件 `score` 的 amount 为负。
   - 统计：击杀数、弱点击杀数、击落数、获救人质、误伤人质、受伤次数、续关次数、最大连击、playing 阶段累计 tick、`boss_defeated`；以及按段记录的受伤次数、耗时 tick、是否超时（`timed_out_segments` 为超时段 id 的列表）。
   - **受伤次数**的定义：生命每实际减少一次计1（含误伤人质，走统一统计入口，player_hurt与hostage_hit不能双计），不因之后回血而抵消。所有验收指标里的"受伤"都指这个数。
2. 流程（全部在 Sim 内，可回放）：
   - `title`：START 或 SHOT → `playing`，从第 0 段开始。
   - `playing` 中生命归零 → `continue`，开始倒计时（rules，10 秒）。
   - **段入口检查点**：正常进入新段、完成上一段威胁收尾、激活新段道具且尚未生成新段 wave 0/Boss 时，深拷贝可恢复的玩法状态：相机起点、carry 角色（含 hp/位置/稳定 id/非攻击状态）、道具及入口拾取物完整状态、人质结果集合、rng seed/state、下一实体序号、分数及奖励统计。检查点不包含自身或 events；重复续关使用同一检查点。
   - `continue`：START 或 SHOT → 恢复段入口检查点，生命与弹匣回满，换弹/射击冷却/无敌计时清零，续关次数 +1，事件 `continue_used`，回到 `playing`。
     - 回退分数及计分用的击杀、获救、最大连击等统计；combo 清零。本段道具和人质恢复到段入口状态，上段已处理的状态保留。carry 角色恢复，继续计入 required。
     - 清除所有旧投射物、拾取物、连锁队列、令牌冷却和字幕，再重建入口原本存在的道具/拾取物和 carry 角色；波次与段内 tick 归零，按本段 spawns 开始。rng及实体序号一并恢复，不使用旧引用。全局tick不回退；检查点以剩余tick保存计时器，恢复时相对当前tick重建到期值。恢复后View依据完整实体状态重建镜像，清除旧HUD/特效，不能只等actor_spawn事件。
     - **累计运行指标不回退**：总受伤/误伤次数、续关次数、总 shots_fired/shots_hit、总击杀/弱点击杀、playing tick、每段各次尝试耗时和受伤、超时记录。这些指标与计分奖励账本分开。命中率和验收指标使用累计运行指标；人质获救数和评级分数使用当前有效奖励账本。
   - `continue` 倒计时结束 → `results`，`cleared = false`，`fail_reason = "down"`，事件 `game_over`。
   - 最后一段结束 → `results`。`cleared` 为真的条件：走完全程，且关卡若有 Boss 段则 `boss_defeated` 为真。满足时加结算奖励，事件 `level_clear`。Boss 超时撤离的情况见 T19（`cleared = false`，`fail_reason = "boss_escaped"`）。
   - 普通 hold 段超时允许继续路线，但记入 `timed_out_segments`，结算画面显示“超时 n 段”；T18/T20 标准验收要求该列表为空。增加 `finished_route` 区分走到结尾和完成 Boss；因倒地结束时为 false。失败结算统一发 `game_over {reason}`，不发 level_clear。
   - playing 计时仅统计实际战斗推进 tick，含失败尝试，不含 title、continue 倒计时、results、Shell 暂停。每段总耗时为其所有尝试之和，并保留逐次明细。
   - `results`：前 3 秒不接受输入。之后 START 或 SHOT → 整个 Sim 重置回 `title`（同一 seed）。
   - 评级：得分 / `par_score` ≥ 1.0 为 S，≥ 0.8 为 A，≥ 0.6 为 B，其余 C。未通关为 `"-"`。
   - COIN：`credits += 1`，只显示。`credits` 是 Sim 状态，results → title 重置时清零。
3. Shell 暂停：Esc 切换。暂停时不推进 Sim，画面压暗并显示"暂停 — Esc 继续 / Q 退出"。暂停时按 Q 退出程序。窗口失去焦点时自动暂停；带 `--script-run`、`--replay`、`--fixed` 或 `--perf` 启动的运行除外。由 Agent 在后台启动的窗口经常拿不到焦点，自动暂停会让脚本和回放永远等下去。
4. HUD：
   - 右上分数（数字滚动），其下连击数与倍率（连击 ≥ 2 才显示）。
   - 飘分：带 `pos` 的 `score` 事件在其投影处上飘 0.8 秒。爆头的字更大、颜色不同。
   - 命中标记：`hit_actor` 时准星处闪一个 X，击杀为红色。
   - 段清场："CLEAR" 横幅 1 秒；有无伤奖励时追加一行。
   - 标题画面：《仓库突入》、"射击屏幕或按 Enter 开始"、操作说明（左键射击 / 右键或 R 换弹 / Esc 暂停 / F11 全屏）。背景是关卡第一个相机姿态的 3D 画面。
   - 续关画面：大号倒计时、"射击或按 Enter 继续"。
   - 结算画面：逐项统计、评级大字、"射击重新开始"。
   - 左下角常驻小字 `CREDITS n`。

**必测**（`tests/test_flow_scoring.gd`）

- 身体命中、弱点击杀、击落投射物、救人质、拾取奖章各自的加分与 rules 一致；连击 3 时倍率 1.15；连击到 25 时倍率仍为 2.0。
- 打空后连击清零；装甲命中清零；受伤清零。
- 误伤人质扣 500 分；总分不足 500 时扣到 0。
- 段无伤奖励只在成功清场且该段所有尝试累计未受伤时给；超时不给。
- 生命归零 → `continue`。倒计时内 START → 回到该段开头、生命满、续关 +1，分数等于进入该段时的分数。倒计时结束 → `results` 且 `cleared == false`。
- 续关不能刷分：在入口combo=0的一段里击杀2个敌人后死亡并续关，再击杀同样 2 个，分数与一次性击杀 2 个相同。
- `carry`：带着上一段的 1 个 carry 敌人进入 hold 段后死亡并续关 → 恢复该敌人在入口的 hp/位置/id，杀光它和本段 required 才可清场；两次续关恢复相同入口，rng 一致。
- 续关时飞行中的投射物与等待连锁的油桶被清除，用无新威胁的最小夹具断言旧投射物和旧连锁不再发出 `player_hurt` 或 `explosion`；令牌全部可用。
- 普通 hold 段超时后通关：`cleared == true`，`timed_out_segments` 含该段 id。
- 结算奖励数值：命中率 0.5、剩余生命 3 → 奖励 1000 + 900。
- 跑完全部段 → `results`、`cleared == true`、含结算奖励；评级四档各测一例。
- `results` 前 3 秒的 SHOT 被忽略；之后的 SHOT 回到 `title`，此时哈希与首次启动的初始哈希相同。
- 上一段击毁的油桶在续关后仍为击毁状态；本段击毁的油桶在续关后复原。上一段获救的人质不再出现。

**截图自检**：标题、战斗中 HUD 全貌、续关、结算四张。文字无重叠、不超出内容区。

---

## T14 音效合成

**目标**：全部声音由代码生成，按事件播放。

**交付**

1. `audio/synth.gd`（纯函数，可无头测试）：生成 22050Hz、单声道的 `PackedFloat32Array`，并可转为 16 位 `AudioStreamWAV`。积木：正弦、方波、锯齿、白噪声（固定种子）、指数包络、频率滑变、一阶低通、混合、归一化（峰值 0.8）。
2. `audio/sounds.gd`：音色表，启动时一次性生成并缓存。

   | 名称 | 做法 | 时长 |
   |---|---|---|
   | gunshot | 噪声爆发（3ms 起音，快速衰减）加 120→50Hz 正弦低频冲击 | 0.25s |
   | dry_fire | 两个短促的高频咔哒 | 0.08s |
   | reload | 低沉的"咔"，间隔后清脆的"嚓"，两段噪声 | 0.5s |
   | hit_body | 低通噪声闷响 | 0.12s |
   | hit_weak | 明亮的双音"叮"（1320Hz 加 1980Hz） | 0.3s |
   | hit_armor | 金属感：多个非谐波正弦快速衰减 | 0.25s |
   | warning | 880Hz 方波短鸣两声 | 0.25s |
   | hurt | 300→90Hz 下滑锯齿加噪声 | 0.4s |
   | heartbeat | 两下 60Hz 低频冲击 | 0.6s |
   | explosion | 长衰减的低通噪声加 60Hz 冲击 | 0.9s |
   | pickup | 上行三音琶音 | 0.3s |
   | rescue | 上行两音，柔和正弦 | 0.4s |
   | hostage_hit | 不和谐的下行两音 | 0.5s |
   | projectile_pop | 短噪声加 600Hz 下滑 | 0.15s |
   | clear | 上行四音，方波 | 0.8s |
   | boss_alarm | 两音交替的警报 | 1.2s |
   | ui_start | 单音上滑 | 0.3s |
   | game_over | 缓慢下行三音 | 1.5s |
   | bgm_pulse | 可循环：55Hz 低音脉冲每 0.5 秒一下，叠加轻微噪声底 | 4.0s，loop |

3. `audio/audio_player.gd`（`Node`）：
   - 16 个 `AudioStreamPlayer` 的池。
   - `event_sound(event: Dictionary) -> String`：事件到音色名的映射（纯函数，可测）。如 `shot_fired` → gunshot、`attack_windup` → warning、`hit_actor` 按 zone、`player_hurt` → hurt。没有声音的事件返回空串。
   - `handle(events)`：同一 tick 同名音色只播一次。枪声每次 ±4% 变调（自己的 rng）。
   - `playing` 阶段循环播放 `bgm_pulse`（−14dB）。提供 `set_intensity(level: int)`：1 时 −9dB、1.25 倍速（Boss 段使用）。
   - `--mute` 时不创建播放器。暂停时暂停全部声音。

**必测**（`tests/test_audio.gd`）

- 表中每个音色：样本数与时长相符（±5%）、RMS > 0.02、峰值 ≤ 0.85。
- 同名音色两次生成结果完全相同。
- `bgm_pulse` 首尾各 10 个样本的幅度都 < 0.05（循环处无爆音）。
- 对附录 A 的每个事件类型调用 `event_sound` 不报错；`shot_fired`、`dry_fire`、`player_hurt`、`attack_windup`、`hit_actor`（weak、body）、`armor_hit`、`explosion`、`pickup_collect`、`hostage_hit`、`hostage_rescued` 返回的音色都存在于音色表。

**人工确认项**（记入 PROGRESS）：声音是否刺耳、音量是否平衡。执行者无法自己听。

---

## T15 打击感与表现打磨

**目标**：让白模打起来有反馈。只改 View、HUD、Audio，不改 Sim 的逻辑。

**交付**

1. 击杀顿帧：仅死亡残骸和击杀粒子冻结 0.04 秒；相机、存活角色、投射物、拾取物和 HUD 瞄准元素继续跟随最新 Sim 状态。
2. 爆头：头部部件在 View 层弹飞（独立碎块，带初速度、重力和旋转，1 秒后消失）。
3. 进场提示：敌人生成后的 0.3 秒，HUD 在其投影位置画一个向外扩散的淡色环。
4. 预警圈：目标投影距内容区边缘 80 像素以内时，在圈旁加一个指向目标的大箭头。
5. 低血量：生命为 1 时屏幕边缘缓慢脉动红色，循环播放 `heartbeat`。
6. 换弹：弹匣图标逐发填充；完成时短促闪光。
7. 相机运动只来自 rail。启停缓动用轨道 ease 表达，View 不追加俯仰、震动或相机插值；所有可命中部件的位置与 Sim 同步。
8. 调试命令 `{"cmd":"luma"}`：返回内容区画面在限亮之后的最大与平均 sRGB 亮度。计算部分写成可测的纯函数 `dev/luma.gd`：`measure(image: Image) -> Dictionary`。测量来源必须是最终窗口截图裁出的内容区域，不能对未限亮的Content在CPU再套限亮公式后宣称通过。增加黑、0.5灰、白、RGB色块的实际渲染检查，验证颜色空间和输出Y′；必要的线性/sRGB转换以这些截图为准。这项检查需要真实渲染，做成窗口模式的 `gunforge3d/tools/luma_check.ps1`（在 `Content` 里铺色块、整窗截图、裁出内容区后用 `luma.measure` 判定，失败时退出码非 0），不放进无头的 `run_all`；结果记入 PROGRESS。

**必测**（`tests/test_feel.gd`）

- 同一输入序列下，挂上全部 View、HUD、Audio 节点运行，与只跑 Sim 相比，最终哈希相同。
- 开启全部反馈，在相同 tick 用 Camera3D 投影实际活体部件中心，转换为内容像素后射击，仍命中相同 id/part；覆盖移动段与窗口缩放。
- `luma.measure` 对手工构造的纯白、纯黑、0.5 灰、半白半黑图像返回正确的最大值与平均值。

**截图自检**：爆头瞬间、低血量、进场提示环各一张。运行 `luma_check.ps1`：白色块限亮后 Y′ 在 0.74–0.76，0.5 灰和黑色块不被改变（误差 ≤ 0.02）。在 `arena_mixed` 战斗中执行 `luma`，最大亮度 ≤ 0.76。

---

## T16 回放与机器人

**目标**：自动跑完整关并量化难度。

**交付**

1. `dev/replay.gd`：
   - 录制：仅 `session_clean=true` 且从 setup/title 开始的对局记录每个进入 Sim 的输入及其入口 tick，同 tick 保持数组顺序。首次进入 results 后立即封存，退出时可保存未完成局；结果画面的重开输入不并入旧回放。重开时建立新录制。调试污染规则见 T07；Shell 暂停不污染。
   - 格式：`{"format":"gunforge3d-replay-v1","engine_build","sim_revision","level_id","level_sha256","rules_sha256","archetypes_sha256","inputs":[{"tick","event","x","y","in_content"}],"inputs_sha256","final_tick","final_hash"}`。
   - `engine_build` 为 Godot 完整构建标识；`sim_revision` 为所有 sim/*.gd（含子目录）按相对路径排序拼接路径和文件 SHA-256 后的总哈希，文件文本先把 CRLF 归一为 LF（同 T05）。输入摘要使用 T03 的规范 JSON 序列化。
   - 无头回放：`run(replay, level, rules, archetypes) -> {"ok": bool, "final_hash", "error"}`。运行前检查格式、引擎/模拟代码版本、三个数据哈希、输入摘要、tick 合法且非递减；不匹配即拒绝。匹配后从 setup 运行 final_tick 步，结束时比较最终哈希并报告差异。禁止将“最终哈希”作为运行前已可验证的字段。
   - 命令行 `--replay=<路径>`：窗口逐 tick 注入同一序列，禁止现场 SHOT/START/RELOAD/COIN 或调试 input/seek/set/step/freeze 混入，仅允许暂停、退出和只读的调试命令（state、capture、luma、quit）。到 final_tick 冻结并报告哈希结果；加 `--quit-on-end` 时报告后自动退出，退出码 0 表示哈希一致（T20 的自动验收用）。回放观看不再录制。
2. `dev/bot.gd`：只通过 `SimWorld` 的只读状态和 `step(inputs)` 驱动。

   | 档位 | 反应时间 | 瞄准时间（d 为准星到目标的内容像素距离） | 落点抖动 σ（内容像素） | 爆头倾向 |
   |---|---|---|---|---|
   | novice | 0.55s | 0.30 + 0.0008·d | 22 | 20% |
   | average | 0.35s | 0.18 + 0.0005·d | 12 | 60% |
   | expert | 0.22s | 0.10 + 0.0003·d | 5 | 90% |
   | idle | 只在 title 发一次 START，之后不操作，不续关 | — | — | — |

   - 机器人维护一个虚拟准星。候选单位为 `(id, part)`；从实际可见、可命中时起经过反应时间才进入候选。连续可见期间只支付一次反应时间，消失后再次暴露重新计时。
   - 优先级：1 秒内将命中的投射物 > windup 中的敌人（剩余时间短者优先）> 近战距离内的冲锋兵 > 其他投射物 > 其他暴露的敌人 > 拾取物 > 含物品的箱子。油桶：爆炸半径内有 ≥ 2 个敌人且没有人质时，与"windup 中的敌人"同级。
   - 瞄点：按爆头倾向决定瞄头还是躯干，瞄点取部件中心。用 `geom.segment_blocked` 确认从相机到瞄点没有被世界、道具、人质或任何角色的 armor 部件（盾、Boss 装甲）挡住；被挡则换另一部件，再不行换目标。盾兵举盾时瞄腿。
   - 选定目标后经过“瞄准时间”开枪；每枪重新支付瞄准时间和枪械冷却，反应时间按上述暴露窗口处理。开枪前重新投影当前部件中心，再加二维高斯抖动；部件消失/不可打时取消瞄准，优先级变化可中止并重新瞄准。不得预读未来状态。
   - 人质保护：瞄点到最近人质部件投影轮廓的距离 < 1.5σ 时，改瞄该目标的头部，并把瞄点沿远离该人质部件的方向偏移 0.5 个头部投影半径。偏移后仍 < 1.5σ 的目标暂不射击，先处理其他候选。两种情况下照常按偏移后的瞄点开枪并承担误伤风险：该目标正在 windup；或已连续 1.0 秒没有其他可射击的候选。没有这个例外，被挟持人质挡住的挟持者会被永远放弃（挟持者头部中心离人质头顶只有 0.13 米，8 米外约 13 内容像素，小于 novice 的 33 和 average 的 18），段只能超时。机器人不得用 `shooting.resolve` 预先试探抖动后的落点。
   - 换弹：弹匣空时立即；没有候选目标且弹药 ≤ 3 时。
   - 流程：title 发 START；continue 立即续关；results 不再操作。
   - 抖动与倾向用独立的 rng，种子由机器人种子与档位决定，结果可复现。
3. `dev/bot_run.gd`（`extends SceneTree`）：
   `& $GODOT --headless --path gunforge3d/game --script res://dev/bot_run.gd -- --level=<路径> --profile=average --runs=5 --out=<json> --save-replays=<目录>`
   - 每次用不同的机器人种子（1..n）。
   - 输出每次运行：是否通关、用时、得分、评级、命中率、弱点击杀率、总受伤、续关次数、人质误伤；以及 `finished_route`、`boss_defeated`、`fail_reason`、`timed_out_segments` 和**每段**的受伤次数、各次尝试及累计耗时、是否超时。总用时按 T13 的 playing tick 计，弱点击杀率为累计弱点击杀数/累计击杀数（0 分母记0）；均值分母必须标明，失败记录不能丢弃。
   - 单次运行 tick 上限 60×900，超过视为失败并报告卡在哪一段。

**必测**（`tests/test_replay_bot.gd`）

- 机器人在 `arena_mixed` 上跑一遍，输入存成回放，再回放 → 最终哈希一致。
- 篡改任意输入但不更新输入摘要 → 运行前拒绝。另用“命中变落空”的夹具，修改坐标并更新输入摘要，先断言命中/弹药等行为差异，再断言最终哈希不符；两次都落空且状态等价时允许最终哈希相同。修改关卡/规则/原型/模拟代码任一项均应在运行前拒绝。
- 正常开局可录制；--segment、seek、--force、调试 set/step/freeze 后不生成标准回放。现场输入不改变窗口回放最终哈希。
- `expert` 在 `arena_gunner` 上不掉血通关；`idle` 在同一关以 `cleared == false` 结束。
- `average` 在 `arena_hostage` 上 5 次运行的人质误伤合计 ≤ 1。
- 同一档位同一种子两次运行，输入序列完全相同。

---

## T17 关卡校验器

**目标**：在运行前挡住不公平或做坏的关卡。

**交付**

1. `sim/level_validator.gd`：`validate(level, rules, archetypes, scope := "playable") -> {"errors": [...], "warnings": [...], "stats": {...}}`。每条 `{"code", "where", "message"}`。scope=structure 只检查类型、范围、引用、轨道合法性；scope=playable 再执行下表公平性检查。生产关卡和 arena_* 必须用 playable；box_room/empty 等结构夹具只要求 structure 通过，不能用于全关验收。

   | 代码 | 级别 | 规则 |
   |---|---|---|
   | REF_MARKER | error | spawn 的 from、to、path 引用的 marker 都存在；`held` 人质的 captor 存在于同一段 |
   | REF_ARCHETYPE | error | archetype 存在 |
   | SPAWN_IN_SOLID | error | 被 spawn 引用的 marker，其上方 0.1–1.7 米的 5 个采样点都不在 solid 几何内 |
   | RAIL_SPEED | error | move 段的平均速度（逐 tick 采样位置累加出的弧长 ÷ 段时长）> 2.5 米/秒；或任意相邻两 tick 的视线夹角 > 0.75°（即 45°/秒）。带 `drift` 的 hold 段同样查角速度 |
   | CAM_IN_SOLID | error | 每段每 6 tick 采样的相机位置距任何 solid 表面 ≥ 0.25 米 |
   | COMBAT_OFFSCREEN | error | 在"采样时刻"，站位处暴露姿态的头部中心投影落在内容区内缩 60 像素的安全框里 |
   | WEAK_OCCLUDED | error | 在"采样时刻"，从相机到暴露姿态头部中心的线段不被 solid 几何或道具挡住。`held` 的挟持者还不得被其人质的部件挡住 |
   | TARGET_TOO_SMALL | error | 在"采样时刻"，头部投影半径 ≥ 12 内容像素，躯干投影半宽 ≥ 16 |
   | TARGET_TOO_FAR | warning | 站位距相机 > 16 米 |
   | NO_COVER | warning | `use_cover` 为 true 的射手在 `crouch` 姿态下，头部从相机仍然可见 |
   | WINDUP_TOO_SHORT | error | 普通敌人 windup < 0.6 秒（冲锋兵）或 < 0.9 秒（射手/投掷兵/盾兵）；Boss 用 T19 专门规则 |
   | TOKENS_RANGE | error | tokens 不在 1–3 |
   | HOLD_TIMEOUT | error | hold 段的 timeout 缺失、≤0或>90秒（Boss段上限180秒） |
   | HOLD_NO_REQUIRED | error | hold 段没有任何 required 敌人，且无入段 carry 敌人（Boss 段除外） |
   | NO_ATTACK_WINDOW | error | 非 carry 的移动段敌人从最早到位到段末，没有完整的可见预警窗口；不能把空采样视为通过 |
   | FIRST_THREAT_TOO_EARLY | warning | 段内最早可能的 `attack_fire` 距段开始 < 2.0 秒 |
   | DENSITY | warning | 任一波的敌人 > 6 |
   | BARREL_NEAR_CAMERA | error | 油桶距其所属段（`segment` 字段；未写的按全部段）内任一相机采样位置 < 4 米。后续段镜头只是路过未引爆的油桶不算（油桶不伤玩家，且小巷宽 8 米，路过时必然近于 4 米） |
   | DURATION | warning | 估算总时长（move 之和，每个普通 hold 估 25 秒，Boss 段估 70 秒）不在 180–300 秒 |
   | LUMA_MATERIAL | warning | 材质颜色的 sRGB 亮度 > 0.75 |

   - 空rail、无效fov/关键帧、重复实体id、未知行为名、非法波次及错误参数类型属于structure错误，必须先拒绝，不能继续几何采样。
   - “采样时刻”：hold 从段首到 timeout 每 0.1 秒采样，末端必须包含，有 `drift` 时按不清场的完整漂移轨迹取相机姿态；后续波次的开始时刻可能随清敌速度改变，因此对各站位保守检查全部相机姿态。move 从 spawn.at 开始每 0.1 秒到段末，包含首尾；path 进场时间纳入最早到位估算，不再跳过出生后首秒。
   - hold 的静态可见性/尺寸要求在所有样本成立。move 允许进出视野，但在可攻击站位上必须存在不少于该敌人完整预警时长的连续合格区间；carry 敌人可在下一 hold 获得窗口，但前段仍由运行时可见性门控禁止不公平攻击。无样本/无窗口报 NO_ATTACK_WINDOW。
   - “站位”：射手/投掷兵取 to；盾兵取 to 和相对每个相机样本计算的停步点；冲锋兵检查路径引用与 windup，攻击时的实际可打性由 T10 门控及动态验收保证。人质不套用敌人头部尺寸规则。
   - “暴露姿态”：射手 aim、投掷兵 throw 的 progress=0/0.5/1、盾兵放下盾的 aim。held 同时测试人质与挟持者，使用共享 pose_lib，不用单独近似。道具按所属段激活且尚未摧毁的保守状态检查。
   - 静态采样不声称证明任意输入下公平；T18/T20 对真实运行逐 tick 审计，攻击必须满足连续可见预警，报告违规攻击数。校验时不递归启动 main 或使用无敌开关运行机器人。
   - `stats`：各段敌人数量与类型分布、人质数、道具数、估算时长。
2. `dev/validate_run.gd`（`extends SceneTree`）：`-- --level=<路径> --scope=playable|structure`（默认 playable），打印报告，有 error 时退出码 1。
3. `main.gd` 加载关卡后运行校验器：有 error 时在画面上列出前 10 条并拒绝开始。`--force` 可跳过 playable 检查，仅供结构夹具截图；结构解析错误仍拒绝。使用 --force 不可录制标准回放或参加 T18/T20 验收。capture.ps1 支持显式 -Force 透传，结构夹具截图须指定。

**必测**（`tests/test_validator.gd`）

- 以一个合法的最小关卡为基底（0 error），每条规则各构造一个违例变体，断言出现对应 code。
- box_room/empty 的 structure 检查为 0 error；box_room 的 playable 检查应按实际报告 HOLD_NO_REQUIRED，证明分层生效。arena_* 全部 playable 0 error。夹具不达标时改夹具的几何和站位，不放宽规则；改完后依赖该夹具的旧测试必须仍然通过。
- 移动段末尾出生的不可攻击敌人、遮挡路径、短于预警的可见窗口均报告对应错误；有效 carry 路径不误报。

---

## T18 关卡《仓库突入》：S0–S8

**目标**：制作正式白模关卡的非 Boss 部分。这是内容任务，标准是"好玩并通过量化验收"，不是"数据填完"。

**交付**：`data/levels/warehouse_raid.json`，并设为默认关卡。

**空间布局**（尺寸可在 ±20% 内调整，保持拓扑与先后顺序）

| 区域 | 范围 | 要点 |
|---|---|---|
| 小巷 | x −4..4，z 0..−22，两侧墙高 7 | 左侧垃圾箱（2.0×1.2×1.0），右侧两层木箱堆，尽头右侧一个油桶。夜景，一盏暖色灯 |
| 卷帘门 | z −22，门洞宽 5 高 4 | 门框厚 0.5，营造穿门感 |
| 装卸区 | x −9..9，z −22..−44，净高 8 | 右侧 1.2 米高的装卸平台（宽 5），平台上有箱子。左侧 3.5 米高的钢走道，栏杆不 solid。地面一台由几个盒子组成的叉车 |
| 货架通道 | x −3..3，z −44..−64 | 两侧各 4 组货架（立柱加 3 层层板），货架之间有 1.5 米宽的横向缺口供敌人闪出。尽头堆箱与一个油桶 |
| 楼梯 | 从 (3, 0, −64) 上到 (8, 3.5, −70) | 8–10 级盒子台阶 |
| 夹层办公室 | x 4..14，地面 y 3.5，z −70..−82 | 办公桌、文件柜、带窗洞的隔断墙（窗洞可射穿） |
| Boss 装卸区 | x −12..12，z −84..−112，地面 y 0 | T19 使用。本任务先搭出空间与四周的集装箱（2.4×2.6×6 的盒子，几种颜色） |

- 材质 6–8 种，亮度都低于 0.7。地面、墙、箱、金属、强调色互相可区分，地面与墙的明度差 ≥ 15%。
- 每个区域一盏主色不同的灯（暖黄、冷蓝、绿、橙红），帮助玩家感知"到了新地方"。

**段落编排**（数量与时间是起点，调到验收达标为止）

| 段 | 类型 | 内容 |
|---|---|---|
| s0_intro | move 4s | 沿小巷前推 6 米。字幕："左键射击 · 右键换弹"，随后"在预警圈收拢前击倒敌人" |
| s1_alley | hold | 波 0（tokens 1）：2 个射手，分别在垃圾箱后与木箱后，`first_delay` 2.0、`windup` 2.0，教学用。波 1（tokens 2）：3 个射手，其中 1 个站在油桶旁。字幕："射击头部可一枪毙命" |
| s2_gate | move 8s | 穿门。2 个冲锋兵从门内迎面跑来，间隔 1.2 秒 |
| s3_dock | hold，tokens 2 | 波 0：平台上 2 个射手，走道上 1 个投掷兵。字幕："击落飞来的投掷物"。波 1：1 个人质 `run_across` 横穿，同时 2 个射手与 1 个冲锋兵。一个含奖章的箱子 |
| s4_aisle | move 15s | 镜头沿通道前进并左右各摆一次。3 个射手依次从货架缺口 `side` 闪出（`use_cover` false，`windup` 1.3）。路边一个含医疗包的箱子 |
| s5_aisle_end | hold，tokens 2 | 镜头停在通道前段（z≈−52），前方留约 12 米通道。波 0：2 个盾兵从通道尽头逼近，1 个射手。字幕："盾牌挡子弹 — 打腿，或等它露头"。波 1：2 个冲锋兵从两侧，1 个投掷兵。油桶在冲锋兵的路径旁 |
| s6_stairs | move 12s | 先走完通道余下约 12 米，再上楼，镜头上抬。楼梯顶 1 个投掷兵（`at` 取镜头进入其 11 米内之后）；办公室门口 1 个射手（`carry: true`） |
| s7_office | hold，tokens 2 | 波 0：1 组挟持（挟持者 `windup` 3.0，给足瞄头的时间；站位距相机 4–6 米，头部够大，机器人和新手才打得了），窗后 2 个射手。波 1：桌后 1 个 `cower` 人质，3 个射手，1 个冲锋兵从门冲入 |
| s8_descend | move 7s | 从夹层边缘俯视 Boss 装卸区，沿斜线降到 (0, 1.6, −88)，看向 −Z。字幕："警告：重型目标接近" |

- 每个 hold 段的相机可有缓慢小幅漂移，避免画面完全静止。用 rail 的 `drift` 字段（T06，amp ≤ 0.5 米、period 6–10 秒），不要用关键帧做漂移。
- move段按实际轨道采样弧长/时长计算平均速度≤2.5米/秒，转头角速度≤45°/秒。先完成路线再布置敌人；不能仅以首尾直线距离代替弧长。建议相机段末位置：s0=(0,1.6,−6)，s2=(0,1.6,−24)，s4=(0,1.6,−52)，s6=(7,5.1,−74)，s8=(0,1.6,−88)。对应直线估算的平均速度约为 1.5、2.25、1.9、2.1、2.4 米/秒。s4 前 20 米穿过装卸区，最后约 8 米进入货架通道，射手从前方的货架缺口闪出；s6 先走完通道，再经过楼梯中间关键帧，不能直线穿过台阶。相应初始移动时长合计46秒，加s10共49秒，hold预算约200秒，总体约249秒。RAIL_SPEED 超限时优先延长该段时长（s8 余量最小），不要删减路线。
- 每个 hold 的停留点前方要有战斗纵深：最远的敌人站位在 11 米内，最近与最远相差 ≥ 5 米，油桶距相机 ≥ 4 米。停留点距前方墙体或通道尽头不足 10 米时，把停留点往回挪，不要把敌人挤在近处。
- 多用纵深与高低：每个 hold 段内最近与最远的敌人站位，深度差 ≥ 5 米。s7 办公室只有 10×12 米，镜头要斜向看过整间办公室（如看向远角，最远约 10 米），才摆得下这个深度差。

**验收**（全部满足才提交）

1. 校验器 0 error。warning 逐条在 PROGRESS 中说明保留的理由。
2. 机器人每档跑 5 次（此时关卡在 s8 之后直接结束）：
   - `average`：5 次全部不续关通关，平均受伤 1–3 次；没有任何 hold 段超时；每个 hold 段耗时 15–45 秒；总用时 130–190 秒；任一段的平均受伤 ≤ 1.5。
   - `expert`：5 次全部不续关通关、无超时，平均受伤 ≤ 1。
   - `novice`：5 次全部通关且无超时，平均续关 ≤ 1。
   - `idle`：在 s3 结束之前死亡。
3. 每个战斗段至少一张战斗中的截图，纯移动演出段至少一张运行中截图并自查：目标清晰可辨、没有被前景完全挡死、相机没有穿进几何体、构图不空旷。结论写入 PROGRESS。
4. 全量测试通过；逐 tick 审计普通敌人的攻击均经历完整连续可见预警，违规攻击数为 0。

达不到指标时的调整顺序：先调 `windup`、`first_delay`、`hide`；再调波次延迟、敌人数量与 tokens；最后才动站位与布局。若几何/可见性检查失败，先修布局，再做难度调参。不得修改机器人档位参数或验收阈值来凑数。

调参按轮进行。一轮是一次有明确假设的改动，加上四档机器人重跑。一轮只改一类参数，这样才能判断是哪项改动起了作用。每轮在 PROGRESS 记一行：改了什么、为什么改、关键指标改动前后的数值。连续 3 轮关键指标都没有向目标靠近，或累计超过 15 轮仍未达标，就停下来按 §0.5 报告，不要继续盲调。

---

## T19 Boss：重装机甲

**交付**

1. `archetypes.json` 增加 `boss_mech`（`body: "mech"`）。`pose_lib` 增加 `MECH` 部件表。根在两脚之间的地面，局部 +Z 为正面，总高约 4.2 米：

   | 部件 | 形状与局部中心 | zone |
   |---|---|---|
   | leg_l / leg_r | box 0.7×1.6×0.8，(∓0.8, 0.8, 0) | armor |
   | hip | box 2.2×0.6×1.2，(0, 1.9, 0) | armor |
   | torso | box 2.4×1.6×1.5，(0, 3.0, 0) | armor |
   | core | sphere r=0.38，(0, 2.9, 0.80) | weak（关闭时被 core_cover 挡住） |
   | core_cover | box 0.9×0.9×0.12，(0, 2.9, 1.20)；打开时上移 1.0 米 | armor |
   | pod_l / pod_r | box 0.9×0.7×0.9，(∓1.7, 3.6, 0) | weak；击毁后移除 |
   | cannon | cylinder r=0.22、长 1.6，从 (0.9, 2.3, 0.75) 沿 +Z 前伸 | armor |
   | head | box 0.6×0.4×0.6，(0, 4.0, 0.2) | armor |

   弱点部件用强调色 `#e0b020`，装甲用深钢色。核心在蓄力时由暗变亮（不超限亮）。
2. Boss 的伤害规则：命中分发先检查 behavior=boss_mech，交给 Boss 部件伤害逻辑并结束分发，不能先套人形 weak 一枪毙命再回调。`weak` 命中每枪 1 点，记到被命中部件自己的生命上（`pod_hp` 各 6，`core_hp` 28），不是一枪毙命。登场/阶段1的core以及阶段2/3未开放的core统一视为armor，避免从侧面绕过盖板偷伤。计分：每次弱点命中 50，击毁一个导弹舱 500，击毁 Boss 3000（都取自 rules）。单枪弱点命中计一次 shots_hit 和连击，50 分乘本枪倍率；导弹舱 500/Boss 3000 是固定奖励，不叠加人形击杀分或爆头奖励。
3. `sim/behaviors/boss_mech.gd`，按 PLAN §4.5。时间参数初值：
   - **登场**：从段 boss.from marker 走到 boss.to marker，用时 3 秒（本关分别 z −110、−100）。期间所有部件按 armor 处理。事件 `boss_intro {id}`。
   - **阶段 1**：每 4.0 秒一次齐射，每个存活的导弹舱发 1 枚，两枚间隔 0.4 秒。齐射前 0.9 秒发 `attack_windup`（事件带 id、part，圈画在对应导弹舱上）。导弹是直线匀速投射物，飞行 2.2 秒，判定半径 0.35。一个舱被毁后齐射间隔缩短为 3.0 秒。两舱全毁 → 事件 `boss_phase {id, phase: 2}`，硬直 1.5 秒。
   - **阶段 2 循环**：
     1. 从 Boss 两侧的 marker 放出 2 个冲锋兵，间隔 0.8 秒。
     2. 等 3.0 秒。
     3. 主炮蓄力：`core_cover` 打开（只在蓄力和瘫痪状态保持打开，阶段切换和等待间隔关闭），事件 `boss_charge {id, ticks, need}`。2.5 秒内核心被命中 5 次 → 事件 `boss_interrupt`，瘫痪 2.0 秒，核心保持打开；否则 `damage_player(1)`，事件 `attack_fire`，核心关闭。
     4. 间隔 2.0 秒，回到第 1 步。

     蓄力期间与瘫痪期间命中核心都扣 `core_hp`。
   - **阶段 3**（`core_hp <= 11` 且 >0）：仅进入一次，取消旧蓄力/瘫痪计时及尚未生成的小怪队列，关闭核心，清除阶段2残留小怪并释放其令牌。事件 `boss_phase {id, phase: 3}`，Boss 从 to 朝相机水平方向前移4米（本关 z −96，1.5 秒）。循环：从躯干两侧共发 3 枚导弹（间隔 0.35 秒）→ 最后一枚发射后 2.0 秒开始蓄力（2.0 秒内需 6 枪）。打断则瘫痪2秒、核心持续打开；失败则 damage_player(1)；两种结果结束后关闭核心，间隔1.5秒重开循环。不再放冲锋兵。
   - **击毁**（`core_hp <= 0`，优先于阶段切换和超时）：设置 boss_defeated=true，事件 `boss_destroyed {id}`。立即清除所有投射物与小怪。2.5 秒内在机体各处发出 5 次 `explosion {pos, radius, visual_only:true}`（只作表现，不造成伤害），然后移除 Boss，段清场。
   - Boss 不占令牌，但所有弱点和威胁都需满足可见性检查；核心蓄力沿用 T10 连续可见重置规则，避免画面外扣血。导弹舱发射预警0.9秒、导弹飞行2.2秒、核心阶段2/3预警2.5/2.0秒作为 Boss 专用校验下限，禁止用普通人形规则检查它。它放出的冲锋兵照常使用令牌。
   - 阶段2循环在两只冲锋兵生成完后才开始等3秒；每轮先清点存活小怪，最多同时2只，不无限叠加。所有间隔/尺寸/部件生命/打断需求放入 archetypes.params；T20 可调 Boss 节奏与生命（必须保持阶段结构和预警下限），不得改机器人参数。任何阶段切换必须终止旧状态的后续伤害和定时动作。
   - Boss 段超时（150秒）：无击毁奖励，记录 segment_timeout、boss_defeated=false，清除全部小怪/投射物/待发动作，跳过 s10，直接 results，finished_route=false、cleared=false、fail_reason="boss_escaped"，发 game_over。不得显示“任务完成”。
4. 导演：段上的 `"boss": {"archetype": "boss_mech", "from": "<marker>", "to": "<marker>", "adds": ["<marker>", "<marker>"]}`。段开始时生成 Boss，仅以 boss_defeated=true 且击毁演出结束为清场条件；超时移除不触发 segment_clear。
5. `warehouse_raid.json` 增加：
   - `s9_boss`：hold，timeout 150。相机在 (0, 1.6, −88) 缓慢左右漂移 ±0.8 米，用 `drift`（amp `[0.8, 0, 0]`、period 10）；不能用关键帧做，否则击毁 Boss 后要等到最后一个关键帧才能离段。场地两侧各 1 个含医疗包的箱子。进入时字幕"摧毁导弹舱！"，阶段 2 时"蓄力时射击核心！"。
   - `s10_outro`：move 3 秒，镜头后拉上升，字幕"任务完成"。
6. View、HUD、Audio：
   - Boss 生命条：屏幕上方，分三格显示（左舱、右舱、核心）。
   - `boss_charge`：核心处的大预警圈与"n / need"打断进度（阶段2为5、阶段3为6）；炮口有逐渐变大的光球。
   - `boss_interrupt`：机体冒电火花，播放 `hit_armor` 的低音变体。
   - `boss_destroyed`：连环爆炸期间 View 层以 0.4 倍速呈现（只放慢已不可命中的残骸与粒子，Sim/相机不变；进入下一段时清理剩余演出），结束后恢复。
   - 进入 Boss 段：`audio.set_intensity(1)`，播放 `boss_alarm`。
7. 校验器：Boss 段豁免 `HOLD_NO_REQUIRED`。新增 `BOSS_WEAK_VISIBLE`（error）：Boss 在 to 和阶段3终点处时，对应存活导弹舱与打开状态的核心在整段相机采样范围内可见（包含自身装甲遮挡），投影最短半尺寸 ≥16像素。box 以屏幕投影包围框最短半边计；sphere 用投影半径计。boss.from/to/adds 的 marker 引用和正的部件生命也需校验。
8. `dev/bot.gd` 增加 Boss 策略：候选仍为 (id, part)。阶段1选存活导弹舱；阶段2/3只选实际打开的核心；头、躯干、关闭核心均不可选。Boss 充能中的核心与其他 windup 威胁按剩余时间排序，紧迫投射物仍优先；开放但未充能的弱点归入“其他暴露敌人”。沿用 T16 的反应、逐枪瞄准、抖动和换弹，禁止无抖动脚本替代。部件毁坏/关闭立即取消旧瞄准。

**必测**（`tests/test_boss.gd`，夹具 `arena_boss.json` 只含 Boss 段）

- 登场期间射击任何部位都是 `armor_hit`。
- 阶段 1：导弹按间隔发射、可击落；每舱 6 枪击毁；两舱全毁后进入阶段 2。核心在关闭状态下瞄其中心得到 `armor_hit`。
- 阶段 2：蓄力期间命中核心 5 次 → `boss_interrupt`，玩家不掉血；不打 → 掉 1 血。瘫痪期间命中核心扣 `core_hp`。
- `core_hp` 降到 11 进入阶段 3；降到 0 → `boss_destroyed`、5 次 `explosion`、段清场、加 3000 分。
- 击毁瞬间残留的导弹与冲锋兵被清除。
- 超时路径：results、boss_defeated=false、cleared=false、fail_reason=boss_escaped，无击毁/通关奖励、不播放胜利字幕；达到时间上限不能算通关。
- 部件独立扣血、阶段3只进入一次、阶段3打断/失败均有完整转移；同 tick 击毁优先于超时。
- 机器人各阶段只瞄有效弱点；记录关闭/销毁部件后取消目标；复用参数且无完美瞄准分支。
- `expert` 机器人能击毁 Boss。同一输入两次运行哈希一致。

**截图自检**：登场、阶段 1 导弹来袭、阶段 2 核心打开与打断进度、击毁爆炸，各一张。

---

## T20 整体调参、验收与交付

**目标**：把整关调到可以交给用户判断方向的状态。

**交付**

1. 机器人全关验收（`warehouse_raid.json`，每档 10 次）。结果写入 `gunforge3d/reports/bot_metrics.json`，摘要表写入 PROGRESS：

   | 档位 | 要求 |
   |---|---|
   | average | 至少9次不续关通关，这些通过的运行各自用时190–270秒；10次运行平均受伤2–4；至少7次评级为A或B |
   | expert | 10 次全部通关；平均受伤 ≤ 1.5；至少 5 次为 S |
   | novice | 10 次全部在续关 ≤ 2 次内通关 |
   | idle | 10 次全部在 s3 结束前死亡 |

   - 所有被计为通过的运行必须 boss_defeated=true、timed_out_segments 为空；novice/expert 每次均须满足，average 至少9次满足。不得删除失败种子或从均值中排除受伤记录。
   - Boss 战在每条通过的 average 记录下耗时50–90秒；首次死亡前的段号用于 idle 验收。
   - 任一段的 `average` 平均受伤 ≤ 1.5，Boss 段 ≤ 2。
   - 固定机器人种子1..10。先取得 expert 的原始得分，再将 par_score 固定为 `max(500, roundi(expert平均得分 * 0.9 / 500) * 500)`；之后重新生成最终数据哈希、指标和回放，不能沿用修改前的回放。
   - 调整顺序、禁令、分轮记录和停止规则同 T18；Boss 专项参数范围见 T19。全程审计可见预警，违规攻击数为0。
2. 性能：窗口模式回放一条 `average` 通关记录，固定1280×720、monitor、Forward+，记录引擎和硬件。新增命令行参数 `--perf=<json 路径>`：关闭 VSync（`DisplayServer.window_set_vsync_mode`），在 `main.gd` 的 `_process` 里用相邻两帧 `Time.get_ticks_usec()` 之差记录帧间隔，排除启动后前 60 帧，退出时写出平均、P95、P99、最大值及 >16.7ms、>33.3ms 的帧数和它们所在的 tick。不用 `Performance.TIME_PROCESS`：它是引擎汇总后的监视值而不是逐帧的帧间隔，开着 VSync 时还可能把等待垂直同步的时间算进去，做不了分位数统计。要求 P99 ≤ 16.7ms，且 >33.3ms 的帧不超过 3 个；超标帧在 PROGRESS 里写明 tick 和原因（如首次出现某种特效时的着色器编译）。不把“全程最大值 < 16.7ms”当硬指标，一万多帧里单次系统抖动就会让它失败。性能采集与截图/图像回读分别运行，避免 luma 回读污染性能。结果写入 PROGRESS。
3. 限亮与白框：回放全程每30帧采一次限亮后的内容区域 luma，并覆盖枪闪、爆炸、纯白HUD和Boss核心最亮时刻，采样最大值≤0.76；结果只代表覆盖到的画面，不能宣称逐帧证明。另取 5 张整窗截图，检查白框四条边中点处的像素为纯白。
4. 确定性回归：把一条 `average` 通关回放存为 `game/tests/fixtures/warehouse_raid_average.replay.json`，新增测试断言回放的最终哈希。有意修改关卡、规则、原型或 `sim/` 下任何代码后都要重新生成它（`sim_revision` 会变，旧回放在运行前就被拒绝）。
5. 画廊：`gunforge3d/tools/make_gallery.ps1` 一键生成 12–16 张代表性截图到 `reports/captures/`；`gunforge3d/reports/gallery.md` 逐张列出文件名和一句说明。
6. `gunforge3d/README.md` 定稿：启动、操作、命令行参数、测试、机器人与校验器的用法、新建一个关卡的最小步骤、目录说明、已知限制。
7. `gunforge3d/docs/PLAYTEST.md`：给用户的试玩清单。启动方法、建议试玩 3 遍、PLAN §8 的五个判断问题、每段希望留意的点、反馈记录表（段、问题、感受）。
8. PROGRESS.md 定稿：每个任务的状态、测试总数、机器人指标表、性能与限亮结果、所有偏离与未解决问题、需要人工确认的事项（音效听感、手感、眩晕感）。
9. 不修改仓库根的 `README.md`。在最终答复里问用户是否要在根 README 加一行指向 `gunforge3d/README.md` 的链接。

**验收**

- 上述指标全部达到，全量测试通过。
- 删除 `game/.godot/` 后执行 `play_3d.cmd`，能启动并进入标题画面。
- 用 `--replay` 加 `--quit-on-end` 窗口回放第 4 点的回放文件，能从标题一路播放到结算，退出码 0。

---

## 附录 A：Sim 事件清单

View、HUD、Audio 只通过这些事件和 Sim 的只读状态工作。新增事件时同步更新本表与 `test_audio` 的覆盖列表。

| 事件 | 主要字段 |
|---|---|
| phase_change | from, to |
| segment_enter / segment_clear / segment_timeout | id, index |
| rail_end, level_clear, continue_used | — |
| game_over | reason |
| caption | text, duration |
| shot_fired | px |
| dry_fire, shot_miss, reload_start, reload_done | — |
| impact_world | pos, normal |
| hit_actor | id, part, zone, pos, killed |
| armor_hit | id, part, pos |
| actor_spawn | id, archetype, pos |
| actor_die | id, zone |
| actor_remove | id |
| attack_windup / attack_resume | id, ticks, part（普通敌人可省略part） |
| attack_hold | id |
| attack_cancel / attack_fire | id |
| player_hurt | life, source_id |
| player_down | — |
| projectile_spawn | id, ticks |
| projectile_destroyed | id, pos |
| projectile_hit_player | id |
| explosion | pos, radius, visual_only（默认false） |
| prop_hit / prop_break | id, pos |
| pickup_spawn / pickup_collect / pickup_expire | id, type, pos |
| hostage_hit / hostage_rescued | id, pos |
| score | amount, total, pos, label |
| combo_break | combo |
| boss_intro | id |
| boss_phase | id, phase |
| boss_charge | id, ticks, need |
| boss_interrupt, boss_destroyed | id |

## 附录 B：常见坑

- 文档中的 `JSON` 内联字段列表是接口示意，不是可直接解析的JSON文件；带 json 标记的代码块为完整语法示例。
- `--script` 运行的 `SceneTree` 脚本，`_initialize()` 里根节点还不在树内。先 `await process_frame` 再操作节点或取全局变换。
- 无头模式没有渲染，取不到画面。截图一律走非无头模式。
- `SubViewport` 里的 `Camera3D.project_ray_normal` 需要视口尺寸已设置并经过一帧。
- 删除 `.godot/` 后首次运行需要导入资源，`run.ps1` 已处理。直接用 `$GODOT` 跑测试时若报资源找不到，先执行一次 `& $GODOT --headless --path gunforge3d/game --import`。
- 状态哈希用 `JSON.stringify(snapshot(), "", true, true)`：键排序、完整浮点精度；数组保留稳定生成序号，rng 的64位整数用十进制字符串。不要依赖对象引用或默认浮点格式。
- 浮点数进 snapshot 前不要四舍五入，保持原值，否则回放会分叉。
- `Vector3`、`Transform3D` 不能直接进 JSON。snapshot 里统一转成数组。
- 内容 SubViewport 固定 1776×936，HUD 在同一像素空间布局，最终由 Shell 统一等比缩放。不得分别取整宽高改变渲染宽高比。
- 强光加浅色材质会顶到限亮上限，被压暗后发灰。优先降低灯光能量，不要依赖限亮来兜底。
- Git Bash 会改写以 `/` 开头的命令行参数。`res://` 路径不受影响；绝对路径写成 `E:/...`。

## 附录 C 文档修订核对

v0.2 保留原产品范围，并将上一轮 review 落实到任务和必测项：R01→T09/T12；R02→T10/T11；R03→T16/T19；R04→T13/T19/T20；R05→T08/T09及事件表；R06→T13；R07/R08→T03；R09→T01/T10/T12/T15；R10→T10/T17/T18；R11/R12→T07/T16。二次审查另补齐了计时边界、carry跨段/续关生命周期、Boss阶段3打断和状态收尾、结构夹具校验、回放代码版本、固定视口比例、真实限亮测量与性能采集隔离，以及88米推进距离与移动时长/限速的可行性。

v0.3（三次评审）只修正文档内部的矛盾和会卡住执行的缺口，范围不变，摘要见 PLAN §10。落点：路径与超时约定、安全框、实体 id→§0；冷却测试移位→T03/T08；换行归一的哈希→T05/T16；`drift` 与空轨道→T06/T10/T17/T18/T19；调试端口→T07；HUD 不二次缩放→T08；盾的尺寸→T11；失焦暂停的例外、credits→T13；窗口模式的限亮检查→T15；机器人的人质保护与装甲遮挡、回放只读命令→T16；油桶规则与测速口径→T17；S5 停留点、S6 时长→T18；性能口径→T20。

v0.5（交付执行前复核）不改任务范围和验收数值，只补三处执行规则：每个任务的开工与收工流程→§0.7；弹孔不用 `Decal` 节点→T08；调参的分轮记录与停止规则→T18/T20。

本文件定义待实现的行为与验收，不代表已有游戏通过测试。不得因文档标为修订完成就将PROGRESS中的开发任务或人工试玩标为完成。

## 附录 D 美术阶段衔接（2026-11-16）

本机工具路径、版本、验证范围和未具备条件见[DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)。T00–T20仍是独立白模阶段：禁止引入外部素材/额外工具链的限制适用于该阶段。后续美术框架AF任务允许在gunforge3d/artkit下使用隔离Python环境和已有Blender；素材导入及EI/WR接入在T20完成且用户认可方向后执行，按两份ART3D文档验收。不提前改变白模验收标准。

纯表现资产覆盖原颜色，不删除或迁移archetypes里的字段。EI05启用姿态轨属于玩法改动：加载阶段校验并注入Sim（step期间不读文件），轨迹存game/data/poses；回放增加pose_data_sha256及姿态配置标识，快照包含clip/tick。修改轨迹必须拒绝旧回放并重新跑T20。--art开关仅控制View；同一玩法姿态配置开/关美术的最终哈希相同。

Compatibility属于后续EI06新增验收，Forward+白模性能结果不代表Compatibility性能。启动器必须把引擎参数`--rendering-method gl_compatibility`放在`--`之前，游戏参数放在之后；建议EI06新增`-Renderer forward_plus|gl_compatibility`并验证透传。框架与游戏文档若数值冲突，玩法尺寸以TASKS及已生成的Sim数据为准，美术不得擅改。

扩展空间（2026-11-16）：美术风格和硬件档位不是引擎的固定属性。白模阶段和首个美术档案之外，以后可以增加别的风格和更强的硬件档位，规则见[ART3D_FRAMEWORK.md](ART3D_FRAMEWORK.md) §18。对引擎侧的要求有四条：渲染器由启动参数选择，`-Renderer`的取值同时预留`mobile`；`--art`的取值是`off`、`on`或档案名，`on`等同于游戏的基准档案；灯光、环境、后期的设置按档案放在美术数据里，由View读取，Sim不读，同一玩法姿态配置下任何档案的最终哈希相同；任何后期效果都在内容视口内完成，限亮着色器和白边框仍在它们之后，白边框始终是画面里最亮的。这些要求在EI阶段落实，不改变T00–T20的白模验收，白模阶段不需要为此提前写代码。
