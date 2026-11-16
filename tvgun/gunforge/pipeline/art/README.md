# 美术离线工具

本地审核服务退出或电脑重启后，在仓库根目录执行 `./gunforge/pipeline/art/start_review.ps1` 恢复。当前人物审核为 http://127.0.0.1:8767/gallery/；8765 为历史 T02 参考图、8766 为 T03。脚本隐藏启动服务，仅绑定 127.0.0.1，已监听的端口不会重复启动；日志在本目录 `.review-logs/`。这不是随系统登录自动启动的常驻服务。

当前图片路径已改为内置 GPT 图像工具，由 agent 直接调用；不需要 `.env` 或出图 API 密钥。T01 改为最多三次实际出图/透明/编辑/参考小样验证。Python CLI 继续负责元数据、组装和检查，不尝试替代内置出图工具。

用量按 `config.yaml` 的 `task_call_caps` 记录，每批最多十次、0A 最多一百二十次，含失败和重试。工具未披露的费用记 null/not_reported，不能套旧供应商价格或记成免费。现有美元费用账本仅供未来明确启用的外部付费服务使用，不能把 null 金额传给它当零结算。

在仓库根目录执行：

```powershell
uv sync --project gunforge/pipeline/art
uv run --project gunforge/pipeline/art python gunforge/pipeline/art/verify.py
uv run --project gunforge/pipeline/art python gunforge/pipeline/art/cli.py --help
```

`bootstrap.py` 仅首次执行；已有配置时拒绝运行，避免覆盖费用配置与审核记录。

`cli.py` 提供 crop、sdf、split、matte、checks、render、whitebox、gallery、review。帮助与实际 JSON/YAML 字段见相应 Python 模块；checks 输入是以检查编号为键的字典，路径相对输入文件目录。结果写入每项 JSON，存在图像输入时附预览证据。`verify.py` 提供可运行的合成正反例。

缓存、原始 fixture 和中间文件在 `D:/gunforge_cache/g01/T00/`；报告与可打开的独立画廊在游戏 reports/art/T00 下。画廊只展示证据，不自动修改审核表；review.yaml 需要审核人决定。重复生成画廊不会覆盖审核表。

费用账本使用 SQLite 事务保存生成尝试、预留款、供应商任务 ID 与结算金额。提交前 reserve；供应商接受后立即 submitted；返回费用后 settle；重启 recovery。没有供应商任务 ID 的在途记录属于未知提交，不能自动再花钱提交一次。`records()` 可导出 manifest 数据；API 密钥不能放入 payload。固定汇率 7.0 是规划记账值，不是实时汇率，所有美元/人民币比较使用此配置。

当前没有外部付费服务客户端；图片直接用内置工具，输出复制到任务缓存后再处理。优先保留原生 alpha；BiRefNet 仅是可选本地适配，需要 `uv sync --project gunforge/pipeline/art --extra matting`、权重和输出约定验证，不作为直接 GPT 出图的前置条件。

C05 需要本地 Tesseract 及中文语言包；C14 需要锚点和标定后的视觉模型。数字检查只证明所运行的部分：C06 数值通过不等于缩略图识别通过；C10 清单通过不等于姿势接缝通过；C11 静态包含不等于实际着色器全状态对齐；C15 离线估算合格不等于引擎显存实测通过。缺失证据返回 pending。

C13 只读调用现有追踪器，以已有根目录 Python 环境的 cv2 运行三组确定性投影。既不修改追踪代码，也不生成该目录的字节码。合成截图筛查不能替代真机连续录制。

合成器支持分层视差与呼吸、纸偶层级变换、墨怪共同画布与裁剪原点、近似位移/淡出、灯光叠加、HUD 与调试叠图。它不是 Godot 渲染器；实际风格包的位移、溶解、过滤、压缩和峰值显存均需另行验收。不得将其通过结果直接标成实际 0B 或 A7 通过。
# A2b 人物动作与墨怪受击修正

当前已收到 A2 的部分视觉认可；人物旧动画退回，等待新版动作和墨怪受击反馈。
本轮不新增 GPT 图像调用。不要用旧的姿势轮换视频代表新版动作，也不要将视觉认可写成技术或真实 0B 通过。

复现顺序（使用本目录 `.venv/Scripts/python.exe`）：

1. `build_motion_v2.py`：独立人物片段、髋部根、腿 IK、脚落地及附墨专用姿态；原 PNG 保留。
2. `verify_motion_v2.py`：逐帧附墨保护、实际膝肘方向、像素接缝抽查和破坏样本。
3. `enemy_feedback.py`：普通命中、印迹命中、净化消散的离线近似及逐帧对齐检查。
4. `motion_reservations_v2.py`：完整候选动作范围与相机/呼吸、HUD、边缘带检查。
5. `publish_a2b.py`：发布到现有 T07 审核页，保留 A2 意见与失败历史；`finalize_a2.py` 在已有 A2b 反馈时也会走此分支。

