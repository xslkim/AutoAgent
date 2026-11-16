"""Prepare two ink-only enemies, shared-coordinate layers, SDFs and offline effects."""
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageEnhance,ImageOps
from scipy import ndimage as ndi
from artlib import GAME,write_json,encode_sdf,effective_radius,crop_bleed,yprime
from paper_ops import alpha_crop,limit_luminance,raw_checks
from preview import movie
from checks import run

REPORT=GAME/'reports/art/T06';CACHE=Path('D:/gunforge_cache/g01/T06');S=1024

def warp(image,reference_size,scale,center):
    im=image.convert('RGBA')
    if im.size!=reference_size:im=im.resize(reference_size,Image.Resampling.LANCZOS)
    # All channels use exactly the same source-to-asset affine transform.
    return im.transform((S,S),Image.Transform.AFFINE,(1/scale,0,center[0]-S/2/scale,0,1/scale,center[1]-S/2/scale),Image.Resampling.BICUBIC)

def cut(name,im,folder):
    array=np.array(im.convert('RGBA'));crop,origin=crop_bleed(array);path=folder/(name+'.png');Image.fromarray(crop).save(path)
    return {'file':path.name,'crop_origin':origin,'size':list(Image.open(path).size)}

def prepare_one(name,design_path,body_path,eyes_path):
    folder=CACHE/name;folder.mkdir(exist_ok=True)
    gallery=REPORT/'gallery';gallery.mkdir(exist_ok=True)
    design=Image.open(design_path).convert('RGBA');a=np.array(design);m=a[...,3]>=128
    dist=ndi.distance_transform_edt(m);cy,cx=np.unravel_index(dist.argmax(),dist.shape)
    yy,xx=np.nonzero(m);extent=max(cx-xx.min(),xx.max()-cx,cy-yy.min(),yy.max()-cy)
    scale=455/max(1,extent);center=[int(cx),int(cy)]
    registered=warp(design,design.size,scale,center);body=warp(Image.open(body_path),design.size,scale,center)
    arr=np.array(registered);rgb=arr[...,:3].astype(float);red=(rgb[...,0]>70)&(rgb[...,0]>rgb[...,1]*1.6)&(rgb[...,0]>rgb[...,2]*1.4)&(arr[...,3]>0)
    core=arr.copy();core[~red,3]=0;core=Image.fromarray(core)
    body=limit_luminance(body,.599)
    ba=np.array(body);visible=ba[...,3]>=128;lum=yprime(ba)
    # Keep the existing 5%/.60 limits; do not loosen checks to match the candidate.
    q=float(np.quantile(lum[visible],.95));gloss_factor=min(1,.219/max(q,1e-9))
    ba[...,:3]=np.floor(ba[...,:3]*gloss_factor).astype('uint8');body=Image.fromarray(ba)
    ma=np.asarray(body)[...,3]>=128;coremask=np.asarray(core)[...,3]>=128
    if coremask.any():ys,xs=np.nonzero(coremask);core_center=[float(xs.mean()),float(ys.mean())]
    else:core_center=[512.,512.]
    eyes,_=alpha_crop(Image.open(eyes_path).convert('RGBA'),pad=2);eyes=eyes.resize((208,40),Image.Resampling.LANCZOS)
    eye_layer=Image.new('RGBA',(S,S));eye_layer.alpha_composite(eyes,(round(core_center[0]-104),round(core_center[1]-20)))
    body.save(folder/'body_full.png');core.save(folder/'core_full.png');eye_layer.save(folder/'core_hardened_full.png')
    Image.fromarray(encode_sdf(ma)).save(folder/'sdf_full.png');Image.fromarray((ma*255).astype('uint8')).save(folder/'alpha_full.png')
    files={'body':cut('body',body,folder),'core':cut('core',core,folder),'core_hardened':cut('core_hardened',eye_layer,folder)}
    crop_box=files['body']['crop_origin'];size=files['body']['size'];sdf=Image.open(folder/'sdf_full.png').crop((crop_box[0],crop_box[1],crop_box[0]+size[0],crop_box[1]+size[1]));sdf.save(folder/'sdf.png');files['sdf']={'file':'sdf.png','crop_origin':crop_box,'size':size,'source_color':False,'midpoint':128,'distance_range':32}
    bbox=body.getbbox();extent=max(bbox[2]-bbox[0],bbox[3]-bbox[1]);minimum=None;measurements=[]
    # Tadpole size is defined by its head, not the tail. Head is the largest inscribed disk.
    head_radius=float(ndi.distance_transform_edt(ma).max())
    for display in range(200 if name=='crow' else 90,361 if name=='crow' else 131,10):
        factor=display/extent if name=='crow' else display/(2*head_radius)
        pixels=np.asarray(Image.fromarray((ma*255).astype('uint8')).resize((max(1,round(S*factor)),max(1,round(S*factor))),Image.Resampling.NEAREST))>=128
        if name!='crow':
            # Restrict the primary target to the head disk in display coordinates.
            d=ndi.distance_transform_edt(ma);hy,hx=np.unravel_index(d.argmax(),d.shape);yy,xx=np.ogrid[:S,:S];head=((xx-hx)**2+(yy-hy)**2<=head_radius**2)&ma
            pixels=np.asarray(Image.fromarray((head*255).astype('uint8')).resize((max(1,round(S*factor)),max(1,round(S*factor))),Image.Resampling.NEAREST))>=128
        radius,_=effective_radius(pixels);measurements.append({'display_size':display,'effective_radius':radius})
        if radius>=40 and minimum is None:minimum=display
    model={'id':'g01_ink_'+name,'kind':'enemy','human':False,'asset_canvas':[S,S],'origin':[512,512],'files':files,'core_center':core_center,'source_registration':{'original_size':list(design.size),'scale':scale,'center':center},'display':{'minimum':minimum,'maximum':360 if name=='crow' else 130,'measure':'longest_extent' if name=='crow' else 'head_diameter'},'material':{'gloss':'brighter_than_T03_restrained_wet','cinnabar':'flat_stamp','highlight_area_max':.05,'highlight_Yprime_max':.60},'shader_parameters':{'wobble_amplitude':2.0,'edge_bleed':1.5,'dissolve_noise_scale':16,'warning_pulse_hz':1.5,'hardened_saturation':.15},'approval':'pending_A2'}
    write_json(folder/'enemy.json',model)
    c11=run('C11',{'body':str(folder/'alpha_full.png'),'core':str(folder/'core_full.png')})
    # C11 expects a grayscale mask, not RGB intensity of a red stamp.
    Image.fromarray((coremask*255).astype('uint8')).save(folder/'core_mask.png')
    c11=run('C11',{'body':str(folder/'alpha_full.png'),'core':str(folder/'core_mask.png')})
    checks={'C01':run('C01',{'file':str(folder/'body_full.png'),'kind':'color','size':[S,S]}),'C03':run('C03',{'file':str(folder/'body_full.png')}),'C11':c11,'C16':run('C16',{'alpha':str(folder/'alpha_full.png'),'sdf':str(folder/'sdf_full.png'),'source_color':False}),'C14':run('C14',{}),'minimum_size_evidence':measurements,'eye_containment':{'status':'pass' if not ((np.asarray(eye_layer)[...,3]>=128)&~ma).any() else 'fail'},'raw_body_red_pixels':int(((np.asarray(body)[...,0].astype(float)>np.asarray(body)[...,1]*1.6)&(np.asarray(body)[...,0]>70)&ma).sum()),'gloss_normalization':{'maximum_luminance':.599,'quantile_scale':gloss_factor,'source_preserved':True}}
    rgba=np.array(body);highlight=(yprime(rgba)>.22)&ma
    checks['highlight_screen']={'status':'pass' if float(highlight.sum()/max(1,ma.sum()))<=.05 and float(yprime(rgba)[ma].max())<=.60 else 'fail','bright_fraction_over_Yprime_0_22':float(highlight.sum()/max(1,ma.sum())),'max_Yprime':float(yprime(rgba)[ma].max()),'reason':'Conservative brightness proxy, not a semantic specular-area measurement'}
    for state in ['normal','warning','hardened','hit','dissolve']:
        bg=Image.new('RGBA',(S,S),(115,121,132,255));layer=body.copy();stamp=(eye_layer if state=='hardened' else core).copy()
        if state=='hardened':layer=ImageEnhance.Color(layer).enhance(.1)
        if state in ['hit','dissolve']:
            ar=np.array(layer);ar[...,3]=(ar[...,3]*(.65 if state=='hit' else .25)).astype('uint8');layer=Image.fromarray(ar)
            ar=np.array(stamp);ar[...,3]=(ar[...,3]*(.65 if state=='hit' else .25)).astype('uint8');stamp=Image.fromarray(ar)
        bg.alpha_composite(layer);bg.alpha_composite(stamp);bg.resize((600,600),Image.Resampling.LANCZOS).save(gallery/(name+'_'+state+'.png'))
    frames=[];cycle=[]
    for i in range(16):
        t=i/15;layer=Image.new('RGBA',(S,S));layer.alpha_composite(body,(round(math.sin(t*math.tau)*3),0));layer.alpha_composite(core,(round(math.sin(t*math.tau)*3),0));path=folder/(f'loop_{i:02}.png');layer.resize((360,360),Image.Resampling.LANCZOS).save(path);cycle.append(str(path));bg=Image.new('RGBA',(S,S),(115,121,132,255));bg.alpha_composite(layer);frames.append(bg.resize((600,600)))
    checks['C12']=run('C12',{'frames':cycle,'pixel_threshold':.02,'velocity_threshold':.02})
    movie(frames*5,gallery/(name+'_motion.mp4'),fps=15)
    write_json(REPORT/(name+'_checks.json'),checks)
    return model,checks

