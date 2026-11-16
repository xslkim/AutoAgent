"""Record A2d approval, then audit unresolved offline technical requirements."""
import json,hashlib,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
import yaml
from artlib import GAME,write_json,yprime
from puppet_motion_v4 import Civilian,CLIPS
from checks import run
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2e';CACHE=Path('D:/gunforge_cache/g01')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def record():
    REV.mkdir(parents=True,exist_ok=True)
    if (REV/'user_feedback.yaml').exists():return
    feedback={'stage':'A2d','source':'explicit_user_chat','lowered_elbow':'approved_natural','enemy_hit_feedback':'retain_A2c_approved','notes':'放下手的肘部：自然了，可以。继续开发，到下次检查点再叫我。','technical_acceptance':False,'actual_0B':False}
    (REV/'user_feedback.yaml').write_text(yaml.safe_dump(feedback,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review=yaml.safe_load((BASE/'T07/review.yaml').read_text(encoding='utf-8'))
    for i in review['items']:
        if i['id']=='people_elbow_v4':i.update(status='approved',source='explicit_A2d_user_chat',scope='lowered elbow visual direction only')
    review.update(status='visual_revisions_accepted_offline_technical_audit_in_progress',latest_feedback='revisions/A2e/user_feedback.yaml')
    (BASE/'T07/review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    state=read(BASE/'execution_state.json');state.update(T05='A2d_lowered_elbow_visually_approved_other_technical_pending',T07='A2e_offline_technical_audit_in_progress',next_task='resolve_remaining_offline_technical_checks');state['current_blockers']=[b for b in state['current_blockers'] if b!='A2d_lowered_elbow_visual_feedback'];write_json(BASE/'execution_state.json',state)
def loops():
    out=CACHE/'T07/A2e/loops';out.mkdir(parents=True,exist_ok=True);results={}
    for role in ['vendor','video']:
        folder=CACHE/'T05'/role;c=Civilian(read(folder/'puppet.json'),folder);results[role]={}
        for clip,dur in CLIPS.items():
            if clip=='rescued_bounce':results[role][clip]={'status':'na','reason':'one-shot rescue state transition'};continue
            paths=[]
            for label,t in [('first',0),('second',1/24),('penultimate',dur-1/24),('last',dur)]:
                im,_=c.render(c.sample(clip,t));p=out/(role+'_'+clip+'_'+label+'.png');im.save(p);paths.append(str(p))
            results[role][clip]=run('C12',{'frames':paths,'pixel_threshold':.02,'velocity_threshold':.02})
    write_json(REV/'loop_checks.json',results)
def readability():
    folder=CACHE/'T06/crow';body=Image.open(folder/'body_full.png').convert('RGBA');src=np.array(body);ys,xs=np.nonzero(src[...,3]>=128);scale=200/max(xs.max()-xs.min()+1,ys.max()-ys.min()+1);im=body.resize((round(1024*scale),round(1024*scale)),Image.Resampling.LANCZOS);a=np.array(im);mask=a[...,3]>=128;ink=yprime(a)
    # Test every declared candidate as a full target footprint, not a centre pixel.
    rows=[];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    for state in ['unlit','lit']:
        bg=Image.open(BASE/'T04/gallery'/('station_'+state+'.png')).convert('RGBA');Y=yprime(np.array(bg));overlay=bg.copy();d=ImageDraw.Draw(overlay)
        for y in [210,350,490,630]:
            for x in [420,650,880,1110,1340]:
                left=round(x-im.width/2);top=round(y-im.height/2);patch=Y[top:top+im.height,left:left+im.width];contrast=float(np.median(np.abs(ink[mask]-patch[mask])));back=float(np.median(patch[mask]));ok=contrast>=.2 and back>=.25
                rows.append({'state':state,'center':[x,y],'crow_extent_px':200,'median_absolute_contrast':contrast,'median_background_Yprime':back,'numeric_normal_pass':ok,'thumbnail_recognition':'pending'});color=(100,220,160) if ok else (235,130,100);d.rectangle((left,top,left+im.width,top+im.height),outline=color,width=3);d.text((left,top),f'{contrast:.2f}',font=font,fill=color)
        overlay.save(REV/(state+'_readability_slots.png'))
        thumb=bg.copy();thumb.alpha_composite(im,(round(880-im.width/2),round(490-im.height/2)));thumb.resize((222,117),Image.Resampling.LANCZOS).save(REV/(state+'_thumbnail.png'))
    write_json(REV/'readability_checks.json',{'scope':'200px crow, 20 candidate positions per lighting state, target-alpha median; no waiver of C03 or visual recognition','normal_slots':rows,'passed':sum(r['numeric_normal_pass'] for r in rows),'total':len(rows)})
def hidden_geometry():
    folder=CACHE/'T04/station';station=read(folder/'station.json');out=[]
    for l in station['layers']:
        if 'extent' not in l:continue
        alpha=np.array(Image.open(folder/'layers'/(l['id']+'_full.png')).convert('RGBA'))[...,3]>=128;extent=np.array(Image.open(folder/l['extent']).convert('L'))>=128
        out.append({'layer':l['id'],'extent_equals_actual_alpha':bool(np.array_equal(alpha,extent)),'certification':'pending_independent_intended_geometry','reason':'Expected extent duplicates current visible alpha; holes already present in both cannot be discovered by this comparison'})
    write_json(REV/'hidden_geometry_audit.json',{'status':'pending','layers':out,'next_requirement':'Independent intended silhouette/whitebox annotation, then compare moving occlusion against that mask; do not certify current-alpha self-comparison'})
def main():
    record();loops();readability();hidden_geometry();print('A2d approval recorded; loop, readability and hidden-geometry audits exported')
if __name__=='__main__':main()
