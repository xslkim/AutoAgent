"""Catch the submitted lowered-elbow regression and inspect the entire return path."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
import imageio_ffmpeg
from artlib import GAME,write_json
from puppet_motion_v4 import Civilian,CLIPS,point
from puppet_motion_v3 import Civilian as Previous
from preview import translation,transform

BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2d';CACHE=Path('D:/gunforge_cache/g01/T05');GALLERY=BASE/'T05/gallery'
def writer(path):
    w=imageio_ffmpeg.write_frames(str(path),(640,720),fps=24,codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,output_params=['-crf','20']);w.send(None);return w
def main():
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17);results={};board=Image.new('RGB',(1280,960),(42,48,62));bd=ImageDraw.Draw(board)
    for row,role in enumerate(['vendor','video']):
        folder=CACHE/role;model=json.loads((folder/'puppet.json').read_text(encoding='utf-8'));c=Civilian(model,folder);old=Previous(model,folder)
        def lowered_ok(controller,s):return 0<=controller.constraints(s)['elbow_flexion']['l']<=12+1e-6
        old_bend=old.constraints(old.sample('wave_for_help',3.5))['elbow_flexion']['l'];assert not lowered_ok(old,old.sample('wave_for_help',3.5));assert lowered_ok(c,c.sample('wave_for_help',4.5))
        frames=[];paths={};maxgap=0
        for rescue in [False,True]:
            path=[]
            for i in range(round(CLIPS['wave_for_help']*24)+1):
                t=i/24;s=c.sample('wave_for_help',t,rescue);r=c.constraints(s);world=c.world_matrices(s);wrist=point(world['forearm_l'],c.wrists['l']);path.append(wrist)
                slots={k:(im,m) for k,im,m,z in c.drawables(s)};hi,hm=slots['right_palm'];ai,am=slots['forearm_l'];cam=translation(48-wrist[0],48-wrist[1]);ha=np.asarray(transform(hi,cam@hm,(96,96)))[...,3]>=128;aa=np.asarray(transform(ai,cam@am,(96,96)))[...,3]>=128;yy,xx=np.ogrid[:96,:96];zone=(xx-48)**2+(yy-48)**2<=12**2;gap=float(ndi.distance_transform_edt(~aa)[ha&zone].min()) if (ha&zone).any() else 999;maxgap=max(maxgap,gap)
                assert r['elbow_target_error_deg']<1e-6 and r['min_transform_determinant']>0 and s['expression']=='distress'
                if 1.12<=t<=2.78:assert hm[0,0]>.8
                frames.append({'time':t,'rescue':rescue,'elbow_flexion_deg':r['elbow_flexion']['l'],'elbow_target_error_deg':r['elbow_target_error_deg'],'wrist':wrist.tolist(),'wrist_gap':gap,'wrist_attachment_error':r['wrist_attachment_error']})
            path=np.array(path);paths[str(rescue)]={'maximum_wrist_step_source_px':float(np.linalg.norm(np.diff(path,axis=0),axis=1).max())}
        lower=[r for r in frames if not r['rescue'] and 2.78<=r['time']<=4.5];monotonic=all(b['elbow_flexion_deg']<=a['elbow_flexion_deg']+1e-6 for a,b in zip(lower,lower[1:]));assert monotonic
        # Dedicated one-shot review: raised hand -> lowering -> rest. No loop jump.
        w=writer(GALLERY/(role+'_lowering_v4.mp4'))
        for i in range(54):
            t=min(4.5,2.60+i/24);s=c.sample('wave_for_help',t);im,_=c.render(s);bg=Image.new('RGBA',im.size,(102,111,122,255));bg.alpha_composite(im);d=ImageDraw.Draw(bg);ground=20+c.ground*.68;d.line((25,ground,615,ground),fill=(165,171,180),width=2);d.text((24,625),'放下手 / 肘部逐渐舒展并停稳',font=font,fill=(235,223,201));d.text((24,662),'单次播放；点「放下手」可重播',font=small,fill=(196,207,220));w.send(np.asarray(bg.convert('RGB')))
            if i==45:bg.save(GALLERY/(role+'_lowering_v4.png'))
        w.close()
        for j,t in enumerate([2.78,3.08,3.42,3.78,4.15]):
            s=c.sample('wave_for_help',t);im,_=c.render(s);bg=Image.new('RGBA',im.size,(102,111,122,255));bg.alpha_composite(im);board.paste(bg.resize((256,288)),(j*256,row*480));board.paste(bg.crop((90,130,460,420)).resize((256,200)),(j*256,row*480+280));bd.text((j*256+8,row*480+254),f'{t:.2f}s / 肘 {c.constraints(s)["elbow_flexion"]["l"]:.0f}°',font=small,fill=(255,230,190))
        result={'status':'pass' if maxgap<=2 else 'fail','previous_lowered_elbow_deg':old_bend,'previous_lowered_pose_rejected':True,'current_lowered_elbow_deg':c.constraints(c.sample('wave_for_help',4.5))['elbow_flexion']['l'],'project_relaxed_pose_limit_deg':[0,12],'not_a_universal_anatomical_limit':True,'lowering_monotonic_extension':monotonic,'wave_states_checked':len(frames),'max_wrist_gap_source_px':maxgap,'paths':paths,'visual_acceptance':'pending_A2d','frames':frames};results[role]=result
    board.save(GALLERY/'lowering_contact_v4.jpg',quality=93);write_json(REV/'lowering_checks.json',results);print(json.dumps({k:{x:v for x,v in r.items() if x!='frames'} for k,r in results.items()}))
if __name__=='__main__':main()
