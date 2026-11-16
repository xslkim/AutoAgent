"""Normalize generated station layers, preserve coverage evidence and render motion."""
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageOps,ImageFilter
from scipy import ndimage as ndi
from artlib import GAME,write_json,yprime,crop_bleed
from paper_ops import paper_palette,raw_checks
from preview import render,movie
from checks import run

REPORT=GAME/'reports/art/T04';CACHE=Path('D:/gunforge_cache/g01/T04');CANVAS=(1920,1020)
LAYERS=[('far_base',.1,'far'),('far_town',.25,'far'),('mid_ground',.45,'middle'),('mid_left',.55,'middle'),('mid_right',.6,'middle'),('near_left',.9,'near'),('near_right',1.,'near')]

def main():
    jobs=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'));byid={j['id']:j for j in jobs if j['state']=='returned'}
    folder=CACHE/'station';folder.mkdir(exist_ok=True);(folder/'layers').mkdir(exist_ok=True);(folder/'lights').mkdir(exist_ok=True)
    gallery=REPORT/'gallery';gallery.mkdir(exist_ok=True)
    station={'id':'g01_st_l1_01_alley','canvas':list(CANVAS),'content_origin':[72,42],'layers':[],'lights':[],
             'camera_limits':[60,30],'breath_limits':[8,4],'approval':'pending_A2','metadata_scope':'offline prototype only','slots':[
             {'id':'hostage_vendor','human_role':'hostage','is_enemy':False,'space':'mid_ground','bbox':[650,400,230,460],'paper_body_protected':True,'only_attackable_attachment':'separate_ink_blob'},
             {'id':'crow','space':'mid_ground','bbox':[970,290,330,300]}]}
    checks={};alphas={};full_paths={};record={}
    for index,(ident,parallax,band) in enumerate(LAYERS):
        print('Layer '+ident,flush=True)
        job=byid['layer_'+ident]
        if ident=='mid_right' and 'repair_mid_right' in byid:job=byid['repair_mid_right']
        if ident=='near_left' and 'extract_near_left' in byid:job=byid['extract_near_left']
        source=Image.open(job['output']).convert('RGBA').resize(CANVAS,Image.Resampling.LANCZOS)
        corrected=paper_palette(source,'near' if band=='near' else 'middle')
        # Generated paper layers often have semi-transparent interiors. The station
        # contract requires opaque paper, while retaining the outer sub-0.5 AA fringe.
        arr=np.array(corrected);arr[arr[...,3]>=128,3]=255;corrected=Image.fromarray(arr)
        if ident=='far_base':corrected.putalpha(255)
        pos=[0,120] if ident=='mid_ground' else [0,0]
        # Align the generated street's high horizon with the actual distant railing.
        if pos[1]:
            moved=Image.new('RGBA',CANVAS);moved.alpha_composite(corrected,tuple(pos));corrected=moved;pos=[0,0]
        full=folder/'layers'/(ident+'_full.png');corrected.save(full);full_paths[ident]=full
        a=np.array(corrected);alpha=a[...,3]>=128;alphas[ident]=alpha
        mask=Image.fromarray((alpha*255).astype('uint8'));mask.save(folder/'layers'/(ident+'_extent.png'))
        crop,origin=crop_bleed(a);file='layers/'+ident+'.png';Image.fromarray(crop).save(folder/file)
        station['layers'].append({'id':ident,'file':file,'pos':origin,'z':index,'parallax':parallax,'band':band,'extent':'layers/'+ident+'_extent.png','crop_origin':origin,'blocks_shots':band=='near'})
        if band=='near':mask.save(folder/'layers'/(ident+'_block.png'))
        checks[ident]=raw_checks(full)
        checks[ident]['C02']={'status':'pending','reason':'Native alpha retained; black/white composite visual review required, no known matte color supplied'}
        if band=='near':checks[ident]['C08']=run('C08',{'file':str(full),'block_mask':str(folder/'layers'/(ident+'_block.png'))})
        record[ident]={'source_job':job['id'],'normalization':'full-canvas resize to 1920x1020; source registration retained','palette':'minimum RGB movement to CIEDE2000 <=14.5, originals retained','expected_extent':'current full shape support, pending human verification of hidden geometry','ground_registration_shift_y':120 if ident=='mid_ground' else 0}
        preview=Image.new('RGBA',CANVAS,(110,116,127,255));preview.alpha_composite(corrected);preview.convert('RGB').resize((960,510)).save(gallery/(ident+'_layer.jpg'))
    for index,(ident,p,band) in enumerate(LAYERS):
        occlusion=np.zeros((1020,1920),bool);reveal=np.zeros_like(occlusion)
        for front,fp,_ in LAYERS[index+1:]:
            m=alphas[front];dx=math.ceil(68*abs(fp-p));dy=math.ceil(34*abs(fp-p))
            eroded=ndi.minimum_filter(m,size=(max(1,2*dy+1),max(1,2*dx+1)),mode='constant',cval=0)
            occlusion|=m;reveal|=m&~eroded
        fill=alphas[ident]&reveal
        Image.fromarray((fill*255).astype('uint8')).save(folder/'layers'/(ident+'_fill.png'))
        Image.fromarray((occlusion*255).astype('uint8')).save(folder/'layers'/(ident+'_occlusion.png'))
        checks[ident]['C07b']=run('C07b',{'file':str(full_paths[ident]),'extent':str(folder/'layers'/(ident+'_extent.png')),'occlusion':str(folder/'layers'/(ident+'_occlusion.png'))})
        checks[ident]['C07b']['scope']='Declared current-shape support only; does not independently certify intended hidden geometry'
        record[ident]['reveal_band_pixels']=int(fill.sum())
    if 'lamp_off' in byid:
        lamp=Image.open(byid['lamp_off']['output']).convert('RGBA').resize(CANVAS,Image.Resampling.LANCZOS);lamp=paper_palette(lamp)
        a=np.array(lamp);a[a[...,3]>=128,3]=255;lamp=Image.fromarray(a)
        lamp.save(folder/'layers/lamp_full.png');a=np.array(lamp);cropped,origin=crop_bleed(a);Image.fromarray(cropped).save(folder/'layers/lamp.png')
        station['layers'].append({'id':'lamp','file':'layers/lamp.png','pos':origin,'z':4.5,'parallax':.6,'band':'interactive_object','crop_origin':origin,'independent_light':True})
    # Keep a background-only assembled reference for the native lamp-on edit.
    static=render(station,folder);static.save(gallery/'station_unlit.png')
    static.save(CACHE/'assembled_unlit.png')
    states=[('static',(0,0),(0,0))]
    for x in [-60,60]:
        for y in [-30,30]:
            for sign in [1,-1]:states.append((f'cam_{x}_{y}_breath_{sign}',(x,y),(8*sign*(1 if x>0 else -1),4*sign*(1 if y>0 else -1))))
    coverage={}
    for name,camera,breath in states:
        frame=render(station,folder,camera,breath);frame.save(gallery/(name+'.png'))
        # Render each alpha separately in exactly the same declared motion state.
        paths=[]
        for layer in station['layers']:
            im=Image.new('RGBA',CANVAS);src=Image.open(folder/layer['file']).convert('RGBA');x,y=np.array(layer['pos'])-(np.array(camera)+np.array(breath))*layer['parallax'];im.alpha_composite(src,(round(x),round(y)))
            c=im.crop((72,42,1848,978));path=CACHE/(name+'_'+layer['id']+'_coverage.png');c.save(path);paths.append(str(path))
        coverage[name]=run('C07a',{'layers':paths})
    for percent in [0,25,50,75,100]:
        source=static.convert('RGB');target=Image.new('RGB',source.size,(30,33,49));target.paste(source,(round(-1776*percent/100),0));target.save(gallery/(f'transition_{percent}.png'))
    # A true lit-frame edit will replace these provisional no-light previews after generation.
    if 'station_lit_edit' in byid:
        lit=ImageOps.fit(Image.open(byid['station_lit_edit']['output']).convert('RGBA'),(1776,936),Image.Resampling.LANCZOS)
        un=np.asarray(static);la=np.asarray(lit);diff=np.maximum(0,yprime(la)-yprime(un))
        # Spatially reject unrelated edit drift while keeping the measured positive delta.
        field=Image.new('L',(1776,936));fd=ImageDraw.Draw(field);fd.ellipse((1100,390,1555,930),fill=255);field=field.filter(ImageFilter.GaussianBlur(45))
        Image.fromarray(np.rint(np.clip(diff,0,1)*255).astype('uint8')).save(folder/'lights/native_positive_delta.png')
        spill=Image.fromarray(np.rint(np.clip(diff*2,0,1)*np.asarray(field)/255*255).astype('uint8')).filter(ImageFilter.GaussianBlur(5));full=Image.new('L',CANVAS);full.paste(spill,(72,42));full.save(folder/'lights/streetlamp_spill.png')
        yy,xx=np.ogrid[:936,:1776];bulb=((xx-1355)/38)**2+((yy-487)/22)**2<=1
        bulb=(np.asarray(Image.fromarray((bulb*255).astype('uint8')).filter(ImageFilter.GaussianBlur(3)))/255)
        glow_a=la.copy();glow_a[...,3]=np.rint(np.clip(diff*1.8,0,1)*bulb*255).astype('uint8')
        glow=Image.new('RGBA',CANVAS);glow.alpha_composite(Image.fromarray(glow_a),(72,42));glow.save(folder/'lights/streetlamp_glow.png')
        affected=[name for name in alphas if (alphas[name]&(np.asarray(full)>10)).any()]
        station['lights']=[{'id':'streetlamp','space':'lamp','spill':'lights/streetlamp_spill.png','glow':'lights/streetlamp_glow.png','affected_layers':affected,'color':'#D9A066','intensity':.7,'soften_threshold':.3,'status_cycle':['ink_covered','lit','dimmed','ink_covered'],'extraction':'positive native-frame luminance delta, localized to reject unrelated edit drift; bulb pixels extracted from lit frame','preview_only':True}]
        lit.save(gallery/'native_lit_reference.png');render(station,folder,light_states={'streetlamp':1}).save(gallery/'station_lit.png')
        frames=[]
        for i in range(120):
            t=i/15
            value=0 if t<1.5 or t>6.5 else min(1,(t-1.5)/.3,(6.5-t)/.3)
            im=render(station,folder,camera=(math.sin(t)*15,math.cos(t*.7)*6),breath=(math.sin(t*2)*4,math.cos(t*2)*2),light_states={'streetlamp':max(0,value)})
            # Temporary ink cover explicitly allowed by T04; not a formal texture.
            if value<.5:
                d=ImageDraw.Draw(im);d.ellipse((1290,455,1410,515),fill=(11,11,14,245))
            frames.append(im.resize((960,506),Image.Resampling.LANCZOS))
        movie(frames,gallery/'light_cycle.mp4',fps=15)
    write_json(folder/'station.json',station);write_json(REPORT/'station.json',station)
    write_json(REPORT/'checks.json',{'layers':checks,'C07a_motion_states':coverage,'extent_status':'provisional_current_shape_support_requires_human_confirmation','normalization':record})
    print(json.dumps({'layers':len(LAYERS),'coverage':{n:v['status'] for n,v in coverage.items()},'light_edit_ready':'station_lit_edit' in byid}))

if __name__=='__main__':main()
