"""Export separated friendly clips and actual-frame kinematic evidence."""
import json,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import imageio_ffmpeg
from artlib import GAME,write_json
from puppet_motion import Civilian,CLIPS,NAMES,point

BASE=GAME/'reports/art';CACHE=Path('D:/gunforge_cache/g01');FPS=24;SIZE=(640,720)
def writer(path):
    w=imageio_ffmpeg.write_frames(str(path),SIZE,fps=FPS,codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,output_params=['-crf','21']);w.send(None);return w
def main():
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    gallery=BASE/'T05/gallery';results={}
    for role in ['vendor','video']:
        folder=CACHE/'T05'/role;model=json.loads((folder/'puppet.json').read_text(encoding='utf-8'));c=Civilian(model,folder);frames=[]
        overview=writer(gallery/(role+'_actions_v2.mp4'));contact=Image.new('RGB',(1280,1440),(102,111,122));diags=[]
        for ci,(clip,dur) in enumerate(CLIPS.items()):
            output=writer(gallery/(role+'_'+clip+'_v2.mp4'));count=round(dur*FPS)
            for i in range(count):
                sample=c.sample(clip,i/FPS);image,mats=c.render(sample);bg=Image.new('RGBA',SIZE,(102,111,122,255));d=ImageDraw.Draw(bg)
                ground=20+c.ground*.68;d.line((25,ground,615,ground),fill=(165,171,180),width=2)
                step=32*.68
                for j in range(-1,33):
                    xx=(j*step-sample['camera_x']*.68)%(32*step)-step;d.line((xx,ground+2,xx-7,ground+7),fill=(126,135,148),width=1)
                bg.alpha_composite(image);d=ImageDraw.Draw(bg);d.text((24,625),NAMES[clip],font=font,fill=(235,223,201));d.text((24,662),'人物仅为 NPC / 人质；不含攻击动作',font=small,fill=(196,207,220))
                raw=np.asarray(bg.convert('RGB'));output.send(raw);overview.send(raw)
                check=c.constraints(sample);check.update(clip=clip,frame=i,time=i/FPS);frames.append(check)
                if i==count//2:
                    bg.save(gallery/(role+'_'+clip+'_v2.png'))
                    thumb=bg.resize((320,360));contact.paste(thumb,((ci%4)*320,(ci//4)*720))
                    debug=bg.copy();dd=ImageDraw.Draw(debug)
                    for n in c.model['parts']:
                        p=point(mats[n['id']],n['pivot']);dd.ellipse((p[0]-4,p[1]-4,p[0]+4,p[1]+4),fill=(255,206,120))
                        if n['parent']:
                            par=c.nodes[n['parent']];q=point(mats[par['id']],par['pivot']);dd.line((*q,*p),fill=(112,230,220),width=2)
                    contact.paste(debug.resize((320,360)),((ci%4)*320,(ci//4)*720+360))
            output.close();print(role+' '+clip,flush=True)
        overview.close();contact.save(gallery/(role+'_motion_contact_v2.jpg'))
        # A separately staged hostage clip: protected hands stay outside the decal.
        output=writer(gallery/(role+'_hostage_v2.mp4'));height=512 if role=='vendor' else 300;sc=height/768
        blob=Image.open(CACHE/'T05/ink_blobs/blob_00.png').convert('RGBA');offset=[320-c.origin[0]*sc,590-c.ground*sc]
        for i in range(72):
            s=c.sample('struggle',i/FPS,rescue=True);image,_,_,_=c.rescue_render(s,blob,160 if role=='vendor' else 256,sc,SIZE,offset)
            bg=Image.new('RGBA',SIZE,(102,111,122,255));bg.alpha_composite(image);d=ImageDraw.Draw(bg);d.line((25,590,615,590),fill=(165,171,180),width=2);d.text((24,625),'附墨人质 / 双手避开胸腹',font=font,fill=(235,223,201));d.text((24,662),'可见墨和命中区共用裁切；纸身始终受保护',font=small,fill=(196,207,220));output.send(np.asarray(bg.convert('RGB')))
            if i==36:bg.save(gallery/(role+'_hostage_v2.png'))
        output.close();shutil.copy2(gallery/(role+'_actions_v2.mp4'),gallery/(role+'_actions.mp4'))
        maximum=max(f['max_attachment_error'] for f in frames);ankle=max(x for f in frames for x in f['ankle_target_errors'].values());knees=[x for f in frames for x in f['knee_flexion'].values()];elbows=[x for f in frames for x in f['elbow_flexion'].values()]
        # A planted foot is tested in world space, not against camera-follow video coordinates.
        drift=[]
        for clip in CLIPS:
            previous={}
            for i in range(round(CLIPS[clip]*FPS)):
                s=c.sample(clip,i/FPS);m=c.world_matrices(s)
                for side in ['l','r']:
                    p=point(m['shin_'+side],c.legs[side]['ankle'])
                    if s['planted'][side] and side in previous:drift.append(float(np.linalg.norm(p-previous[side])))
                    if s['planted'][side]:previous[side]=p
                    else:previous.pop(side,None)
        passed=maximum<1e-6 and ankle<1e-6 and max(drift)<1e-6 and min(knees)>=0 and max(knees)<=95 and min(elbows)>=0 and max(elbows)<=125 and not any(f['unreachable'] for f in frames)
        record={'status':'pass' if passed else 'fail','scope':'all exported frames at 24fps; numeric rig motion only, human animation review pending','frames':len(frames),'max_attachment_error_source_px':maximum,'max_ankle_target_error_source_px':ankle,'max_planted_foot_frame_drift_source_px':max(drift),'knee_flexion_range':list([min(knees),max(knees)]),'elbow_flexion_range':[min(elbows),max(elbows)],'joint_seam_visual_review':'pending on rendered source pixels and ankle overlap; kinematic attachment is not a visual seam certificate','details':frames}
        write_json(BASE/'T05'/(role+'_motion_checks_v2.json'),record)
        model['animation_v2']=c.metadata();model['animation_v2'].update(review='pending_A2b',paper_alpha='opaque interior normalization at render time; source PNG untouched',rescue_render='separate arm clearance posture; visible decal and primary target clipped to torso inset of 7 content pixels')
        write_json(folder/'puppet.json',model)
        results[role]={k:v for k,v in record.items() if k!='details'}
        if not passed:raise RuntimeError('Kinematic checks failed for '+role)
    write_json(BASE/'T05/motion_checks_v2.json',results)

if __name__=='__main__':main()
