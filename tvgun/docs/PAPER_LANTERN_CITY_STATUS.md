# 《纸灯城》开发状态与换机交接

更新于 2026-11-13。开发分支为 `main`，T13 本轮代码基线为 `c4d6ee1`。

## 当前进度

- **三关候选的 PC 鼠标和手机光枪配 PC 显示器均已通过用户验收。** 手机可通过局域网自动发现播放器并开打。[设备验证路线](../gunforge/games/g01/reports/art/T16/cast/a7/device_route.md)
- **巷口七层已完成 C07b 实际渲染检查。** 遮罩内部未发现低于半透明的缺口，六层轮廓有低于严格不透明门槛的像素，留待美术复核。[逐层诊断与复跑](../gunforge/games/g01/reports/art/T16/cast/supplies/c07b_report.md)
- **三关 15 站的 C07a 画面覆盖复测通过。** 406 个回放时刻与 185 个静止和视差极限样本均未露底。[逐帧数据和复跑](../gunforge/games/g01/reports/art/T16/cast/supplies/c07a_report.md)
- **生命和补给版已通过用户的 PC 鼠标验收。** 左下角显示生命数字，救援回复 1 点生命，8 发开局，首次点亮每盏灯补 4 发。[新版试玩与补给规则](../gunforge/games/g01/reports/art/T16/cast/supplies/report.md)
- **上一版 PC 试玩反馈已修订。** 当时的三关弹匣为 18 发，打空 0.35 秒自动换弹。巷灯退到墨鸦后方，巷口蓄力与扑击延长。新版通过鼠标定点回归和三关 15 站回放。[新版试玩与复测](../gunforge/games/g01/reports/art/T16/cast/mouse_balance/report.md)
- **片尾全景左侧摊位与屋檐已有可试玩的调色对照。** 拉远后的近朱砂面积从 1.031% 降到 0.313%，叠化时序和 118 条输入回放一致。正式播放器复测通过，调色待美术签核。[试玩与七组同帧对照](../gunforge/games/g01/reports/art/T16/cast/a7/ending_palette/report.md)
- **三关候选完成 C04 色板筛查。** 120 条贴图达到初始门槛，91 条低于门槛。Godot 同帧对照定位到片尾全景左侧摊位和屋檐的近朱砂色。[逐件数据和同帧对照](../gunforge/games/g01/reports/art/T16/cast/a7/c04_report.md)
- **三关候选完成 C05 文字筛查。** 四张标题与关卡字形在原贴图和 Godot 实际画面中均识别正确。256 条色彩图记录中，174 条自动通过，82 条留待目视复核。[检查报告与复核页](../gunforge/games/g01/reports/art/T16/cast/a7/c05_report.md)
- **候车室的回放检查点耗时降至 1.92–2.05 ms。** 第 8520 帧在两轮全程复测中分别为 8.55 和 8.31 ms。两轮共 26,634 帧，全部低于 16.67 ms。银幕前首帧为 5.37–5.62 ms。[分段采样、复测和试玩](../gunforge/games/g01/reports/art/T16/cast/performance.md)
- **上一轮序列化优化通过回放复测。** 单站 48.37 MiB，转场 72.33 MiB。调整射击姿态序列化和回放检查点后，两轮共 26,634 帧保留一次银幕前首帧 17.50 ms 的记录，118 条输入逐字节一致。[性能数据和复跑](../gunforge/games/g01/reports/art/T16/cast/performance.md)
- **本轮已修整 50 张贴图的透明边缘。** 本轮填齐 98,570 个紧贴轮廓的透明黑点。256 张色彩图的四邻检查均通过，三关回放、第三关 C06 与 606 组 C13 模拟投影均复测通过。[逐件对照与复跑](../gunforge/games/g01/reports/art/T16/cast/a7/remaining_edges_report.md)
- **龙头、骑车居民、影院弱点和准星的八张贴图已修整。** 16 组 Godot 缩放对照、两处朱砂弱点、30 个墨舞龙姿势与 15 站连续回放均通过。当前构建 606 组 C13 合成追踪全部锁定，最大角点偏差 0.749 个模拟相机像素。[修整、弱点和追踪](../gunforge/games/g01/reports/art/T16/cast/a7/priority_edges_report.md)
- **两张挡弹前景和七份纸偶图集已修整透明边缘。** 91 个绑定分件已复查，九张图均保留原 alpha 与可见 RGB。18 组 Godot 缩放图、四次挡弹与空枪和 118 条三关回放均已验证。[修整前后对照与复跑](../gunforge/games/g01/reports/art/T16/cast/a7/edge_fill_report.md)
- **半透明边缘对照已生成。** 136 张源图与 4 张正式 HUD 字形可并排看黑白底和边缘近景。最新隔离包已更新这些对照。[对照、位置和复跑](../gunforge/games/g01/reports/art/T16/cast/a7/alpha_edges_report.md)
- **三关候选已补齐 19 张色彩图的 RGBA8 运行副本。** 296 张 PNG 均通过用途对应的编码检查。新旧构建的 50 张 Godot 路线原帧逐像素相同，15 站、118 条回放输入、失败重试和开场片尾均复测通过。[编码、像素比对与复跑](../gunforge/games/g01/reports/art/T16/cast/a7/asset_coverage.md)
- **A7 验收材料和真机路线已就绪。** 最新隔离目录核对了 384 个文件，复跑 15 站、118 条输入及开场和片尾。342 个编译资源的来源记录已核对路径。显示器和电视的录制、混音实听及人工签核待完成。[验收索引、真机路线与证据](../gunforge/games/g01/reports/art/T16/cast/a7/report.md)
- **已修正全屏白框裁切和缩放同帧的光枪偏移。** 显示器档与电视档的六种窗口或全屏配置、37 次 UDP 扳机均通过。旧版缩放同帧偏离 225.03 像素的灯笼一枪，修正后坐标吻合并命中。[窗口对照、坐标数据与复跑](../gunforge/games/g01/reports/art/T16/cast/display_resize/report.md)
- **隔离候选的 90 秒开场与 58 秒有声片尾已通过正式播放器回归。** 开场 14 条字幕、片尾两句旁白的起止窗口、四种片尾跳过与 UDP 重试均已验证，所有片尾路径保持同一结算。[画面、时序和复跑](../gunforge/games/g01/reports/art/T16/cast/cutscene_player/report.md)
- **墨舞龙的龙节和龙嘴通过当前候选的随动命中区复查。** 30 个游动、开口和摆头姿势的有效半径均达到 40 px。八节依序净化后才开放龙嘴，龙颚挡弹、打断喷墨和影院交接均已验证。[游动图板、龙嘴近景与复跑](../gunforge/games/g01/reports/art/T16/cast/dragon_masks/report.md)
- **银幕影 Boss 的三盘墨渍和影核通过命中区复查。** 四个目标的有效半径为 56.49–58.42 px，命中像素均落在墨色内。三路暖光独立切换，最后一盘净化后解锁影核，机身误射与火车站交接也已验证。[命中边界、暖光对照与复跑](../gunforge/games/g01/reports/art/T16/cast/screen_boss_masks/report.md)
- **天桥和影院已补齐攻击预警对照。** 车铃、居民受惊和墨车夫的预警同帧触发，三个放映机各自按时生成磁带墨怪。四条中断分支在对应伤害时刻保住灯芯，12 组 1/8 对照均保留像素差异。[图板、音画时序与复跑](../gunforge/games/g01/reports/art/T16/cast/attack_warnings/report.md)
- **工作台「忘」字七笔已在最新候选逐笔复查。** 七个落笔光点均可命中对应笔画，有效半径为 40.71–75.46 px。第 2、3 笔的 363 个交叉像素均归第 3 笔，实际射击只擦伤第 3 笔。七笔完成后进入点灯片尾。[缩略图、交叉近景与复跑](../gunforge/games/g01/reports/art/T16/cast/workbench_readability/report.md)
- **第三关四个战斗站点已补齐当前候选的 C06 数值证据。** 20 个普通态样本和 10 只硬化眼均达标，8 个预警在 1/8 缩略图保留像素差异，33 张整帧均通过 C03。[图板、数据与复跑](../gunforge/games/g01/reports/art/T16/cast/readability_c06/report.md)
- **正式播放器战斗输入已通过软件回归。** 白边和内侧暗区开枪会扣弹，校准框外才换弹。隔离候选通过 15 个 UDP 扳机事件和 2 次 HTTP 请求，覆盖水洼、天桥、站台和转场。[回归与复跑](../gunforge/games/g01/reports/art/T16/cast/udp/report.md)
- **当前候选的三关候选通过 C13 合成追踪筛查。** Godot 整窗画面的 606 组正常几何投影均捕获白边四角并通过中空校验，最大模拟角点偏差为 0.749 像素。实体光枪录制待验收。[追踪证据与复跑](../gunforge/games/g01/reports/art/T16/cast/tracking_c13.md)
- **RGBA8 补齐前的三关候选通过 C15 资产预算复测。** 两轮共 26,634 帧，单站资产峰值 48.37 MiB，转场资产峰值 72.33 MiB。两轮均未超过 16.67 ms。摸底的两处慢帧已保留记录。[性能数据与复跑](../gunforge/games/g01/reports/art/T16/cast/performance.md)
- **最新三关候选的全作画廊已更新。** 51 张同一构建的 Godot 抓帧覆盖 15 站、8 套居民造型、7 种墨怪、3 个 Boss 和 15 个界面状态。天桥警铃同框、路人 A 救援前后、水洼小群和片尾全景均可审看。[最新全作画廊](../gunforge/games/g01/reports/art/T16/cast/gallery.html)
- **天桥已接入骑车的居民。** 桥上居民和自行车可被光弹穿过，桥下墨车夫仍可命中。`paper.lantern_city_cast` 包含 8 套居民造型和 7 种墨怪，三关 15 站、118 条输入回放和 384 文件的隔离副本均已验证。[试玩、抓帧与交付清单](../gunforge/games/g01/reports/art/T16/cast/report.md)
- **路人 A 已接入第三关站台。** `paper.platform_passerby` 可直达站台，`paper.lantern_city_rescue` 可从头连玩。纸身保护、胸口墨团、获救反馈及跨站救援计数通过。三关 15 站和 118 条输入回放通过。[试玩与抓帧](../gunforge/games/g01/reports/art/T16/passerby/report.md)
- **墨蝌蚪已接入三关候选。** `paper.lantern_city_tadpole` 在巷口第六波后加入水洼小群。三关 15 站、118 条输入回放、灯芯与光弹等资源衔接、水洼和工作台重试均通过。12 个头部对比度样本达到 C06 数值门槛。[试玩、抓帧与回归](../gunforge/games/g01/reports/art/T16/tadpole_campaign/report.md)
- **墨蝌蚪独立试玩已通过软件回归。** `paper.tadpole_encounter` 在夜市巷口安排三只墨蝌蚪从水洼扑近，头部可命中，朱印加分。头部尺寸、群体间距、尾部空枪、失败重试和回放已验证。[试玩与抓帧](../gunforge/games/g01/reports/art/T16/tadpole/report.md)
- **T16 早期画廊可用于对照。** 46 张 Godot 抓帧记录水洼接入前的三关场景、Boss 和界面状态。[早期画廊](../gunforge/games/g01/reports/art/T16/gallery.html)
- **T16 交付候选清单已核对。** 333 个编译资源和两份开场媒体通过完整性检查。375 文件的隔离副本通过开场、三关 15 站、114 条输入回放、工作台重试和片尾跳过。正式 A7 验收待完成。[交付清单与复跑](../gunforge/games/g01/reports/art/T16/report.md)
- **T15 58 秒有声片尾可试玩。** `paper.lantern_city_epilogue` 的灯城全景让夜市、旧影院和火车站同框。四段均可跳过，自然播完与跳过进入相同结算。美术、节奏、混音和实体光枪仍待验收。[片尾预览与试玩](../gunforge/games/g01/reports/art/T15/report.md)
- **T14 全套界面预审已就绪。** `paper.lantern_city_ui` 接入三关 HUD、开始与重试、字形和校准。光枪失锁时保留 HUD，并提示「请对准屏幕」。画廊集中展示同一构建的 17 张画面及待验项目。[预审画廊和试玩入口](../gunforge/games/g01/reports/art/T14/gallery.html)
- **三关连续候选已通过软件回归。** `paper.lantern_city_campaign` 从夜市巷口经过旧影院和火车站，在工作台第七笔净化后结算。15 站与 114 条输入回放通过，工作台失败能从巷口重试。第七笔后接入 10.8 秒的可跳过工作台片尾，正式旁白、完整版片尾和整作光枪验收待完成。[片尾抓帧与软件回归](../gunforge/games/g01/reports/art/T13/gallery.html#ending)
- **0B 与 T12 已验收。** 用户确认 0B 五项正式签核。T12 已完成 A5，手机光枪在显示器和电视上均通过。两关连续包 `paper.lantern_city` 已通过十站软件回归。第一关部分独立候选的设备复测仍有历史待项，详见[美术执行状态](../gunforge/games/g01/reports/art/execution_state.json)。
- **T13 连续候选已到工作台。** `paper.train_station` 串联候车室、站台、绿皮车厢和灯座，最后拉镜抵达工作台。通关、失败重试、资源跨站、输入回放、灯光预载均已验证。用户已验收原版候车室。[T13 报告](../gunforge/games/g01/reports/art/T13/report.md)
- **三站普通态对比度试样已可运行。** 候车室、站台、绿皮车厢各有一个独立候选，每站六个可射样本均达到 C06 的 0.20 数值门槛。灯座原版的两个样本已达标。试样色调与 1/8 缩略图辨识度留待美术复核。[四站预审画廊与 JPG 对照](../gunforge/games/g01/reports/art/T13/gallery.html)
- **四站硬化眼试样已可运行。** `paper.train_station_hardened` 采用原站点画面，四站五个姿态的 10 只眼均达到 C06 的亮度与尺寸门槛。射击硬化眼判为无效，软化时切回原朱砂印记。全程软件回归和回放已通过，墨伞眼形留待 A5。[硬化眼对照与验收记录](../gunforge/games/g01/reports/art/T13/variants/hardened_eyes/comparison/checks.json)
- **T13 可读性合并候选已获用户确认。** `paper.train_station_readability` 串联三站普通态调色与四站暖纸色硬化眼。33 张抓帧通过 C03，20 个普通态样本与 10 只眼达到 C06 数值门槛。用户于 2026-11-11 确认可读性合并候选验证通过。[同姿态对照与试玩入口](../gunforge/games/g01/reports/art/T13/gallery.html#combined-readability)
- **工作台「忘」字 Boss 已接入第三关候选。** `paper.train_station_boss` 从候车室打到第七笔结算。顺序命中、误射、交叉层级、失败重试和 26 条输入回放通过。Boss 美术和第三关实体光枪待验。[Boss 画廊与回归](../gunforge/games/g01/reports/art/T13/gallery.html#forget-boss)

## 在新 Windows 机器上启动

准备 Git、Git LFS、uv 和 **Godot 4.6.3 Windows console**。下列命令在 PowerShell 执行。Godot 路径换成新机器上的实际位置。

```powershell
git lfs install
git clone --branch main https://github.com/xslkim/tvgun.git
Set-Location tvgun
git lfs pull

uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r gunforge/pipeline/level_design/requirements.lock

$env:GODOT_BIN = 'C:\Tools\Godot\Godot_v4.6.3-stable_win64_console.exe'
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_cast -Candidate -QuitAfter 2
```

已有本地克隆时，在 `main` 上执行 `git pull --ff-only origin main`，再执行 `git lfs pull`。启动冒烟检查应输出 `level_player_ready:true`、`http_error:0` 和空的 `udp_errors`。去掉 `-QuitAfter 2` 即可试玩。按 Enter 开始，左键射击，R 换弹。

- `paper.lantern_city_epilogue` 打开 T15 片尾候选，按 Enter、Esc 或光枪开始键可跳过片尾。
- `paper.lantern_city_cast` 打开含 8 套居民造型和 7 种墨怪的完整三关候选。`paper.footbridge_cyclist` 可直接试玩天桥。
- `paper.lantern_city_rescue` 打开含水洼和路人 A 救援的三关候选。`paper.platform_passerby` 可直接试玩站台。
- `paper.lantern_city_tadpole` 打开包含墨蝌蚪水洼、完整界面和有声片尾的三关候选。加 `-SkipOpening` 可跳过开场。
- `paper.lantern_city_ui` 打开 T14 界面候选，按 H 切换准星。
- `paper.lantern_city_campaign` 打开三关连续候选。加 `-SkipOpening` 可跳过开场。
- `paper.tadpole_encounter` 直接打开巷口水洼的墨蝌蚪小群试玩。
- `paper.train_station_boss` 打开可打到工作台 Boss 结算的第三关候选。
- `paper.train_station_readability` 打开已验证的可读性合并候选。
- `paper.train_station` 打开 T13 原版四站连续候选。
- `paper.train_station_hardened` 打开四站暖纸色硬化眼试样。
- `paper.waiting_room_contrast`、`paper.platform_contrast`、`paper.green_car_contrast` 分别打开三个普通态对比度试样。
- `paper.lantern_city` 打开前两关连续包。加 `-SkipOpening` 可直接进玩法。

素材和 JPG 证据随 Git LFS 获取。`.venv`、Godot 可执行文件和编译缓存由新机器准备。启动器会按当前仓库路径生成关卡资源和编译收据。旧收据中的 `D:\tvgun`、`D:\gunforge_cache` 路径用于定位原机证据；新机器启动时用 `-Package … -Candidate` 生成本机路径。

继续做美术数值检查时，执行 `uv sync --locked --project gunforge/pipeline/art`。该环境包含 SciPy 和 scikit-image；当前候选的启动和关卡编译使用根目录的 `.venv`。旧 GPU 原始抓帧位于原机缓存，代表帧 JPG 和验收 JSON 已入库。

## 在新机器上复跑

先运行上面的三关启动命令生成本机收据，再运行关卡工具测试和三关软件回归。

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s gunforge/pipeline/level_design -p 'test_*.py'
$review = Get-Content -Raw gunforge/level_design/reviews/lantern_city_cast_build.json | ConvertFrom-Json
$root = (Get-Location).Path
& $env:GODOT_BIN --headless --path gunforge/framework --script res://tests/night_market_tests.gd -- "--build=$($review.compiled)" "--assets=$root" --failure-retry=true
```

三关回归预期在工作台结算，最终为 4 条灯芯、11 发光弹、7 人获救、9275 分。独立 Boss 回归用 `train_station_boss_build.json` 和 `res://tests/workbench_boss_tests.gd`。可读性抓帧由 `gunforge/framework/tests/train_stop_readability.gd` 生成，数值由 `gunforge/pipeline/art/t13_readability.py` 复算。`build_train_station_readability.py --probe-builds <目录>` 可同时生成四站的单独抓帧构建。

## 接下来做什么

PC 鼠标和手机光枪配 PC 显示器的试玩验收已通过。电视仍安排在发布验收。[手机光枪实测路线](../gunforge/games/g01/reports/art/T16/cast/a7/device_route.md)

1. **复核巷口轮廓与挡弹。** 确认 C07b 的半透明轮廓是否符合纸层效果，继续核对 C08 近景挡弹与可见轮廓的一致性。[巷口诊断](../gunforge/games/g01/reports/art/T16/cast/supplies/c07b_report.md)
2. **整作美术签核与发行包验证。** 复核待签素材，补齐正式资产清单，并验证最终 Windows 发行包。
