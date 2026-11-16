"""Evidence-based checks. Missing inputs never mean pass."""
import json
import math
import shutil
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.color import rgb2lab, deltaE_ciede2000
from artlib import rgba, mask, yprime, effective_radius, decode_sdf

IDS = ['C01','C02','C03','C04','C05','C06','C07a','C07b','C08','C09','C10','C11','C12','C13','C14','C15','C16']

def result(status, reason, **details):
    assert status in {'pass','fail','pending','na'}
    return dict(status=status, reason=reason, details=details)

def verdict(ok, reason, **details):
    return result('pass' if ok else 'fail', reason, **details)

def check_ocr_data(data, expected):
    text = ''.join(data['text'].split())
    details = dict(recognized=text, confidence=data['confidence'], engine=data['engine'])
    # Keep low-confidence detections for visual confirmation.
    has_confident_word = any(word['confidence'] >= 85 and len(word['text']) >= 2
                             for word in data.get('words', []))
    if text and data['confidence'] < 70 and not has_confident_word:
        return result('pending', 'Low-confidence OCR needs visual confirmation', **details)
    return verdict(text == expected, 'OCR text versus permitted text', **details)


def overlap(a,b):
    x,y,w,h=a; X,Y,W,H=b
    return x<X+W and X<x+w and y<Y+H and Y<y+h

def run(check, spec, base=Path('.')):
    """Spec is a JSON/YAML dict, file paths relative to base."""
    base=Path(base)
    def path(key): return base/spec[key]
    if spec.get('applicable') is False:
        if not spec.get('reason'): raise ValueError('NA requires a reason')
        return result('na',spec['reason'])
    try:
        return _run(check,spec,path,base)
    except (KeyError,FileNotFoundError,ModuleNotFoundError) as e:
        return result('pending',f'Missing input/dependency: {e}')

