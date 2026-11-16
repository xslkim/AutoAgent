"""Record A2c decisions before changing animation, preserving accepted FX."""
import json,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2d';CACHE=Path('D:/gunforge_cache/g01')
def main():
    REV.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    archive=CACHE/'T07/A2c';archive.mkdir(parents=True,exist_ok=True)
    for task in ['T05','T06','T07']:shutil.copytree(BASE/task,archive/task,ignore=shutil.ignore_patterns('revisions'),dirs_exist_ok=True)
    shutil.copytree(Path(__file__).parent,archive/'code',ignore=shutil.ignore_patterns('.venv','__pycache__'),dirs_exist_ok=True)
    shutil.copy2('C:/Users/xsl/AppData/Local/Temp/codex-clipboard-f91a4bab-5a24-419d-bb90-16689569d0e7.png',REV/'user_elbow_reference.png')
    feedback={'stage':'A2c','source':'explicit_user_chat_and_screenshot','people_acting_v3':'revision_required_elbow_unnatural_when_arm_lowered','enemy_hit_fx_v3':'approved_clear_and_appropriate','notes':'手关节还需要修改，当手放下的时候，肘关节不自然。墨怪受击：清楚合适。补充意见：无。','retained_visual_approvals':['scene','lighting','character_design','ink_material','ink_gloss'],'expression_approval':'not separately stated; retain current work, no inferred approval','technical_acceptance':False,'actual_0B_approved':False}
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'))
    for x in review['items']:
        if x['id']=='people_acting_v3':x.update(status='rejected',scope='lowered elbow motion requires revision',source='explicit_A2c_user_feedback')
        if x['id']=='enemy_hit_fx_v3':x.update(status='approved',scope='visual hit feedback direction only',source='explicit_A2c_user_feedback')
    review.update(status='A2d_elbow_revision_in_progress',revision_report='revisions/A2d/report.md',latest_feedback='revisions/A2d/user_feedback.yaml')
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state=json.loads((BASE/'execution_state.json').read_text(encoding='utf-8'));state.update(T06='A2c_hit_feedback_visually_approved_engine_pending',T07='A2d_elbow_revision_in_progress',next_task='correct_lowered_elbow_then_A2d_review');state['approved_visual_directions']=list(dict.fromkeys(state['approved_visual_directions']+['enemy_hit_feedback_v3']));write_json(BASE/'execution_state.json',state)
    print('A2c feedback and screenshot archived; v3 FX approved visually only')
if __name__=='__main__':main()
