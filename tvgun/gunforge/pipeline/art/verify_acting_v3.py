"""Verify attachment-specific failure modes and export human-readable key poses."""
import copy,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from artlib import GAME,write_json
from puppet_motion_v3 import Civilian,CLIPS,point
from preview import translation,transform
from scipy import ndimage as ndi

BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2c';CACHE=Path('D:/gunforge_cache/g01/T05')
def main():
    records={};font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    board=Image.new('RGB',(1280,900),(42,48,62));bd=ImageDraw.Draw(board)
    for ri,role in enumerate(['vendor','video']):
        f=CACHE/role;c=Civilian(json.loads((f/'puppet.json').read_text(encoding='utf-8')),f);rows=[]
        for i in range(84):
            s=c.sample('wave_for_help',i/24);check=c.constraints(s);slots={k:(im,m) for k,im,m,_ in c.drawables(s)};hi,hm=slots['right_palm'];ai,am=slots['forearm_l'];wp=point(am,c.wrists['l']);cam=translation(48-wp[0],48-wp[1]);ha=np.asarray(transform(hi,cam@hm,(96,96)))[...,3]>=128;aa=np.asarray(transform(ai,cam@am,(96,96)))[...,3]>=128
            yy,xx=np.ogrid[:96,:96];zone=(xx-48)**2+(yy-48)**2<12**2;gap=float(ndi.distance_transform_edt(~aa)[ha&zone].min()) if (ha&zone).any() else 999
            raised=1.05<=i/24<=2.72
            rows.append({'frame':i,'wrist_gap_source_px':gap,'hand_transform_determinant':float(np.linalg.det(hm[:2,:2])),'thumb_direction_component_x':float(hm[0,0]),'raised_pose':raised,'expression':s['expression']})
        # Same predicate applied to normal and deliberately reflected transforms.
        def correct_hand(m,raised):return np.linalg.det(m[:2,:2])>0 and (not raised or m[0,0]>.8)
        s=c.sample('wave_for_help',1.5);hm=next(m for k,_,m,_ in c.drawables(s) if k=='right_palm');bad=hm@np.diag([-1,1,1]);assert correct_hand(hm,True) and not correct_hand(bad,True)
        def expression_ok(s):return s['expression']=='distress' if s['rescue'] or s['clip'] in ['peek','startle','wave_for_help','struggle'] else True
        bad=copy.deepcopy(s);bad['expression']='relieved';assert expression_ok(s) and not expression_ok(bad)
        expression_frames=0
        for clip in CLIPS:
            for rescue in [False,True]:
                for i in range(round(CLIPS[clip]*24)):
                    assert expression_ok(c.sample(clip,i/24,rescue));expression_frames+=1
        sources=c.attachments['base_pngs_sha256'];assert all(hashlib.sha256((f/n['file']).read_bytes()).hexdigest()==sources[n['id']] for n in c.model['parts'])
        for j,t in enumerate([0,.65,1.38,1.73,3.14]):
            im,_=c.render(c.sample('wave_for_help',t));bg=Image.new('RGBA',im.size,(102,111,122,255));bg.alpha_composite(im)
            # Upper-body close-up, same framing across moments for useful comparison.
            crop=bg.crop((65,45,470,400)).resize((256,225));board.paste(crop,(j*256,ri*450));bd.text((j*256+12,ri*450+230),f'{t:.2f}s '+['准备','抬手','摆动一端','摆动另一端','收回'][j],font=font,fill=(234,215,186))
            full=bg.resize((128,144));board.paste(full,(j*256+64,ri*450+267))
        record={'status':'pass' if all(r['wrist_gap_source_px']<=2 and r['hand_transform_determinant']>0 and (not r['raised_pose'] or r['thumb_direction_component_x']>.8) for r in rows) else 'fail','wave_frames':len(rows),'max_wrist_gap_source_px':max(r['wrist_gap_source_px'] for r in rows),'reflected_hand_negative_rejected':True,'smiling_distress_negative_rejected':True,'expression_state_frame_checks':expression_frames,'base_source_pngs_unchanged':True,'visual_inspection':'executor inspected five-digit palm, thumb screen-right when raised, worried brows/open mouth and contact poses; user acceptance pending','not_covered':'pixel artwork chirality is an annotated visual inspection, not inferred from a right-hand label or solely from determinant','frames':rows}
        records[role]=record
    out=BASE/'T05/gallery/acting_keyposes_v3.jpg';board.save(out,quality=93);write_json(REV/'acting_checks.json',records);print(json.dumps({k:{x:v for x,v in r.items() if x!='frames'} for k,r in records.items()}))

if __name__=='__main__':main()
