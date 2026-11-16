"""Joint minimum-size enemy/hostage protection over every attached-eligible frame."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
from artlib import GAME,write_json,effective_radius
from puppet_motion_v4 import Civilian,CLIPS
from materials import hardened_eyes
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2f';CACHE=Path('D:/gunforge_cache/g01')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    slots=[s for s in read(BASE/'T07/revisions/A2e/slot_motion_checks.json')['slots'] if s['numeric_pass_all_states']];f=CACHE/'T06/crow';model=read(f/'enemy.json');body=Image.open(f/'body_full.png').convert('RGBA');a=np.array(body);ys,xs=np.nonzero(a[...,3]>=128);sc=200/max(np.ptp(xs)+1,np.ptp(ys)+1);body=body.resize((round(1024*sc),)*2,Image.Resampling.LANCZOS);mask=np.array(body)[...,3]>=128;core=Image.open(f/'core_full.png').convert('RGBA').resize(body.size,Image.Resampling.LANCZOS);weak=np.array(core)[...,3]>=128
    # Test coordinates are shared .45-parallax space: relative protection is invariant
    # to common camera/breath translation; near-layer clearance checked separately.
    region=[400,140];size=(800,700);rows=[];frames=0;approved=[]
    for role,height in [('vendor',512),('video',300)]:
        folder=CACHE/'T05'/role;c=Civilian(read(folder/'puppet.json'),folder);scale=height/768;offset=np.array([760,500])-region-c.origin*scale;maxima={tuple(s['center']):{'max_protected_overlap':0,'max_weak_protected_overlap':0,'failed_frames':0,'samples':0} for s in slots}
        for clip in ['idle','peek','startle','wave_for_help','struggle']:
            for i in range(round(CLIPS[clip]*24)):
                s=c.sample(clip,i/24,rescue=True);paper,_=c.render(s,size=size,scale=scale,offset=offset);protected=np.array(paper)[...,3]>=128;frames+=1
                for slot in slots:
                    x,y=slot['center'];l=round(x-region[0]-body.width/2);t=round(y-region[1]-body.height/2);local=np.zeros(mask.shape,bool);sx=max(0,l);sy=max(0,t);ex=min(size[0],l+body.width);ey=min(size[1],t+body.height)
                    if ex>sx and ey>sy:local[sy-t:ey-t,sx-l:ex-l]=protected[sy:ey,sx:ex]
                    overlap=int((mask&local).sum());wo=int((weak&local).sum());r=maxima[(x,y)];r['samples']+=1;r['max_protected_overlap']=max(r['max_protected_overlap'],overlap);r['max_weak_protected_overlap']=max(r['max_weak_protected_overlap'],wo);r['failed_frames']+=overlap>0
                if i==0:print(role+' '+clip,flush=True)
        for pos,r in maxima.items():rows.append({'role':role,'enemy_center':list(pos),'human_origin':[760,500],**r,'simultaneous_allowed':r['max_protected_overlap']==0})
    # Conservative motion reservations include camera/breath and may be stricter than pixels.
    reservations=read(BASE/'T07/revisions/A2d/motion_reservations.json');hud=read(GAME/'assets/ui/hud_layout.json');from checks import overlap
    for slot in slots:
        x,y=slot['center'];box=[math.floor(x-body.width/2-30.6),math.floor(y-body.height/2-15.3),math.ceil(body.width+61.2),math.ceil(body.height+30.6)];in_bounds=box[0]>=60 and box[1]>=60 and box[0]+box[2]<=1716 and box[1]+box[3]<=876;hudclear=not any(overlap(box,v['rect']) for v in hud['reserved'].values() if v['when']=='playing');rs=[r for r in rows if r['enemy_center']==slot['center']];approved.append({'center':slot['center'],'motion_bbox':box,'edge_hud_pass':in_bounds and hudclear,'allowed_with_roles':[r['role'] for r in rs if r['simultaneous_allowed']],'min_contrast':slot['minimum_normal_contrast'],'effective_radius':effective_radius(mask)[0]})
    # Actual integrated CPU reference: NPC at approved origin; safe enemy slot, both states.
    bg=Image.open(BASE/'T04/gallery/station_unlit.png').convert('RGBA');folder=CACHE/'T05/vendor';c=Civilian(read(folder/'puppet.json'),folder);offset=np.array([760,500])-c.origin*(512/768);human,_=c.render(c.sample('wave_for_help',1.8,rescue=True),size=(1776,936),scale=512/768,offset=offset);bg.alpha_composite(human)
    for state in ['normal','hardened']:
        frame=bg.copy();eyes=hardened_eyes(Image.open(f/'core_hardened_full.png').convert('RGBA'),model).resize(body.size,Image.Resampling.LANCZOS);overlay=core if state=='normal' else eyes
        for slot in approved:
            if 'vendor' in slot['allowed_with_roles'] and slot['edge_hud_pass']:
                x,y=slot['center'];pos=(round(x-body.width/2),round(y-body.height/2));frame.alpha_composite(body,pos);frame.alpha_composite(overlay,pos)
        frame.save(REV/('joint_'+state+'.png'));frame.resize((222,117),Image.Resampling.LANCZOS).save(REV/('joint_'+state+'_thumbnail.png'))
    write_json(REV/'joint_slot_checks.json',{'scope':'360 actual frames per civilian; fixed 200px crow; invariant common .45 parallax; 4 prefiltered slots; no runtime certification','human_frames':frames,'joint_tests':sum(r['samples'] for r in rows),'rows':rows,'slots':approved,'hardened_material_version':model['hardened_eye_material']['version'],'alpha_preservation':bool(np.array_equal(np.array(eyes)[...,3],np.array(Image.open(f/'core_hardened_full.png').convert('RGBA').resize(body.size,Image.Resampling.LANCZOS))[...,3]))});print(json.dumps(approved))
if __name__=='__main__':main()
