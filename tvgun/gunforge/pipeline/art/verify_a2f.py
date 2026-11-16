"""Regression checks for explicit policy scope and approved material invariants."""
import copy,json
from pathlib import Path
import numpy as np
from PIL import Image
from artlib import GAME,write_json
from materials import hardened_eyes
from station_policy import evaluate
from checks import run
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2f'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    policy=read(GAME/'bible/luminance_policy.json');frames=read(REV/'integrated_checks.json');old=read(BASE/'T04/additional_checks.json');near=[v['C03_band'] for v in old['C03_bands'].values() if v['band']=='near'];limits=[run('C03',{'file':str(REV/('integrated_'+s+'.png'))}) for s in ['unlit','lit']];result=evaluate(policy,policy['station_id'],near,limits,frames['rows']);assert result['status']=='pass'
    bad=copy.deepcopy(frames['rows']);bad[0]['normal_body_contrast']=.19;assert evaluate(policy,policy['station_id'],near,limits,bad)['status']=='fail'
    try:evaluate(policy,'different_station',near,limits,frames['rows']);raise AssertionError('Wrong station accepted')
    except ValueError:pass
    try:evaluate(policy,policy['station_id'],near,limits,[]);raise AssertionError('No evidence accepted')
    except ValueError:pass
    f=Path('D:/gunforge_cache/g01/T06/crow');model=read(f/'enemy.json');eye=Image.open(f/'core_hardened_full.png').convert('RGBA');assert np.array_equal(np.array(eye)[...,3],np.array(hardened_eyes(eye,model))[...,3]);foreign=copy.deepcopy(model);foreign['id']='g01_ink_tadpole';assert np.array_equal(np.array(eye),np.array(hardened_eyes(eye,foreign)))
    assert any(v['C03_band']['status']=='fail' for v in old['C03_bands'].values()),'Historical failures must stay'
    write_json(REV/'policy_checks.json',{'sampled_station_policy':result,'near_original_checks':near,'integrated_frame_C03':limits,'negatives':{'weak_contrast_rejected':True,'other_station_rejected':True,'missing_slot_evidence_rejected':True},'material':{'alpha_preserved':True,'other_enemy_unchanged':True},'historical_C03_failures_preserved':True,'checker_calibration':'unchanged_uncalibrated','actual_0B':False});print('Scoped policy and material regression checks passed')
if __name__=='__main__':main()
