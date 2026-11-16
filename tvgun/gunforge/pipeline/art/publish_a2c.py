"""Publish A2c without overwriting human decisions or hiding historical failures."""
import hashlib,json,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
from puppet_motion_v3 import Civilian

BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2c';GALLERY=BASE/'T07/gallery';CACHE=Path('D:/gunforge_cache/g01');CODE=Path(__file__).parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if (BASE/'T07/revisions/A2d/user_feedback.yaml').exists():
        from publish_a2d import main as latest_revision
        return latest_revision()
    groups={'motion':read(BASE/'T05/motion_checks_v3.json'),'rescue_motion':read(BASE/'T05/rescue_motion_checks_v3.json'),'acting':read(REV/'acting_checks.json'),'enemy_hit_feedback':read(BASE/'T06/feedback_checks_v3.json'),'motion_reservations':read(REV/'motion_reservations.json')}
    assert all(r['status']=='pass' for group in groups.values() for r in group.values()),'Resolve offline revision failures first'
    state=read(BASE/'execution_state.json')
    for role in ['vendor','video']:
        folder=CACHE/'T05'/role;model=read(folder/'puppet.json');c=Civilian(model,folder);model['animation_v3']=c.metadata();model['animation_v3'].update(review='pending_A2c',rescue_wave_preparation_shoulder_offsets=[25,25,0,0,0,0,0,0,0,10,25])
        for n in model['parts']:n['angle_range']=c.local_limits[n['id']]
        write_json(folder/'puppet.json',model)
        # Review source assets live in the workspace, outside production assets/.
        dest=BASE/'T05/revisions/A2c'/role;dest.mkdir(parents=True,exist_ok=True)
        for name in ['distress_head.png','right_palm.png','distress_head_source.png','right_palm_source.png','attachments.json','cuff_annotation.png']:shutil.copy2(folder/'attachments_v3'/name,dest/name)
        shutil.copy2(folder/'puppet.json',dest/'puppet.json')
    media=[]
    for task in ['T05','T06']:
        for src in (BASE/task/'gallery').glob('*_v3.*'):
            shutil.copy2(src,GALLERY/src.name);media.append(GALLERY/src.name)
    shutil.copy2(CODE/'t07_gallery_v3.html',GALLERY/'index.html');media.append(GALLERY/'index.html')
    for role in ['vendor','video']:shutil.copy2(GALLERY/(role+'_actions_v3.mp4'),GALLERY/(role+'_actions.mp4'))
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review.update(status='A2c_awaiting_acting_expression_and_hit_strength_review',revision_report='revisions/A2c/report.md',technical_acceptance=False,actual_0B_approved=False)
    for ident in ['people_acting_v3','enemy_hit_fx_v3']:
        if not any(x['id']==ident for x in review['items']):review['items'].append({'id':ident,'status':'pending','scope':'A2c visual prototype only'})
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    motion=groups['motion'];rescue=groups['rescue_motion'];fx=groups['enemy_hit_feedback']
    report=f'''# A2c 人物动作、表情与墨怪受击修正

A2b 明确退回：人物求助手掌方向错误，动作仍需修改；缺少与处境匹配的表情；墨怪受击偏弱。原话见 user_feedback.yaml。场景、点灯、人物造型、墨材质与反光继续沿用。A2b 报告/视频/检查和当时代码归档于 D:/gunforge_cache/g01/T07/A2b/，不把旧失败覆盖成通过。

## 调研结论与上轮漏检

详见 D:/tvgun/docs/art/ANIMATION_RULES_A2c.md。查阅 [Godot 剪纸动画](https://docs.godotengine.org/en/stable/tutorials/animation/cutout_animation.html)、[Spine 附件](https://esotericsoftware.com/spine-attachments)、[Spine IK](https://esotericsoftware.com/spine-ik-constraints)、[Spine 曲线编辑](https://esotericsoftware.com/spine-graph) 与 [Spine 姿态提示](https://esotericsoftware.com/spine-tips)。这些资料支持骨架、姿态附件、表情附件相结合；并不提供通用“人体正确角度”，也不替代具体动作的人审。

上轮只验证骨长、连接和转角，漏掉掌面/左右侧的视觉语义。旧 `_l/_r` 是画面侧，不能直接称角色左/右手。旧腕点自动检测还落入了手掌内部。现在保留 ID 兼容，但标明画面左臂=角色自身右臂，画面右臂=角色自身左臂；实际腕点改为袖口开口，并保存标注图。

## 人物修改

- 两人各增加一个 GPT 右手掌附件、一个担忧呼救头部附件，原造型 PNG 保留。抬手右掌朝观众，拇指位于图像右侧；不镜像整块前臂。十骨架保留，手掌是腕部视觉附件，表情是头部替换附件，同一时刻只显示一个头。
- 求助改为准备、抬臂、摆腕两端、收回等独立关键姿势，用缓入缓出衔接；不再以连续正弦摆动整臂。拿物品的一侧保持原握持关系。
- 受困、求助、受惊、探身使用担忧表情；所有附墨人质状态均禁止笑脸。获救动作起初仍紧张，0.95秒后切换原轻松表情；感谢使用轻松表情。只交付这两类表情，不宣称已有精细口型/眨眼/多方向表情库。
- 为附墨状态单独调整求助准备和收回时的肩姿，手掌避开胸腹墨区。此次先发现卖糖葫芦居民9条、老板6条失败记录，均保留在 T05/*_rescue_motion_v3_initial_failure.json；修正动作后重新检查，没有放宽半径或边界要求。

## 实际离线检查范围

两人各8段动作，共 {sum(v['frames'] for v in motion.values())} 帧，24fps。实际变换的骨长、关节连接、脚目标、支撑脚漂移及腕附件误差都小于0.0001源像素；所有选中附件变换保持正行列式。求助每人84帧的腕部可见接缝单独检查，最大测得间距0源像素。五指、拇指侧和担忧眉眼/口型由执行者检查实际图像；不能从 right 标签或矩阵正号推导出图像解剖正确。

镜像手掌变换、求助笑脸状态的破坏负例被拒绝；原膝盖反折、脚目标偏移负例继续通过拒绝检查。表情状态累计检查2160帧（含附墨分支）。新源图、缩放、锚点、原始PNG哈希随附件记录保存。

附墨允许的5类动作，每人336帧×6墨形，总计 {sum(v['blob_frame_tests'] for v in rescue.values())} 次实际渲染：

- 卖糖葫芦居民：候选高度512，最小有效半径 {rescue['vendor']['minimum_effective_radius']:.3f}、最小纸身包围 {rescue['vendor']['minimum_paper_clearance_px']:.3f} 内容像素。
- 录像厅老板：候选高度300，最小有效半径 {rescue['video']['minimum_effective_radius']:.3f}、最小纸身包围 {rescue['video']['minimum_paper_clearance_px']:.3f} 内容像素。
- 两人印迹被保护手部遮挡的像素数均0，半径40/边界6要求不变。实际可见附墨与命中遮罩一致，人物纸身始终受保护。
- 运动范围重新纳入真正显示的手掌、表情及脚踝补偿附件，加上相机/呼吸极值，两个候选人质槽位均避开 playing HUD 与60像素边缘带。它是离线槽位子集，不等于完整引擎遮挡验收。
- 循环片段检查首尾位置差；获救属于一次性状态转换，不用笑脸/担忧首尾不一致冒充循环失败或循环通过。完整运行时 C12 仍待验。

## 墨怪受击加强

普通命中后退参数由6增至20预览像素，印迹命中由9增至32；停顿分别为0.10/0.16秒参数（30fps离散采样）。增加可辨的横向压缩、转动、阻尼回弹；固定命中位置出现局部冲击星、扩散环和更多墨滴，不让命中光点跟着怪物后退。印迹命中更强一档，净化仍使用墨身可见范围约束印迹。常驻反光参数未改变，无全屏白闪。

墨鸦与墨蝌蚪共 {sum(v['frames'] for v in fx.values())} 个实际合成帧，印迹超出可见墨的像素数0；合成后、限亮前 Y′>0.75 比例最大0，符合原2%限制。以上是离线近似，尚无正式引擎着色器、音效/触觉反馈或运行时命中判定验收；人物没有这套受击效果和敌方血量。

## 复核与仍待办

入口继续是 http://127.0.0.1:8767/gallery/ 。本轮只问“动作与表情”和“受击力度”，提供半速、关键姿势近景。新稿从0/2开始，不继承上轮拒绝为新稿选择，也不因自动检查而批准。

C03 深度带亮度历史失败、完整隐藏几何独立核对、引擎运动/遮挡、阈值标定、C13追踪筛查失败、正式引擎导入/性能、真实光枪均保留。部分特征认可和这两次动画退回，不被伪造为20例完整风格/循环标签。A2技术项仍未全部通过，T08未启动；T09–T16批量仍等真实0B五项验收。

本轮新增4次内置GPT出图（两个表情、两个掌面），不是付费API；T05为27/32，0A累计 {state['phase_0A_calls']}/120，含T01总计 {state['builtin_image_calls']}。费用未披露，仍为未知/null。完整提示词在 T05/*_v3_prompt.txt，原生返回与处理后附件保存在 T05/revisions/A2c/，仅为审核候选，不进入生产 assets/。

当前状态：等待 A2c 人工观感反馈。手掌方向、表情、自然度和打击力度不能由数值检查代替人工批准。
'''
    # Preserve separately collected browser evidence across deterministic republication.
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    for task in ['T05','T06']:
        p=BASE/task/'report.md';txt=p.read_text(encoding='utf-8');marker='\n## A2c 修正记录\n';txt=txt.split(marker)[0];p.write_text(txt+marker+'\nA2b被退回；已完成新一轮动作/表情/受击试做和离线检查，等待A2c人审。完整报告见 ../T07/revisions/A2c/report.md。\n',encoding='utf-8')
    contract=read(GAME/'bible/animation_contract.json');contract.update(version='civilian-motion-3',free_hand='anatomical right, legacy _l / screen left',held_prop='anatomical left, legacy _r / screen right',laterality={'legacy_l':'screen_left_anatomical_right','legacy_r':'screen_right_anatomical_left'},hand_attachment='correct anatomical right palm, no mirrored forearm, cuff wrist anchor',expressions={'distress':['hostage','peek','startle','wave_for_help','struggle'],'relieved':['after_rescue_0.95s','thank']},acceptance='pending_A2c_visual_and_remaining_technical_checks',rules='D:/tvgun/docs/art/ANIMATION_RULES_A2c.md');write_json(GAME/'bible/animation_contract.json',contract)
    cal=read(BASE/'T07/calibration.json');cal.update(A2_decisions='partial visual directions approved; A2 and A2b animation revisions required; A2b hit feedback too weak',A2c='pending; no fabricated full-asset or per-loop calibration labels');write_json(BASE/'T07/calibration.json',cal)
    pending=['C03_depth_bands','complete_hidden_geometry','engine_motion_and_occlusion','C14_calibration','C13_tracker_screen_failures','engine_import_and_actual_0B']
    check={'revision':'A2c',**groups,'scope':'offline selected prototypes only; human approval pending','original_A2_technical_pending':pending,'production_approved':False};write_json(REV/'checks.json',check);write_json(BASE/'T07/checks.json',check)
    sources=[p for p in CODE.iterdir() if p.is_file() and ('v3' in p.name or 'a2c' in p.name)]
    source_assets=[p for p in (BASE/'T05/revisions/A2c').rglob('*') if p.is_file()]
    manifest={'revision':'A2c','status':'pending_human_acting_expression_hit_strength_review','production_asset_approved':False,'new_image_generation_calls':4,'phase_0A_calls':state['phase_0A_calls'],'builtin_total_calls':state['builtin_image_calls'],'cost':None,'checker_version':'art-checks-0.2-uncalibrated','motion_version':'civilian-motion-3','code_sha256':{p.name:sha(p) for p in sources},'outputs':[{'file':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(media+source_assets)],'feedback':'user_feedback.yaml','report':'report.md'}
    write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest)
    for task in ['T05','T06']:
        p=BASE/task/'manifest.json';m=read(p)
        for f in m.get('candidate_files',[]):
            file=Path(f['file']);f.update(sha256=sha(file),bytes=file.stat().st_size)
        m.update(status='A2c_visual_review_pending',revision_manifest=str(REV/'manifest.json'));write_json(p,m)
    state.update(T05='A2c_pose_hand_expression_and_rescue_checks_delivered_pending_review',T06='A2c_stronger_hit_feedback_delivered_pending_review',T07='A2c_visual_review_pending',next_task='A2c_visual_feedback_then_remaining_technical_items',current_blockers=['A2c_visual_feedback']+pending);write_json(BASE/'execution_state.json',state)
    print(json.dumps({'gallery':str(GALLERY),'new_image_calls':4,'NPC_frames':1080,'ink_frame_checks':4032,'FX_frames':408,'human_review':'pending'}))

if __name__=='__main__':main()
