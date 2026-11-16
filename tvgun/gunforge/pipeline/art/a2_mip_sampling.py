"""CPU mip/UV sampling comparison, independent tiles versus original texture."""
import json,math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.ndimage import map_coordinates
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h';OLD=BASE/'T07/revisions/A2g'
def pixels(im):
    a=np.array(im,dtype='float32')/255
    if a.ndim==2:return a[...,None]
    a[...,:3]*=a[...,3:4];return a
def mip(a,level):
    for _ in range(level):
        h,w=a.shape[:2];a=np.stack([np.asarray(Image.fromarray(a[...,c],'F').resize((max(1,w//2),max(1,h//2)),Image.Resampling.BOX)) for c in range(a.shape[2])],axis=-1)
    return a
def sample(a,x,y):return np.stack([map_coordinates(a[...,c],[y,x],order=1,mode='nearest',prefilter=False) for c in range(a.shape[2])],axis=-1)
def compare(src,bleed,scale):
    im=Image.open(src['source']);a=pixels(im);h,w=a.shape[:2];level=round(math.log2(1/scale));ow=math.ceil(w*scale);oh=math.ceil(h*scale);yy,xx=np.mgrid[:oh,:ow];sx=(xx+.5)/scale-.5;sy=(yy+.5)/scale-.5
    full=mip(a,level);ref=sample(full,(sx+.5)*full.shape[1]/w-.5,(sy+.5)*full.shape[0]/h-.5);out=np.zeros_like(ref)
    support=a[...,0]>0 if a.shape[2]==1 else a[...,3]>0
    for y in range(0,h,128):
        for x in range(0,w,128):
            ex=min(x+128,w);ey=min(y+128,h)
            if not support[y:ey,x:ex].any():continue
            x0=max(0,x-bleed);y0=max(0,y-bleed);x1=min(w,ex+bleed);y1=min(h,ey+bleed);tile=mip(a[y0:y1,x0:x1],level)
            region=(sx>=x-.5)&(sx<ex-.5)&(sy>=y-.5)&(sy<ey-.5)
            tx=(sx[region]-x0+.5)*tile.shape[1]/(x1-x0)-.5;ty=(sy[region]-y0+.5)*tile.shape[0]/(y1-y0)-.5;out[region]=sample(tile,tx,ty)
    # Evaluate premultiplied channels, including alpha, across the entire texture.
    diff=np.abs(ref-out);return {'max_channel_error':float(diff.max()),'mean_channel_error':float(diff.mean()),'fraction_pixels_error_over_1_byte':float((diff.max(axis=2)>1/255+1e-6).mean())},ref,out
def main():
    plan=json.loads((OLD/'sparse_texture_plan.json').read_text(encoding='utf-8'));rows=[];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    for src in plan['sources']:
        if src['selected']!='sparse_tiles':continue
        for bleed in [2,4,8]:
            for scale in [1.,.5,.25]:
                r,ref,out=compare(src,bleed,scale);rows.append({'source':src['source'],'bleed':bleed,'scale':scale,**r})
        print(Path(src['source']).name,flush=True)
    write_json(REV/'mip_sampling_checks.json',{'scope':'CPU premultiplied encoded-space BOX mip chains, bilinear UV sampling; not Godot GPU/linear-light/trilinear certification','one_byte_tolerance_is_diagnostic_not_calibrated':True,'rows':rows,'summary':{str(b):{'max_error':max(r['max_channel_error'] for r in rows if r['bleed']==b),'max_bad_fraction':max(r['fraction_pixels_error_over_1_byte'] for r in rows if r['bleed']==b)} for b in [2,4,8]}});print('Mip sampling comparison complete')
if __name__=='__main__':main()
