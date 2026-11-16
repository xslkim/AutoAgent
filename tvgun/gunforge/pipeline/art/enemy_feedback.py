"""Ink-only hit feedback and purification: offline shader/particle approximation."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
import imageio_ffmpeg
from artlib import GAME,write_json,yprime
from paper_ops import limit_luminance
from preview import transform,translation
from puppet_motion import rotation

BASE=GAME/'reports/art/T06';CACHE=Path('D:/gunforge_cache/g01/T06');SIZE=(640,600);FPS=15
CLIPS={'hit':2.,'weak_hit':2.2,'purify':2.6}
LABELS={'hit':'普通命中：短硬直 → 后退 → 恢复','weak_hit':'印迹命中：局部亮点 → 更强反馈','purify':'净化消散：从墨身边缘散开'}
def write_movie(path):
    w=imageio_ffmpeg.write_frames(str(path),SIZE,fps=FPS,codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,output_params=['-crf','20']);w.send(None);return w
def main():
    gallery=BASE/'gallery';font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16);records={}
    for name in ['crow','tadpole0']:
        folder=CACHE/name;model=json.loads((folder/'enemy.json').read_text(encoding='utf-8'));body=Image.open(folder/'body_full.png').convert('RGBA');core=Image.open(folder/'core_full.png').convert('RGBA')
        src=np.array(body);cm=np.array(core);mask=src[...,3]>=128;distance=ndi.distance_transform_edt(mask);rng=np.random.default_rng(421);noise=ndi.gaussian_filter(rng.standard_normal(mask.shape),5);noise/=max(.0001,noise.std())
        scale=.36 if name=='crow' else 130/(2*distance.max());center=np.array([320.,255.]);rows=[];overview=write_movie(gallery/(name+'_feedback_v2.mp4'))
        for clip,duration in CLIPS.items():
            writer=write_movie(gallery/(name+'_'+clip+'_v2.mp4'))
            for i in range(round(duration*FPS)):
                t=i/FPS;u=t-.55;strong=clip!='hit';kick=0 if u<0 else (1 if u<.08 else math.exp(-9*(u-.08))*math.cos(14*(u-.08)))
                amplitude=9 if strong else 6;offset=np.array([kick*amplitude,0.]);m=translation(*(center+offset))@rotation(kick*(3 if strong else 2))@np.diag([scale*(1-.055*kick),scale*(1+.035*kick),1])@translation(-512,-512)
                b=src.copy();c=cm.copy();progress=0.
                if clip=='purify' and u>=0:
                    progress=min(1,u/1.05);threshold=progress*(distance.max()+30);alpha=np.clip((distance+noise*5-threshold+2)/4,0,1)
                    if progress>=1:alpha[:]=0
                    b[...,3]=np.rint(b[...,3]*alpha).astype('uint8');c[...,3]=np.minimum(c[...,3],b[...,3])
                if 0<=u<.22:
                    flash=(1-u/.22)*(.16 if strong else .08)
                    visible=b[...,3]>0;b[visible,:3]=np.clip(b[visible,:3].astype(float)+flash*np.array([150,117,80]),0,255).astype('uint8')
                bl=transform(Image.fromarray(b),m,SIZE);co=transform(Image.fromarray(c),m,SIZE);ba=np.asarray(bl);ca=np.array(co)
                # A printed stamp cannot remain where the actual ink has disappeared.
                ca[...,3]=np.minimum(ca[...,3],ba[...,3]);co=Image.fromarray(ca)
                clean=Image.new('RGBA',SIZE,(110,118,132,255));clean.alpha_composite(bl);clean.alpha_composite(co);fx=Image.new('RGBA',SIZE);d=ImageDraw.Draw(fx)
                hit=np.array(model['core_center'] if strong else [455,500]);hp=(m@np.array([*hit,1]))[:2]
                if 0<=u<.45:
                    life=1-u/.45;radius=5+u*47;alpha=round(life*220)
                    ring=8+u*25;d.ellipse((*list(hp-ring),*list(hp+ring)),outline=(217,160,102,round(140*life)),width=2)
                    for j in range(8 if strong else 6):
                        angle=j*math.tau/(8 if strong else 6)+.25;v=np.array([math.cos(angle),math.sin(angle)])
                        p=hp+v*radius;q=hp+v*(radius+12*life);d.line((*p,*q),fill=(217,160,102,alpha),width=3 if strong else 2)
                    for j in range(5):
                        a=j*1.7;xy=hp+np.array([math.cos(a)*u*65,math.sin(a)*u*45+u*u*60]);r=1.5+life*1.5;d.ellipse((*list(xy-r),*list(xy+r)),fill=(11,11,14,alpha))
                if clip=='purify' and .1<u<1.3:
                    life=max(0,1-(u-.1)/1.2)
                    for j in range(10):
                        angle=j*math.tau/10;v=np.array([math.cos(angle),math.sin(angle)]);p=center+v*(25+u*70);r=1+life*2;d.ellipse((*list(p-r),*list(p+r)),fill=(217,160,102,round(180*life)))
                clean.alpha_composite(fx);before=yprime(np.asarray(clean));clipped=float((before>.75).mean());clean=limit_luminance(clean)
                outside=int(((ca[...,3]>=128)&~(ba[...,3]>=128)).sum())
                rows.append({'clip':clip,'frame':i,'time':t,'core_outside_visible_ink_pixels':outside,'attackable':not (clip=='purify' and u>=0),'purify_progress':progress,'precap_overbright_fraction':clipped,'shared_body_core_transform':m.tolist(),'max_effect_radius_px':32,'hit_stop_seconds':.08})
                if i==round(.62*FPS):clean.save(gallery/(name+'_'+clip+'_v2.png'))
                captioned=clean.copy();dd=ImageDraw.Draw(captioned);dd.rectangle((0,510,640,600),fill=(40,46,63,255));dd.text((18,523),LABELS[clip],font=font,fill=(230,210,179));dd.text((18,561),'仅墨怪受击；程序特效预览，正式引擎效果待验',font=small,fill=(182,200,213))
                raw=np.asarray(captioned.convert('RGB'));writer.send(raw);overview.send(raw)
            writer.close();print(name+' '+clip,flush=True)
        overview.close();model['feedback_v2']={'provider':'offline_procedural_preview','clips':CLIPS,'hit_stop_seconds':.08,'hit_recoil_pixels':[6,9],'impact':'local warm paper rays and black ink droplets; no full-screen white flash','dissolve':'distance-field erode plus bounded deterministic noise; stamp masked by visible ink','target_during_purification':False,'engine_validation':'pending','human_targets':False};write_json(folder/'enemy.json',model)
        summary={'status':'pass' if all(r['core_outside_visible_ink_pixels']==0 and r['precap_overbright_fraction']<=.02 for r in rows) else 'fail','scope':'actual offline rendered frames; not Godot shader, tracker or hit-registration acceptance','frames':len(rows),'max_core_outside_ink_pixels':max(r['core_outside_visible_ink_pixels'] for r in rows),'max_pre_cap_overbright_fraction':max(r['precap_overbright_fraction'] for r in rows),'details':rows};write_json(BASE/(name+'_feedback_checks_v2.json'),summary);records[name]={k:v for k,v in summary.items() if k!='details'}
    write_json(BASE/'feedback_checks_v2.json',records)

if __name__=='__main__':main()
