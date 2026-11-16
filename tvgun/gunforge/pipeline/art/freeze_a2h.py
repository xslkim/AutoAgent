"""Freeze explicitly accepted design extents; never rebuild them from revised art."""
import json,shutil,hashlib
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2i';FREEZE=GAME/'bible/geometry/alley_extent_v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    REV.mkdir(parents=True,exist_ok=True);FREEZE.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    feedback={'stage':'A2h','source':'explicit_user_chat','warning':'both_enemies_readable_approved','whole_layer_design_extents':'seven_shapes_and_cutouts_accepted_as_expected_design_baseline','notes':'两种墨怪的预警容易识别，可以；七张完整纸层的外形与镂空可作为预期设计范围基线。','technical_acceptance':False,'production_approved':False,'actual_0B':False}
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    proposal=json.loads((BASE/'T07/revisions/A2h/extent_proposals.json').read_text(encoding='utf-8'));rows=[]
    for r in proposal['rows']:
        assert sha(r['proposal_mask'])==r['proposal_sha256'] and sha(r['source_image'])==r['source_sha256'],'Accepted design input changed before freezing'
        dest=FREEZE/(r['layer']+'.png');shutil.copy2(r['proposal_mask'],dest);rows.append({'layer':r['layer'],'file':str(dest),'sha256':sha(dest),'accepted_color_reference':r['source_image'],'accepted_color_sha256':r['source_sha256']})
    write_json(FREEZE/'baseline.json',{'version':'g01-alley-extent-1','station_id':'g01_st_l1_01_alley','acceptance_source':str(REV/'user_feedback.yaml'),'basis':'explicit A2h acceptance of complete shapes as 2D design specification; not independent historic truth','rule':'immutable; asset changes compared to this baseline, mask changes require new design review','rows':rows})
    write_json(GAME/'bible/warning_contract.json',{'version':'g01-warning-1','visual_approval':'approved_A2h','applies_to':['g01_ink_crow','g01_ink_tadpole0'],'pulse_hz':1.5,'stamp_alpha_range':[.35,1.],'halo_color':[217,160,102],'halo_radius_content_px':[17,26],'halo_alpha_range':[70,190],'halo_hit_target':False,'primary_target_unchanged':True,'source':str(REV/'user_feedback.yaml'),'engine_validation':'pending'})
    p=BASE/'T07/review.yaml';r=yaml.safe_load(p.read_text(encoding='utf-8'));r['items'] += [{'id':'warning_v1','status':'approved','scope':'two enemies, minimum-size shown preview only','source':'explicit_A2h_user_chat'},{'id':'full_extent_design_v1','status':'approved','scope':'seven complete shapes as design baseline, not automatic engine or production acceptance','source':'explicit_A2h_user_chat'}];r.update(status='A2i_final_offline_evidence_in_progress',latest_feedback='revisions/A2i/user_feedback.yaml');p.write_text(yaml.safe_dump(r,allow_unicode=True,sort_keys=False),encoding='utf-8')
    p=BASE/'execution_state.json';s=json.loads(p.read_text(encoding='utf-8'));s.update(T07='A2i_final_offline_evidence_in_progress',next_task='frozen_geometry_motion_and_pipeline_readiness_audit');write_json(p,s);print('Accepted extents frozen with hashes; warning contract recorded')
if __name__=='__main__':main()
