"""Publish focused A2b revisions, preserving A2 feedback and historical failures."""
import hashlib,json,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
from puppet_motion import CLIPS,Civilian

BASE=GAME/'reports/art';CACHE=Path('D:/gunforge_cache/g01');REV=BASE/'T07/revisions/A2b';GALLERY=BASE/'T07/gallery'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if (BASE/'T07/revisions/A2c/user_feedback.yaml').exists():
        from publish_a2c import main as latest_revision
        return latest_revision()
    state=read(BASE/'execution_state.json');motion=read(BASE/'T05/motion_checks_v2.json');rescue=read(BASE/'T05/rescue_motion_checks_v2.json');fx=read(BASE/'T06/feedback_checks_v2.json');reservations=read(REV/'motion_reservations.json')
    for category in [motion,rescue,fx,reservations]:
        if any(r['status']!='pass' for r in category.values()):raise RuntimeError('Resolve revision failures before publishing')
    for role in ['vendor','video']:
        folder=CACHE/'T05'/role;model=read(folder/'puppet.json');controller=Civilian(model,folder)
        model['animation_v2']={**model.get('animation_v2',{}),**controller.metadata()}
        for node in model['parts']:node['angle_range']=controller.local_limits[node['id']]
        write_json(folder/'puppet.json',model)
    sources={name:sha(Path(__file__).with_name(name)) for name in ['puppet_motion.py','build_motion_v2.py','verify_motion_v2.py','enemy_feedback.py','motion_reservations_v2.py']}
    # Only change the statements whose approval the user actually supplied.
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'))
    review['status']='partial_visual_approval_awaiting_A2b_motion_and_hit_feedback';review['revision_report']='revisions/A2b/report.md'
    if not any(i['id']=='people_art' for i in review['items']):review['items'].append({'id':'people_art','status':'approved','scope':'character visual direction only, explicit A2 user feedback'})
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    contract={'version':'civilian-motion-2','source':'A2 explicit animation feedback and offline revision validation','human_roles':['hostage','npc'],'human_body_attackable':False,'human_attack_animations':[],'root':'hips','legs':'two-bone IK with positive knee flexion, constant bone lengths, world-space planted feet','hinges':{'knee':[0,95],'elbow':[0,125]},'free_hand':'left','held_prop':'right, rigid hand attachment','foot':'procedural articulation of original shin/foot pixels, no added rig PNG','paper':'opaque interiors at rendering, original source PNG preserved','rescue':{'eligible_clips':['idle','peek','startle','wave_for_help','struggle'],'visible_decal_inset_content_px':7,'hit_mask':'same visible ink alpha, excluding foreground protected hands','candidate_minimum_heights':{'vendor':512,'video':300}},'acceptance':'pending_A2b_visual_and_remaining_technical_checks'}
    write_json(GAME/'bible/animation_contract.json',contract)
    report=f'''# A2b 人物动作与墨怪受击修正

已归档 A2 明确意见：场景、点灯、人物造型、墨材质和反光继续沿用；旧人物动画因生硬、关节运动不合理而退回。本轮只复核新动作和新增的墨怪受击预览，不重复索要已确认的美术意见。

## 人物动画修正

旧预览在不相关的整套姿势之间轮换，膝、肘允许双向转动，躯干绕颈部附近旋转，脚底没有落地约束。这些检查即使能证明部件接上，也不能证明动作自然。

新版从髋部带动身体，使用两段腿部 IK；支撑脚固定在世界坐标，摆动脚抬起。膝盖只有正确方向的屈曲，脚踝对原小腿+脚图内部进行反向补偿，让鞋底落地；未增加新的肢体 PNG。原始十部件和手持物不重新出图。右手保持道具，左手求助；上臂先抬、肘部后摆，再平缓放下。获救有蓄力、离地、落地缓冲，感谢从髋部轻微前倾并让头部稍后跟随。每种动作独立成片，24fps，不再靠整套姿势轮换展示。

保留站立、探身、行走、受惊、求助、受困挣扎、获救、感谢八种。两个人各540帧，共1080帧，逐帧检查实际变换得到的膝肘屈曲、骨长、关节连接和脚目标。不是读取预设角度后自称通过。可见的纸偶风格和观感仍需 A2b 人审。

- 关节连接、脚目标和连续支撑帧漂移均小于0.0001源像素。
- 瘦高居民膝屈曲 {motion['vendor']['knee_flexion_range'][0]:.1f}–{motion['vendor']['knee_flexion_range'][1]:.1f}°；老板 {motion['video']['knee_flexion_range'][0]:.1f}–{motion['video']['knee_flexion_range'][1]:.1f}°。限制0–95°。肘的实际屈曲均处于0–125°。
- 人为反折膝盖和移动脚目标的负例均被拒绝。原 PNG 的颜色、纹理、部件数量保留；纸片内部不透明度在渲染时规范化，避免半透明插值损坏边界。
- 附墨允许动作每6帧抽查原像素接缝，最大测得间距为0源像素；各片段起终点图像差均在0.02初始值内。此项不是正式引擎 C10/C12 的全面验收。

## 附墨保护与运动标注

逐帧检查发现旧静态通过不能外推到动作：手臂可能遮住墨，抬手后部分墨边缺少纸身包围。初次失败结果保存在 T05/*_rescue_motion_v2_initial_failure.json，不删除历史失败。

已为人质状态设置双手避开胸腹的独立姿态；可见附墨按纸躯干内缩7个内容像素做裁切，命中区与可见墨使用同一遮罩，并排除前景手臂。没有扩大隐形命中区，没有把纸身登记为敌人。净化后再播放获救/感谢。

瘦高居民按512、老板按300候选高度，各336帧×6墨形，合计4032次实际渲染检查：

- 瘦高居民：最小有效半径 {rescue['vendor']['minimum_effective_radius']:.2f}，最小纸身边界 {rescue['vendor']['minimum_paper_clearance_px']:.2f} 内容像素。
- 老板：最小有效半径 {rescue['video']['minimum_effective_radius']:.2f}，最小纸身边界 {rescue['video']['minimum_paper_clearance_px']:.2f} 内容像素。
- 两者所有样本的印迹均未落入被手臂遮住的保护区。半径40、边界6的原要求不放宽；快速距离变换算法与原开运算在六个实际墨形上结果一致。
- 两个替代人质槽位全动作保守包围盒，叠加相机/呼吸位移后均避开60像素边缘带与 playing HUD 保留矩形。标注见 motion_reservations.json；完整引擎运动、遮挡与真实光枪仍待验，不把此子集检查当全游戏 C09/C11 通过。

## 墨怪被攻击的动作和特效

之前只有受击/消散静态图和简单位移，未向用户展示完整命中反应。现在墨鸦、墨蝌蚪各提供三段15fps视频：

1. 普通命中：0.08秒参数的短硬直、轻微压缩和后退回弹、局部暖色纸光点、黑色墨滴。
2. 印迹命中：更强的局部反馈与回弹，仍保留平面朱砂印迹；没有全屏白闪，也没有更改常驻墨材质。
3. 净化消散：用距离场和确定性噪声让墨从边缘散开，印迹跟随实际墨的可见范围退去；开始净化时关闭该墨怪可伤害目标。小光屑只是非命中装饰。

两种墨怪共 {sum(v['frames'] for v in fx.values())} 帧，实际渲染中印迹超出可见墨的像素数均0；过亮比例在2%以内。这是离线程序/着色器近似，不是 Godot 正式特效、音效、命中判定或真机验收。人物没有这套受击、消散或敌方血量。

## 保留事项与预算

继续保留 C03 深度带亮度失败、完整隐藏几何、实际引擎运动遮挡、风格阈值标定、C13追踪筛查失败、引擎导入/峰值和真实0B待办。已认可的暗夜画面方向不会被自动当成删除数值失败的理由；这次也不宣称全部技术待办完成。A2尚未正式通过，T08未启动，T09–T16仍等真实0B五项验收。

本轮未新增 GPT 出图或付费 API 调用。0A仍为 {state['phase_0A_calls']}/120，含T01累计 {state['builtin_image_calls']} 次；工具未披露费用，金额仍未知。新视频来自既有 GPT 美术和本地程序动画/特效，原图留缓存。

## 如何反馈

打开 http://127.0.0.1:8767/gallery/ ，人物动作和墨怪受击各选一项，补充意见后整理、复制回聊天。已认可的五项美术方向会明确显示为已确认。新动作和新增特效的人工状态仍pending，不会因自动检查通过而批准。

代码与文件哈希见 manifest.json，逐帧数据见 T05/*_motion_checks_v2.json、T05/*_rescue_motion_v2.json、T06/*_feedback_checks_v2.json。用户原话与上轮报告、视频、manifest均已归档。
'''
    (REV/'report.md').write_text(report,encoding='utf-8');(BASE/'T07/report.md').write_text(report,encoding='utf-8')
    for task,paragraph in [('T05','新版约束人物动作、附墨保护及检查结果已完成离线修正，A2b人审待办。'),('T06','已补普通命中、印迹命中、净化消散的动态动作与特效预览，正式引擎待验。')]:
        p=BASE/task/'report.md';text=p.read_text(encoding='utf-8');marker='\n## A2b 修正记录\n'
        if marker in text:text=text.split(marker)[0]
        p.write_text(text+marker+'\n'+paragraph+'完整结果见 ../T07/revisions/A2b/report.md。旧版检查不代表本轮修正已获人工批准。\n',encoding='utf-8')
    media=[]
    for role in ['vendor','video']:
        for clip in [*CLIPS,'hostage']:
            for suffix in ['.mp4','.png']:media.append((BASE/'T05/gallery'/(role+'_'+clip+'_v2'+suffix),GALLERY/(role+'_'+clip+'_v2'+suffix)))
        for name in [role+'_actions_v2.mp4',role+'_motion_contact_v2.jpg']:media.append((BASE/'T05/gallery'/name,GALLERY/name))
    for enemy in ['crow','tadpole0']:
        for clip in ['hit','weak_hit','purify']:
            for suffix in ['.mp4','.png']:media.append((BASE/'T06/gallery'/(enemy+'_'+clip+'_v2'+suffix),GALLERY/(enemy+'_'+clip+'_v2'+suffix)))
    for src,dst in media:shutil.copy2(src,dst)
    for role in ['vendor','video']:shutil.copy2(BASE/'T05/gallery'/(role+'_actions_v2.mp4'),GALLERY/(role+'_actions.mp4'))
    shutil.copy2(Path(__file__).with_name('t07_gallery_v2.html'),GALLERY/'index.html')
    check={'revision':'A2b','motion':motion,'rescue_motion':rescue,'enemy_hit_feedback':fx,'motion_reservations':reservations,'scope':'offline revision only','original_A2_technical_pending':['C03_depth_bands','complete_hidden_geometry','engine_motion_and_occlusion','C14_calibration','C13_tracker_screen_failures','engine_import_and_actual_0B'],'production_approved':False};write_json(REV/'checks.json',check);write_json(BASE/'T07/checks.json',check)
    outputs=[p for p in GALLERY.iterdir() if p.is_file() and ('_v2' in p.name or p.name=='index.html')]
    manifest={'revision':'A2b','status':'pending_human_animation_and_hit_feedback','production_asset_approved':False,'new_image_generation_calls':0,'phase_0A_calls':state['phase_0A_calls'],'builtin_total_calls':state['builtin_image_calls'],'cost':None,'checker_version':'art-checks-0.2-uncalibrated','motion_version':'civilian-motion-2','code_sha256':sources,'outputs':[{'file':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(outputs)],'feedback':'user_feedback.yaml','report':'report.md'}
    write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest)
    for task in ['T05','T06']:
        p=BASE/task/'manifest.json';m=read(p)
        for f in m.get('candidate_files',[]):
            file=Path(f['file']);f.update(sha256=sha(file),bytes=file.stat().st_size)
        m.update(status='A2_visual_direction_approved_motion_revision_pending_A2b',revision_manifest=str(REV/'manifest.json'));write_json(p,m)
    state.update(T05='constrained_motion_and_dynamic_rescue_checks_delivered_pending_A2b',T06='enemy_hit_feedback_delivered_pending_A2b',T07='A2b_animation_and_hit_feedback_review_pending',next_task='A2b_animation_and_hit_feedback_then_remaining_technical_items',current_blockers=['A2b_animation_and_hit_feedback','C03_depth_bands','complete_hidden_geometry','engine_motion_and_occlusion','C14_calibration','C13_tracker_screen_failures','engine_import_and_actual_0B']);write_json(BASE/'execution_state.json',state)
    print(json.dumps({'published':str(GALLERY),'new_image_calls':0,'NPC_frames':sum(v['frames'] for v in motion.values()),'ink_frame_checks':sum(v['blob_frame_tests'] for v in rescue.values())}))

if __name__=='__main__':main()
