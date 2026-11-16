"""T07 mandated stage review; publishing never grants T08 or production permission."""
import json,hashlib
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2i';CODE=Path(__file__).parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    if (BASE/'T07/revisions/A2j/user_feedback.yaml').exists():
        from publish_a2j import main as publish_current
        return publish_current()
    r=read(REV/'readiness.json');assert not r['automatic_A2_acceptance'] and not r['T08_started']
    freeze=read(REV/'checker_freeze.json')
    for name,digest in freeze['code_sha256'].items():assert hashlib.sha256((CODE/name).read_bytes()).hexdigest()==digest,name
    gallery=BASE/'T07/gallery';(gallery/'index.html').write_text((CODE/'t07_gallery_v9.html').read_text(encoding='utf-8'),encoding='utf-8')
    report='''# A2i：T07 离线管线审核

## 结论与本次决定

本轮把 A2h 明确认可的两种墨怪预警及七张完整纸层范围归档。七张范围已独立冻结，后续素材修改不能重新生成基线来规避比较。当前离线流程具备继续首站点试做的证据，但阈值充分标定、GPU、引擎及真实光枪仍未完成，不能称为 A2 全技术通过。

依据任务文档 T07「停止，等审核人：A2 判断管线是否可行」，现停在阶段审核，等待是否允许进入 T08 离线试做的明确决定。T08 尚未开始；选择继续必须同时保留以下缺口。T09–T16 批量仍等真实 0B 五项验收。没有把历史的美术方向批准扩展为正式生产批准。

## 已完成与适用范围

- C07：七张形状采用用户认可的 2D 设计规范；125 状态（静态、四极值、120 个连续组合状态）共 1,000 项覆盖检查通过，缺失像素均为 0。仅覆盖当前相机/视差范围；不是对未知几何或实际 Godot 采样的证明。缺口反例和冻结 mask 篡改检测通过。完整基线、用户来源及哈希在 bible/geometry/alley_extent_v1/。
- C10/动作：每角色四次原始零件表均十件完整，原极端姿势接缝/铜钉检查通过。当前 v5 两人物各 564 帧通过已实现动作的离线运动检查；两人物各 2,160 项救援附墨帧检查通过。糖葫芦、肘部沿用用户确认。人物只做人质/NPC，救援命中对象是独立附墨，没有人体敌人攻击或受击动作。
- 状态与同屏：沿用 A2f 同屏/墙面、A2e 暖纸硬化眼及本巷口亮度例外、A2c 受击、A2h 预警视觉认可。当前调度仅为离线候选，不能冒称实际引擎碰撞/状态逻辑通过。
- 追踪：合法边框合成筛查通过，越界压力失败保留；未改追踪算法来迎合夹具，未冒称真实光枪通过。
- C15：原整层站点超预算、独立块 mipmap 的缩放采样失败均保留。混合稀疏 base＋整层低分辨率链候选在 CPU 参考比较通过，保守 RGBA8 估算 42.47 MiB，低于 48MB/48MiB。不是 GPU 导入包或真实显存实测；量化、上传、sRGB/线性、预乘、LOD、接缝、draw calls 与峰值待验。

## 反例复跑：9/9 拦截

逐项真实结果见 revisions/A2i/negative_recheck/negative_checks.json。本轮复跑覆盖：中景删除运动显露纹样（C07b）、弱点移出墨身（C09 和 C11 两项）、包围盒压住 HUD（C09）、SDF 错误 sRGB 转换（C16）、SDF 错标颜色纹理（C16）、4096² 无损 RGBA 图集超预算（C15）、背景加字（C05）、零件表多头（C10）。全部按预期失败，对应正常控制保留。

该反例报告中“full hidden geometry still pending”描述的是最初反例夹具的证据范围；本轮完整层设计基线覆盖结果另见 frozen_geometry_checks.json，不改写旧夹具历史。

## 阈值及样本不足

版本 art-checks-0.3-initial-offline 冻结初始阈值与代码哈希（checker_freeze.json），配置指向此快照。不是充分标定版本。

- C04：ΔE 15、覆盖率 0.90；可用于全资产正/负标定的明确标签各 0。A1 只有特征选择（其中配色参考 6 张），不能把未选素材当反例，也不能把局部特征认可当整张通过。
- C12：端点差与速度差初值均 0.02。可用于独立循环正/负标定的明确标签各 0。已确认肘部和握持不等于给全部循环打了正标签；计算接缝通过不计作人工标定样本。
- C14：评分阈值 null，可用完整风格正/负标定标签各 0；目前没有可用的已标定评分器。不得伪造风格分数或自动风格通过。

每类不足 20 张正例和 20 张反例，按任务文档如实记录实际数量。T08 若获准只继续离线试做，保留上述未满足项；不生成“全部适用检查已通过”结论。

## 0A 调用、可用性与费用

'''
    for t,j in r['jobs'].items():report+=f"- {t}：实际调用 {j['calls_including_failures_retries']} 次（返回 {j['returned']}、接口报错 {j['failed']}、未返回 {j['pending']}）；任务上限 {j['task_cap']}。\n"
    report+='''
0A 合计 98/120 次（含重试），含 T01 共 101 次。本轮新增出图 0，外部付费 API 调用 0；工具不披露金额，实际费用未知，不等于零费用。接口返回成功不代表资产可用。

站点有一套离线七层/灯光候选；人物两类各 4/4 张原零件表十件完整（结构完整率 100%，各达到至少四次中两次完整的试做要求）；墨怪两类、四个姿态候选。原生成有配色、文字、深度亮度、动画观感、握持及原眼睛对比等问题；拒绝及修正链分别保留在 T04–T06 检查和 A2b–A2h 报告中，不能因接口零报错而算零失败。当前整类正式生产批准数为 0。

完整生产可用率不能由特征/片段认可计算；不把零件表完整率外推为成品率。完整资产率及其量产调用预测为未知，量产金额同样不能由调用次数虚构。批量放行前需补完整标签和真实 0B 证据，再重算调用量/费用。

## 证据索引与后续

- 本轮反馈：revisions/A2i/user_feedback.yaml；冻结几何：revisions/A2i/frozen_geometry_checks.json。
- 阶段汇总及调用账：revisions/A2i/readiness.json；检查版本：revisions/A2i/checker_freeze.json；阈值：calibration.json。
- 当前动作：../T05/motion_checks_v5.json、../T05/rescue_motion_checks_v5.json、revisions/A2g/prop_checks.json；人物零件表：../T05/vendor_rig_checks.json、../T05/video_rig_checks.json。
- GPU 候选与失败：revisions/A2h/hybrid_texture_plan.json、hybrid_sampling_checks.json、mip_sampling_checks.json。
- 浏览器审核页汇集站点点灯、两个角色动作、两种墨怪及受击/预警回看。用户只需决定“保留待办继续 T08 离线试做”或“留在 T07 并说明修改”。

T08 若获准，下一检查点为 30–60 秒首站点样片、标注叠加版、完整素材清单与显存估算的 A3 离线预审。真实光枪暂不要求用户操作，硬件条件就绪再验证真实 0B 五项。
'''
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    checks={'revision':'A2i','checker_version':freeze['version'],'readiness':r,'technical_acceptance':False,'T08_started':False,'production_approved':False,'actual_0B':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review.update(status='A2_offline_pipeline_decision_required',revision_report='revisions/A2i/report.md',technical_acceptance=False,T08_started=False);(BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state=read(BASE/'execution_state.json');state.update(T07='A2_offline_pipeline_decision_required',next_task='A2_stage_review_before_T08',current_blockers=['A2_stage_decision','C04_C12_C14_calibration_shortfall','GPU_engine_validation','actual_0B']);write_json(BASE/'execution_state.json',state)
    paths=[p for p in REV.rglob('*') if p.is_file() and p.name!='manifest.json']+[gallery/'index.html'];manifest={'revision':'A2i','checker_version':freeze['version'],'new_image_calls':0,'production_approved':False,'actual_0B':False,'outputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest)
    print('A2 stage review published; T08 remains unstarted')
if __name__=='__main__':main()
