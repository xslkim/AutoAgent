"""Record explicit A2f approvals before applying the civilian prop correction."""
import json,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2g';CACHE=Path('D:/gunforge_cache/g01')
def main():
    REV.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    archive=CACHE/'T07/A2f';archive.mkdir(parents=True,exist_ok=True)
    for role in ['vendor','video']:shutil.copy2(CACHE/'T05'/role/'puppet.json',archive/(role+'_puppet.json'))
    for name in ['report.md','review.yaml','checks.json','manifest.json']:shutil.copy2(BASE/'T07'/name,archive/name)
    shutil.copy2(BASE/'T07/gallery/index.html',archive/'index.html')
    for name in ['puppet_motion_v4.py','a2_composite.py','preview.py']:shutil.copy2(Path(__file__).with_name(name),archive/name)
    feedback={'stage':'A2f','date':'2026-11-05','source':'explicit_user_chat','integrated_readability':'approved_easy_to_distinguish','structural_regions':'approved_four_solid_regions_only','revision':'tanghulu_orientation_wrong','notes':'同屏对象与硬化态容易分清，可以继续；四块绿色结构区域应为连续纸面，标注可以；人物的糖葫芦方向不对。','technical_acceptance':False,'actual_0B':False,'production_approved':False}
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'));review['items'] += [{'id':'integrated_readability_A2f','status':'approved','scope':'two selected slots and shown states only','source':'explicit_A2f_user_chat'},{'id':'wall_regions_v1','status':'approved','scope':'four solid architectural regions only; full hidden geometry pending','source':'explicit_A2f_user_chat'}];review.update(status='A2g_tanghulu_correction_and_technical_followup',latest_feedback='revisions/A2g/user_feedback.yaml');(BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    p=BASE/'T07/revisions/A2f/structural_geometry_checks.json';m=json.loads(p.read_text(encoding='utf-8'));m['semantic_review']='four regions approved by explicit A2f feedback';m['approval_source']=str(REV/'user_feedback.yaml');write_json(REV/'approved_structural_regions.json',m)
    state=json.loads((BASE/'execution_state.json').read_text(encoding='utf-8'));state.update(T07='A2g_tanghulu_and_technical_followup',next_task='correct_prop_grip_and_validate_then_remaining_technical');write_json(BASE/'execution_state.json',state)
    print('A2f approvals recorded; tanghulu correction in progress')
if __name__=='__main__':main()
