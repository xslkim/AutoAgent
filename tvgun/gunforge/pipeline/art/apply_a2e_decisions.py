"""Apply explicit A2e decisions, scoped to this prototype and its approved material."""
import json,hashlib
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2f';CACHE=Path('D:/gunforge_cache/g01')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    REV.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    feedback={'stage':'A2e','date':'2026-11-05','source':'explicit_user_chat','hardened_eyes':'approved_warm_paper_tint','luminance_policy':'approved_station_scoped_diagnostic_layer_means_and_hard_slot_readability','notes':'采用暖纸色硬化眼试稿；保留已确认夜景，同意本试做站点整层均值转为诊断，按槽位可读性硬指标验收，并记录版本化例外。','technical_acceptance':False,'production_approved':False,'actual_0B':False}
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    policy={'version':'g01-alley-luminance-exception-1','station_id':'g01_st_l1_01_alley','approved_date':'2026-11-05','source':str(REV/'user_feedback.yaml'),'scope':'this prototype station only; other stations retain ART_PLAN 2.2 ranges','layer_means':'diagnostic; keep original C03 results','near_range':[.05,.20],'whole_frame':{'max_Yprime':.75,'max_over_limit_fraction':.02},'slot':{'background_Yprime_min':.25,'normal_contrast_min':.2,'hardened_eye_contrast_min':.3,'individual_eye_length_min_px':16,'all_camera_light_motion_states_required':True},'scope_does_not_approve':['hidden_geometry','C14_calibration','engine_validation','actual_0B','batch_production']}
    write_json(GAME/'bible/luminance_policy.json',policy)
    material={'version':'g01-crow-hardened-eyes-1','approved_date':'2026-11-05','applies_to':['g01_ink_crow'],'state':'hardened','eye_tint_rgb':[217,160,102],'alpha':'original eye attachment alpha preserved','normal_and_hit_feedback':'unchanged','engine_validation':'pending','source':str(REV/'user_feedback.yaml')};write_json(GAME/'bible/material_contract.json',material)
    p=CACHE/'T06/crow/enemy.json';m=read(p);m['hardened_eye_material']={**material,'visual_approval':'approved_A2e'};write_json(p,m)
    for task in ['T06']:
        p=BASE/task/'manifest.json';m=read(p)
        for f in m.get('candidate_files',[]):
            path=Path(f['file']);f.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
        write_json(p,m)
    config=Path(__file__).with_name('config.yaml');cfg=yaml.safe_load(config.read_text(encoding='utf-8'));cfg['station_policy_overrides']={'g01_st_l1_01_alley':{'version':policy['version'],'policy_file':str(GAME/'bible/luminance_policy.json')}};config.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'))
    review['items'] += [{'id':'crow_hardened_eyes_v1','status':'approved','scope':'warm paper eye material in hardened state only','source':'explicit_A2e_user_feedback'},{'id':'alley_luminance_exception_v1','status':'approved','scope':'this prototype station only; no A2 or production approval','source':'explicit_A2e_user_feedback'}]
    review.update(status='A2f_technical_work_in_progress',latest_feedback='revisions/A2f/user_feedback.yaml');(BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    p=BASE/'execution_state.json';s=read(p);s.update(updated='2026-11-05',T07='A2f_technical_work_in_progress',next_task='joint_slot_protection_and_hidden_geometry_audit',current_blockers=['joint_slot_protection','complete_hidden_geometry','C14_calibration','engine_validation','actual_0B']);write_json(p,s)
    p=Path('D:/tvgun/docs/ART_PLAN_PAPER_LANTERN_CITY.md');text=p.read_text(encoding='utf-8');text+='\n\n### A2e 已批准的首站点亮度例外（2026-11-05）\n\n仅适用于 `g01_st_l1_01_alley` 试做，版本 `g01-alley-luminance-exception-1`。审核人明确同意保留已认可夜景，将整层均值转为诊断，原C03结果保留；各可射槽位仍须在相机/点灯/运动状态满足：背底Y′≥0.25、普通目标差≥0.20、硬化眼与墨身差≥0.30、单眼≥16像素。近景范围及整帧限亮规则保留。其他站点仍按第2.2节；本例外不批准A2技术项、正式生产或真实0B。机器可读规范见 `gunforge/games/g01/bible/luminance_policy.json`。硬化墨鸦采用已审核的暖纸色眼材质，原始贴图与普通态保留。\n';p.write_text(text,encoding='utf-8')
    print('A2e decisions applied with station-scoped versioned policy and material contract')
if __name__=='__main__':main()
