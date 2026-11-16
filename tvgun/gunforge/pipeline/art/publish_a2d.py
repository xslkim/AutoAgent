"""Publish an elbow-only review while preserving A2c's accepted ink feedback."""
import json,hashlib,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
from puppet_motion_v4 import Civilian
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2d';GALLERY=BASE/'T07/gallery';CACHE=Path('D:/gunforge_cache/g01');CODE=Path(__file__).parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if (BASE/'T07/revisions/A2e/loop_checks.json').exists():
        from publish_a2e import main as latest_revision
        return latest_revision()
    groups={'motion':read(BASE/'T05/motion_checks_v4.json'),'rescue_motion':read(BASE/'T05/rescue_motion_checks_v4.json'),'lowering':read(REV/'lowering_checks.json'),'motion_reservations':read(REV/'motion_reservations.json')}
    assert all(v['status']=='pass' for g in groups.values() for v in g.values()),'Offline checks must be resolved before publication'
    accepted=[]
    for p in sorted((BASE/'T06/gallery').glob('*_v3.*')):
        archived=CACHE/'T07/A2c/T06/gallery'/p.name;assert sha(p)==sha(archived),'Accepted ink feedback changed: '+p.name
        target=GALLERY/p.name;assert sha(target)==sha(p),'Gallery no longer serves accepted ink version'
        accepted.append({'file':str(p),'sha256':sha(p),'status':'visually_approved_A2c_unchanged'})
    outputs=[]
    for p in (BASE/'T05/gallery').glob('*_v4.*'):
        dest=GALLERY/p.name;shutil.copy2(p,dest);outputs.append(dest)
    for role in ['vendor','video']:
        folder=CACHE/'T05'/role;m=read(folder/'puppet.json');c=Civilian(m,folder);m['animation_v4']={**c.metadata(),'review':'pending_A2d'};write_json(folder/'puppet.json',m)
        dest=REV/(role+'_puppet.json');shutil.copy2(folder/'puppet.json',dest);outputs.append(dest)
        shutil.copy2(GALLERY/(role+'_actions_v4.mp4'),GALLERY/(role+'_actions.mp4'))
    shutil.copy2(CODE/'t07_gallery_v4.html',GALLERY/'index.html');outputs.append(GALLERY/'index.html')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'))
    assert next(i for i in review['items'] if i['id']=='enemy_hit_fx_v3')['status']=='approved'
    if not any(i['id']=='people_elbow_v4' for i in review['items']):review['items'].append({'id':'people_elbow_v4','status':'pending','scope':'lowered elbow motion visual review only'})
    review.update(status='A2d_awaiting_lowered_elbow_review',revision_report='revisions/A2d/report.md',latest_feedback='revisions/A2d/user_feedback.yaml',technical_acceptance=False,actual_0B_approved=False)
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    motion,rescue,lower=groups['motion'],groups['rescue_motion'],groups['lowering'];state=read(BASE/'execution_state.json')
    report=f'''# A2d：放下手时的肘部修正

用户 A2c 反馈：手放下时肘关节不自然；墨怪受击清楚合适。原话、截图分别保存在 user_feedback.yaml、user_elbow_reference.png。墨怪受击只获得视觉方向确认，未推导为正式引擎/真实0B通过；表情未单独获得批准，本轮沿用但不擅自标记通过。

## 原因与修改

旧版将同样的前臂局部旋转用于不同贴图。两人的前臂绑定位轴向不同，手放下末帧的实际肩—肘—腕弯曲角分别为 {lower['vendor']['previous_lowered_elbow_deg']:.2f}°、{lower['video']['previous_lowered_elbow_deg']:.2f}°。局部转角相同不等于姿势相同，尤其卖糖葫芦居民仍明显向外折。

新版先给定实际肘屈曲，再按各自绑定位轴向换算前臂旋转。下垂最终使用约6°轻微屈曲；0–12°是这套机位和动作的低位姿态检查范围，不是人体通用医学限制。肩、肘、腕逐步回到放松姿势，不把整个手臂强制拉直。

完整求助延长至4.5秒：2.78–4.15秒收臂，随后停稳到4.5秒。关节曲线使用保持形状的三次 Hermite 插值，使连续中间关键帧处速度衔接，避免每到一个关键帧都停顿。放下阶段肘部单调舒展，不在末段再次折回。站立、探身、行走、获救中的低位空手也采用一致的几何角控制；受惊、挣扎、感谢保留各自的有意屈肘动作。

附墨状态在低位稍微外展上臂保持安全距离，不靠增加肘部折角避开墨区。纸居民仍仅为 NPC/人质，纸身没有敌人血量、攻击或受击行为。原造型、表情和已认可的场景/点灯/墨反光不重画。本轮新增 GPT 调用0次。

## 复核结果与范围

- 两人8类动作，共 {sum(v['frames'] for v in motion.values())} 个24fps帧；关节、骨长、脚落地、腕附件变换检查通过。数值通过不代表自然度获人工认可。
- 求助每人含普通/附墨分支与端点共 {lower['vendor']['wave_states_checked']} 个状态，实际肘角与目标误差小于0.0001°，掌面不镜像、担忧表情保持，腕部可见接缝最大测得间距0源像素。旧末帧姿势作为回归反例，两个人物均被新的低位姿态检查拒绝。
- 5类可附墨动作，每人360帧×6墨形，总计 {sum(v['blob_frame_tests'] for v in rescue.values())} 次真实离线渲染。最小有效半径：卖糖葫芦居民 {rescue['vendor']['minimum_effective_radius']:.3f}，老板 {rescue['video']['minimum_effective_radius']:.3f}；纸身边界分别 {rescue['vendor']['minimum_paper_clearance_px']:.3f}、{rescue['video']['minimum_paper_clearance_px']:.3f} 内容像素。印迹被手部遮挡像素数均0；原半径40、边界6不放宽。
- 实际新动作含所有附件的保守范围，加相机/呼吸位移后，两个人质槽均避开 HUD 和60像素边缘带。这仍是离线候选槽子集，完整运行时遮挡待验。
- 原有 A2c 墨怪全部 `{len(accepted)}` 个 v3 预览文件与归档逐一比较 SHA-256，内容未变；审核页沿用同样文件。没有把人物修改混入已确认的墨怪反馈。

## 如何复核

原地址 http://127.0.0.1:8767/gallery/ 。本次只问一个问题：手放下时，肘部是否自然。默认展示低位姿势；点“放下手（重播）”同时播放两个人物的单次收臂片段，可用半速观察末段，不循环跳回举手。也可切完整求助、行走、附墨，展开五姿势近景。

墨怪受击明确标为已确认，仅保留可展开的原版视频，不要求重复审批。新稿从0/1开始，不替用户选择。旧A2c草稿仍在原存储键中。

## 门槛与交付

深度带亮度历史失败、完整隐藏几何、正式引擎运动/遮挡、阈值标定、C13追踪筛查失败、引擎导入/性能和真实光枪待办全部保留。A2尚未全部通过，T08未启动，T09–T16批量仍等真实0B五项验收。此次只补强人物动画及对应运动范围/救援检查，不把局部通过泛化到完整A2。

内置GPT调用不变：0A {state['phase_0A_calls']}/120，含T01累计 {state['builtin_image_calls']}；本轮无新增生成、无外部付费API调用。此前未披露费用仍记未知/null。视频来自既有GPT素材的本地动画装配。

逐帧记录见 checks.json、lowering_checks.json、motion_reservations.json 和 T05/*_v4.json；源代码/媒体哈希见 manifest.json。旧代码、视频、报告及检查归档于 D:/gunforge_cache/g01/T07/A2c/。
'''
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    p=BASE/'T05/report.md';text=p.read_text(encoding='utf-8').split('\n## A2d 修正记录\n')[0];p.write_text(text+'\n## A2d 修正记录\n\n按实际几何肘角修正低位与收臂动作，附墨检查和运动范围已重算，等待A2d人审；详见 ../T07/revisions/A2d/report.md。\n',encoding='utf-8')
    contract=read(GAME/'bible/animation_contract.json');contract.update(version='civilian-motion-4',lowered_elbow={'target_deg':6,'project_visual_check_deg':[0,12],'angle_space':'actual shoulder-elbow-wrist, adjusted per bind axes','not_universal_anatomical_limit':True},acceptance='pending_A2d_lowered_elbow_and_remaining_technical_checks');write_json(GAME/'bible/animation_contract.json',contract)
    cal=read(BASE/'T07/calibration.json');cal.update(A2c='enemy hit feedback visually approved; lowered elbow requires revision; expression not separately approved',A2d='pending lowered-elbow review; no new full-asset or per-loop calibration labels');write_json(BASE/'T07/calibration.json',cal)
    checks={'revision':'A2d',**groups,'accepted_ink_feedback_unchanged':accepted,'scope':'offline animation and rescue subset only','production_approved':False,'actual_0B':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    code=[p for p in CODE.iterdir() if p.is_file() and ('v4' in p.name or 'a2d' in p.name)]
    manifest={'revision':'A2d','status':'pending_lowered_elbow_visual_review','production_asset_approved':False,'new_image_calls':0,'phase_0A_calls':state['phase_0A_calls'],'builtin_total_calls':state['builtin_image_calls'],'cost':None,'code_sha256':{p.name:sha(p) for p in code},'outputs':[{'file':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(outputs)],'accepted_ink_feedback_unchanged':accepted,'feedback':'user_feedback.yaml'};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest)
    p=BASE/'T05/manifest.json';m=read(p)
    for f in m.get('candidate_files',[]):
        path=Path(f['file']);f.update(sha256=sha(path),bytes=path.stat().st_size)
    m.update(status='A2d_lowered_elbow_review_pending',revision_manifest=str(REV/'manifest.json'));write_json(p,m)
    p=BASE/'T06/manifest.json';m=read(p);m.update(status='A2c_hit_feedback_visually_approved_engine_pending',visual_feedback=str(REV/'user_feedback.yaml'));write_json(p,m)
    pending=['C03_depth_bands','complete_hidden_geometry','engine_motion_and_occlusion','C14_calibration','C13_tracker_screen_failures','engine_import_and_actual_0B'];state.update(T05='A2d_lowered_elbow_and_rescue_checks_delivered_pending_review',T06='A2c_hit_feedback_visually_approved_engine_pending',T07='A2d_lowered_elbow_review_pending',next_task='A2d_lowered_elbow_feedback_then_remaining_technical_items',current_blockers=['A2d_lowered_elbow_visual_feedback']+pending);write_json(BASE/'execution_state.json',state)
    print(json.dumps({'published':str(GALLERY),'NPC_frames':sum(v['frames'] for v in motion.values()),'rescue_checks':sum(v['blob_frame_tests'] for v in rescue.values()),'new_image_calls':0,'approved_FX_files_unchanged':len(accepted),'human_review':'one_question_pending'}))
if __name__=='__main__':main()
