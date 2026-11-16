"""Integrated offline reference: protected hostage, disjoint enemy slots and camera/light."""
import json,math,itertools,copy
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import imageio_ffmpeg
from artlib import GAME,write_json,yprime
from preview import render
from puppet_motion_v4 import Civilian
from materials import hardened_eyes
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2f';CACHE=Path('D:/gunforge_cache/g01')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    f=CACHE/'T06/crow';model=read(f/'enemy.json');body=Image.open(f/'body_full.png').convert('RGBA');a=np.array(body);ys,xs=np.nonzero(a[...,3]>=128);scale=200/max(np.ptp(xs)+1,np.ptp(ys)+1);sz=round(1024*scale);body=body.resize((sz,sz),Image.Resampling.LANCZOS);normal=Image.open(f/'core_full.png').convert('RGBA').resize(body.size,Image.Resampling.LANCZOS);eyes=hardened_eyes(Image.open(f/'core_hardened_full.png').convert('RGBA'),model).resize(body.size,Image.Resampling.LANCZOS);mask=np.array(body)[...,3]>=128;Y=yprime(np.array(body));joint=read(REV/'joint_slot_checks.json');choices=[s for s in joint['slots'] if 'vendor' in s['allowed_with_roles'] and s['edge_hud_pass']];pairs=[]
    for p,q in itertools.combinations(choices,2):
        ax,ay=p['center'];bx,by=q['center'];overlap=max(0,sz-abs(ax-bx))*max(0,sz-abs(ay-by));pairs.append({'centers':[p['center'],q['center']],'conservative_texture_rect_overlap_px':overlap,'simultaneous_allowed':overlap==0})
    selected=next(p['centers'] for p in pairs if p['simultaneous_allowed']);write_json(REV/'slot_schedule.json',{'candidates':pairs,'preview_selected_centers':selected,'forbidden_slot_with_hostage':[650,350],'policy':'mutually overlapping slots never scheduled together; fixed 200px enemy size; engine enforcement pending'})
    station=read(CACHE/'T04/station/station.json');base=render(station,CACHE/'T04/station');test=copy.deepcopy(station);test['preview_enemies']=[{'metadata':str(f/'enemy.json'),'folder':str(f),'position':[-5000,-5000],'scale':scale,'hardened':True}];control=render(test,CACHE/'T04/station');assert np.array_equal(np.array(base),np.array(control)),'Offscreen enemy must not change content crop origin'
    original=Image.open(f/'core_hardened_full.png').convert('RGBA');assert np.array_equal(np.array(original)[...,3],np.array(hardened_eyes(original,model))[...,3])
    folder=CACHE/'T05/vendor';c=Civilian(read(folder/'puppet.json'),folder);blob=Image.open(CACHE/'T05/ink_blobs/blob_00.png').convert('RGBA');font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22);w=imageio_ffmpeg.write_frames(str(REV/'integrated_preview.mp4'),(888,468),fps=15,codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,output_params=['-crf','20']);w.send(None);rows=[];thumb=Image.new('RGB',(888,468),(35,40,55))
    for i in range(120):
        t=i/15;cam=np.array([68*math.sin(t*math.tau/8),34*math.sin(t*math.tau/4)]);lamp=float(t>=4);bg=render(station,CACHE/'T04/station',camera=cam,light_states={'streetlamp':lamp});bgY=yprime(np.array(bg));offset=np.array([760,500])-cam*.45-c.origin*(512/768);s=c.sample('struggle',t%3,rescue=True);actor,_,_,_=c.rescue_render(s,blob,160,512/768,(1776,936),offset);bg.alpha_composite(actor)
        for j,(x,y) in enumerate(selected):
            state='hardened' if (j==1 and 2<=t<6) else 'normal';p=(round(x-cam[0]*.45-sz/2),round(y-cam[1]*.45-sz/2));patch=bgY[p[1]:p[1]+sz,p[0]:p[0]+sz];contrast=float(np.median(abs(Y[mask]-patch[mask])));behind=float(np.median(patch[mask]));bg.alpha_composite(body,p);bg.alpha_composite(eyes if state=='hardened' else normal,p);rows.append({'frame':i,'enemy':j,'state':state,'camera':cam.tolist(),'lamp':lamp,'normal_body_contrast':contrast,'background_Yprime':behind,'numeric_background_pass':contrast>=.2 and behind>=.25})
        if i in [15,60]:
            bg.save(REV/('integrated_'+('unlit' if i==15 else 'lit')+'.png'));small=bg.resize((222,117),Image.Resampling.LANCZOS);small.save(REV/('integrated_thumbnail_'+str(i)+'.png'));thumb.paste(small.resize((444,234)),(0 if i==15 else 444,0))
        w.send(np.asarray(bg.resize((888,468),Image.Resampling.LANCZOS).convert('RGB')))
        if i%30==0:print('integrated '+str(i)+'/120',flush=True)
    w.close();write_json(REV/'integrated_checks.json',{'frames':120,'enemy_frame_checks':len(rows),'all_sampled_background_numeric_pass':all(r['numeric_background_pass'] for r in rows),'minimum_contrast':min(r['normal_body_contrast'] for r in rows),'minimum_background':min(r['background_Yprime'] for r in rows),'material_alpha_preserved':True,'offscreen_enemy_crop_origin_regression_rejected':True,'scope':'8s CPU reference, two fixed slots; actual engine, full trajectory and hardware pending','rows':rows});print('Integrated preview complete')
if __name__=='__main__':main()
