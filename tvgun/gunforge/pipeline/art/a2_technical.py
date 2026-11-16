"""Complete offline evidence while preserving semantic and engine review gaps."""
import json,math,sys
from pathlib import Path
import numpy as np
from PIL import Image
from artlib import GAME,write_json,yprime
from checks import run
from paper_ops import raw_checks

CACHE=Path('D:/gunforge_cache/g01');BASE=GAME/'reports/art'
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def main():
    station=read(CACHE/'T04/station/station.json');folder=CACHE/'T04/station';out=CACHE/'T07';out.mkdir(exist_ok=True)
    states=[('static',(0,0),(0,0))]
    for x in [-60,60]:
        for y in [-30,30]:
            for sign in [1,-1]:states.append((f'{x}_{y}_{sign}',(x,y),(8*sign*(1 if x>0 else -1),4*sign*(1 if y>0 else -1))))
    motion={};layers=sorted(station['layers'],key=lambda p:p['z'])
    for name,cam,breath in states:
        rendered={};extents={}
        for layer in layers:
            shift=(np.array(cam)+breath)*layer['parallax'];pos=np.rint(np.array(layer['pos'])-shift).astype(int)
            im=Image.new('RGBA',(1920,1020));im.alpha_composite(Image.open(folder/layer['file']).convert('RGBA'),tuple(pos));rendered[layer['id']]=im
            if 'extent' in layer:
                actual_step=pos-np.array(layer['pos'])
                source=Image.open(folder/layer['extent']).convert('L');ext=Image.new('L',(1920,1020));ext.paste(source,tuple(actual_step));extents[layer['id']]=ext
        motion[name]={}
        for i,layer in enumerate(layers):
            if layer['id'] not in extents:continue
            occ=np.zeros((1020,1920),bool)
            for front in layers[i+1:]:occ|=np.asarray(rendered[front['id']])[...,3]>=128
            paths={}
            for ident,im in [('file',rendered[layer['id']]),('extent',extents[layer['id']]),('occlusion',Image.fromarray((occ*255).astype('uint8')))]:
                p=out/(name+'_'+layer['id']+'_'+ident+'.png');im.crop((72,42,1848,978)).save(p);paths[ident]=str(p)
            motion[name][layer['id']]=run('C07b',paths)
    if '--motion-only' in sys.argv:
        path=BASE/'T04/additional_checks.json';record=read(path);record['C07b_motion']=motion
        record['mask_registration']='Expected masks use the identical integer translation as their cropped color layer, including half-pixel tie rounding.'
        write_json(path,record);print(json.dumps({'motion_checks':sum(map(len,motion.values())),'motion_pass':sum(v['status']=='pass' for x in motion.values() for v in x.values())}));return
    bandchecks={}
    ranges={'far':[.45,.75],'middle':[.25,.55],'near':[.05,.20]}
    for layer in layers:
        if layer['band'] not in ranges:continue
        p=folder/'layers'/(layer['id']+'_full.png');a=np.asarray(Image.open(p).convert('RGBA'));w=np.where(a[...,3]>=128,a[...,3]/255,0)
        mean=float((w*yprime(a)).sum()/w.sum());bandchecks[layer['id']]={'band':layer['band'],'weighted_mean_Yprime':mean,'required':ranges[layer['band']],'C03_band':run('C03',{'file':str(p),'band_range':ranges[layer['band']]})}
    frames={}
    for state in ['unlit','lit']:
        im=Image.open(BASE/'T04/gallery'/f'station_{state}.png').convert('RGBA');frames[state]={'C03':run('C03',{'file':str(BASE/'T04/gallery'/f'station_{state}.png')}),'C13':{}}
        for profile,pad in [('monitor',22),('tv',47)]:
            screen=Image.new('RGB',(1920+2*pad,1080+2*pad),'black');screen.paste('white',(pad,pad,pad+1920,pad+1080));screen.paste('black',(pad+24,pad+24,pad+1896,pad+1056));screen.paste(im.convert('RGB'),(pad+72,pad+72));p=out/f'{state}_{profile}_display.png';screen.save(p);frames[state]['C13'][profile]=run('C13',{'file':str(p),'full_display_frame':True})
    write_json(BASE/'T04/additional_checks.json',{'C07b_motion':motion,'extent_scope':'Only declared current shape support; independent complete hidden geometry remains unapproved','C03_bands':bandchecks,'frames':frames,'C06':{'status':'pending','reason':'Complete state contrast/recognition and bright-background layout require follow-up'},'C11':{'status':'pending','reason':'Offline common coordinates only; full interaction and engine camera tests required'}})
    parts={}
    for role in ['vendor','video']:
        model=read(CACHE/'T05'/role/'puppet.json');parts[role]={}
        for node in model['parts']:
            p=CACHE/'T05'/role/node['file'];im=Image.open(p).convert('RGBA')
            # Keep OCR separate; running every tiny component OCR is not a semantic approval.
            checks=raw_checks(p);parts[role][node['id']]=checks
        pair=Image.new('RGB',(1200,700),'white');paper=Image.open(BASE/'T05/gallery'/f'{role}_idle.png').convert('RGBA');paper.thumbnail((600,700))
        pair.paste('black',(0,0,600,700));pair.paste(paper,(0,0),paper);pair.paste(paper,(600,0),paper);pair.save(BASE/'T05/gallery'/f'{role}_black_white.jpg')
    write_json(BASE/'T05/raw_checks.json',parts)
    atlas=read(BASE/'T06/atlas.json');write_json(BASE/'T06/memory_check.json',run('C15',{'textures':[{'size':atlas['size'],'bytes_per_pixel':4,'mipmaps':False}],'limit_bytes':32*1024*1024}))
    print(json.dumps({'motion_checks':sum(map(len,motion.values())),'motion_pass':sum(v['status']=='pass' for x in motion.values() for v in x.values()),'band_fail':[k for k,v in bandchecks.items() if v['C03_band']['status']=='fail'],'C13':{k:{p:r['status'] for p,r in v['C13'].items()} for k,v in frames.items()}}))

if __name__=='__main__':main()
