"""Consolidate actual A2 evidence and freeze INITIAL, not falsely calibrated, checks."""
import json,hashlib
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2i';CODE=Path(__file__).parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    cfg=yaml.safe_load((CODE/'config.yaml').read_text(encoding='utf-8'));state=read(BASE/'execution_state.json');geometry=read(REV/'frozen_geometry_checks.json');negative=read(REV/'negative_recheck/negative_checks.json');motion=read(BASE/'T05/motion_checks_v5.json');rescue=read(BASE/'T05/rescue_motion_checks_v5.json');sampling=read(BASE/'T07/revisions/A2h/hybrid_sampling_checks.json')
    assert geometry['status']=='pass' and negative['all_negative_checks_rejected'] and sampling['all_pass'] and all(r['status']=='pass' for r in motion.values()) and all(r['status']=='pass' for r in rescue.values())
    jobs={};total=0;batch_pending=[]
    for task in ['T02','T03','T04','T05','T06']:
        ledger=read(BASE/task/'calls.json')['calls'];q=read(BASE/task/'queue.json') if (BASE/task/'queue.json').exists() else []
        jobs[task]={'calls_including_failures_retries':len(ledger),'task_cap':cfg['task_call_caps'][task],'returned':sum(c['state']=='returned' for c in ledger),'failed':sum(c['state']=='error' for c in ledger),'pending':sum(c['state'] not in ['returned','error'] for c in ledger),'candidate_jobs':len(q),'unreported_cost':None};total+=len(ledger)
    assert total==state['phase_0A_calls'] and total<=cfg['generation']['phase_0A_call_cap'] and all(r['pending']==0 for r in jobs.values())
    usable={}
    for role in ['vendor','video']:
        r=read(BASE/'T05'/(role+'_rig_checks.json'));usable[role]={'sheet_attempts':len(r['source_sheets']),'ten_part_complete_sheets':sum(v['count_complete'] for v in r['source_sheets'].values()),'complete_rate':r['raw_sheet_complete_rate'],'original_rig_C10':r['C10'],'current_actual_motion_frame_checks':motion[role]['frames'],'current_rescue_blob_checks':rescue[role]['blob_frame_tests'],'limits':'sheet completeness is not final production acceptance or animation production yield'}
    # User feature-only anchors and clip decisions must not become fabricated
    # full-asset style labels or 20-example calibration sets.
    cal=read(BASE/'T07/calibration.json');cal['A2h']='warning and seven full-shape design extents explicitly approved';cal['thresholds_frozen_as_calibrated']=False;cal['initial_thresholds_frozen']=True;cal['calibration_shortfall']='C04/C12/C14 have fewer than 20 full positive and negative samples per class; no numeric C14 scorer';cal['checker_version']='art-checks-0.3-initial-offline';write_json(BASE/'T07/calibration.json',cal)
    snapshot_names=['checks.py','artlib.py','paper_ops.py','ocr.cjs','preview.py','materials.py','puppet_motion.py','puppet_motion_v3.py','puppet_motion_v4.py','puppet_motion_v5.py','station_policy.py','tracker_screen.py','verify_frozen_geometry.py','t07_validate.py']
    freeze={'version':'art-checks-0.3-initial-offline','status':'initial_threshold_snapshot_not_calibrated','C04':{'delta_E':15,'coverage':.9},'C12':{'endpoint_difference':.02,'velocity_difference':.02},'C14':{'score':None,'status':'pending_no_calibrated_scorer'},'code_sha256':{n:sha(CODE/n) for n in snapshot_names},'extent_baseline_sha256':sha(GAME/'bible/geometry/alley_extent_v1/baseline.json'),'luminance_policy_sha256':sha(GAME/'bible/luminance_policy.json'),'scope':'reproducible offline evidence only; no engine or actual0B acceptance'};write_json(REV/'checker_freeze.json',freeze)
    cfg['checker_version']=freeze['version'];cfg['checker_freeze_file']=str(REV/'checker_freeze.json');(CODE/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
    write_json(REV/'readiness.json',{'stage':'A2_offline_pipeline_review','automatic_A2_acceptance':False,'T08_started':False,'geometry':{k:v for k,v in geometry.items() if k!='rows'},'negative_tests':{'verified':sum(r['verified'] for r in negative['rows']),'total':len(negative['rows'])},'jobs':jobs,'resident_sheet_yield':usable,'phase_0A_calls':total,'phase_0A_cap':120,'including_T01_calls':state['builtin_image_calls'],'external_API_calls':0,'cost':None,'cost_reason':'builtin tool does not disclose price; never infer zero cost or money from call count','approved_asset_yield':'not measurable from feature/clip approvals alone; do not extrapolate 100% complete sheets into production asset yield','remaining':['C04_C12_C14_calibration_shortfall','GPU_8bit_upload_color_space_LOD_drawcalls_peak','Godot_motion_collision_sampling','actual_0B_five_checks'],'review_decision_needed':'whether to allow T08 offline trial with these explicitly retained pending items; this does not approve formal production or actual0B'});print('A2 evidence consolidated; initial checker snapshot frozen without claiming calibration')
if __name__=='__main__':main()
