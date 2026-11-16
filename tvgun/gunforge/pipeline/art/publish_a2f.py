"""Publish integrated readability and independent structural-annotation spot checks."""
import json,shutil,hashlib
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2f';GALLERY=BASE/'T07/gallery'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    if (BASE/'T07/revisions/A2g/integrated_checks.json').exists():
        from publish_a2g import main as latest_revision
        return latest_revision()
    joint=read(REV/'joint_slot_checks.json');integrated=read(REV/'integrated_checks.json');policy=read(REV/'policy_checks.json');structure=read(REV/'structural_geometry_checks.json');schedule=read(REV/'slot_schedule.json');state=read(BASE/'execution_state.json');tests=read(BASE/'T00/verification.json')
    assert integrated['all_sampled_background_numeric_pass'] and policy['sampled_station_policy']['status']=='pass'
    assert all(r['numeric_status']=='pass' for r in structure['rows'])
    for name in ['integrated_preview.mp4','integrated_unlit.png','integrated_lit.png','mid_left_structure_review.png','mid_right_structure_review.png','integrated_thumbnail_15.png','integrated_thumbnail_60.png']:shutil.copy2(REV/name,GALLERY/('a2f_'+name))
    shutil.copy2(Path(__file__).with_name('t07_gallery_v6.html'),GALLERY/'index.html')
    write_json(GAME/'bible/prototype_slot_schedule.json',{'version':'g01-alley-slot-schedule-1','station_id':'g01_st_l1_01_alley','source_evidence':str(REV/'joint_slot_checks.json'),'schedule':schedule,'human_origin':[760,500],'parallax':.45,'enemy_size_px':200,'status':'offline_candidate_not_runtime_enforced','production_approved':False})
    checks={'revision':'A2f','joint_slots':joint,'integrated':integrated,'policy':policy,'structural_geometry':structure,'schedule':schedule,'core_regression_tests':len(tests['tests']),'production_approved':False,'actual_0B':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    report=f'''# A2f：已批准策略落地与联合场景复核

2026-11-05，用户明确采用暖纸色硬化眼，并同意本试做站点整层均值转为诊断、保留槽位可读性硬指标，记录版本化例外。原话见user_feedback.yaml；该认可不放行A2技术项、正式生产或真实0B。

## 已落实的规范与材质

亮度例外版本g01-alley-luminance-exception-1写入bible/luminance_policy.json、config.yaml，并补入美术方案。只绑定g01_st_l1_01_alley，其他站点不能套用。历史C03失败不删除；近景范围、整帧限亮、背景≥0.25、普通差≥0.20、硬化眼差≥0.30、单眼≥16保持。缺少槽位证据不能通过。另一站点、低对比样本、空证据负例都被拒绝。

暖纸色材质版本g01-crow-hardened-eyes-1写入bible/material_contract.json和墨鸦元数据，CPU参考渲染器已接入。仅硬化墨鸦使用[217,160,102]眼色，原生alpha和眼形保留；普通墨鸦、其他敌人及已确认的受击视频不变。正式Godot采样、颜色空间及性能仍待验。

## 槽位联合检查

两居民各360个允许附墨动作帧，共{joint['human_frames']}帧×4候选槽={joint['joint_tests']}次检查。实际角色纸身alpha作为保护区，不允许墨鸦目标/印迹与其重叠。共用0.45视差时相机平移不改变相对关系，近景与边缘/HUD极值用独立检查。

650,350虽然此前背景可读，却与两居民保护区重叠，已从人质同屏排布排除，失败像素记录保留。420,350与420,490的保守图像矩形互相重叠，标记互斥。联合预览只选420,350和1110,350两个互不重叠槽位；人质原点760,500，墨鸦候选尺寸200。有效半径约67.75，HUD与60像素边缘预留通过。bible/prototype_slot_schedule.json保存的是候选约束，尚无引擎强制调度。

导出8秒15fps联合参考视频：人质附墨挣扎、两只墨鸦、右侧墨鸦普通/硬化切换、点灯与连续相机/呼吸运动。120帧×2墨鸦共{integrated['enemy_frame_checks']}个样本，最小中位对比{integrated['minimum_contrast']:.3f}，最小背底Y′{integrated['minimum_background']:.3f}，全部满足已批准例外的当前样本条件。其余轨迹、其他尺寸、预警/受击状态仍不能由这个片段推断通过。222×117缩略图已输出，辨识观感待本次人审。

联合渲染时修复一个参考合成器问题：enemy origin变量误覆盖station content_origin，放入敌人会改变最终裁切。现在两者分名；离屏敌人不得改变背景的负例已覆盖。此修复只涉及离线合成器，不是追踪器或游戏引擎。核心回归检查{len(tests['tests'])}/{len(tests['tests'])}通过；旧C13三投影断言同步为保留越界压力样本的四条记录，历史基线先归档再更新。

## 独立结构标注

按原稿视觉独立手工标出左上墙、左卷帘后纸面、右侧自行车后墙、右上墙四块必须连续的纸面。坐标直接写入多边形，不从alpha反推预期形状；四区域共159854源像素，当前无缺失，5种相机组合无缺失。人为挖洞后能检测到缺纸。

这些标注仅验证四块实心建筑区域。它们不覆盖复杂屋檐、树枝、镂空边界或全部隐藏结构，也不把原来自洽的extent检查升级为完整C07b验收。本轮需要人工抽查绿色区域应否为连续纸面；完整隐藏几何仍保留待办。

## 当前检查点与门槛

请看联合试播，判断墨鸦/人质/硬化态在场景中是否容易分清；再抽查两张墙面图里的绿色区域是否应为连续纸面。已确认的材质、亮度路线、肘部和受击不重复问。

A2尚未全部通过；完整隐藏几何、其余状态的可读性、充分阈值标定、正式引擎运动/遮挡/采样/峰值、真实光枪继续保留。T08未启动，T09–T16批量仍等真实0B五项验收。本轮新增GPT/付费API调用0次；0A仍{state['phase_0A_calls']}/120，含T01总计{state['builtin_image_calls']}，未披露费用仍未知。
'''
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review.update(status='A2f_joint_readability_and_structural_annotation_checkpoint',revision_report='revisions/A2f/report.md');(BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    cal=read(BASE/'T07/calibration.json');cal.update(A2e='warm paper hardened eyes and station-scoped policy exception explicitly approved 2026-11-05',A2f='integrated readability and four wall-region annotations pending; no new full-asset calibration labels');write_json(BASE/'T07/calibration.json',cal)
    contract=read(GAME/'bible/animation_contract.json');contract.update(acceptance='A2d_lowered_elbow_visually_approved_remaining_technical_checks_pending');write_json(GAME/'bible/animation_contract.json',contract)
    state.update(T07='A2f_joint_readability_and_structural_annotation_checkpoint',next_task='A2f_integrated_readability_and_wall_annotation_spotcheck',verified_offline_tests=len(tests['tests']),current_blockers=['A2f_integrated_visual_check','complete_hidden_geometry','remaining_state_readability','C14_calibration','engine_validation','actual_0B']);write_json(BASE/'execution_state.json',state)
    files=[p for p in REV.iterdir() if p.is_file() and p.name!='manifest.json']+[GALLERY/'index.html'];manifest={'revision':'A2f','new_image_calls':0,'policy_version':'g01-alley-luminance-exception-1','material_version':'g01-crow-hardened-eyes-1','production_asset_approved':False,'actual_0B':False,'outputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest);print('A2f integrated checkpoint published')
if __name__=='__main__':main()
