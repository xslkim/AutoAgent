"""Record explicit A2 feedback without promoting visual decisions to technical passes."""
import json,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json

def main():
    base=GAME/'reports/art';revision=base/'T07/revisions/A2b';revision.mkdir(parents=True,exist_ok=True)
    if (revision/'user_feedback.yaml').exists():return
    archive=Path('D:/gunforge_cache/g01/T07/A2_v1');archive.mkdir(exist_ok=True)
    for role in ['vendor','video']:
        shutil.copy2(Path('D:/gunforge_cache/g01/T05')/role/'puppet.json',archive/(role+'_puppet.json'))
        shutil.copy2(base/'T05/gallery'/(role+'_actions.mp4'),archive/(role+'_actions.mp4'))
    for task in ['T05','T06','T07']:
        for name in ['report.md','manifest.json','review.yaml','checks.json']:
            p=base/task/name
            if p.exists():shutil.copy2(p,archive/(task+'_'+name))
    shutil.copy2(base/'T07/gallery/index.html',archive/'gallery_index.html')
    feedback={'stage':'A2','source':'explicit_user_chat','scene_and_lighting':'approved_visual_direction','character_art':'approved_visual_direction','character_animation':'revision_required_stiff_and_wrong_joint_motion','ink_material_and_reflections':'approved_visual_direction','enemy_hit_reaction':'user_requests_visible_animation_and_effects','notes':'场景、点灯、墨、反光都可以。人物美术也可以，但动画生硬、不符合关节运动。希望看到怪物被攻击动作和特效。','technical_acceptance':False,'actual_0B_approved':False}
    (revision/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review={'stage':'A2','status':'partial_visual_approval_animation_revision_required','source':'explicit_user_chat','items':[{'id':'scene','status':'approved','scope':'visual direction only'},{'id':'people','status':'rejected','scope':'animation only; character artwork approved'},{'id':'ink','status':'approved','scope':'material and gloss direction only'},{'id':'people_motion_v2','status':'pending'},{'id':'enemy_hit_fx','status':'pending'}],'technical_acceptance':False,'actual_0B_approved':False,'feedback_history':'revisions/A2b/user_feedback.yaml'}
    (base/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state=json.loads((base/'execution_state.json').read_text(encoding='utf-8'));state.update(T07='A2_partial_visual_approval_animation_revision_in_progress',next_task='fix_humanoid_motion_and_enemy_hit_feedback_then_A2b',approved_visual_directions=['scene','lighting','character_art','ink_material','ink_gloss']);write_json(base/'execution_state.json',state)
    with (GAME/'bible/style.md').open('a',encoding='utf-8') as f:f.write('\n## A2 视觉反馈\n\n场景、点灯、墨材质和反光、人物美术获得方向认可。人物动画因生硬和关节运动问题退回修正；补充墨怪被命中的动作与特效预览。以上不放行技术项、正式生产或真实0B。\n')

if __name__=='__main__':main()
