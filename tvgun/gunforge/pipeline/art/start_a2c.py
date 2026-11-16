"""Record explicit A2b rejection and reserve scoped A2c attachment artwork."""
import json,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
from phase0a_jobs import add

BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2c';CACHE=Path('D:/gunforge_cache/g01')
def main():
    REV.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    archive=CACHE/'T07/A2b';archive.mkdir(parents=True,exist_ok=True)
    for task in ['T05','T06','T07']:
        shutil.copytree(BASE/task,archive/task,ignore=shutil.ignore_patterns('revisions'),dirs_exist_ok=True)
    shutil.copytree(Path(__file__).parent,archive/'code',ignore=shutil.ignore_patterns('.venv','__pycache__'),dirs_exist_ok=True)
    for role in ['vendor','video']:shutil.copy2(CACHE/'T05'/role/'puppet.json',archive/(role+'_puppet.json'))
    feedback={'stage':'A2b','source':'explicit_user_chat','character_animation':'revision_required_wrong_hand_mirroring','enemy_hit_feedback':'too_weak','expression':'help_and_distress_must_not_smile','notes':'人物动作还是不行，比如招手的时候，手左右镜像都反了。仔细调研业界2D人物动画方案和规则；加表情，求助不能笑呵呵。墨怪受击偏弱。','retained_visual_approvals':['scene','lighting','character_design','ink_material','ink_gloss'],'technical_acceptance':False,'actual_0B_approved':False}
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'))
    for item in review['items']:
        if item['id'] in ['people_motion_v2','enemy_hit_fx']:item.update(status='rejected',source='explicit_A2b_user_feedback')
    review.update(status='A2b_rejected_A2c_in_progress',revision_report='revisions/A2c/report.md',latest_feedback='revisions/A2c/user_feedback.yaml')
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state=json.loads((BASE/'execution_state.json').read_text(encoding='utf-8'));state.update(T07='A2c_animation_expression_hit_revision_in_progress',next_task='A2c_correct_laterality_expression_and_hit_feedback');write_json(BASE/'execution_state.json',state)
    jobs=[]
    for role in ['vendor','video']:
        jobs.append({'id':role+'_distress_head_v3','asset_key':role+'_distress_head','references':[str(CACHE/'T05'/role/'parts/head.png')],'prompt':'''Use case: identity-preserve. Edit target is the supplied isolated paper-cut puppet head. Produce ONE transparent isolated head, same character, same 3/4 camera facing screen right, exact same hair/hat, head silhouette, skin color, paper texture, neck and circular copper neck pivot. Only change facial acting: visibly WORRIED and CALLING FOR HELP, inner eyebrows raised in anxiety, eyes open looking for rescue, small open rounded calling mouth with corners not smiling, no cheerful crescent eyes. Restrained appealing theatrical paper-cut acting, not exaggerated horror. Preserve original likeness and proportions and outer boundary as closely as possible. No extra parts, no body, no text, no shadows/background. Leave generous transparent margin. This is an alternate face attachment for a game NPC in distress, never a monster.'''})
        jobs.append({'id':role+'_right_palm_v3','asset_key':role+'_right_palm','references':[str(CACHE/'T05'/role/'parts/forearm_l.png')],'prompt':'''Use case: precise-object-edit. Supporting reference shows the skin color and paper texture of this puppet. Generate ONLY ONE isolated anatomical RIGHT HAND, OPEN PALM FACING THE VIEWER, wrist at bottom, four fingers pointing up, THUMB ON THE IMAGE RIGHT SIDE. This hand belongs to a front-facing person's arm on screen LEFT. Correct right-hand palm anatomy is essential: thumb extends screen RIGHT, little finger is far screen LEFT, index finger is next to the thumb, middle finger tallest. Five digits total, slightly separated relaxed curved fingertips, slim consistent paper-cut fingers. Match reference warm peach skin and tactile paper grain exactly, simple drawn palm creases; no fingernails on palm. Include a short straight bare wrist tab for attachment at bottom. No sleeve, forearm, elbow, joint metal, text, extra hands or background. Transparent background. Do NOT copy the handedness of the relaxed reference hand; this is a new correctly sided raised palm attachment.'''})
    add('T05',jobs)
    print('A2b rejection archived; four scoped attachment jobs queued')

if __name__=='__main__':main()