审核入口继续使用 `http://127.0.0.1:8767/gallery/`。新一轮只问人物动作和墨怪受击两项，其他已确认的美术方向不重复审批。正式引擎、追踪筛查和真实 0B 门槛保持。

## A2c：以本轮为当前版本

A2b 被明确退回：掌面左右错误、动画与表情不合适、受击偏弱。调研规则见 `D:/tvgun/docs/art/ANIMATION_RULES_A2c.md`。旧版本和失败数据保留，新版本不继承旧人审选择。

已归档的四次内置 GPT 返回用于两个担忧头部、两个正确右手掌；不应重新调用出图。复现顺序：`prepare_attachments_v3.py`、`build_motion_v3.py`、`verify_motion_v3.py`、`verify_acting_v3.py`、`enemy_feedback_v3.py`、`motion_reservations_v3.py`、`publish_a2c.py`。所有命令用本目录 `.venv/Scripts/python.exe`。前臂原始 `_l` 表示画面左、角色自身右；新增掌面为腕部视觉附件，不是第十一根人体骨骼。

新页面增加半速和手掌/表情关键姿势近景，仍只反馈两项。`verify_a2c_gallery.cjs` 是独立 VM 的交互检查，不操作实际用户草稿。真实浏览器播放证据在 `T07/revisions/A2c/`。`finalize_a2.py` 和旧发布器会优先发布 A2c；不能用旧A2b报告覆盖新一轮意见。A2全技术验收和真实0B均未通过。

## A2d：当前版本，只复核放下手的肘部

A2c 墨怪受击已被用户明确认可，保持全部 v3 预览文件哈希不变，不重复索要审核；人物低位肘部退回。`puppet_motion_v4.py` 用实际肩—肘—腕夹角换算每个人的局部旋转，低位约6度，三次 Hermite 曲线连贯收臂。角度是项目姿态选择，不是通用人体限制。

复现：`build_motion_v4.py` → `verify_motion_v4.py` → `verify_lowering_v4.py` → `motion_reservations_v4.py` → `publish_a2d.py`。无需新图、无需重跑敌人生成。新增 `lowering` 视频是完整求助片段的单次收臂预览，不作为新的运行时攻击动作。`verify_a2d_gallery.cjs` 验证单问题反馈与保留的受击认可；最新发布分支会优先 A2d。原始截图和意见保存在 `T07/revisions/A2d/`，历史A2c在外部缓存归档。批量仍等真实0B。

## A2e 技术检查点

A2d肘部已明确通过，墨怪受击沿用A2c。`a2_followthrough.py` 记录意见、实测C12首尾速度、静态可读性和extent独立性；`a2_slots.py` 检查200px墨鸦的20槽位×5相机×2灯光，并输出硬化眼暖纸色运行时材质试稿。`tracker_diagnostic.py` 用根目录cv2环境定位原C13夹具问题；`tracker_screen.py` 保留原越界透视压力样本，合法几何测试独立计分，真实相机仍pending。不要改动追踪器来迎合合成样本。

`publish_a2e.py` 发布当前技术决策页；需用户选择硬化眼试稿和C03亮度路线，不能自动批准规范例外。完整隐藏几何、正式引擎与真实0B待办保留。`verify_a2e_gallery.cjs` 只在独立VM验证反馈，不能替用户作选择。当前报告在T07/revisions/A2e/。

## A2f：已批准材质/亮度例外与联合排布

A2e两项已由用户明确批准。`apply_a2e_decisions.py` 幂等保存原话，绑定本试做站点的 `bible/luminance_policy.json`，更新方案与配置，硬化墨鸦材质写 `bible/material_contract.json`；其他站点不可复用例外，历史C03失败保留。

复现顺序：`a2_joint_slots.py`（720居民帧×4槽，固定相对视差）→ `a2_structure.py`（独立手工四墙面区域，不等于完整隐藏几何）→ `a2_composite.py`（互斥排布和8秒联合参考）→ `verify_a2f.py`（例外范围与材质负例）→ `verify.py`（45核心检查）→ `publish_a2f.py`。不需要新出图。

`preview.py` 已修复敌人坐标原点覆盖场景裁切原点的问题，`materials.py` 保持眼形alpha并应用已批准硬化眼材质。`station_policy.py` 不接受其他站点、缺失槽位证据或低对比样本。候选调度在 `bible/prototype_slot_schedule.json`，并非已经接入引擎。T08及批量门槛不变。

