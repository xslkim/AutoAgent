"""Deterministic normalization and inspectable paper-asset diagnostics."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.color import rgb2lab,deltaE_ciede2000
from artlib import GAME, yprime, write_json
from checks import run

def palette(include_ink=False):
    colors=json.loads((GAME/'bible/palette.json').read_text(encoding='utf-8'))['colors']
    return [list(bytes.fromhex(c['hex'][1:])) for c in colors if c['hex']!='#C8322C' and (include_ink or c['hex']!='#0B0B0E')]

def limit_luminance(image,high=.75):
    a=np.array(image.convert('RGBA'));lum=yprime(a)
    factor=np.minimum(1,high/np.maximum(lum,1e-9))
    a[...,:3]=np.floor(a[...,:3]*factor[...,None]).astype('uint8')
    return Image.fromarray(a)

def paper_palette(image,level='middle',include_ink=False,delta_e=14.3):
    """Color correction required by production steps; originals stay untouched."""
    a=np.array(image.convert('RGBA'));rgb=a[...,:3].astype(float)
    colors=np.array(palette(include_ink=include_ink),dtype=float)
    if level=='near':colors=np.array([[20,26,51],[42,30,61]],dtype=float)
    visible=a[...,3]>=128
    original=rgb[visible]
    lab=rgb2lab((original/255).reshape(-1,1,3)).reshape(-1,3)
    plab=rgb2lab((colors/255).reshape(-1,1,3)).reshape(-1,3)
    distances=np.stack([deltaE_ciede2000(lab,np.broadcast_to(c,lab.shape)) for c in plab],axis=1)
    nearest=distances.argmin(axis=1);outside=distances.min(axis=1)>delta_e+.2
    index_image=np.zeros(a.shape[:2],dtype='int16');index_image[visible]=nearest
    stable=ndi.median_filter(index_image,size=5)[visible]
    local=ndi.gaussian_filter(yprime(a),1.5)[visible]
    strong_detail=np.abs(yprime(a)[visible]-local)>.04
    nearest=np.where(strong_detail,nearest,stable)
    # Move only out-of-range pixels by the minimum needed; preserve facial features,
    # existing paper fibers and all pixels already within the palette tolerance.
    src=original[outside];dst=colors[nearest[outside]];target=plab[nearest[outside]]
    lo=np.zeros(len(src));hi=np.ones(len(src))
    for _ in range(8):
        amount=(lo+hi)/2;mixed=src*(1-amount[:,None])+dst*amount[:,None]
        mlab=rgb2lab((mixed/255).reshape(-1,1,3)).reshape(-1,3)
        too_far=deltaE_ciede2000(mlab,target)>delta_e
        lo=np.where(too_far,amount,lo);hi=np.where(too_far,hi,amount)
    original[outside]=src*(1-hi[:,None])+dst*hi[:,None]
    a[visible,:3]=np.clip(original,0,255).astype('uint8')
    return limit_luminance(Image.fromarray(a))

def fit_full(image,size):
    return image.convert('RGBA').resize(size,Image.Resampling.LANCZOS)

def alpha_crop(image,threshold=128,pad=8):
    a=np.array(image.convert('RGBA'));visible=a[...,3]>=threshold
    if not visible.any():raise ValueError('Empty candidate')
    yy,xx=np.nonzero(visible)
    box=(max(0,int(xx.min())-pad),max(0,int(yy.min())-pad),min(a.shape[1],int(xx.max()+1)+pad),min(a.shape[0],int(yy.max()+1)+pad))
    return Image.fromarray(a).crop(box),list(box)

def raw_checks(file,include_ink=False):
    return {c:run(c,{'file':str(file),**({'kind':'color'} if c=='C01' else {}),**({'palette_rgb':palette(include_ink)} if c=='C04' else {}),**({'expected_text':''} if c=='C05' else {})}) for c in ['C01','C03','C04','C05','C14']}

def component_map(image,min_fraction=.002):
    a=np.array(image.convert('RGBA'));labels,n=ndi.label(a[...,3]>=128)
    rows=[]
    for label,sl in enumerate(ndi.find_objects(labels),1):
        if sl is None:continue
        y,x=sl;region=labels[sl]==label;area=int(region.sum())
        if area<a.shape[0]*a.shape[1]*min_fraction:continue
        yy,xx=np.nonzero(region)
        rows.append({'label':label,'area':area,'bbox':[x.start,y.start,x.stop,y.stop],'center':[float(xx.mean()+x.start),float(yy.mean()+y.start)]})
    return labels,rows

def sheet_diagnostics(file):
    im=Image.open(file).convert('RGBA');labels,rows=component_map(im)
    # Assign by vertical centroid ordering, paired left/right; the guide has five rows.
    ordered=sorted(rows,key=lambda r:r['center'][1]);parts=[]
    for n in range(0,len(ordered),2):parts.extend(sorted(ordered[n:n+2],key=lambda r:r['center'][0]))
    names=['torso','head','upper_arm_l','upper_arm_r','forearm_l','forearm_r','thigh_l','thigh_r','shin_l','shin_r']
    mapping={name:r for name,r in zip(names,parts)}
    return {'component_count':len(rows),'count_complete':len(rows)==10,'mapping':mapping,
            'semantic_review':'executor must verify head/torso/limb identity from original image; counts alone never suffice','source_size':list(im.size)}

def isolated_component(image,label,labels):
    a=np.array(image.convert('RGBA'));a[labels!=label,3]=0
    return alpha_crop(Image.fromarray(a),pad=8)[0]
