"""Readability across camera extremes, plus a procedural hardened-eye material."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
from artlib import GAME,write_json,yprime
from preview import render
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2e';CACHE=Path('D:/gunforge_cache/g01')
def main():
    f=CACHE/'T06/crow';body=Image.open(f/'body_full.png').convert('RGBA');a=np.array(body);yy,xx=np.nonzero(a[...,3]>=128);sc=200/max(np.ptp(xx)+1,np.ptp(yy)+1);size=(round(1024*sc),)*2;body=body.resize(size,Image.Resampling.LANCZOS);a=np.array(body);mask=a[...,3]>=128;Y=yprime(a)
    core=Image.open(f/'core_full.png').convert('RGBA').resize(size,Image.Resampling.LANCZOS);eyes=Image.open(f/'core_hardened_full.png').convert('RGBA').resize(size,Image.Resampling.LANCZOS);old=np.array(eyes);eye_mask=old[...,3]>=128
    # Runtime material preview: same native alpha/shape; warm paper tint only in hardened state.
    warm=old.copy();warm[...,:3]=np.array([217,160,102],dtype='uint8');warmeyes=Image.fromarray(warm);newY=yprime(warm);oldcontrast=float(np.median(np.abs(yprime(old)[eye_mask]-Y[eye_mask])));newcontrast=float(np.median(np.abs(newY[eye_mask]-Y[eye_mask])))
    labels,n=ndi.label(eye_mask);lengths=[sl[1].stop-sl[1].start for sl in ndi.find_objects(labels) if sl is not None and (labels[sl]>0).sum()>8];eye_length=min(lengths) if lengths else 0
    station=json.loads((CACHE/'T04/station/station.json').read_text());states=[(0,0)]+[(x,y) for x in [-68,68] for y in [-34,34]];rows=[]
    for state in ['unlit','lit']:
        for dx,dy in states:
            bg=render(station,CACHE/'T04/station',camera=(dx,dy),light_states={'streetlamp':state=='lit'});bgY=yprime(np.array(bg));oc=Image.new('L',(1920,1020))
            for layer in station['layers']:
                if not layer.get('blocks_shots'):continue
                im=Image.open(CACHE/'T04/station'/layer['file']).convert('RGBA');px,py=np.rint(np.array(layer['pos'])-np.array([dx,dy])*layer['parallax']).astype(int);oc.paste(im.getchannel('A'),(int(px),int(py)))
            # Union near occluders independently: later transparent pixels must not erase earlier masks.
            ocarr=np.zeros((1020,1920),bool)
            for layer in station['layers']:
                if layer.get('blocks_shots'):
                    im=Image.open(CACHE/'T04/station'/layer['file']).convert('RGBA');tile=Image.new('L',(1920,1020));p=np.rint(np.array(layer['pos'])-np.array([dx,dy])*layer['parallax']).astype(int);tile.paste(im.getchannel('A'),tuple(map(int,p)));ocarr|=np.array(tile)>=128
            ocarr=ocarr[42:978,72:1848]
            for y in [210,350,490,630]:
                for x in [420,650,880,1110,1340]:
                    left=round(x-dx*.45-size[0]/2);top=round(y-dy*.45-size[1]/2);patch=bgY[top:top+size[1],left:left+size[0]];contrast=float(np.median(abs(Y[mask]-patch[mask])));behind=float(np.median(patch[mask]));overlap=int((ocarr[top:top+size[1],left:left+size[0]]&mask).sum());ok=contrast>=.2 and behind>=.25 and overlap==0
                    rows.append({'lighting':state,'camera_breath':[dx,dy],'slot':[x,y],'normal_contrast':contrast,'background_Yprime':behind,'foreground_overlap_pixels':overlap,'normal_numeric_pass':ok})
    slots=[]
    for y in [210,350,490,630]:
        for x in [420,650,880,1110,1340]:
            samples=[r for r in rows if r['slot']==[x,y]];slots.append({'center':[x,y],'states':len(samples),'numeric_pass_all_states':all(r['normal_numeric_pass'] for r in samples),'minimum_normal_contrast':min(r['normal_contrast'] for r in samples),'hardened_tint_numeric_pass':newcontrast>=.3 and eye_length>=16,'runtime_interaction_and_thumbnail_review':'pending'})
    bg=Image.open(BASE/'T04/gallery/station_unlit.png').convert('RGBA');font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20);d=ImageDraw.Draw(bg)
    for s in slots:
        x,y=s['center'];color=(100,220,160) if s['numeric_pass_all_states'] else (235,130,100);d.rectangle((x-110,y-110,x+110,y+110),outline=color,width=3);d.text((x-100,y-110),f'{s["minimum_normal_contrast"]:.2f}',font=font,fill=color)
    bg.save(REV/'motion_readability_slots.png')
    board=Image.new('RGBA',(900,330),(100,110,125,255));bd=ImageDraw.Draw(board)
    for i,(title,overlay) in enumerate([('普通态（沿用）',core),('硬化旧预览',eyes),('硬化眼材质试做',warmeyes)]):
        p=(i*300+35,30);board.alpha_composite(body,p);board.alpha_composite(overlay,p);bd.text((i*300+15,275),title,font=font,fill=(235,220,195))
    board.save(REV/'hardened_material_comparison.png')
    write_json(REV/'slot_motion_checks.json',{'scope':'200px crow, 20 slots, five combined camera/breath states, two lamp states; numeric/offline only','slots':slots,'samples':rows,'robust_slots':sum(s['numeric_pass_all_states'] for s in slots),'hardened':{'original_eye_contrast':oldcontrast,'trial_eye_contrast':newcontrast,'individual_eye_length_px':eye_length,'trial_pass':newcontrast>=.3 and eye_length>=16,'trial_material_tint_rgb':[217,160,102],'native_art_unchanged':True,'human_acceptance':'pending'}});print(json.dumps({'robust_slots':sum(s['numeric_pass_all_states'] for s in slots),'hardened_old':oldcontrast,'hardened_trial':newcontrast,'eye_length':eye_length}))
if __name__=='__main__':main()
