"""Record A2g prop approval and freeze its accepted visual scope."""
import json
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h'
def main():
    REV.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump({'stage':'A2g','source':'explicit_user_chat','prop_direction':'approved','notes':'糖葫芦方向与握持可以；继续技术待办，到下个检查点再通知。','technical_acceptance':False,'production_approved':False,'actual_0B':False},allow_unicode=True,sort_keys=False),encoding='utf-8')
    p=BASE/'T07/review.yaml';review=yaml.safe_load(p.read_text(encoding='utf-8'));review['items'].append({'id':'tanghulu_grip_v5','status':'approved','scope':'direction and grip only','source':'explicit_A2g_user_feedback'});review.update(status='A2h_remaining_technical_in_progress',latest_feedback='revisions/A2h/user_feedback.yaml');p.write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    p=BASE/'execution_state.json';s=json.loads(p.read_text(encoding='utf-8'));s.update(T05='A2g_prop_direction_visually_approved_technical_pending',T07='A2h_remaining_technical_in_progress',next_task='texture_sampling_and_full_layer_review_preparation');s['current_blockers']=[v for v in s['current_blockers'] if v!='A2g_prop_direction_review'];write_json(p,s)
    p=GAME/'bible/animation_contract.json';s=json.loads(p.read_text(encoding='utf-8'));s['acceptance']='A2g_prop_direction_and_prior_visuals_approved_remaining_technical_pending';write_json(p,s)
    print('A2g approval recorded')
if __name__=='__main__':main()
