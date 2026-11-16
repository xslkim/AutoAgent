"""Publish concrete technical decisions after approved A2d visual revisions."""
import json,shutil,hashlib
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2e';GALLERY=BASE/'T07/gallery'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    if (BASE/'T07/revisions/A2f/policy_checks.json').exists():
        from publish_a2f import main as latest_revision
        return latest_revision()
    loops=read(REV/'loop_checks.json');slots=read(REV/'slot_motion_checks.json');tracker=read(REV/'tracker_contract_screening.json');bands=read(BASE/'T04/additional_checks.json')['C03_bands'];state=read(BASE/'execution_state.json')
    for p in REV.glob('*.png'):shutil.copy2(p,GALLERY/('a2e_'+p.name))
    report=f'''# A2e：A2d通过后的技术复核与下个决策点

已归档用户A2d明确认可：放下手肘部自然，墨怪受击沿用A2c；场景、点灯、人物造型、墨材质和反光继续沿用。该反馈没有放行A2技术项、正式生产或真实0B。

## 本轮完成

1. 两个人物共14个循环，用实际渲染的首、次、倒数第二、末帧执行现有C12位置/速度检查，全部通过当前0.02初始阈值。获救为一次性状态转换，不纳入循环。阈值尚未充分标定，不称正式引擎通过。
2. 普通墨鸦按200像素候选大小检查20个槽位：5组相机/呼吸组合×灯灭/灯亮，共200样本。4槽全部数值通过，中心为420,350；650,350；1110,350；420,490。最低对比分别约0.244、0.249、0.272、0.236；包含目标实际alpha覆盖范围、背底亮度及近景遮挡检查。它们是候选站位，还需与人质运动/HUD统一排布、视觉缩略识别和引擎路径验证，不直接登记为正式生产槽。
3. 硬化态旧眼睛与周围墨身的中位亮度差约{slots['hardened']['original_eye_contrast']:.3f}，未满足0.30；同一原生眼形的暖纸色运行时材质试做约{slots['hardened']['trial_eye_contrast']:.3f}，单眼长度{slots['hardened']['individual_eye_length_px']}像素，超过16像素要求。新材质尚待视觉认可。只改变硬化态眼睛材质，原图、普通态和受击视频均保留。
4. 追踪失败定位到测试夹具：原第二个透视四边形相对边角度分歧超过追踪器既有15度限制，纯边框控制也在geometry阶段被拒。旧失败保留在历史报告与tracker_diagnostic.json；修正合成筛查的样本分类，保留越界压力样本，并加入符合既有几何范围的倾斜样本。显示器/电视、灯灭/灯亮4组的合法样本均通过合成获取及四边测量。未更改scripts/guntrack.py、Android源码或追踪参数，也未用该结果代表相机/真实0B通过。
5. 独立审计确认7个站点extent与当前图像alpha完全相同。这能检测后续删除像素的错误，但不能发现原图与extent同时缺失的预期隐藏结构，因此完整隐藏几何仍待独立白模/结构标注；没有把63/63的自洽比较升级为几何验收。

## 需要选择的亮度规范

原C03按远景0.45–0.75、中景0.25–0.55检查。当前far_base约0.176、far_town约0.307、mid_ground约0.248，原失败继续保留。用户多次认可夜景，不足以自动删除这些规则。

建议的明确变更提案（尚未应用）：保留已确认夜景；仅本试做站点，将整层均值作为诊断，不作为A2离线预审的单独否决条件；可射槽位仍严格要求背底Y′≥0.25、普通目标差≥0.20、硬化眼与墨身差≥0.30且单眼≥16，运动/点灯全状态均满足；近景及整帧限亮原规则保留。原规范失败以“待审核规范变更”保留，批准后写版本化例外，不能冒称旧C03通过。

另一选择：维持原整层范围，先做远景与地面提亮试稿，再重新审核受影响场景、点灯和可读性；现有已确认夜景保留为历史基准。本轮未擅自改规范或重画已认可场景。

## 仍有门槛

完整隐藏几何、真实引擎运动/遮挡与采样、GPU导入峰值、足量C04/C12/C14标定样本、缩略/预警视觉识别和真实光枪全部保留。当前库没有Godot游戏工程；任务文档明确游戏框架不在本美术任务范围，因此未擅自扩成另一套游戏框架。既有硬件录制不能冒充纸灯城真实0B测试。

T08仍等A2，T09–T16批量仍等真实0B五项验收。本轮新增GPT/付费API调用0次，0A仍{state['phase_0A_calls']}/120，总计{state['builtin_image_calls']}；已发生费用未披露，记未知。

审核页只需选择硬化眼试稿和亮度处理路线。角色肘部、受击与已确认美术不重复询问。原始数据见loop_checks.json、slot_motion_checks.json、tracker_contract_screening.json、tracker_diagnostic.json、hidden_geometry_audit.json。
'''
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    checks={'revision':'A2e','loops':loops,'slots':slots,'tracker':tracker,'hidden_geometry':read(REV/'hidden_geometry_audit.json'),'original_C03_bands':bands,'norm_change_approved':False,'actual_0B':False,'production_approved':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    shutil.copy2(Path(__file__).with_name('t07_gallery_v5.html'),GALLERY/'index.html')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review.update(status='A2e_hardened_eyes_and_luminance_policy_checkpoint',revision_report='revisions/A2e/report.md')
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    cal=read(BASE/'T07/calibration.json');cal.update(A2d='lowered elbow visually approved by explicit user feedback',A2e='hardened-eye trial and C03 policy awaiting user; existing thresholds not waived');write_json(BASE/'T07/calibration.json',cal)
    state.update(T07='A2e_next_checkpoint_hardened_eyes_and_C03_policy',next_task='A2e_material_and_C03_policy_decision_then_continue',C13_synthetic_screening='pass_within_existing_geometry_contract_historical_outside_contract_stress_retained',current_blockers=['A2e_hardened_eyes_visual_review','C03_policy_decision','complete_hidden_geometry','engine_motion_and_occlusion','C14_calibration','real_camera_and_actual_0B']);write_json(BASE/'execution_state.json',state)
    files=list(REV.glob('*.json'))+list(REV.glob('*.png'))+[GALLERY/'index.html'];manifest={'revision':'A2e','status':'technical_decision_checkpoint','new_image_calls':0,'actual_0B':False,'production_asset_approved':False,'outputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files if p.name!='manifest.json'],'tracker_source_sha256':hashlib.sha256(Path('D:/tvgun/scripts/guntrack.py').read_bytes()).hexdigest()};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest)
    print('A2d approval retained; A2e technical checkpoint published')
if __name__=='__main__':main()
