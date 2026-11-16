"""Conservative offline movement reservations for the revised hostage prototypes."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from artlib import GAME,write_json
from puppet_motion import Civilian,point,rotation
from preview import translation,transform
from checks import overlap

CACHE=Path('D:/gunforge_cache/g01');BASE=GAME/'reports/art';SIZE=(1776,936)
def main():
    hud=json.loads((GAME/'assets/ui/hud_layout.json').read_text(encoding='utf-8'));reserved=[v['rect'] for v in hud['reserved'].values() if v['when']=='playing'];records={}
    for role,height in [('vendor',512),('video',300)]:
        folder=CACHE/'T05'/role;model=json.loads((folder/'puppet.json').read_text(encoding='utf-8'));c=Civilian(model,folder);sc=height/768;offset=np.array([760,500])-c.origin*sc;points=[]
        for clip,dur in [('idle',2.5),('peek',3),('startle',2),('wave_for_help',3.5),('struggle',3)]:
            for i in range(round(dur*24)):
                s=c.sample(clip,i/24,rescue=True);world=c.world_matrices(s);cam=translation(*offset)@np.diag([sc,sc,1])
                for node in c.model['parts']:
                    im=c.images[node['id']];alpha=np.asarray(im)[...,3]>=128;yy,xx=np.nonzero(alpha);box=(xx.min(),yy.min(),xx.max()+1,yy.max()+1)
                    for x,y in [(box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3])]:points.append(point(cam@world[node['id']],[x,y]))
        p=np.array(points);mn=p.min(axis=0)-[30.6,15.3];mx=p.max(axis=0)+[30.6,15.3];bbox=[math.floor(mn[0]),math.floor(mn[1]),math.ceil(mx[0])-math.floor(mn[0]),math.ceil(mx[1])-math.floor(mn[1])]
        safe=bbox[0]>=60 and bbox[1]>=60 and bbox[0]+bbox[2]<=1716 and bbox[1]+bbox[3]<=876 and not any(overlap(bbox,r) for r in reserved)
        records[role]={'status':'pass' if safe else 'fail','kind':'protected_human','human_attackable':False,'slot_origin':[760,500],'motion_bbox':bbox,'parallax':.45,'camera_breath_padding':[30.6,15.3],'alternative_slot':True,'scope':'conservative source-part rectangles over every attached-eligible frame, plus camera/breath extrema; not engine occlusion acceptance'}
        if role=='vendor':
            bg=Image.open(BASE/'T04/gallery/station_unlit.png').convert('RGBA');s=c.sample('wave_for_help',1.5,rescue=True);blob=Image.open(CACHE/'T05/ink_blobs/blob_00.png').convert('RGBA');actor,_,_,_=c.rescue_render(s,blob,160,sc,SIZE,offset);bg.alpha_composite(actor)
            f=CACHE/'T06/crow';m=translation(1120,405)@np.diag([.33,.33,1])@translation(-512,-512)
            for name in ['body_full.png','core_full.png']:bg.alpha_composite(transform(Image.open(f/name).convert('RGBA'),m,SIZE))
            clean=bg.copy();d=ImageDraw.Draw(bg);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
            x,y,w,h=bbox;d.rectangle((x,y,x+w,y+h),outline=(88,213,218),width=3);d.text((x,y-30),'保护对象的运动预留范围',font=font,fill=(88,213,218));d.rectangle((60,60,1716,876),outline=(232,174,89),width=2)
            for name,v in hud['reserved'].items():
                if v['when']=='playing':
                    X,Y,W,H=v['rect'];d.rectangle((X,Y,X+W,Y+H),outline=(232,174,89),width=2);d.text((X+2,Y+2),name,font=font,fill=(232,174,89))
            gallery=BASE/'T07/gallery';clean.save(gallery/'hostage_in_scene_v2.png');bg.save(gallery/'motion_reservations_v2.png')
    path=BASE/'T07/revisions/A2b/motion_reservations.json';write_json(path,records);print(json.dumps(records))

if __name__=='__main__':main()
