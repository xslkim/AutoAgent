"""Minimum-size warning-state comparison, native ink art unchanged."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
import imageio_ffmpeg
from artlib import GAME,write_json,yprime
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h';CACHE=Path('D:/gunforge_cache/g01/T06')
def main():
    scene=Image.open(BASE/'T04/gallery/station_unlit.png').convert('RGBA');bg=scene.crop((180,220,660,520));font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21);parts={};rows=[]
    for name in ['crow','tadpole0']:
        f=CACHE/name;model=json.loads((f/'enemy.json').read_text(encoding='utf-8'));body=Image.open(f/'body_full.png').convert('RGBA');a=np.array(body);mask=a[...,3]>=128;ys,xs=np.nonzero(mask)
        scale=200/max(np.ptp(xs)+1,np.ptp(ys)+1) if name=='crow' else 90/(2*ndi.distance_transform_edt(mask).max());sz=round(1024*scale);body=body.resize((sz,sz),Image.Resampling.LANCZOS);core=Image.open(f/'core_full.png').convert('RGBA').resize((sz,sz),Image.Resampling.LANCZOS);parts[name]=(body,core,model,scale)
    w=imageio_ffmpeg.write_frames(str(REV/'warning_comparison.mp4'),(960,600),fps=30,codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,output_params=['-crf','20']);w.send(None)
    for i in range(120):
        t=i/30;canvas=Image.new('RGBA',(960,600));d=ImageDraw.Draw(canvas)
        for row,name in enumerate(['crow','tadpole0']):
            body,core,model,scale=parts[name];a=np.array(body)
            for col,state in enumerate(['normal','warning']):
                tile=bg.copy();pos=(round(240-body.width/2),round(130-body.height/2));tile.alpha_composite(body,pos);c=np.array(core);pulse=.5+.5*math.sin(t*math.tau*1.5);factor=1. if state=='normal' else .35+.65*pulse;c[...,3]=np.minimum(np.rint(c[...,3]*factor).astype('uint8'),a[...,3]);tile.alpha_composite(Image.fromarray(c),pos)
                if state=='warning':
                    fx=Image.new('RGBA',tile.size);fd=ImageDraw.Draw(fx);cx=pos[0]+model['core_center'][0]*scale;cy=pos[1]+model['core_center'][1]*scale;r=17+9*pulse;fd.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(217,160,102,round(70+120*pulse)),width=2);tile.alpha_composite(fx)
                before=yprime(np.array(tile));outside=int(((c[...,3]>=128)&~(a[...,3]>=128)).sum());rows.append({'frame':i,'enemy':name,'state':state,'primary_target_unchanged':True,'core_outside_body':outside,'overbright_fraction':float((before>.75).mean())});td=ImageDraw.Draw(tile);td.rectangle((0,255,480,300),fill=(34,39,56,255));td.text((14,263),('墨鸦' if name=='crow' else '墨蝌蚪')+' / '+('普通' if col==0 else '预警：印迹脉动与暖环'),font=font,fill=(235,216,190));canvas.alpha_composite(tile,(col*480,row*300))
        w.send(np.asarray(canvas.convert('RGB')))
        if i==10:canvas.convert('RGB').save(REV/'warning_comparison.jpg',quality=92)
    w.close();write_json(REV/'warning_checks.json',{'status':'pass_numeric_pending_visual' if all(r['core_outside_body']==0 and r['overbright_fraction']<=.02 for r in rows) else 'fail','frames':120,'sample_checks':len(rows),'crow_extent_px':200,'tadpole_head_diameter_px':90,'warning_pulse_hz':1.5,'primary_target_unchanged':True,'effect_approval':'pending','engine_validation':'pending','rows':rows});print('Warning-state comparison rendered')
if __name__=='__main__':main()
