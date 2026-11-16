"""Record the occlusion revision request and publish research, without art approval."""
import json,hashlib,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2j';CODE=Path(__file__).parent;DOCS=GAME.parents[2]/'docs/art'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    if (REV.parent/'A2k/checks.json').exists():
        from publish_a2k import main as publish_current
        return publish_current()
    REV.mkdir(parents=True,exist_ok=True)
    feedback=REV/'user_feedback.yaml'
    if not feedback.exists():feedback.write_text(yaml.safe_dump({'stage':'A2i_followup_character_occlusion','source':'explicit_user_chat','quote':'人物美术的，各种部件，前后的遮挡关系还是有问题。 你在仔细调研一下，给出一个正确稳定的规则。','request':'research_stable_character_occlusion_rules','current_character_occlusion':'requires_revision','retained':'previous approved visual directions and scoped decisions','technical_acceptance':False,'T08_authorized':False,'production_approved':False,'actual_0B':False},allow_unicode=True,sort_keys=False),encoding='utf-8')
    audit=read(REV/'current_occlusion_audit.json');rules=DOCS/'CHARACTER_OCCLUSION_RULES_A2j.md';contract=DOCS/'CHARACTER_OCCLUSION_CONTRACT_A2j.yaml'
    spec=yaml.safe_load(contract.read_text(encoding='utf-8'));assert spec['status']=='specification_only_not_runtime_enabled' and not spec['acceptance']['implemented'] and not spec['characters']
    gallery=BASE/'T07/gallery';old=BASE/'T07/revisions/A2i/review_page.html'
    if not old.exists() and 'PAPER LANTERN CITY / A2i' in (gallery/'index.html').read_text(encoding='utf-8'):shutil.copy2(gallery/'index.html',old)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>纸灯城 A2j / 人物遮挡规则</title><style>body{background:#141827;color:#eee6d6;font:17px/1.8 system-ui;margin:0}main{max-width:900px;margin:auto;padding:30px 22px}h1{font-size:30px}section{background:#242a3c;border-radius:12px;padding:22px;margin:22px 0}a{color:#a9d4df}.status{background:#4b3631;padding:16px;border-radius:8px}.muted{color:#bdc6d3}</style><main><p>PAPER LANTERN CITY / A2j</p><h1>人物遮挡：规则已整理，仍需返修</h1><div class="status">已记录你的意见。A2i 的“继续 T08”阶段选择暂停；本页无需填写反馈，也不要求再次确认已认可的美术方向。</div><section><h2>查到的当前问题</h2><p>两条上臂固定在躯干后，两条前臂固定在躯干前，没有按姿态编排前后；袖口、手、关节装饰和道具也缺少局部遮挡约定。骨骼连接正确并不能证明遮挡正确。</p><h2>后续执行规则</h2><ol><li>骨骼跟随与绘制槽分开，十个运动部件可以对应更多视觉槽。</li><li>肩根、颈根、袖口、衣摆分别控制局部覆盖，不用一张完整大图压住所有部件。</li><li>抓握按“后掌 → 道具 → 前指”安排；原手、鞋、铜钉不能重复画出。</li><li>按姿态确定前后，只在编排好的位置离散换层；跳转和循环必须得到一致结果。</li><li>普通画面、附墨画面及可见命中区消费同一份最终绘制清单，遮住的墨不能继续算可见命中区。</li></ol><p><a href="/report.md" target="_blank" rel="noopener">阅读完整规则、调研来源与当前代码审计</a></p></section><section><h2>本轮完成范围</h2><p>已调研 Spine、Godot 与 Toon Boom 官方资料，保存规则文档、未启用的契约模板及当前绘制顺序审计。本轮尚未重新制作人物动画。</p><p class="muted">T07 人物遮挡待修，T08 未开始。已确认的造型、肘部、糖葫芦、场景、灯光与墨怪方向沿用；修正后复核受影响项。标定、GPU、引擎和真实追踪待办保留；批量仍等真实 0B 五项验收。</p></section></main></html>'''
    (gallery/'index.html').write_text(page,encoding='utf-8')
    report=rules.read_text(encoding='utf-8')+'\n\n## 本轮执行归档\n\n当前 v5 每角色检查了普通/附墨共 1,128 个时间采样，每角色仅有两种绘制清单（求助增加掌附件形成差异），各动作内部未编排前后变化。该统计只描述实现，不证明每一帧应当换层。逐项数据及源文件哈希在 current_occlusion_audit.json；用户原话在 user_feedback.yaml。\n\n契约模板未启用、角色基线刻意留空，避免用未标注的前后关系直接驱动动画。此处保存的是实施依据，后续必须按规则拆片/标注、改渲染路径并产出新样片。内置出图本轮 0 次，0A 保持 98/120，含 T01 共 101 次，费用未知。\n'
    if (REV/'verification.md').exists():report+='\n'+(REV/'verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    p=BASE/'T07/review.yaml';review=yaml.safe_load(p.read_text(encoding='utf-8'))
    if not any(i['id']=='character_occlusion_v5' for i in review['items']):review['items'].append({'id':'character_occlusion_v5','status':'rejected','scope':'body part front/back occlusion; visual design and prior scoped approvals retained','source':'explicit_A2i_followup_user_chat'})
    review.update(status='A2j_character_occlusion_revision_required',revision_report='revisions/A2j/report.md',latest_feedback='revisions/A2j/user_feedback.yaml',technical_acceptance=False,T08_started=False);p.write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state=read(BASE/'execution_state.json');state.update(T05='character_occlusion_v5_requires_revision_prior_scoped_approvals_retained',T07='A2j_character_occlusion_revision_required',T08='blocked_until_character_occlusion_fix_and_A2_decision',next_task='implement_character_occlusion_rules_and_render_review',current_blockers=['character_occlusion_revision','C04_C12_C14_calibration_shortfall','GPU_engine_validation','actual_0B']);write_json(BASE/'execution_state.json',state)
    cfg=yaml.safe_load((CODE/'config.yaml').read_text(encoding='utf-8'));checks={'revision':'A2j','checker_version':cfg['checker_version'],'status':'research_rules_complete_implementation_pending','rules':str(rules),'contract':str(contract),'current_v5_audit':audit,'technical_acceptance':False,'T08_started':False,'production_approved':False,'actual_0B':False};write_json(REV/'checks.json',checks);write_json(BASE/'T07/checks.json',checks)
    files=[p for p in REV.iterdir() if p.is_file() and p.name!='manifest.json']+[rules,contract,gallery/'index.html',CODE/'audit_character_occlusion.py',CODE/'publish_a2j.py'];manifest={'revision':'A2j','checker_version':cfg['checker_version'],'rules_version':spec['version'],'renderer_changed':False,'new_image_calls':0,'production_approved':False,'actual_0B':False,'outputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]};write_json(REV/'manifest.json',manifest);write_json(BASE/'T07/manifest.json',manifest);print('A2j research published; occlusion remains revision-required, T08 unstarted')
if __name__=='__main__':main()
