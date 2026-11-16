"""Publish remaining warning readability and full-shape design-review checkpoint."""
import json,hashlib,shutil,html
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h';GALLERY=BASE/'T07/gallery'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    if (BASE/'T07/revisions/A2i/readiness.json').exists():
        from publish_a2i import main as publish_current
        return publish_current()
    plan=read(REV/'hybrid_texture_plan.json');sampling=read(REV/'hybrid_sampling_checks.json');bad=read(REV/'mip_sampling_checks.json');extent=read(REV/'extent_proposals.json');warning=read(REV/'warning_checks.json');verify=read(REV/'verification.json');state=read(BASE/'execution_state.json')
    assert sampling['all_pass'] and warning['status']=='pass_numeric_pending_visual'
    for p in [REV/'warning_comparison.mp4',REV/'warning_comparison.jpg',*REV.glob('*_extent_review.jpg')]:shutil.copy2(p,GALLERY/('a2h_'+p.name))
    cards=''.join('<details><summary>'+html.escape(r['name'])+'</summary><img loading="lazy" src="a2h_'+r['layer']+'_extent_review.jpg" alt="'+html.escape(r['name'])+'原图与完整范围提案"></details>' for r in extent['rows'])
    template=Path(__file__).with_name('t07_gallery_v8.html').read_text(encoding='utf-8');(GALLERY/'index.html').write_text(template.replace('<!--EXTENT_CARDS-->',cards),encoding='utf-8')
    report=f'''# A2h：预警态、完整纸层设计范围与打包采样复核

用户A2g明确认可糖葫芦方向与握持；同屏可读性、四块墙面区域、暖纸色硬化眼、站点亮度例外与其他已确认方向继续沿用。反馈归档于user_feedback.yaml，不放行正式生产或真实0B。

## 打包采样：保留失败，替换候选

上轮g01-alley-sparse-1在原尺寸下黑白重组完全相同，不能外推到mipmap采样。本轮以CPU浮点预乘alpha、编码空间BOX mip链及双线性UV采样比较整层和独立分块：2px bleed在已测半/四分之一缩放下最大单通道偏差{bad['summary']['2']['max_error']:.3f}；4px和8px仍有偏差，未把扩大bleed当作修复。原记录在mip_sampling_checks.json，独立局部mipmap候选不再列为可直接用于引擎的方案。

原因包含非二次幂纹理的全局mip网格与各块独立缩小的网格不一致，以及透明邻接块的过滤范围。新候选g01-alley-hybrid-2b保留稀疏base层且不生成块内mipmap；低分辨率链在整层上先生成，再以全层UV采样，并保留采样邻域guard。各图在32/64/128/256内容块候选中按保守分配选较省者；若原整图更省则保留原图。CPU参考包含1、0.75、0.5、0.25倍缩放。

{len(sampling['rows'])}组源图/缩放比较全部满足小于0.00001浮点通道误差的参考一致性要求（这是比较容差，不是已标定视觉评分）。已选纹理估算{plan['selected_bytes']/1024**2:.2f}MiB；全部按RGBA8保守计算{plan['conservative_RGBA8_bytes']/1024**2:.2f}MiB，低于十进制48MB及48MiB。初始固定128块方案也保留为*_initial128.json；当前按每图块大小选择后的方案在hybrid_texture_plan.json。

GPU尚未通过：8bit量化/上传、sRGB与线性空间、预乘处理、三线性LOD混合、实际接缝、draw calls和临时上传/峰值仍待测。保存的.npy是CPU浮点参考，不是已交付的Godot导入包；不能把浮点文件的磁盘体积当成GPU8bit分配。当前美术参考播放器仍使用整图。

## 预警态

墨鸦按200像素最长外形、墨蝌蚪按90像素头部直径，使用既有1.5Hz预警参数。保持墨身、常驻反光和主命中区，预警仅为朱砂印迹脉动加局部暖环。普通态作同背景对照；既有硬化眼与受击视频不重做。

4秒30fps对照片共{warning['sample_checks']}个对象/状态帧检查：印迹没有超出可见墨身，亮度超限比例未超过原2%限制。暖环是非命中装饰。是否一眼看出“正在预警”仍待本次人审；正式引擎时序、攻击判定和硬件待验。

## 七张完整纸层范围提案

此前四块墙面有独立多边形且已获认可，不能据此批准全部纸层。本轮把七张完整层各自独立展示，并给出浅色有纸、深色为空的范围提案，源图及mask哈希在extent_proposals.json。

这些mask来源于现有整层alpha，不是独立、预先存在的完整性真值；与原图相同不证明原先被挡区域已经补齐。本检查点要求明确确认“此完整外形及镂空是否就是这张纸的预期设计范围”，或指出应补的缺口。尚未确认时，不冻结为已验收extent，也不把C07b改为完整通过。若无法判断，可选择暂不确认。后续须基于明确认可的设计基线验证运动显露和变更，而非拿改动后的alpha重新生成基线规避检查。

## 门槛与预算

本次只复核未覆盖的预警观感和完整纸层范围，不重复问糖葫芦及既有认可。A2仍未正式全部通过；完整隐藏几何、状态辨识、阈值充分标定、引擎/GPU和真实光枪等按证据保留。T08未启动，T09–T16批量仍等真实0B五项验收。本轮新增GPT/外部付费API调用0次，0A仍{state['phase_0A_calls']}/120、含T01累计{state['builtin_image_calls']}；工具未披露费用仍未知。
'''
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    checks={'revision':'A2h','local_mip_failure_summary':bad['summary'],'hybrid_summary':{k:v for k,v in plan.items() if k!='sources'},'sampling':sampling,'warning':warning,'extent_proposals':extent,'verification':verify,'full_hidden_geometry_approved':False,'production_approved':False,'actual_0B':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review.update(status='A2h_warning_and_full_layer_design_checkpoint',revision_report='revisions/A2h/report.md');(BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    cal=read(BASE/'T07/calibration.json');cal.update(A2g='prop direction and grip explicitly approved',A2h='warning and full-layer proposed design scope pending, no fabricated calibration samples');write_json(BASE/'T07/calibration.json',cal)
    write_json(GAME/'bible/texture_candidate_status.json',{'station_id':'g01_st_l1_01_alley','GPU_approved_candidate':None,'current_CPU_reference_candidate':'g01-alley-hybrid-2b','not_engine_import_ready':True,'rejected_for_independent_mipmap_use':[{'version':'g01-alley-sparse-1','reason':'measured CPU downscale sampling mismatch; native-size reconstruction alone insufficient','evidence':str(REV/'mip_sampling_checks.json')}],'engine_validation_required':plan['engine_pending']})
    state.update(T07='A2h_warning_and_full_layer_design_checkpoint',next_task='A2h_warning_readability_and_full_layer_design_review',current_blockers=['A2h_warning_visual_review','full_extent_design_review','C14_calibration','GPU_hybrid_pack_validation','actual_0B']);write_json(BASE/'execution_state.json',state)
    files=[p for p in REV.iterdir() if p.is_file() and p.name!='manifest.json']+[GALLERY/'index.html'];manifest={'revision':'A2h','new_image_calls':0,'production_asset_approved':False,'actual_0B':False,'outputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest);print('A2h warning and whole-layer design checkpoint published')
if __name__=='__main__':main()