## A2g：糖葫芦握持与纹理预算

用户A2f认可同屏可读性和四块墙面区域，但指出糖葫芦方向。`start_a2g.py` 归档意见；`puppet_motion_v5.py` 只给卖糖葫芦居民的裸签/掌心握点与世界朝向补偿，录像厅老板不改。旧角度负例、1128道具状态、7循环与24个老板对照由 `verify_prop_v5.py` 复核。

复现：`build_motion_v5.py` → `verify_motion_v5.py` → `verify_prop_v5.py` → `motion_reservations_v5.py` → `a2_joint_slots_v5.py` → `a2_composite_v5.py` → `a2_memory.py` → `a2_texture_pack.py` → `publish_a2g.py`。无需新出图。

纹理原估算超站点48MiB，稀疏128px内容块+2px bleed候选使估算下降且黑/白重组完全一致。只是GPU打包计划，当前参考视频仍用整图；mip接缝、采样、draw calls和真实峰值待引擎实测。预算估算不能标成正式C15通过。当前审核只问修正后的糖葫芦方向，旧认可不重复询问。

## A2h：预警态、完整层设计范围与采样失败处理

A2g糖葫芦已获认可。`start_a2h.py` 记录意见；`a2_mip_sampling.py` 暴露独立块mipmap采样偏差，原A2g低估算方案不可直接用于GPU。增加bleed未解决全部偏差，失败证据保留。

`a2_hybrid_pack.py` 采用稀疏base（不生成局部mip）和预生成的整层低分辨率链，透明边界guard及每图块大小选择。当前g01-alley-hybrid-2b只在CPU浮点参考中验证，8bit上传、颜色空间、LOD和GPU性能仍pending。`bible/texture_candidate_status.json` 明确旧方案用途限制与无GPU批准候选。

`a2_extent_proposals.py` 提供7张完整层与mask设计提案，来源是当前alpha，未伪装为独立几何真值；需用户明确确认预期整纸形状，才可冻结设计基线，不能由现有alpha自洽自动算C07b通过。`a2_warning_readability.py` 提供最小尺寸墨鸦/墨蝌蚪普通/预警对照；`verify_a2h.py` 检查采样负例、哈希与待审状态；`publish_a2h.py` 发布当前两项检查点。不增加出图调用，T08和真实0B门槛保留。

## A2i：A2h 已认可，进入 T07 阶段审核

`freeze_a2h.py` 记录明确反馈，将七张设计范围复制到独立的 `bible/geometry/alley_extent_v1/`，同时记录认可的预警参数。`verify_frozen_geometry.py` 用冻结哈希、实际图像、125 个状态检查覆盖；篡改负例调用同一个真实加载器验证拒绝，不能重生成基线规避检查。

复现：`verify_frozen_geometry.py` → `t07_validate.py --output D:/tvgun/gunforge/games/g01/reports/art/T07/revisions/A2i/negative_recheck` → `a2_readiness.py` → `publish_a2i.py`。后者不会重跑出图，也不会批准 T08。`art-checks-0.3-initial-offline` 只冻结初始阈值和代码哈希；C04/C12/C14 的充分标定仍未满足。不要用较早的 `verify_a2h.py`“待审”断言覆盖现有人审记录。

当前网页只问是否保留列出的待办继续 T08 离线试做；这是任务文档 T07 的 A2 停止点。`verify_a2i_gallery.cjs` 在隔离 VM 检查反馈导出和门槛，不改用户页面选择。旧发布链优先转交 A2i，防止重新询问已认可事项。GPU、引擎、真实追踪和真实 0B 保留；T08 未启动，批量未批准。

## A2j：人物遮挡返修，规则已调研

用户指出各部件前后遮挡仍有问题，要求深入调研并给出稳定规则。当前以 `docs/art/CHARACTER_OCCLUSION_RULES_A2j.md` 为修正依据，契约模板 `CHARACTER_OCCLUSION_CONTRACT_A2j.yaml` 未启用，角色的前后基线和局部 mask 尚未标注，不可直接生成虚构配置。

`audit_character_occlusion.py` 检查当前 v5 实际绘制清单，普通/附墨每角色 1,128 个采样；该统计不是视觉通过。`publish_a2j.py` 归档用户意见、规则、源哈希和状态，暂停旧 A2i 的阶段继续选项，旧发布链不会覆盖遮挡返修。当前没有重画或改动画渲染器，原检查冻结快照仍是历史初始版本。后续先拆视觉槽与局部遮挡、统一普通/救援绘制清单、验证跳转和循环，再给用户看新样片；不得把已有锚点检查算作遮挡通过。
