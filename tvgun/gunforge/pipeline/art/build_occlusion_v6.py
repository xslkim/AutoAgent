"""Export a scoped first occlusion prototype, keeping original images and motion."""
import json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from artlib import GAME,write_json,effective_radius
from puppet_motion_v6 import Civilian,CLIPS
from build_motion_v5 import writer
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2k';CACHE=Path('D:/gunforge_cache/g01/T05')
def main():
    REV.mkdir(parents=True,exist_ok=True);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20);checks={}
    for role in ['vendor','video']:
        folder=CACHE/role;model=json.loads((folder/'puppet.json').read_text(encoding='utf-8'));c=Civilian(model,folder);w=writer(REV/(role+'_occlusion_v6.mp4'));board=Image.new('RGB',(1280,720),(102,111,122));samples=[]
        for ci,clip in enumerate(CLIPS):
            for i in range(round(CLIPS[clip]*24)):
                s=c.sample(clip,i/24);im,_=c.render(s);bg=Image.new('RGBA',im.size,(102,111,122,255));bg.alpha_composite(im);ImageDraw.Draw(bg).text((20,640),clip+' / v6 front slots',font=font,fill=(245,225,200));w.send(np.asarray(bg.convert('RGB')))
                r=c.constraints(s);assert r['max_attachment_error']<1e-6 and r['min_transform_determinant']>0
                ids=[k for k,_,_,_ in c.drawables(s)];assert len(ids)==len(set(ids));assert ids.index('torso')<ids.index('upper_arm_l')<ids.index('forearm_l');assert ids.index('holding_sleeve_back')<ids.index('prop')<ids.index('holding_fingers_front')
                samples.append({'clip':clip,'frame':i,'slots':ids})
                if i==round(CLIPS[clip]*24)//2:board.paste(bg.resize((320,360)),((ci%4)*320,(ci//4)*360))
            print(role+' '+clip,flush=True)
        w.close();board.save(REV/(role+'_contact.jpg'))
        # Shared-layer rescue invariant, visible ink alpha vs actual occluders.
        blob=Image.open(CACHE/'ink_blobs/blob_00.png').convert('RGBA');rescue=[];w=writer(REV/(role+'_rescue_v6.mp4'));sc=(512 if role=='vendor' else 300)/768;offset=[320-c.origin[0]*sc,590-c.ground*sc]
        for i in range(72):
            s=c.sample('struggle',i/24,True);combined,paper,raw,visible=c.rescue_render(s,blob,160 if role=='vendor' else 256,sc,(640,720),offset);ordinary,_=c.render(s,(640,720),sc,offset);assert np.array_equal(np.array(ordinary),np.array(paper));assert np.all(visible<=raw[...,3]);bg=Image.new('RGBA',paper.size,(102,111,122,255));bg.alpha_composite(combined);w.send(np.array(bg.convert('RGB')));rescue.append(effective_radius(visible>=128)[0])
        w.close();checks[role]={'frames':len(samples),'rescue_frames':72,'min_rescue_radius':min(rescue),'status':'numeric_subset_pass_visual_review_pending','scope':'first lateral-front arm and grip layering prototype; full joint masks/foot ownership/near-far annotation pending','samples':samples};print(role+' done',flush=True)
    write_json(REV/'checks.json',checks)
if __name__=='__main__':main()