def main():
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'));jobs={j['id']:j for j in queue if j['state']=='returned'}
    eye=jobs['crow_eyes']['output'];results={}
    model,c=prepare_one('crow',jobs['crow_design']['output'],jobs['crow_body']['output'],eye);results['crow']={'minimum':model['display']['minimum'],'C16':c['C16']['status']}
    for i in range(3):
        model,c=prepare_one('tadpole'+str(i),jobs['tadpole_pose'+str(i)]['output'],jobs['tadpole_body'+str(i)]['output'],eye);results['tadpole'+str(i)]={'minimum':model['display']['minimum'],'C16':c['C16']['status']}
    # Optional small offline loop atlas: 16 tiles, padded GPU allocation recorded separately.
    atlas=Image.new('RGBA',(1536,1536))
    for i in range(8):
        for row,name in [(0,'crow'),(2,'tadpole0')]:
            im=Image.open(CACHE/name/(f'loop_{i*2:02}.png')).convert('RGBA');atlas.alpha_composite(im,((i%4)*384+12,(row+i//4)*384+12))
    atlas.save(REPORT/'gallery/loop_atlas.png');write_json(REPORT/'atlas.json',{'size':[1536,1536],'format':'RGBA8','mipmaps':False,'allocated_bytes':1536*1536*4,'display_cell':[360,360],'frame_rate':15,'loops':{'crow':8,'tadpole0':8},'offline_preview_only':True})
    print(json.dumps(results))

if __name__=='__main__':
    main()
    if (REPORT.parent/'T07/revisions/A2c/user_feedback.yaml').exists():
        from enemy_feedback_v3 import main as build_feedback
    else:
        from enemy_feedback import main as build_feedback
    build_feedback()