def _run(check,s,p,base):
    if check=='C01':
        im=Image.open(p('file'))
        mode='RGBA' if s['kind']=='color' else 'L'
        return verdict(im.format=='PNG' and im.mode==mode and (not s.get('size') or list(im.size)==s['size']),
                       'PNG format, channel mode and declared size',mode=im.mode,size=im.size)
    if check=='C02':
        a=rgba(p('file')); semi=(a[...,3]>0)&(a[...,3]<255)
        matte=np.array(s['matte_rgb'])
        contaminated=semi & (np.linalg.norm(a[...,:3].astype(float)-matte,axis=-1)<s.get('matte_tolerance',10))
        fraction=float(contaminated.sum()/max(1,semi.sum()))
        return verdict(fraction<=.01,'Known matte color residue in semi-transparent pixels',fraction=fraction,
                       limitation='Black/white composite evidence still requires visual review')
    if check=='C03':
        a=rgba(p('file')); weight=np.where(a[...,3]>=128,a[...,3]/255,0)
        if not weight.any(): return result('fail','No visible pixels')
        y=yprime(a); clipped=float((weight*(y>.75)).sum()/weight.sum())
        ok=clipped<=.02
        if 'band_range' in s:
            mean=float((weight*y).sum()/weight.sum()); low,high=s['band_range']
            ok=ok and low<=mean<=high
        return verdict(ok,'Visible alpha-weighted encoded luminance',clipped_fraction=clipped)
    if check=='C04':
        a=rgba(p('file')); visible=a[...,3]>=128
        if not visible.any(): return result('fail','No visible pixels')
        rgb=a[...,:3][visible]/255.; weight=a[...,3][visible]/255.
        palette=np.asarray(s['palette_rgb'])/255.
        lab=rgb2lab(rgb.reshape(-1,1,3)).reshape(-1,3)
        plab=rgb2lab(palette.reshape(-1,1,3)).reshape(-1,3)
        nearest=np.full(len(lab),np.inf)
        for color in plab: nearest=np.minimum(nearest,deltaE_ciede2000(lab,np.broadcast_to(color,lab.shape)))
        coverage=float(weight[nearest<=s.get('delta_e',15)].sum()/weight.sum())
        return verdict(coverage>=.9,'Palette coverage after caller excludes permitted cinnabar/light layers',coverage=coverage)
    if check=='C05':
        exe=shutil.which('tesseract')
        if not exe:
            node=shutil.which('node')
            if not node:return result('pending','No usable OCR runtime')
            try:
                proc=subprocess.run([node,str(Path(__file__).with_name('ocr.cjs')),str(p('file').resolve())],capture_output=True,text=True,encoding='utf-8',timeout=90)
                if proc.returncode:return result('pending','Bundled OCR invocation failed',error=proc.stderr[-1000:])
                return check_ocr_data(json.loads(proc.stdout), s.get('expected_text', ''))
            except (subprocess.TimeoutExpired,json.JSONDecodeError) as e:
                return result('pending','Bundled OCR unavailable',error=str(e))
        proc=subprocess.run([exe,str(p('file')),'stdout','-l',s.get('language','chi_sim+eng')],capture_output=True,text=True,encoding='utf-8')
        if proc.returncode: return result('pending','OCR invocation failed',error=proc.stderr)
        text=''.join(proc.stdout.split()); expected=s.get('expected_text','')
        return verdict(text==expected,'OCR text versus permitted text',recognized=text)
    if check=='C06':
        if s['state']=='warning': return result('pending','Warning readability needs visual model/human evidence')
        a=rgba(p('file')); region=mask(p('target')); background=rgba(p('background'))
        if not region.any(): return result('fail','Empty target')
        contrast=float(np.median(np.abs(yprime(a)[region]-yprime(background)[region])))
        threshold=.3 if s['state']=='hardened' else .2
        numeric=contrast>=threshold and (s['state']!='hardened' or s['eye_length']>=16)
        if not numeric: return result('fail','Readability contrast/size',contrast=contrast)
        return result('pending','Numeric contrast passed; thumbnail recognition has not been reviewed',contrast=contrast)
    if check in {'C07a','C07b'}:
        if check=='C07a':
            alphas=[rgba(base/f)[...,3]/255 for f in s['layers']]
            if not alphas: return result('fail','No layers')
            combined=1-np.prod([1-a for a in alphas],axis=0)
            missing=combined<.999
        else:
            extent=mask(p('extent')); alpha=rgba(p('file'))[...,3]>=254
            occlusion=mask(p('occlusion'))
            missing=extent & ~occlusion & ~alpha
        return verdict(not missing.any(),'Coverage at this declared motion state',missing_pixels=int(missing.sum()))
    if check=='C08':
        expected=rgba(p('file'))[...,3]>=128
        difference=expected ^ mask(p('block_mask'))
        return verdict(not difference.any(),'Shot-blocking mask matches visible layer',different_pixels=int(difference.sum()))
    if check=='C09':
        primary=mask(p('primary')); protected=mask(p('protected')); weak=mask(p('weak'))
        radius,_=effective_radius(primary)
        bad_overlap=bool((primary & protected).any()); bad_weak=bool((weak & ~primary).any())
        w,h=s['content_size']; bbox=s['motion_bbox']; x,y,bw,bh=bbox
        in_bounds=x>=60 and y>=60 and x+bw<=w-60 and y+bh<=h-60
        hud=any(overlap(bbox,r) for r in s['hud_rects'])
        return verdict(radius>=40 and not bad_overlap and not bad_weak and in_bounds and not hud,
                       'Primary size, visible protection, weak point and motion reservation',
                       effective_radius=radius,protected_overlap=bad_overlap,weak_outside=bad_weak,hud_overlap=hud)
    if check=='C10':
        expected=set(s['expected_parts']); actual=s['parts']
        if len(actual)!=len(set(actual)) or set(actual)!=expected:
            return result('fail','Rig part list mismatch',expected=sorted(expected),actual=actual)
        if 'pose_seam_errors' not in s: return result('pending','Part list passed; rendered extreme-pose seam evidence missing')
        return verdict(max(s['pose_seam_errors'],default=0)<=2 and s['copper_clear'],
                       'Extreme-pose seams and copper coverage',rig=s['rig'])
    if check=='C11':
        body=mask(p('body')); core=mask(p('core'))
        if (core & ~body).any(): return result('fail','Core lies outside visible body')
        return result('pending','Static containment passed; complete state/frame/alignment evidence missing')
    if check=='C12':
        frames=[rgba(base/f).astype(float) for f in s['frames']]
        if len(frames)<3: return result('pending','Need at least three aligned frames')
        dif=float(np.abs(frames[-1]-frames[0]).mean()/255)
        speed=float(np.abs((frames[1]-frames[0])-(frames[-1]-frames[-2])).mean()/255)
        return verdict(dif<=s['pixel_threshold'] and speed<=s['velocity_threshold'],
                       'Aligned loop endpoint position and velocity',pixel_difference=dif,velocity_difference=speed)
    if check=='C13':
        if not s['full_display_frame']:return result('pending','Full display frame including border required')
        from artlib import ROOT
        interpreter=ROOT/'.venv/Scripts/python.exe'
        if not interpreter.exists():return result('pending','Tracker interpreter with cv2 is unavailable')
        proc=subprocess.run([str(interpreter),'-B',str(Path(__file__).with_name('tracker_screen.py')),str(p('file').resolve())],capture_output=True,text=True,timeout=60)
        if proc.returncode:return result('pending','Tracker screening invocation failed',error=proc.stderr)
        return json.loads(proc.stdout)
    if check=='C14':
        return result('pending','No calibrated visual-model review; never infer a style score from file metadata')
    if check=='C15':
        # Disk size never enters the estimate. Padded atlas allocations count in full.
        total=0
        for t in s['textures']:
            w,h=t['size']; bpp=t['bytes_per_pixel']
            size=w*h*bpp
            if t.get('mipmaps'):
                while w>1 or h>1:
                    w=max(1,w//2); h=max(1,h//2); size+=w*h*bpp
            total+=math.ceil(size)
        if total>s['limit_bytes']: return result('fail','Offline texture estimate exceeds budget',bytes=total)
        return result('pending','Offline estimate fits; Godot import/peak measurement pending',bytes=total)
    if check=='C16':
        raw=np.asarray(Image.open(p('sdf')))
        if raw.ndim!=2: return result('fail','SDF must be one-channel data')
        if s['source_color']: return result('fail','Data texture incorrectly declared as color')
        truth=mask(p('alpha')); decoded=decode_sdf(raw)>=0
        if not truth.any() or truth.all(): return result('fail','Non-trivial shape required')
        edge=lambda a: a ^ ndi.binary_erosion(a)
        e1,e2=edge(truth),edge(decoded)
        if not e2.any(): return result('fail','Decoded SDF has no contour')
        error=float(max(ndi.distance_transform_edt(~e1)[e2].max(),ndi.distance_transform_edt(~e2)[e1].max()))
        return verdict(error<=1,'Offline SDF round-trip; engine sampling is a separate pending check',max_error_px=error)
    raise ValueError(f'Unknown check: {check}')

def suite(specs,base,output):
    from artlib import write_json
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    results={}
    for check in IDS:
        r=run(check,specs.get(check,{}),base)
        results[check]=r
        # Every result has inspectable evidence; only render image evidence where relevant inputs exist.
        write_json(output/f'{check}.json',r)
        spec=specs.get(check,{})
        if 'file' in spec and (Path(base)/spec['file']).exists():
            im=Image.open(Path(base)/spec['file']).convert('RGBA')
            im.thumbnail((960,540)); im.save(output/f'{check}.png')
    write_json(output/'checks.json',results)
    return results
