"""Assemble T03 previews and conservative manually annotated inspection masks."""
import json
from pathlib import Path
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from scipy import ndimage as ndi
import yaml
from artlib import GAME, write_json, yprime, effective_radius
from checks import run
from t03_stage import REPORT, CACHE

SIZE=(1776,936)

def polygon(points):
    im=Image.new('L',SIZE);ImageDraw.Draw(im).polygon(points,fill=255)
    return np.asarray(im)>0

def save_mask(name,a):
    path=CACHE/(name+'.png');Image.fromarray((a*255).astype('uint8')).save(path)
    return str(path)

def capped(image):
    a=np.array(image.convert('RGBA'));before=yprime(a)
    scale=np.minimum(1,.75/np.maximum(before,1e-9))
    a[...,:3]=np.floor(a[...,:3]*scale[...,None]).astype('uint8')
    return Image.fromarray(a),float((before>.75).mean())

def main():
    out=REPORT/'gallery';out.mkdir(exist_ok=True)
    jobs=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'))
    byid={j['id']:j for j in jobs}
    hud=json.loads((GAME/'assets/ui/hud_layout.json').read_text(encoding='utf-8'))
    norms={};records={}
    for j in jobs:
        im=Image.open(j['output']).convert('RGBA')
        if j['id'].startswith('frame_'):
            im=ImageOps.fit(im,SIZE,Image.Resampling.LANCZOS)
            how='aspect-preserving scale and center crop to 1776x936'
        else:
            alpha=np.asarray(im)[...,3]>=128
            yy,xx=np.nonzero(alpha)
            box=(int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1))
            im=im.crop(box)
            target={'wick_lit':(36,64),'wick_out':(36,64),'ammo_full':(32,48),'ammo_empty':(32,48),'score_frame':(112,112),'prompt_frame':(600,72)}[j['id']]
            if j['id'].startswith('wick'):
                fit=ImageOps.contain(im,target,Image.Resampling.LANCZOS);im=Image.new('RGBA',target);im.alpha_composite(fit,((target[0]-fit.width)//2,(target[1]-fit.height)//2))
            else:im=im.resize(target,Image.Resampling.LANCZOS)
            how='crop to alpha>=128 bounds, preserve alpha inside crop, resize to temporary HUD cell; wick aspect preserved'
            records[j['id']]={'crop':box,'source_C03':run('C03',{'file':j['output']})}
        path=out/(j['id']+'_normalized.png');im.save(path);norms[j['id']]=im
        records.setdefault(j['id'],{}).update(file=str(path),size=list(im.size),normalization=how)
    frames={};raws={}
    for state in ['unlit','lit']:
        im=norms['frame_'+state].copy();raws[state]=im.copy()
        for i in range(5):im.alpha_composite(norms['wick_lit' if i<4 else 'wick_out'],(24+44*i,848))
        for i in range(6):im.alpha_composite(norms['ammo_full' if i<4 else 'ammo_empty'],(1530+38*i,864))
        im.alpha_composite(norms['score_frame'],(1640,24));im.alpha_composite(norms['prompt_frame'],(588,24))
        im,clipped=capped(im);im.save(out/f'{state}.png');frames[state]=im
        ImageOps.grayscale(im).resize((222,117),Image.Resampling.LANCZOS).save(out/f'{state}_thumbnail.png')
        records['frame_'+state]['postprocess']={'operation':'render-contract Yprime cap at .75 including HUD','fraction_affected':clipped}
    # Conservative primary regions are annotated on the generated image, not copied from the whitebox.
    definitions={
      'resident':{'roi':[(632,546),(656,535),(700,536),(723,548),(737,581),(729,603),(651,607),(628,588)],'bbox':[590,375,214,492],'weak_center':[703,563],'weak_radius':13},
      'crow':{'roi':[(977,442),(1009,439),(1047,444),(1086,463),(1111,493),(1103,527),(1076,550),(1037,542),(1001,517),(981,487)],'bbox':[881,349,360,282],'weak_center':[1054,487],'weak_radius':15},
      'lamp':{'roi':[(1266,473),(1280,439),(1308,415),(1341,409),(1373,415),(1403,439),(1425,473),(1425,483),(1266,483)],'bbox':[1255,398,181,95],'weak_center':None,'weak_radius':0}}
    gray=yprime(np.asarray(raws['unlit']))
    red=(np.asarray(raws['unlit'])[...,0]>100)&(np.asarray(raws['unlit'])[...,0]>np.asarray(raws['unlit'])[...,1]*1.5)
    protected=polygon([(0,691),(43,667),(100,739),(163,754),(191,854),(381,885),(381,936),(0,936)])|polygon([(1557,797),(1600,748),(1690,789),(1775,776),(1775,936),(1514,936)])
    protection_path=save_mask('protected_foreground',protected)
    zero=save_mask('zero',np.zeros((936,1776),bool))
    target_checks={};annotation={};union=np.zeros((936,1776),bool)
    for name,d in definitions.items():
        region=polygon(d['roi'])
        if name!='lamp':region=region&((gray<.19)|red)
        region=ndi.binary_fill_holes(region)
        weak=np.zeros_like(region)
        if d['weak_center']:
            x,y=d['weak_center'];yy,xx=np.ogrid[:936,:1776]
            weak=((xx-x)**2+(yy-y)**2<=d['weak_radius']**2)&red
        primary=save_mask(name+'_primary',region);weak_path=save_mask(name+'_weak',weak)
        c09=run('C09',{'primary':primary,'protected':protection_path,'weak':weak_path,'content_size':list(SIZE),'motion_bbox':d['bbox'],'hud_rects':[v['rect'] for v in hud['reserved'].values() if v['when']=='playing']})
        # Genuine background behind an actor is unavailable in a flattened generated frame.
        # Adjacent-ring contrast is useful evidence, never a substitute underlayer for C06.
        ring=ndi.binary_dilation(region,iterations=20)&~ndi.binary_dilation(region,iterations=5)
        contrast=abs(float(np.median(gray[region]))-float(np.median(gray[ring])))
        target_checks[name]={'C09':c09,'C06':run('C06',{'state':'normal','file':str(out/'unlit.png'),'target':primary}),
            'adjacent_contrast_proxy':{'difference':contrast,'status':'diagnostic_only','reason':'Ring includes nearby geometry; not the hidden layer behind the actor'}}
        annotation[name]={**d,'primary':primary,'weak':weak_path,'effective_radius':c09['details']['effective_radius'],'static_candidate_only':True}
        union|=region
    write_json(REPORT/'annotations.json',{'source':'executor conservative manual polygons on actual generated unlit frame','requires_human_confirmation':True,'targets':annotation,'protected':protection_path,'planned_layout':'layout_plan.json'})
    overlay=frames['unlit'].copy();d=ImageDraw.Draw(overlay);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    tint=np.zeros((936,1776,4),dtype='uint8');tint[protected]=(230,50,150,90)
    overlay=Image.alpha_composite(overlay,Image.fromarray(tint));d=ImageDraw.Draw(overlay)
    for name,a in annotation.items():
        m=np.asarray(Image.open(a['primary']))>=128;edge=m^ndi.binary_erosion(m)
        layer=np.zeros((936,1776,4),dtype='uint8');layer[edge]=(70,245,160,255)
        overlay=Image.alpha_composite(overlay,Image.fromarray(layer));d=ImageDraw.Draw(overlay)
        x,y,w,h=a['bbox'];d.rectangle((x,y,x+w,y+h),outline='#63b8ed',width=2)
        d.text((x,y-25),f"{name} r={a['effective_radius']:.1f}",fill='#74ffc3',font=font)
        if a['weak_center']:
            cx,cy=a['weak_center'];r=a['weak_radius'];d.ellipse((cx-r,cy-r,cx+r,cy+r),outline='#ef754a',width=2)
    for name,r in hud['reserved'].items():
        if r['when']!='playing':continue
        x,y,w,h=r['rect'];d.rectangle((x,y,x+w,y+h),outline='#f4c75d',width=3);d.text((x+3,y+3),name,font=font,fill='#f4c75d')
    d.rectangle((60,60,1716,876),outline='#f99a61',width=3);overlay.save(out/'overlay.png')
    full_checks={}
    for state,im in frames.items():
        full_checks[state]={'C03':run('C03',{'file':str(out/f'{state}.png')}),'C06':{'status':'pending','reason':'Flattened screen has no isolated underlayer; human 1/8 thumbnail recognition and later layer contrast required'},'C09':{'status':'fail' if any(c['C09']['status']=='fail' for c in target_checks.values()) else 'pending','reason':'Numeric static annotations available; masks and motion extremes require review'},'C14':run('C14',{})}
        full_checks[state]['C14']['reference_review']='12 A1 anchors approved for named properties; no calibrated model score'
        full_checks[state]['C13']={}
        for profile,pad in [('monitor',22),('tv',47)]:
            screen=Image.new('RGB',(1920+2*pad,1080+2*pad),'black');screen.paste('white',(pad,pad,pad+1920,pad+1080));screen.paste('black',(pad+24,pad+24,pad+1896,pad+1056));screen.paste(im.convert('RGB'),(pad+72,pad+72));path=out/f'{state}_{profile}_display.png';screen.save(path)
            full_checks[state]['C13'][profile]=run('C13',{'file':str(path),'full_display_frame':True})
    diff=np.maximum(0,yprime(np.asarray(raws['lit']))-yprime(np.asarray(raws['unlit'])))
    Image.fromarray(np.rint(np.clip(diff,0,1)*255).astype('uint8')).filter(ImageFilter.GaussianBlur(2)).save(out/'light_difference.png')
    write_json(REPORT/'checks.json',{'frames':full_checks,'targets':target_checks,'normalization':records,'light_edit_evidence':{'mean_positive_Yprime_difference':float(diff.mean()),'fraction_increased_by_0_03':float((diff>.03).mean()),'not_a_production_spill_mask':True}})
    ledger=json.loads((REPORT/'calls.json').read_text(encoding='utf-8'))
    for c in ledger['calls']:
        if c['attempt']==byid[c['id']]['attempt']:c['normalization']=records[c['id']]
        else:
            c['normalization']={'status':'superseded_attempt_original_retained','reason':'Lamp target too small; background readability improvement'}
            c['review_status']='superseded_by_executor_prescreen'
    write_json(REPORT/'manifest.json',{'task':'T03','status':'pending_A1b_review','production_asset_approved':False,'calls':ledger['calls'],'cost':None,'cost_status':'not_reported'})
    if not (REPORT/'review.yaml').exists():
        (REPORT/'review.yaml').write_text(yaml.safe_dump({'stage':'A1b','status':'awaiting_human_review','items':[{'id':x,'status':'pending','note':''} for x in ['unlit','lit','overlay']],'overall_notes':''},allow_unicode=True,sort_keys=False),encoding='utf-8')
    shutil.copy2(Path(__file__).with_name('t03_gallery.html'),out/'index.html')
    print(json.dumps({'radii':{n:v['effective_radius'] for n,v in annotation.items()},'C09':{n:v['C09']['status'] for n,v in target_checks.items()},'C13':{s:{p:r['status'] for p,r in v['C13'].items()} for s,v in full_checks.items()}}))

if __name__=='__main__':main()
