"""Real rendered prop anchors, axis directions, loops and unaffected-character check."""
import json,copy
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from artlib import GAME,write_json
from puppet_motion_v5 import Civilian,CLIPS,point
from puppet_motion_v4 import Civilian as Previous
from checks import run
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2g';CACHE=Path('D:/gunforge_cache/g01/T05')
def main():
    f=CACHE/'vendor';m=json.loads((f/'puppet.json').read_text(encoding='utf-8'));c=Civilian(m,f);old=Previous(m,f);rows=[];loops={};font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19);board=Image.new('RGB',(1440,780),(102,111,122))
    for rescue in [False,True]:
        for clip,dur in CLIPS.items():
            for i in range(round(dur*24)):
                s=c.sample(clip,i/24,rescue);r=c.constraints(s)['skewer'];assert r['grip_error_source_px']<1e-6 and r['angle_target_error_deg']<1e-6 and r['fruit_above_grip'] and r['bare_handle_below_grip'] and r['fruit_outside_hand'];assert c.local_limits['prop'][0]<=s['angles']['prop']<=c.local_limits['prop'][1];rows.append({'clip':clip,'rescue':rescue,'frame':i,**r})
    # A prop direction negative: original forearm-inherited orientation is visibly inward.
    s=old.sample('struggle',1.5,rescue=True);world=old.world_matrices(s);p=old.nodes['prop'];fruit=point(world['prop'],[20,70]);grip=point(world['prop'],p['pivot']);assert fruit[0]<grip[0]
    for clip,dur in CLIPS.items():
        if clip=='rescued_bounce':continue
        paths=[]
        for label,t in [('first',0),('second',1/24),('penultimate',dur-1/24),('last',dur)]:
            im,_=c.render(c.sample(clip,t));p=REV/(clip+'_'+label+'.png');im.save(p);paths.append(str(p))
        loops[clip]=run('C12',{'frames':paths,'pixel_threshold':.02,'velocity_threshold':.02});assert loops[clip]['status']=='pass'
    # Five key gestures, same framing, and a source-pixel crop showing grip and stick.
    for j,clip in enumerate(['idle','walk','wave_for_help','struggle','thank']):
        s=c.sample(clip,1.5,rescue=clip=='struggle');im,mats=c.render(s);bg=Image.new('RGBA',im.size,(102,111,122,255));bg.alpha_composite(im);board.paste(bg.resize((288,324)),(j*288,0));d=ImageDraw.Draw(board);d.text((j*288+8,326),clip,font=font,fill=(235,215,190));anchor=point(mats['prop'],c.nodes['prop']['pivot']);x,y=anchor;crop=bg.crop((round(x-70),round(y-170),round(x+70),round(y+45))).resize((240,369));board.paste(crop,(j*288+24,365))
    board.save(REV/'prop_contact.jpg',quality=93)
    f=CACHE/'video';m=json.loads((f/'puppet.json').read_text(encoding='utf-8'));a=Civilian(m,f);b=Previous(m,f);same=0
    for clip in CLIPS:
        for t in [0,1,CLIPS[clip]]:
            x,_=a.render(a.sample(clip,t));y,_=b.render(b.sample(clip,t));assert np.array_equal(np.array(x),np.array(y));same+=1
    write_json(REV/'prop_checks.json',{'status':'pass','actual_frame_states':len(rows),'max_grip_error_source_px':max(r['grip_error_source_px'] for r in rows),'world_angle_range':[min(r['world_angle_deg'] for r in rows),max(r['world_angle_deg'] for r in rows)],'original_inward_prop_negative_rejected':True,'video_owner_unchanged_samples':same,'loops':loops,'source_png_changes':0,'scope':'vendor prop only; all ordinary/rescue branch samples; numeric grip and direction do not replace visual review','frames':rows});print('Prop frame states '+str(len(rows))+' passed; unaffected owner '+str(same))
if __name__=='__main__':main()
