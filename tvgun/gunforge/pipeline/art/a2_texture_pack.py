"""Lossless sparse texture candidate; exact content reconstruction, GPU still pending."""
import json,math,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from artlib import GAME,write_json
from a2_memory import allocation
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2g';PACK=REV/'texture_pack'
def main():
    PACK.mkdir(exist_ok=True);estimate=json.loads((REV/'texture_memory_estimate.json').read_text(encoding='utf-8'));sources=estimate['categories']['station_and_lights']['textures'];rows=[];total=0
    for n,src in enumerate(sources):
        im=Image.open(src['file']);a=np.array(im);support=a>0 if im.mode=='L' else a[...,3]>0;tiles=[];reconstructed=Image.new(im.mode,im.size);tilebytes=0
        for y in range(0,im.height,128):
            for x in range(0,im.width,128):
                ex=min(x+128,im.width);ey=min(y+128,im.height)
                if not support[y:ey,x:ex].any():continue
                # Two-pixel bleed for texture sampling; content UV excludes it.
                box=[max(0,x-2),max(0,y-2),min(im.width,ex+2),min(im.height,ey+2)];tile=im.crop(box);path=PACK/f'{n:02}_{x}_{y}.png';tile.save(path);record=allocation(path,bpp=src['assumed_gpu_bytes_per_pixel']);tilebytes+=record['allocated_bytes'];uv=[x-box[0],y-box[1],ex-x,ey-y];content=tile.crop((uv[0],uv[1],uv[0]+uv[2],uv[1]+uv[3]));reconstructed.paste(content,(x,y));tiles.append({'texture':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'content_origin':[x,y],'content_rect_in_texture':uv,'size':list(tile.size),'allocated_bytes':record['allocated_bytes']})
        if im.mode=='L':exact=np.array_equal(a,np.array(reconstructed))
        else:
            black=Image.new('RGBA',im.size,(0,0,0,255));white=Image.new('RGBA',im.size,(255,255,255,255));b2=black.copy();w2=white.copy();black.alpha_composite(im);b2.alpha_composite(reconstructed);white.alpha_composite(im);w2.alpha_composite(reconstructed);exact=np.array_equal(np.array(black),np.array(b2)) and np.array_equal(np.array(white),np.array(w2))
        assert exact,'Reconstruction altered visible pixels'
        sparse=tilebytes<src['allocated_bytes'];chosen=tilebytes if sparse else src['allocated_bytes'];total+=chosen;rows.append({'source':src['file'],'source_size':src['size'],'source_allocated_bytes':src['allocated_bytes'],'sparse_allocated_bytes':tilebytes,'selected':'sparse_tiles' if sparse else 'original','selected_allocated_bytes':chosen,'reconstruction_black_white_exact':exact,'tiles':tiles if sparse else []})
    all_rgba_total=sum(r['selected_allocated_bytes']*(4 if s['assumed_gpu_bytes_per_pixel']==1 else 1) for r,s in zip(rows,sources))
    write_json(REV/'sparse_texture_plan.json',{'version':'g01-alley-sparse-1','status':'offline_lossless_candidate_engine_sampling_pending','tile_content_size':128,'bleed_px':2,'source_total_bytes':sum(r['source_allocated_bytes'] for r in rows),'selected_total_bytes':total,'conservative_all_RGBA8_bytes':all_rgba_total,'budget_bytes':48*1024**2,'estimate_within_budget':total<=48*1024**2,'also_within_48_decimal_MB':all_rgba_total<=48_000_000,'sources':rows,'shader_engine_notes':'Draw only content UV rectangle; bleed is sampling guard, not overlapping visible geometry. Mipmap/seam/filtering and draw-call cost must be measured in engine. Full mip chains counted. Do not substitute file size for VRAM.'});print(json.dumps({'original_bytes':sum(r['source_allocated_bytes'] for r in rows),'selected_bytes':total,'conservative_RGBA8_bytes':all_rgba_total,'budget_bytes':48*1024**2,'within_budget':total<=48*1024**2,'reconstruction_exact':True}))
if __name__=='__main__':main()
