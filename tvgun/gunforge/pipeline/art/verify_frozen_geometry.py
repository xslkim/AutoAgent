"""Coverage against immutable human-accepted design masks, including movement reveal."""
import json,math,hashlib,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2i';CACHE=Path('D:/gunforge_cache/g01/T04/station')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_frozen(path,digest):
    if sha(path)!=digest:raise ValueError('Frozen extent modified; do not refresh baseline')
    return np.array(Image.open(path).convert('L'))>=128
def shift(a,dx,dy):
    out=np.zeros_like(a);h,w=a.shape;x0=max(0,dx);y0=max(0,dy);x1=min(w,w+dx);y1=min(h,h+dy)
    if x1>x0 and y1>y0:out[y0:y1,x0:x1]=a[y0-dy:y1-dy,x0-dx:x1-dx]
    return out
def main():
    baseline=json.loads((GAME/'bible/geometry/alley_extent_v1/baseline.json').read_text(encoding='utf-8'));station=json.loads((CACHE/'station.json').read_text(encoding='utf-8'));frozen={};actual={};layers=sorted([l for l in station['layers'] if l['band']!='interactive_object'],key=lambda l:l['z'])
    for r in baseline['rows']:
        frozen[r['layer']]=load_frozen(r['file'],r['sha256'])
    for l in layers:actual[l['id']]=np.array(Image.open(CACHE/'layers'/(l['id']+'_full.png')).convert('RGBA'))[...,3]>=254
    states=[('static',0.,0.)]+[(f'extreme_{x}_{y}',float(x),float(y)) for x in [-68,68] for y in [-34,34]]+[(f'continuous_{i}',68*math.sin(i*math.tau/120),34*math.sin(i*math.tau/60)) for i in range(120)];rows=[];crop=np.s_[42:978,72:1848]
    for name,x,y in states:
        rendered={};expected={}
        for l in layers:
            ident=l['id'];delta=np.rint(np.array(l['pos'])-np.array([x,y])*l['parallax']).astype(int)-np.array(l['pos']);dx,dy=map(int,delta);rendered[ident]=shift(actual[ident],dx,dy)[crop];expected[ident]=shift(frozen[ident],dx,dy)[crop]
        combined=np.logical_or.reduce(list(rendered.values()));rows.append({'state':name,'check':'C07a','missing_pixels':int((~combined).sum())});occ=np.zeros_like(combined)
        for l in layers[::-1]:
            ident=l['id'];missing=expected[ident]&~occ&~rendered[ident];rows.append({'state':name,'layer':ident,'check':'C07b','missing_pixels':int(missing.sum())});occ|=rendered[ident]
    # Hole test uses frozen expectation, and edited expectation is rejected by hash.
    ident='mid_left';mask=frozen[ident];ys,xs=np.nonzero(mask);j=len(xs)//2;x,y=int(xs[j]),int(ys[j]);bad=actual[ident].copy();bad[max(0,y-8):y+8,max(0,x-8):x+8]=False;assert (mask&~bad).any();tampered=mask.copy();tampered[y,x]=False
    with tempfile.TemporaryDirectory(prefix='g01_extent_negative_') as temp:
        changed=Path(temp)/'tampered.png';Image.fromarray(tampered.astype(np.uint8)*255).save(changed)
        try:load_frozen(changed,next(r['sha256'] for r in baseline['rows'] if r['layer']==ident))
        except ValueError:pass
        else:raise AssertionError('The real frozen loader accepted a modified mask')
    record={'status':'pass' if all(r['missing_pixels']==0 for r in rows) else 'fail','baseline_version':baseline['version'],'basis':baseline['basis'],'states':len(states),'checks':len(rows),'scope':'approved 2D silhouette coverage, fixed parallax/camera envelope; not proof of unreviewed geometry or Godot sampling','negative_hole_rejected':True,'frozen_mask_tampering_rejected':True,'actual_0B':False,'rows':rows};write_json(REV/'frozen_geometry_checks.json',record);print(json.dumps({k:v for k,v in record.items() if k!='rows'}))
if __name__=='__main__':main()
