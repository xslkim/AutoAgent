"""Publish only the current arm/grip staging prototype, not whole-rig acceptance."""
import json,hashlib,shutil
from pathlib import Path
import yaml
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2k';GALLERY=BASE/'T07/gallery'
def main():
    state=json.loads((BASE/'execution_state.json').read_text(encoding='utf-8'))
    if state.get('resumed',{}).get('character_commit'):
        raise SystemExit('A2k is archived; current T07 evidence uses the art2d character exports.')
    checks=json.loads((REV/'checks.json').read_text(encoding='utf-8'))
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump({'source':'explicit_user_chat','quote':'继续吧','scope':'implement A2j occlusion rules; not visual approval','technical_acceptance':False,'T08_authorized':False,'actual_0B':False},allow_unicode=True,sort_keys=False),encoding='utf-8')
    for role,r in checks.items():
        assert r['frames']==564 and r['rescue_frames']==72
        for suffix in ['occlusion_v6.mp4','rescue_v6.mp4','contact.jpg']:shutil.copy2(REV/(role+'_'+suffix),GALLERY/('a2k_'+role+'_'+suffix))
    page=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>纸灯城 A2k / 上臂与握持遮挡试稿</title><style>body{margin:0;background:#141827;color:#eee6d6;font:17px/1.8 system-ui}main{max-width:1000px;margin:auto;padding:25px 20px}section{background:#242a3c;padding:20px;margin:20px 0;border-radius:12px}video,img{width:100%}button,textarea{font:inherit}label{display:block;padding:12px;background:#30384e;margin:10px 0}textarea{width:100%;box-sizing:border-box;min-height:90px}button{padding:10px 18px;margin:12px 0}a{color:#a9d4df}[hidden]{display:none!important}</style><main><p>PAPER LANTERN CITY / A2k</p><h1>上臂与握持：第一版遮挡试稿</h1><p>这次只复核上臂是否还被身体错误盖住，以及手与道具的前后关系。原肘部曲线、糖葫芦握点和朝向沿用。</p><section><h2>卖糖葫芦居民</h2><video controls muted loop playsinline src="a2k_vendor_occlusion_v6.mp4" poster="a2k_vendor_contact.jpg"></video><details><summary>关键姿势</summary><img src="a2k_vendor_contact.jpg"></details><h2>录像厅老板</h2><video controls muted loop playsinline src="a2k_video_occlusion_v6.mp4" poster="a2k_video_contact.jpg"></video><details><summary>附墨状态：同一套遮挡合成</summary><video controls muted loop playsinline src="a2k_vendor_rescue_v6.mp4"></video><video controls muted loop playsinline src="a2k_video_rescue_v6.mp4"></video></details></section><section><h2>尚未完成</h2><p>这是局部试稿：肩部原图仍含固定轮廓；肩根/领口的完整局部遮罩、脚踝像素归属、近远侧标注、跨前后/遮脸姿态及过渡还需继续处理。当前动作保持侧向身前编排，没有宣称已支持所有姿态或完整落实全部规则。</p><p>两个角色共 1,128 个动作帧通过本轮槽位顺序与连接检查；144 个救援帧的纸身与普通路径逐像素相同。数值检查不替代人看遮挡是否自然。</p><a href="/report.md" target="_blank">本轮实现与限制</a></section><section><h2>上臂与握持的方向</h2><label><input type="radio" name="d" value="这版上臂与握持方向可以，继续完成剩余遮挡修正"> 方向改善，可以继续细化</label><label><input type="radio" name="d" value="上臂或握持仍有问题，请按补充意见修正"> 仍有问题</label><textarea id="notes" placeholder="有问题时写角色、动作和部位即可"></textarea><button onclick="prepare()">整理反馈</button><p id="err"></p><textarea id="out" readonly hidden></textarea><button id="copy" hidden onclick="copy()">复制反馈</button></section><p>本次不代表人物全部遮挡、A2技术项、正式生产或真实光枪通过。T08未开始；批量仍等真实0B五项验收。</p></main><script>function prepare(){const d=document.querySelector('input:checked');if(!d){document.getElementById('err').textContent='请先选择方向。';return;}document.getElementById('err').textContent='';const out=document.getElementById('out');out.value=['纸灯城 A2k / 上臂与握持遮挡试稿','人物遮挡：'+d.value,'补充意见：'+(document.getElementById('notes').value.trim()||'无'),'已确认的其他美术方向继续沿用。','请继续遮挡修正；人物整体遮挡、A2技术项、引擎与真实追踪待办保留。','本次不代表正式生产或真实光枪通过；批量仍等真实0B五项验收。'].join('\n');out.hidden=false;document.getElementById('copy').hidden=false;}async function copy(){await navigator.clipboard.writeText(document.getElementById('out').value);document.getElementById('err').textContent='已复制，请发回聊天。';}document.querySelectorAll('input,textarea:not([readonly])').forEach(e=>e.addEventListener('input',()=>{document.getElementById('out').hidden=true;document.getElementById('copy').hidden=true}));</script></html>'''
    (GALLERY/'index.html').write_text(page,encoding='utf-8')
    report='''# A2k：上臂与握持遮挡试稿

用户“继续吧”授权按 A2j 规则实施，不是批准 A2 或 T08。本轮新建 puppet_motion_v6.py，不覆盖旧 PNG、骨架或已确认运动曲线。采用命名视觉槽和完整顺序；上臂不再统一压在整张躯干下面，头位于前景手臂下。当前八个动作均编排为侧向身前，不根据角度或 Y 坐标自动换层；不支持未编排的背后/遮脸跨越。

持物前臂按局部标注的区域分为后片和前手指，道具放在中间；这是现有绘图的局部近似，并非完整新手势库。最终渲染对原前臂采样一次，再将采样像素分给前后项，避免分开过滤造成重复透明边缘。八组变换重组误差为 0（grip_reconstruction.json）。糖葫芦变换、握点和朝向沿用 v5。未新增图像调用。

普通和救援共用 layers()，墨紧跟衣服表面绘制；按其后所有实际 alpha 扣除遮住的墨。144 个附墨帧中，不含墨的纸身与普通路径逐像素相同，可见墨不超过原裁切墨。最小半径按 checks.json 如实记录，不因路径一致就自动登记救援尺寸达标。两个角色 1,128 个普通动作帧验证连接、正行列式、唯一槽位及当前 profile 的局部顺序。

## 仍需完成，未算通过

肩部原图烘焙的固定轮廓、完整肩根/领口 mask、脚踝重叠像素所有权、按角色标注的近远侧、跨前后与遮脸姿态、状态过渡和负例覆盖仍未完成；当前只解决了顺序和握持的第一步。原始图源未改，当前视频不是新绘制分件已经齐备的证明。新增槽的实际成本、所有附墨形状/动作、同屏标注、循环、GPU、引擎及追踪还需复核。原 C04/C12/C14 标定缺口保留，T08 未开始；批量仍等真实 0B 五项验收。

本次只请看上臂和握持试稿是否朝正确方向改进，不再请求 A2 阶段放行。0A仍98/120、含T01累计101次，费用未知。
'''
    report+='\n实际渲染器的遮挡反例：注入不透明前层后，原本可见的墨采样点被扣为 0，两个角色均通过（occluded_target_negative.json）。槽位随机跳转测试见 seek_checks.json；不是完整状态过渡通过。\n'
    if (REV/'browser_verification.md').exists():report+='\n'+(REV/'browser_verification.md').read_text(encoding='utf-8')
    for p in [REV/'report.md',BASE/'T07/report.md']:p.write_text(report,encoding='utf-8')
    write_json(BASE/'T07/checks.json',{'revision':'A2k','scope':'arm and grip first prototype only','evidence':'revisions/A2k/checks.json','technical_acceptance':False,'T08_started':False,'actual_0B':False})
    p=BASE/'T07/review.yaml';review=yaml.safe_load(p.read_text(encoding='utf-8'));review.update(status='A2k_arm_grip_prototype_review_pending',revision_report='revisions/A2k/report.md',technical_acceptance=False,T08_started=False);p.write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state.update(T07='A2k_arm_grip_prototype_review_pending',next_task='complete_character_occlusion_masks_and_validation',T08='blocked_until_occlusion_fix_and_A2_decision');write_json(BASE/'execution_state.json',state)
    files=[p for p in REV.iterdir() if p.is_file() and p.name!='manifest.json']+[GALLERY/'index.html',Path(__file__).with_name('puppet_motion_v6.py')];write_json(REV/'manifest.json',{'revision':'A2k','new_image_calls':0,'production_approved':False,'actual_0B':False,'outputs':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]});print('Scoped A2k prototype published')
    shutil.copy2(REV/'manifest.json',BASE/'T07/manifest.json')
if __name__=='__main__':main()
