"""Publish local review artifacts, never production or human approvals."""
import json,hashlib,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import yaml
from artlib import GAME,write_json
from phase0a_jobs import update_counts

BASE=GAME/'reports/art';CACHE=Path('D:/gunforge_cache/g01');VERSION='art-checks-0.2-uncalibrated'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def report(task,text):(BASE/task/'report.md').write_text(text,encoding='utf-8')
def table(rows):return '\n'.join('| '+' | '.join(str(x).replace('|','/') for x in row)+' |' for row in rows)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if (BASE/'T07/revisions/A2d/user_feedback.yaml').exists():
        from publish_a2d import main as publish_revision
        return publish_revision()
    if (BASE/'T07/revisions/A2c/user_feedback.yaml').exists():
        from publish_a2c import main as publish_revision
        return publish_revision()
    if (BASE/'T07/revisions/A2b/user_feedback.yaml').exists():
        from publish_a2b import main as publish_revision
        return publish_revision()
    update_counts();state=read(BASE/'execution_state.json');counts=state['task_image_calls'];tech=read(BASE/'T04/additional_checks.json');rescue=read(BASE/'T05/rescue_checks.json');negative=read(BASE/'T07/negative_checks.json');cal=read(BASE/'T07/calibration.json')
    motion=tech['C07b_motion'];motion_count=sum(map(len,motion.values()));motion_pass=sum(v['status']=='pass' for rs in motion.values() for v in rs.values())
    common='本轮为离线试做。未经审核不进入 assets/。人物只做人质或 NPC，无敌人血量、攻击、受击或死亡动作；救援对象是独立附着墨。真实 0B 五项验收之前，T09–T16 保持禁止开始。\n'
    cost=f'内置 GPT 调用：本任务 {{count}} 次；0A 累计 {state["phase_0A_calls"]}/120，含失败与重试；累计含 T01 为 {state["builtin_image_calls"]} 次。外部付费 API 为 0 次。模型、种子、供应商任务 ID 和费用未披露，记 null / 未知，不能以 0 元替代。'
    bands=[['纸层','Y′加权均值','原范围','状态'],['---','---','---','---']]+[[k,f'{v["weighted_mean_Yprime"]:.3f}',str(v['required']),v['C03_band']['status']] for k,v in tech['C03_bands'].items()]
    report('T04',f'''# T04 首站点拆层与灯光试做

七个背景纸层加一盏独立路灯已生成和组装，正在等待 A2 视觉复核；本任务尚未正式验收。{common}
## 已交付

- D:/gunforge_cache/g01/T04/station/：完整及裁切 PNG、8 像素 bleed、crop_origin、extent/fill/occlusion/block 遮罩、station.json、灯光数据。
- 四张构图探索、选稿、正式构图、逐层白模；近左层试做构图提取替代方案，中右层修正自行车。
- 静止、八个相机与呼吸极值组合、五个转场进度、灯灭/灯亮图和 8 秒点灯过程视频。转场另一侧为色块占位，不是第二站正式资产。
- 点亮版经原生 GPT 编辑；正差分输出原始 delta 与局部影响遮罩，剔除无关重绘漂移；发光部分从点亮版提取。受影响层已列在 station.json。遮灯暂用允许的临时形状。

## 验证

九个运动状态 C07a 全通过；同样状态逐层 C07b {motion_pass}/{motion_count} 通过。C07b 只验证已声明的当前形状范围；应有隐藏几何来自当前支持形状，仍须独立校核，不能把该数值当完整隐藏几何验收。为匹配不透明纸层契约，将 alpha≥128 的纸实体置为不透明，外侧抗锯齿保留；原生返回图未改。

七层 C01、C04 和亮度上限检查通过，近景 block 与可见层一致。alpha 边缘黑白底复核、低置信 OCR 与风格评分保留待办。新接入本地 Tesseract.js 中英文 OCR；低置信识别留为 pending，不丢弃疑似文字后冒充通过。

完整深度带检查另存 additional_checks.json，不能用“未过曝”代替深度带亮度：

{table(bands)}

far_base、far_town 仍低于原远景范围；mid_ground 略低于下限。当前暗夜方向来自 A1b 认可，但不因此删除原数值失败；须按视觉意见修正/明确规格后再验。完整 C06 可读性、槽位运动及 C11、C15 引擎检查未完成。四组新整帧追踪截图筛查仍 fail，未修改追踪器；真实光枪未测试。

## 调用与产率

{cost.format(count=counts['T04'])}

返回 {counts['T04']}/{counts['T04']}；候选七背景层、一灯、一组灯光，正式批准可用站点为 0。生成返回率不等于最终可用率。生成对齐并非像素级保证：中景地面手工下移 120 画布像素；替代层及灯局部经过重新对齐，细节见 checks.json / manifest.json。
''')
    rigs={r:read(BASE/'T05'/f'{r}_rig_checks.json') for r in ['vendor','video']}
    rr=[['角色','零件齐全率','关键姿势/极限 C10','最终可用率'],['---','---','---','---']]+[[r,'4/4（100%）',rigs[r]['C10']['status'],'0/1 正式批准；视觉及技术未验完'] for r in rigs]
    report('T05',f'''# T05 纸居民与独立附墨试做

瘦高卖糖葫芦居民、胖录像厅老板已各完成十部件纸偶和一件日常手持物，提供连续插值动作预览。{common}
## 产出与方法

每人四次完整零件图，均按原图逐件核对为头、躯干、四段手臂、四段腿；每人另试一次逐件生成头部，仅证明单件备选，不伪称完成整套备用十件。零件按原设定比例规格化到组装高 768，保留所有原始图。衣物并入身体部件。金属铜扣补片的纸搭接直径 71、实测铜扣等效直径约 37.88 源像素；属于测量证据，视觉大小和颈部扣形仍等你判断。

动作仅含窥视、走路、受惊、挥手求助、挣扎、获救弹跳、感谢。每人已保存 {len(rigs['vendor']['poses'])} 个关键/极限姿势及动作 MP4；接缝最大间隙 {max(v['max_joint_gap_px'] for v in rigs['vendor']['poses'].values()):.1f} / {max(v['max_joint_gap_px'] for v in rigs['video']['poses'].values()):.1f} 像素。铜扣与搭接片已并入原部件，不增加伪造肢体。录像盒原生编辑仍带软光晕，归档保留两次结果；以高 alpha 主体支持清理外部光晕，黑白底效果留供复核。

{table(rr)}

## 六种附墨与救援

六种墨团保存在 D:/gunforge_cache/g01/T05/ink_blobs/。blob_02 横向形状未满足小尺寸要求，已用 GPT 改为紧凑竖向形状，原版本保留。附墨与身体分层，弱点、命中区只跟随墨；人物不具有可攻击区域。挂点取实际躯干纸片的腹部最大内切区域，完整变换记录在 puppet.json。

按真实 alpha、半径 12 开运算和六像素纸身包围边界实测：卖糖葫芦居民 300 下失败，400 仍有边界失败，512 下六种通过；录像厅老板 300 下六种通过。建议附墨救援最小候选显示高度分别为 {rescue['vendor']['candidate_minimum']} / {rescue['video']['candidate_minimum']}。不扩大不可见命中区，不改 40 半径或 6 像素标准。300 失败样本及 300/400/512 全部数据保留在 rescue_checks.json。512 为原方案显示上限内的试做提案，须 A2 认可后采用。

以上是静态检查；全部动作下的保护边界、相机、掩体和 HUD 预留仍需完整验证。透明边缘、C03/C04 原始部件结果见 raw_checks.json，存在的 fail/pending 不被 C10 通过覆盖。C06、C11、C14、C15 仍有待办。

## 调用与成本

{cost.format(count=counts['T05'])}

两人探索相关 15 次，平均 7.5 次/角色；共享墨团与关节相关 8 次。本轮 8/8 完整零件图的齐全率只说明部件枚举成功，不能外推正式资产合格率。正式批准角色为 0/2，无法据此计算可靠批量成本。
''')
    enemies={name:read(BASE/'T06'/f'{name}_checks.json') for name in ['crow','tadpole0','tadpole1','tadpole2']}
    erows=[['素材','有效半径最小尺寸证据','C16误差','高光筛查','循环'],['---','---','---','---','---']]+[[k,str(v['minimum_size_evidence'][0]),v['C16']['details']['max_error_px'],v['highlight_screen']['status'],v['C12']['status']] for k,v in enemies.items()]
    report('T06',f'''# T06 墨怪与湿墨材质试做

已按 A1b 要求增加更明确的局部湿墨反光，保留平面朱砂印迹。敌人只有墨生物，没有人形敌人或变黑的人。{common}
## 已交付

墨鸦，以及三只不同姿态的墨蝌蚪，均有 body、core、core_hardened、8 位单通道 SDF、公共 1024 画布、origin、各自 crop_origin 和 enemy.json。分件共用同一仿射变换；印迹从设定图颜色分离，墨身由 GPT 编辑移除印迹后归一。硬化眼为独立素材。

普通、预警、硬化、受击、溶解为离线近似；受击/溶解时印迹跟随墨身同时淡出。循环采用分件位移，15fps。着色器实现及引擎导入不在本次离线验收内，不称为真实着色器效果。

{table(erows)}

墨鸦最小整体尺寸 200，墨蝌蚪按头部直径最小 90，均测出有效半径≥40；尾巴不计入墨蝌蚪可伤害主体。三只在实际巷口试放，头部主命中区无重叠，C09 静态通过。完整群体运动、前景遮挡和 HUD 标注继续待验。

## 高光、对齐和预算

限制高光亮度至 Y′≤0.599，保持原≤0.60上限；用 Y′>0.22 面积作为保守筛查代理，最多5%。该代理不是语义高光分割，最终反光强度仍请你选择。C04 另有记录。静态 core/eyes 包含和离线 SDF 往返通过，C11 完整状态/相机/引擎证据不足仍 pending；C06 全状态对比和缩略图识别未通过完整验收。

可选图集 1536² RGBA8、无 mip，实际分配 9,437,184 字节（9 MiB），16 格；尺寸小于2048²。C15 只作离线估算，Godot 导入后峰值待测。图集为抽样关键帧预览，最终循环接缝仍需实际播放审核；不以 PNG 磁盘体积代替显存。

{cost.format(count=counts['T06'])}

返回 9/9；两种候选敌人、四个姿态素材；正式批准生产敌人为 0。模型、费用未知，不据此虚构量产金额。
''')
    nrows=[['破坏样本','检查','实际状态'],['---','---','---']]+[[r['counterexample'],r['check'],r['result']['status']] for r in negative['rows']]
    crows=[['任务','内置调用','正式生产验收'],['---','---','---']]+[[t,counts[t],'尚未作为生产通过'] for t in ['T02','T03','T04','T05','T06']]
    report('T07',f'''# T07 / A2 试做汇总与审核待办

已处理本次反馈：墨更明确地反光；点灯方向保留；首站拆层、两类纸居民、两类墨怪继续试做；设计和机器约束都明确人物只能是人质或 NPC。当前来到任务文档要求的 A2 人工停止点，等待视觉意见；**A2 技术项尚未全部通过，不能据此启动 T08 或正式批量。**

## 请审核人看什么

打开 http://127.0.0.1:8767/gallery/ ，只看三组并各选一项：场景和点灯、人物和救援、墨的反光。补一句调整意见，点整理反馈并复制到聊天。页面只保存本机草稿，选择不自动写入 review.yaml，也不触发后续生成。此时不要求做真实光枪测试。

瘦高居民的附墨救援建议显示高512，录像厅老板300；这是保证六种墨团的有效半径和可见纸身边界的试做提案。若不接受瘦高居民的放大方案，需要按 A2 意见改墨形、角色腹部设计或玩法呈现；不放宽命中标准。

## 真实素材反例验证

七类要求覆盖九次检查，全部确实返回 fail（失败是故意破坏样本的预期结果）。每项源文件、变异规格、结果和错误像素量在 negative_checks.json；变异图在 D:/gunforge_cache/g01/T07/。

{table(nrows)}

中景洞的未破坏对照通过；弱点挪出主体同时被 C09/C11 拦截；SDF 同时测试错误颜色标记与实际 sRGB 数值转换；HUD 样本在边缘安全带内，单独触发 HUD 重叠。文字样本使用实际中英文 OCR，不伪造识别结果。

原有离线核心回归 43/43 通过。C07b 同一轮九状态×七层 {motion_pass}/{motion_count}，运动遮罩采用与颜色层相同的整数平移；隐藏完整形状仍未经独立确认。两个人零件图各4/4齐全，关键/极限姿势 C10 通过；三只墨蝌蚪静态群体 C09 通过；四个 SDF 零轮廓误差均0源像素。

## 阈值和检查器版本

代码快照版本 `{VERSION}`，代码哈希见 calibration.json 和 manifest.json。**只冻结可复现的代码快照，不宣称已用人审样本完成阈值标定。**

- C04：保留 ΔE≤15、覆盖率≥90%。A1只有12张特定特点参考，其中6张含配色特点；完整资产通过/拒绝标签各0，不够每类20张。
- C12：首尾位置/速度阈值均0.02。人工通过/拒绝循环各0。
- C14：无已标定评分器，不虚构分数。A1b两帧只确认方向，不能充当全风格通过；未选图片也不是拒绝样本。
- 部分类别特点参考数量：场景5、人物4、墨2、UI1。见 calibration.json。待后续明确人审通过/拒绝样本后继续标定。

## 未通过或待检查

1. C03 深度带：远底 Y′≈0.176、远城≈0.307，低于原远景0.45下限；地面≈0.248，略低于中景0.25。未过曝检查通过不覆盖这些失败。A1b暗夜方向认可不等于删除亮度要求；需按视觉意见调整并再验。
2. 完整隐藏几何、全部运动槽位/保护区标注、所有状态 C06/C11、半透明边缘和部分 OCR 疑似识别仍需核对。数值上 C07b 在当前已声明范围内通过，不代表隐藏形状已经完整。
3. 新站点灯灭/灯亮、monitor/tv四组 C13 截图筛查仍 fail。追踪器原算法未变；合成截图不是实际手机拍摄。真实0B仍未通过。
4. C14 样本不足；C15 Godot 导入/峰值及真实着色器待验。A2视觉反馈、数值复核和真实真机验收分别记录。

## 0A 调用、花费与产率

{table(crows)}

0A累计 **{state['phase_0A_calls']}/120**，剩余 {120-state['phase_0A_calls']} 次；T01另3次，合计 **{state['builtin_image_calls']}**。T04 {counts['T04']}/24、T05 {counts['T05']}/32、T06 {counts['T06']}/16，T07无图像调用；分批不清零，单素材次数仍累计，失败和编辑均计入。

内置费用未披露，累计金额未知；外部付费 API 0次，外部支出0元。所有调用有请求指纹、参考哈希、源文件、输出尺寸与哈希，未写入虚构模型、种子或费用。原生返回率不等于可用率：T04–T06本轮 {counts['T04']+counts['T05']+counts['T06']} 次全部返回，正式批准的站点、角色、敌人数仍均为0；它们是待审候选。

调用量外推尚不能以正式有效率计算：有效素材率 q 尚无完成验收的样本，不能用返回率100%或零批准率估算有限生产成本。可复现的试做观测为：首站探索16次、角色探索平均7.5次/人另共享墨和关节8次、两种墨怪9次；保留供 A2 以后更新。后续有效请求量用“目标有效素材数 ÷ 经验收的有效率”，再计同素材平均尝试次数，费用未知仍保持未知。

## 交付与下一步

T04–T06各有 report.md / manifest.json，全部候选与原图留缓存，审核图和视频留各 gallery/。T07 review.yaml 全部 pending。此轮收到视觉意见后先处理调整项与技术待办、复核 A2；达到任务文档验收条件后才进入 T08。T09–T16另等真实0B五项验收，不受本轮视觉选择自动放行。
''')
    # Candidate manifests include actual files/hashes and original request ledgers.
    for task,folders in [('T04',[CACHE/'T04/station']),('T05',[CACHE/'T05/vendor',CACHE/'T05/video',CACHE/'T05/ink_blobs']),('T06',[CACHE/'T06'/n for n in enemies])]:
        files=[]
        for folder in folders:
            for p in sorted(folder.rglob('*')):
                if p.is_file():files.append({'file':str(p),'sha256':sha(p),'bytes':p.stat().st_size})
        write_json(BASE/task/'manifest.json',{'task':task,'status':'offline_prototype_pending_A2','production_asset_approved':False,'checker_version':VERSION,'checker_snapshot':cal['code_snapshot'],'cost':None,'cost_status':'not_reported','normalization':'see station.json, puppet.json or enemy.json; native source files preserved','calls':read(BASE/task/'calls.json')['calls'],'candidate_files':files})
    gallery=BASE/'T07/gallery';gallery.mkdir(exist_ok=True)
    mapping={'T04':['station_unlit.png','station_lit.png','light_cycle.mp4'],'T05':['vendor_idle.png','video_idle.png','vendor_actions.mp4','video_actions.mp4','vendor_rescue_comparison.png','video_rescue_comparison.png','vendor_rescue_512.png'],'T06':['crow_normal.png','crow_hardened.png','crow_motion.mp4','crow_in_scene.png','tadpole_group.png']}
    for task,names in mapping.items():
        for name in names:shutil.copy2(BASE/task/'gallery'/name,gallery/name)
    for src,dest in [('cam_-60_-30_breath_1.png','camera_a.png'),('cam_60_30_breath_1.png','camera_b.png')]:shutil.copy2(BASE/'T04/gallery'/src,gallery/dest)
    contact=Image.new('RGB',(1200,640),(38,42,60));font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18);d=ImageDraw.Draw(contact)
    for i,name in enumerate(tech['C03_bands']):
        im=Image.open(BASE/'T04/gallery'/(name+'_layer.jpg'));im.thumbnail((290,255));x=(i%4)*300;y=(i//4)*320;contact.paste(im,(x,y+28));d.text((x+8,y+4),name,font=font,fill=(230,214,190))
    contact.save(gallery/'layers_contact.jpg');shutil.copy2(Path(__file__).with_name('t07_gallery.html'),gallery/'index.html')
    review=BASE/'T07/review.yaml'
    if not review.exists():review.write_text(yaml.safe_dump({'stage':'A2','status':'pending_visual_review_with_technical_findings','items':[{'id':x,'status':'pending','note':''} for x in ['scene','people','ink']],'technical_acceptance':False,'actual_0B_approved':False},allow_unicode=True,sort_keys=False),encoding='utf-8')
    write_json(BASE/'T07/checks.json',{'negative_tests':negative,'calibration':cal,'station':tech,'rescue':rescue,'enemies':enemies,'overall':'pending_A2_visual_feedback_and_technical_corrections','production_approved':False})
    write_json(BASE/'T07/manifest.json',{'task':'T07','status':'pending_A2','checker_version':VERSION,'checker_snapshot':cal['code_snapshot'],'image_calls':0,'phase_0A_calls':state['phase_0A_calls'],'builtin_total_calls':state['builtin_image_calls'],'cost':None,'cost_status':'not_reported','production_asset_approved':False,'gallery_files':[{'file':str(p),'sha256':sha(p)} for p in sorted(gallery.iterdir()) if p.is_file()]})
    state.update(T04='prototype_delivered_pending_A2_and_technical_corrections',T05='prototype_delivered_pending_A2_and_motion_validation',T06='prototype_delivered_pending_A2_and_engine_validation',T07='counterexamples_verified_awaiting_A2_visual_feedback',T08='blocked_until_A2_acceptance',next_task='A2_visual_feedback_then_technical_corrections',current_blockers=['A2_visual_feedback','C03_depth_bands','complete_hidden_geometry_and_motion_annotations','C13_screenshot_failures','C14_calibration_samples','engine_import_and_actual_0B_gates'],spent_cny=None,external_spent_cny=0,cost_status='builtin_not_reported',human_roles='hostage_or_NPC_only')
    write_json(BASE/'execution_state.json',state)
    p=BASE/'T03/manifest.json';m=read(p);m['status']='A1b_direction_approved_with_followup';m['review_source']='review.yaml explicit user feedback';m['production_asset_approved']=False;write_json(p,m)
    print(json.dumps({'gallery':str(gallery),'phase_0A':state['phase_0A_calls'],'total':state['builtin_image_calls'],'C07b':f'{motion_pass}/{motion_count}'}))

if __name__=='__main__':main()
