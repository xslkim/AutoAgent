# 关卡原型与可视化工具

这是已能运行的开发原型。三包使用同一编译、运行会话、事件调度、命中、回放和审阅入口。正式关卡采用、真实用户批注及手机/电视验收分别记录，不由自动测试代替。

## 完整首站候选 · 夜市巷口

```powershell
$proposal = '.\gunforge\level_design\reviews\agent_proposals\proposal-1794237379343236500.json'
.\gunforge\start_level_player.ps1 -Proposal $proposal
.\gunforge\start_level_review.ps1 -Proposal $proposal
```

按 Enter 或点击开始，播放 90 秒开场 CG。播放时保留定位白边并同步显示字幕。可用 Enter、Esc 或手机开始键跳过，也可以在启动命令加 `-SkipOpening` 直接测试关卡。播完自动进入首站，本次运行内重试直接从关卡开始。

首站交代墨潮和救援目标，并标出巷灯。等墨鸦入场后射灯，可定住附近墨鸦 2.4 秒。红圈预警后可直接射击，击破墨鸦会取消尚未命中的扑击。前三波依次介绍蓄力、扑击和墨弹拦截。第 46 秒先给出救援窗口，再进入后三波。打墨团可救人，打纸身扣印记。守到约 95.5 秒结算，结尾会区分摊主是否获救。整局使用 80 发光弹。

新版调整了墨鸦经过灯罩时的飞行高度和命中优先级，延长扑击动画，更新枪声并加入循环配乐。查看器会打开在第 11.2 秒附近，可通过「版本」菜单对照上一次首站试玩。旧 Demo 与 R2 仍可用于对照。

首站巷灯教学和靶场延迟出靶都有单独的审阅提案。在项目根目录的 PowerShell 中选定一个提案，再启动对应版本。

```powershell
$proposal = '.\gunforge\level_design\reviews\agent_proposals\proposal-1794220453914520000.json'  # 首站巷灯教学
# $proposal = '.\gunforge\level_design\reviews\agent_proposals\proposal-1794231862601292700.json'  # 靶场提前出靶
.\gunforge\start_level_player.ps1 -Proposal $proposal
.\gunforge\start_level_review.ps1 -Proposal $proposal
```

在查看器里，拖到要反馈的时刻。有对应事件时，先选中该事件，再填写批注并点击「保存当前帧的批注」。如需从头体验候选，使用试玩入口。

## 第二站白模 · 糖葫芦摊

```powershell
.\gunforge\start_level_player.ps1 -Package paper.stall -Candidate
.\gunforge\start_level_review.ps1 -Package paper.stall -Candidate
```

用 Enter 开始，左键射击。每轮先射右边的巷灯。灯亮时会持续发出暖光并显示 6 秒倒计时，墨鸦从冷蓝硬化态恢复原色，可以击破。灯灭后墨鸦恢复硬化，可以再次点灯。首轮只教点灯。后两轮墨鸦入场后会自行蓄力，灯灭时也会攻击。红圈期间可以点灯并击破墨鸦来打断，爪痕飞出后会在到达时造成伤害。共三轮、六只墨鸦，35 发光弹，50 秒内清完通关。这个独立白模复用首站的夜市背景和墨鸦素材。

## 战斗候选 R2

双击根目录 **play_combat_candidate.cmd** 试玩，或 **review_combat_candidate.cmd** 打开只读审阅工具。两者自动准备素材、编译和导入 Godot 资源，不需要先打开编辑器。

```powershell
.\gunforge\start_level_player.ps1 -Package paper.assault -Candidate
.\gunforge\start_level_review.ps1 -Package paper.assault -Candidate
```

按 Enter 或点击画面开始和重试，左键射击，Esc 暂停。每局带 80 发光弹，每次有效开枪消耗一发，打完即无法继续射击。审阅器里先点「播放」，再点击画面射击。

六波共有 29 只敌人。红圈蓄满时怪物会扑向近景或发射可拦截的墨弹。开枪会显示金色弹道，受击会亮起红边并显示灯芯损失。朱印是弱点，射击灯能震退附近怪物 1.5 秒，冷却 6 秒。声音默认开启。

本轮采用已经确认的素材和风格，动作使用位移、旋转、缩放与命中回弹；尚未新增墨鸦逐帧或骨骼扑翼动画。合成的纸墨声音是可替换的原型音效。自然度、声音喜好及光枪手感需要实际试玩继续迭代。

旧 `paper.alley` 仍通过下述旧入口打开，候选不会自动采用。实际用户的五条批注保持 open，Agent 只提出解决版本。

普通 `-Package` 启动会优先读取该包已明确采用的源版本；未采用时使用默认样例。`-Candidate` 强制预览当前生成的默认候选，`-Build` 则打开指定构建。采用记录不会被重建脚本覆盖。软件版本更新后会从不可变源重新编译；审阅器只有在构建 ID 与采用记录一致时才显示“已采用构建”。

## 打开《纸灯城》可视化工具

