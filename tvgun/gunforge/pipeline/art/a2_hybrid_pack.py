"""Sparse base level plus globally generated low-resolution mip chain candidate."""
import json,hashlib,math
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import maximum_filter
from artlib import GAME,write_json
from a2_memory import allocation
from a2_mip_sampling import pixels,mip,sample
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h';PACK=REV/'hybrid_pack';OLD=BASE/'T07/revisions/A2g'
def main():
    PACK.mkdir(exist_ok=True);plan=json.loads((OLD/'sparse_texture_plan.json').read_text(encoding='utf-8'));estimate=json.loads((OLD/'texture_memory_estimate.json').read_text(encoding='utf-8'));bpps={r['file']:r['assumed_gpu_bytes_per_pixel'] for r in estimate['categories']['station_and_lights']['textures']};rows=[];checks=[]
    for n,src in enumerate(plan['sources']):
        im=Image.open(src['source']);a=pixels(im);h,w=a.shape[:2];support=np.array(im)>0 if im.mode=='L' else np.array(im)[...,3]>0;guard=maximum_filter(support,size=3,mode='constant');tiles=[];bytes_base=0;bytes_base_rgba=0
        # Entire-image mip chain is generated BEFORE any spatial split.
        chain=[];q=a
        while q.shape[0]>1 or q.shape[1]>1:q=mip(q,1);chain.append(q)
        low_bytes=sum(level.shape[0]*level.shape[1]*bpps[src['source']] for level in chain);low_rgba=sum(level.shape[0]*level.shape[1]*4 for level in chain)
        # Exact float CPU levels are saved as evidence; an engine uploader must
        # quantize consistently and use the SAME precomputed chain globally.
        for level,q in enumerate(chain,1):np.save(PACK/f'{n:02}_mip_{level:02}.npy',q)
        # Choose a block size per source by actual conservative allocation; sparse
        # foliage benefits from smaller blocks, dense surfaces often keep originals.
        costs={}
        for cell in [32,64,128,256]:
            costs[cell]=sum((min(w,x+cell+2)-max(0,x-2))*(min(h,y+cell+2)-max(0,y-2))*4 for y in range(0,h,cell) for x in range(0,w,cell) if guard[y:min(y+cell,h),x:min(x+cell,w)].any())
        cell=min(costs,key=costs.get)
        for y in range(0,h,cell):
            for x in range(0,w,cell):
                ex=min(w,x+cell);ey=min(h,y+cell)
                if not guard[y:ey,x:ex].any():continue
                box=[max(0,x-2),max(0,y-2),min(w,ex+2),min(h,ey+2)];tile=im.crop(box);p=PACK/f'{n:02}_t{cell}_{x}_{y}.png';tile.save(p);record=allocation(p,mips=False,bpp=bpps[src['source']]);bytes_base+=record['allocated_bytes'];bytes_base_rgba+=tile.width*tile.height*4;tiles.append({'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'box':box,'content':[x,y,ex,ey],'mipmaps':False,'size':list(tile.size)})
        hybrid=bytes_base+low_bytes;hybrid_rgba=bytes_base_rgba+low_rgba;original=src['source_allocated_bytes'];original_rgba=original*(4 if bpps[src['source']]==1 else 1);selected='hybrid' if hybrid_rgba<original_rgba else 'original'
        # CPU reference verifies base-level bilinear and entire-image coarser
        # levels; include fractional .75 scale to catch border/UV discontinuity.
        for scale in [1.,.75,.5,.25]:
            level=0 if scale>.5 else round(math.log2(1/scale));ow=max(1,round(w*scale));oh=max(1,round(h*scale));yy,xx=np.mgrid[:oh,:ow];sx=(xx+.5)/scale-.5;sy=(yy+.5)/scale-.5;full=mip(a,level);ref=sample(full,(sx+.5)*full.shape[1]/w-.5,(sy+.5)*full.shape[0]/h-.5)
            if level:out=sample(chain[level-1],(sx+.5)*full.shape[1]/w-.5,(sy+.5)*full.shape[0]/h-.5)
            else:
                out=np.zeros_like(ref)
                for tile in tiles:
                    x,y,ex,ey=tile['content'];x0,y0,x1,y1=tile['box'];region=(sx+.5>=x)&(sx+.5<ex)&(sy+.5>=y)&(sy+.5<ey);out[region]=sample(a[y0:y1,x0:x1],sx[region]-x0,sy[region]-y0)
            valid=(sx>=-.5)&(sx<w-.5)&(sy>=-.5)&(sy<h-.5);err=np.abs(ref-out)[valid];maximum=float(err.max()) if err.size else 0.;checks.append({'source':src['source'],'scale':scale,'max_premultiplied_channel_error':maximum,'pass':maximum<1e-5})
        rows.append({'source':src['source'],'size':[w,h],'selected':selected,'tile_content_size':cell,'allocated_bytes':hybrid if selected=='hybrid' else original,'conservative_RGBA8_bytes':hybrid_rgba if selected=='hybrid' else original_rgba,'base_bytes':bytes_base,'global_mip_bytes':low_bytes,'tiles':tiles if selected=='hybrid' else [],'global_levels':[{'level':i+1,'float_reference':str(PACK/f'{n:02}_mip_{i+1:02}.npy'),'size':[q.shape[1],q.shape[0]]} for i,q in enumerate(chain)] if selected=='hybrid' else []});print(Path(src['source']).name+' '+selected,flush=True)
    total=sum(r['allocated_bytes'] for r in rows);rgba=sum(r['conservative_RGBA8_bytes'] for r in rows);passed=all(r['pass'] for r in checks)
    write_json(REV/'hybrid_texture_plan.json',{'version':'g01-alley-hybrid-2b','status':'CPU_reference_only_engine_pending','reason':'independent per-tile mipmaps rejected; sample global coarser chain with full-layer UVs','selected_bytes':total,'conservative_RGBA8_bytes':rgba,'within_48MiB':rgba<=48*1024**2,'within_48_decimal_MB':rgba<=48_000_000,'cpu_sampling_pass':passed,'sources':rows,'engine_pending':['consistent sRGB/linear and premultiplication','8bit quantization/upload of global mip levels','trilinear LOD crossfade','GPU seam checks and draw calls','peak memory including transient upload']});write_json(REV/'hybrid_sampling_checks.json',{'scope':'CPU float premultiplied encoded-space BOX mips, bilinear sampling; no GPU certification','all_pass':passed,'rows':checks});print(json.dumps({'selected_bytes':total,'conservative_RGBA8_bytes':rgba,'cpu_sampling_pass':passed}))
if __name__=='__main__':main()
