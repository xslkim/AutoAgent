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

BASE=GAME/'reports/art/T06';CACHE=Path('D:/gunforge_cache/g01/T06');SIZE=(640,600);FPS=30
CLIPS={'hit':2.,'weak_hit':2.2,'purify':2.6}
LABELS={'hit':'普通命中：停顿 → 压缩 → 后退回弹','weak_hit':'印迹命中：更长停顿 + 更强冲击','purify':'净化消散：从墨身边缘散开'}
def write_movie(path):
    w=imageio_ffmpeg.write_frames(str(path),SIZE,fps=FPS,codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,output_params=['-crf','20']);w.send(None);return w
def main():
    gallery=BASE/'gallery';font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21);small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',16);records={}
    for name in ['crow','tadpole0']:
        folder=CACHE/name;model=json.loads((folder/'enemy.json').read_text(encoding='utf-8'));body=Image.open(folder/'body_full.png').convert('RGBA');core=Image.open(folder/'core_full.png').convert('RGBA')
        src=np.array(body);cm=np.array(core);mask=src[...,3]>=128;distance=ndi.distance_transform_edt(mask);rng=np.random.default_rng(421);noise=ndi.gaussian_filter(rng.standard_normal(mask.shape),5);noise/=max(.0001,noise.std())
        scale=.36 if name=='crow' else 130/(2*distance.max());center=np.array([320.,255.]);rows=[];overview=write_movie(gallery/(name+'_feedback_v3.mp4'))
        for clip,duration in CLIPS.items():
            writer=write_movie(gallery/(name+'_'+clip+'_v3.mp4'))
            for i in range(round(duration*FPS)):
                t=i/FPS;u=t-.55;strong=clip!='hit';stop=.16 if strong else .10;kick=0 if u<0 else (1 if u<stop else math.exp(-5*(u-stop))*math.cos(11*(u-stop)))
                amplitude=32 if strong else 20;offset=np.array([kick*amplitude,0.]);m=translation(*(center+offset))@rotation(kick*(10 if strong else 6))@np.diag([scale*(1-(.24 if strong else .17)*kick),scale*(1+(.14 if strong else .10)*kick),1])@translation(-512,-512)
                b=src.copy();c=cm.copy();progress=0.
                if clip=='purify' and u>=0:
                    progress=min(1,u/1.05);threshold=progress*(distance.max()+30);alpha=np.clip((distance+noise*5-threshold+2)/4,0,1)
                    if progress>=1:alpha[:]=0
                    b[...,3]=np.rint(b[...,3]*alpha).astype('uint8');c[...,3]=np.minimum(c[...,3],b[...,3])
                if 0<=u<.22:
                    flash=(1-u/.22)*(.24 if strong else .15)
                    visible=b[...,3]>0;b[visible,:3]=np.clip(b[visible,:3].astype(float)+flash*np.array([150,117,80]),0,255).astype('uint8')
                bl=transform(Image.fromarray(b),m,SIZE);co=transform(Image.fromarray(c),m,SIZE);ba=np.asarray(bl);ca=np.array(co)
                # A printed stamp cannot remain where the actual ink has disappeared.
                ca[...,3]=np.minimum(ca[...,3],ba[...,3]);co=Image.fromarray(ca)
                clean=Image.new('RGBA',SIZE,(110,118,132,255));clean.alpha_composite(bl);clean.alpha_composite(co);fx=Image.new('RGBA',SIZE);d=ImageDraw.Draw(fx)
                hit=np.array(model['core_center'] if strong else [455,500]);hp=(translation(*center)@np.diag([scale,scale,1])@translation(-512,-512)@np.array([*hit,1]))[:2]
                # An incoming ink-only strike cue, then a fixed impact origin.
                if -.10<=u<0:
                    p=hp+np.array([u*1900,-u*150]);d.line((*list(p-[38,0]),*p),fill=(217,160,102,210),width=4)
                if 0<=u<.62:
                    life=1-u/.62;alpha=round(life*245);count=10 if strong else 8
                    reach=(54 if strong else 36);radius=8+u*75
                    if u<.13:
                        points=[]
                        for j in range(count*2):
                            angle=j*math.pi/count;rr=(reach if j%2==0 else reach*.23)*(1-u*.8)
                            points.append(tuple(hp+np.array([math.cos(angle)*rr,math.sin(angle)*rr*.72])))
                        d.polygon(points,fill=(217,160,102,235))
                        d.ellipse((*list(hp-7),*list(hp+7)),fill=(224,180,120,250))
                    ring=10+u*(85 if strong else 65);d.ellipse((*list(hp-ring),*list(hp+ring)),outline=(217,160,102,round(210*life)),width=3 if strong else 2)
                    for j in range(count):
                        angle=j*math.tau/count+.25;v=np.array([math.cos(angle),math.sin(angle)])
                        p=hp+v*radius;q=hp+v*(radius+(25 if strong else 17)*life);d.line((*p,*q),fill=(217,160,102,alpha),width=4 if strong else 3)
                    for j in range(12 if strong else 8):
                        a=j*2.4;speed=95+(j%3)*25;travel=12+u*speed;xy=hp+np.array([math.cos(a)*travel,math.sin(a)*travel+u*u*130]);r=2+life*(4 if strong else 3);d.ellipse((*list(xy-r),*list(xy+r)),fill=(11,11,14,alpha))
                    if u<.10:d.ellipse((*list(hp-5),*list(hp+5)),fill=(224,180,120,255))
                if clip=='purify' and .1<u<1.3:
                    life=max(0,1-(u-.1)/1.2)
                    for j in range(10):
                        angle=j*math.tau/10;v=np.array([math.cos(angle),math.sin(angle)]);p=center+v*(25+u*70);r=1+life*2;d.ellipse((*list(p-r),*list(p+r)),fill=(217,160,102,round(180*life)))
                clean.alpha_composite(fx);before=yprime(np.asarray(clean));clipped=float((before>.75).mean());clean=limit_luminance(clean)
                outside=int(((ca[...,3]>=128)&~(ba[...,3]>=128)).sum())
                rows.append({'clip':clip,'frame':i,'time':t,'core_outside_visible_ink_pixels':outside,'attackable':not (clip=='purify' and u>=0),'purify_progress':progress,'precap_overbright_fraction':clipped,'shared_body_core_transform':m.tolist(),'hit_stop_seconds':stop,'recoil_amplitude_px':amplitude,'actual_recoil_px':float(offset[0]),'body_scale_xy':[float(m[0,0]),float(m[1,1])]})
                if i==round(.62*FPS):clean.save(gallery/(name+'_'+clip+'_v3.png'))
                captioned=clean.copy();dd=ImageDraw.Draw(captioned);dd.rectangle((0,510,640,600),fill=(40,46,63,255));dd.text((18,523),LABELS[clip],font=font,fill=(230,210,179));dd.text((18,561),'仅墨怪受击；程序特效预览，正式引擎效果待验',font=small,fill=(182,200,213))
                raw=np.asarray(captioned.convert('RGB'));writer.send(raw);overview.send(raw)
            writer.close();print(name+' '+clip,flush=True)
        overview.close();model['feedback_v3']={'provider':'offline_procedural_preview','clips':CLIPS,'hit_stop_seconds':{'normal':.10,'stamp':.16},'hit_recoil_pixels':[20,32],'impact':'fixed-origin local impact star, incoming strike cue, expanding ring, larger paper rays and ink droplets; no full-screen flash','dissolve':'distance-field erode plus bounded deterministic noise; stamp masked by visible ink','target_during_purification':False,'engine_validation':'pending','human_targets':False};write_json(folder/'enemy.json',model)
        summary={'status':'pass' if all(r['core_outside_visible_ink_pixels']==0 and r['precap_overbright_fraction']<=.02 for r in rows) else 'fail','scope':'actual offline rendered frames; not Godot shader, tracker or hit-registration acceptance','frames':len(rows),'max_core_outside_ink_pixels':max(r['core_outside_visible_ink_pixels'] for r in rows),'max_pre_cap_overbright_fraction':max(r['precap_overbright_fraction'] for r in rows),'details':rows};write_json(BASE/(name+'_feedback_checks_v3.json'),summary);records[name]={k:v for k,v in summary.items() if k!='details'}
    write_json(BASE/'feedback_checks_v3.json',records)

if __name__=='__main__':main()
