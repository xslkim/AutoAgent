"""Publish prop correction; preserve accepted A2f checks and pending hardware gates."""
import json,hashlib,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
from puppet_motion_v5 import Civilian
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2g';GALLERY=BASE/'T07/gallery';CACHE=Path('D:/gunforge_cache/g01')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if (BASE/'T07/revisions/A2h/verification.json').exists():
        from publish_a2h import main as latest_revision
        return latest_revision()
    prop=read(REV/'prop_checks.json');motion=read(BASE/'T05/motion_checks_v5.json');rescue=read(BASE/'T05/rescue_motion_checks_v5.json');joint=read(REV/'joint_slot_checks.json');integrated=read(REV/'integrated_checks.json');mem=read(REV/'texture_memory_estimate.json');pack=read(REV/'sparse_texture_plan.json');state=read(BASE/'execution_state.json')
    assert prop['status']=='pass' and all(v['status']=='pass' for v in motion.values()) and all(v['status']=='pass' for v in rescue.values()) and integrated['all_sampled_background_numeric_pass']
    f=CACHE/'T05/vendor';model=read(f/'puppet.json');c=Civilian(model,f)
    for n in model['parts']:
        if n['id']=='prop':n.update({k:c.nodes['prop'][k] for k in ['pivot','attach','z','angle_range']})
    model['animation_v5']=c.metadata();model['animation_v5']['review']='pending_prop_direction_A2g';write_json(f/'puppet.json',model);shutil.copy2(f/'puppet.json',REV/'vendor_puppet.json')
    contract=read(GAME/'bible/animation_contract.json');contract.update(version='civilian-motion-5',civilian_prop_constraint=model['animation_v5']['prop'],acceptance='A2f_readability_and_four_structure_regions_approved_prop_correction_pending');write_json(GAME/'bible/animation_contract.json',contract)
    for p in (BASE/'T05/gallery').glob('*_v5.*'):shutil.copy2(p,GALLERY/p.name)
    for name in ['integrated_preview.mp4','integrated_lit.png','prop_contact.jpg','struggle_prop.png']:shutil.copy2(REV/name,GALLERY/('a2g_'+name))
    shutil.copy2(Path(__file__).with_name('t07_gallery_v7.html'),GALLERY/'index.html')
    checks={'revision':'A2g','prop':prop,'motion':motion,'rescue':rescue,'joint_slots':joint,'integrated':integrated,'memory':mem,'sparse_pack':{k:v for k,v in pack.items() if k!='sources'},'approved_structural_regions':read(REV/'approved_structural_regions.json'),'production_approved':False,'actual_0B':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    report=f'''# A2g：糖葫芦握持方向修正与显存风险处理

用户A2f明确认可同屏对象/硬化态可区分，四块绿色结构区域应是连续纸面；仅新增“人物的糖葫芦方向不对”。原话在user_feedback.yaml。以上不放行A2全部技术项、正式生产或真实0B；四块区域认可不泛化为完整隐藏几何。

## 糖葫芦

旧道具直接继承前臂旋转，手臂外展时果串倾向身体内侧；旧握点也没有按裸竹签和掌心分别标注。新版本保持掌心握点跟随，按前臂世界角补偿竹签朝向，让果串在手的上方、略向身体外侧，裸签在下方；道具先于手掌绘制，手掌遮住握住的竹签部分。道具是居民日常物件，不是武器或可伤害目标。

只改卖糖葫芦居民的道具锚点、绘制顺序及约束，原PNG未改、没有新出图。果串角度范围约{prop['world_angle_range'][0]:.1f}–{prop['world_angle_range'][1]:.1f}°，属于项目摆放选择。{prop['actual_frame_states']}个普通/附墨动作状态中，实算握点误差最大{prop['max_grip_error_source_px']:.3g}源像素，果串始终位于握点上方并朝外，裸签在下方。旧内倾方向作为负例被拒绝。录像厅老板24个动作时间点逐像素对照保持一致。7个循环位置/速度复核通过当前初始阈值，获救一次性转换不当循环验。

重跑两居民8类动作共{sum(v['frames'] for v in motion.values())}帧、六墨形附墨{sum(v['blob_frame_tests'] for v in rescue.values())}次；有效半径40、纸边界6和印迹保护标准没有降低。新道具运动包围盒、HUD/边缘带检查通过。两居民720帧×4槽位共{joint['joint_tests']}次联合检查重跑，650,350仍禁止与人质同屏，420,350/420,490互斥，参考片继续选420,350与1110,350。

8秒同屏片按新握持重组，{integrated['enemy_frame_checks']}个墨鸦帧样本最小对比{integrated['minimum_contrast']:.3f}、最小背底{integrated['minimum_background']:.3f}，当前样本满足已批准站点策略。人质、墨鸦及场景其他方向已认可，本轮只问糖葫芦的握持方向。

## 显存估算与无损候选

按实际引用的裁剪PNG、RGBA8/R8和逐级mipmap分配计算，同一贴图多个实例仅计一次，源图/诊断全图及没有使用的序列帧图集不混入：原站点和灯光估算{pack['source_total_bytes']/1024**2:.2f}MiB，超过48MiB；两居民、两类墨怪、六墨形估算{mem['categories']['both_residents_two_enemies_six_blobs']['estimated_bytes']/1024**2:.2f}MiB，低于32MiB。费用或磁盘PNG大小没有用于VRAM推算。

已生成g01-alley-sparse-1无损打包候选：128×128内容块，只跳过完全无贡献的块，保留全部可见半透明像素；每边2像素采样bleed，绘制时只使用内容UV，不能把bleed重叠绘制。每个纹理在黑底、白底重组都逐像素一致。选择原图或稀疏块中较省的分配，完整mipmap链仍计入。

站点和灯光估算降至{pack['selected_total_bytes']/1024**2:.2f}MiB；即使单通道纹理全部按RGBA8保守计，也为{pack['conservative_all_RGBA8_bytes']/1024**2:.2f}MiB，低于48MiB和十进制48MB。原始超预算估算保留在texture_memory_estimate.json，打包计划与所有块在sparse_texture_plan.json及texture_pack/。

这不是实际Godot显存通过。当前参考视频仍用原完整纹理；正式引擎必须实测分块mipmap接缝、过滤、绘制调用数、加载/卸载、转场和峰值后，才能决定采用该候选。特效/UI、字体/渲染目标、第二站转场等也未用此小计冒充完成。

## 当前检查点与保留项

审核页显示新版同屏片和五动作握持近景，只需判断糖葫芦是否已朝向正确；不重新询问已确认的同屏可读性与四块墙面。完整隐藏几何、其余状态可读性、阈值充分标定、引擎/GPU和真实光枪仍待办。T08未启动，T09–T16批量仍等真实0B五项验收。

本轮新增GPT/付费API调用0次；0A仍{state['phase_0A_calls']}/120，含T01总计{state['builtin_image_calls']}。未披露费用仍未知。旧A2f元数据、报告、网页及相关代码已存D:/gunforge_cache/g01/T07/A2f/。
'''
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review.update(status='A2g_prop_direction_checkpoint',revision_report='revisions/A2g/report.md');(BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    cal=read(BASE/'T07/calibration.json');cal.update(A2f='integrated readability and four wall regions explicitly approved; prop direction revision required',A2g='pending prop visual correction; no fabricated full-asset calibration labels');write_json(BASE/'T07/calibration.json',cal)
    p=BASE/'T05/manifest.json';m=read(p)
    for entry in m.get('candidate_files',[]):
        path=Path(entry['file']);entry.update(sha256=sha(path),bytes=path.stat().st_size)
    m.update(status='A2g_prop_direction_review_pending',revision_manifest=str(REV/'manifest.json'));write_json(p,m)
    state.update(T05='A2g_upright_prop_delivered_pending_review',T07='A2g_prop_direction_checkpoint',next_task='A2g_prop_direction_then_remaining_technical',current_blockers=['A2g_prop_direction_review','complete_hidden_geometry','remaining_state_readability','C14_calibration','engine_pack_sampling_and_memory','actual_0B']);write_json(BASE/'execution_state.json',state)
    files=[p for p in REV.iterdir() if p.is_file() and p.name!='manifest.json']+[GALLERY/'index.html'];manifest={'revision':'A2g','new_image_calls':0,'production_asset_approved':False,'actual_0B':False,'code_sha256':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py') if any(k in p.name for k in ['v5','a2_memory','texture_pack','a2g'])},'outputs':[{'file':str(p),'sha256':sha(p)} for p in files]};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest);print('A2g prop checkpoint published')
if __name__=='__main__':main()