在项目根目录双击 **review_levels.cmd**。它会先准备已有素材、编译《纸灯城》巷口，再打开 Godot 审阅窗口。

也可以在 PowerShell 中运行：

```powershell
cd D:\tvgun
.\gunforge\start_level_review.ps1 -Package paper.alley
```

如果系统执行策略拦截 `.ps1`，用根目录 `.cmd`，或：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\gunforge\start_level_review.ps1 -Package paper.alley
```

- 打开后暂停在开头。点“播放”观看当前进度，点“新一局”开始新的试玩。用“单帧”前进一步，也可点击下方时间轴跳转。
- 播放时点击画面射击；暂停时点击对象查看只读信息。
- “玩家正面 / 侧视 / 俯视”在同一时间点切换画面。蓝色箭头标出玩家的朝向，路线上的箭头表示配置的运动方向。示意图和正面小窗共用编号，点击编号或对象列表可查看属性。近远按缩放估算，缺少缩放数据的对象用空心编号放在参考中线上。
- 正面视图的“命中轮廓”显示来自实际图像 alpha、裁剪与透明度的轮廓。画面和试玩使用同一命中模块。
- 右侧“事件”“关卡树”“依赖图”查看触发、属性和依赖。选择事件后，下方显示设计与 source map；动态条件未发生时不编造绝对发生时间。
- “回放”菜单中的“最近输入判定”查看已消费输入、原始姿态绑定和结果。
- 填写批注后保存，会同时保存该版本的玩家画面、Alpha 图和输入记录。从侧视或俯视保存时还会保存对应的示意图。批注位于 `gunforge/level_design/reviews/comments/`，大文件放外部缓存。
- “打开构建”可切换候选，使用“版本”菜单查看差异或切换上一版本。设计数据只读，修改通过 Agent 补丁生成新候选。
- “回放”菜单可以保存和打开同一 build_id 的输入记录。用时间轴上方的 A/B 标记设置循环播放区间。
- 旧关卡及白模声音默认关闭，战斗候选 R2 默认开启。按钮控制实际 WAV cue。跳转不会补播已经过去的一次性声音，持续声音按记录的偏移恢复。
- “采用当前候选”是可选的用户操作：需要理由、警告确认及当前采用版本校验。预览和保存批注都不会自动采用。

保存批注后，可把文件名交给 Agent。Agent 读取画面和命中轮廓，按批注确认可修改字段和必须保留的字段，再生成候选。开发入口如下。

```powershell
$tools = '.\gunforge\pipeline\level_design'
& .\.venv\Scripts\python.exe "$tools\review_revision.py" prepare $annotation $task --allow /entities/launcher/x --preserve /controls
& .\.venv\Scripts\python.exe "$tools\agent_workflow.py" $task $patch
.\gunforge\start_level_review.ps1 -Proposal $receipt
```

准备任务时会校验原构建和批注保存的证据，提交时会再次检查批注与证据。候选预览打开在批注时刻，“切换上一版本”会在同一时刻来回对照。预览从新局推演到该时刻。涉及已打出的枪或道具效果时，可在对应原构建中打开批注保存的输入回放。

下面是《轨道防线》早期侧视白模的历史对照，用于复查发射机位置的批注。当前正面版使用后面的 `-Package orbital.siege -Candidate` 入口。

```powershell
.\gunforge\start_level_review.ps1 -Proposal .\gunforge\level_design\reviews\agent_proposals\proposal-1794208802414694900.json
```

《纸灯城》默认目标时长 78 秒；保留旧版浮点秒时钟的实际完成点为 78.1 秒，审阅范围包含完整结束。涉及续关的录制可继续扩展时间范围。

## 直接玩原型

双击根目录 **play_level_prototype.cmd**，或：

```powershell
.\gunforge\start_level_player.ps1 -Package paper.alley
```

按 Enter 开始/重试/恢复，鼠标点击射击，R 换弹，Esc 暂停，G 切换光枪输入，Q 退出。同一局域网内的手机可自动发现播放器。发现使用 UDP 8001、8081 或 9001，瞄准使用 UDP 9000。自动发现后的 HTTP 事件使用 TCP 9000，原 TCP 8080 入口也可使用。播放入口持续接收网络恢复消息，暂停原因彼此独立。

在播放器按 F2 打开显示设置，按 C 开始光枪校准。《纸灯城》的手机光枪配 PC 显示器已通过用户验收。电视实测安排在发布阶段。

## 验证其他题材

靶场先用鼠标试玩。在项目根目录运行下面的命令，打开已采用的 2.8 秒出靶版本。

```powershell
.\gunforge\start_level_player.ps1 -Package gallery.intro
```

按 Enter 开始。用左键射击左边的蓝绿色圆靶，再射击第 2.8 秒出现的右边移动圆靶。黄色方块是保护对象，误打会立即失败。两个圆靶都命中可得 200 分，打中右靶会结束本局，所以想验证两个靶请先打左靶。一局最多 12 秒，初始 4 发，R 换弹，Enter 重试。

此前的候选在第 4 秒出右靶。运行以下命令可在第 3 秒对照，用「版本」菜单里的「切换上一版本」查看同一时刻的区别。

```powershell
.\gunforge\start_level_review.ps1 -Proposal .\gunforge\level_design\reviews\agent_proposals\proposal-1794231862601292700.json
```

```powershell
.\gunforge\start_level_review.ps1 -Package gallery.intro
.\gunforge\start_level_review.ps1 -Package orbital.convoy
.\gunforge\start_level_player.ps1 -Package gallery.intro
.\gunforge\start_level_review.ps1 -Package orbital.siege -Candidate
.\gunforge\start_level_player.ps1 -Package orbital.siege -Candidate
```

靶场有移动目标、保护对象、区域进入、弹药和成功/失败。护航白模有护盾窗口、双发目标、可拦截投射物、船体与任务分支。《轨道防线》采用玩家所在位置的正面镜头。敌机从舱门方向由远及近，弹体飞向镜头，漏接会扣玩家护盾。射击干扰器可以延缓敌机出手。

## 编写一条战斗关卡

从 [轨道防线的 JSON](../gunforge/level_design/examples/orbital.siege.json) 查看完整示例，选择 `directed_action@1`。

- `encounter.waves.<波次ID>.at_ms` 是波次开始时间。`spawns.<实体ID>` 是相对该波次的出场延迟。每个实体实例只进场一次，同一敌种可以配置多个实例 ID。
- `encounter.attacks.<实体ID>` 定义预警、出手、退场、伤害资源和效果。近战用 `contact_ms`，远程用 `projectile.flight_ms` 和内容坐标中的落点。攻击时间以实体进场后的局部时钟计，干扰会暂停这个时钟，击破会取消尚未发生的攻击。
- 运动关键帧可以用 `attack_time` 引用 `windup`、`release`、`contact` 或 `retire`，也可以用 `offset_ms` 设置相对偏移。修改出手或命中时间时，绑定关键帧一起移动。
- `encounter.supports` 指定支援实体、目标、范围和干扰时长。射击弹道起点和出手特效终点可以用 `anchor_uv` 按画布比例设置。有限弹药用 `controls.ammo_resource` 绑定计数器。

Agent 可以按 ID 修改这些字段，例如 `/encounter/waves/approach/spawns/rammer`。编译器会展开普通运行事件，并在审阅器的事件详情里保留到源字段的路径。

## 打开 Agent 自审候选

示例索引在 `gunforge/level_design/reviews/agent_example_runs.json`。其中 `examples.gallery.compiled` 和 `examples.protection.compiled` 是实际候选构建路径：

```powershell
.venv/Scripts/python.exe .\gunforge\pipeline\level_design\build_examples.py
$examples = Get-Content -Raw -Encoding UTF8 .\gunforge\level_design\reviews\agent_example_runs.json | ConvertFrom-Json
.\gunforge\start_level_review.ps1 -Build $examples.examples.gallery.compiled
```

靶场候选把目标 B 晚出两秒并向中央移动，同时保持预警提前量与入区行程；科幻候选推迟并放慢第二发投射物。它们来自 Agent 查看实际画面后的自审，保留了原版和约束，**不是用户批注或用户已采用**。

## 环境与检查

需要项目 `.venv/Scripts/python.exe`、Godot 4.6.3 Compatibility 和已有已审核素材。可用 `GODOT_BIN` 指定 Godot，`GUNFORGE_LEVEL_CACHE` 指定缓存；默认缓存为项目同级 `gunforge_cache/level_design/`，不要求固定 D 盘。

开发依赖版本记录于 `gunforge/pipeline/level_design/requirements.lock`。当前环境使用 uv，可重装关卡模块依赖：

```powershell
uv pip install --python .venv/Scripts/python.exe -r .\gunforge\pipeline\level_design\requirements.lock
.venv/Scripts/python.exe .\gunforge\pipeline\level_design\verify_software.py
.venv/Scripts/python.exe .\gunforge\pipeline\level_design\verify_delivery.py
```

检查会新建独立证据目录；入口索引为 `gunforge/level_design/reviews/software_acceptance.json`。它涵盖源哈希、编译内容校验、回放、快照/跳转、三包机器人、真实 GPU 界面及回环 HTTP/UDP。手机追踪、电视延迟、真实试听和用户评价不在其通过结论中。

`verify_delivery.py` 需要 uv；它复制必要源码与已审核素材，在独立目录创建新 Python 3.12.10 环境、按锁文件装依赖、使用空缓存重建七个包，核对 build_id，再执行机器人与实际 GPU 启动。结果见 `delivery_acceptance.json`。Godot 4.6.3 必须另行提供，可设置 `GODOT_BIN`。

如果报“版本/资源改变”，先重新运行相应启动脚本构建，或从不可变源重新编译；不要手改缓存中的 `level.json`。关闭占用同一端口的旧游戏再启动新的播放入口。可视化审阅本身不占用手机网络端口。
