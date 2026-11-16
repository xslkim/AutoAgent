"""Actual-asset rescue, enemy-group and scene evidence, without approving assets."""
import json,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
from scipy import ndimage as ndi
from artlib import GAME,write_json,effective_radius,disk,yprime
from paper_ops import alpha_crop,raw_checks
from preview import pose,transform,translation
from t05_puppets import matrices
from checks import run

BASE=GAME/'reports/art';CACHE=Path('D:/gunforge_cache/g01');CONTENT=(1776,936)
HUD=json.loads((GAME/'assets/ui/hud_layout.json').read_text(encoding='utf-8'))
RESERVED=[v['rect'] for v in HUD['reserved'].values() if v['when']=='playing']

def save_mask(m,path):Image.fromarray((m*255).astype('uint8')).save(path)
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def rescue():
    folder=CACHE/'T05/ink_blobs';folder.mkdir(exist_ok=True)
    jobs={j['id']:j for j in read(BASE/'T05/queue.json') if j['state']=='returned'}
    if 'blob_02_compact' in jobs:jobs['blob_02']=jobs['blob_02_compact']
    blobs=[]
    for i in range(6):
        ident=f'blob_{i:02}';im,_=alpha_crop(Image.open(jobs[ident]['output']).convert('RGBA'),pad=2)
        im.thumbnail((256,256),Image.Resampling.LANCZOS);out=Image.new('RGBA',(256,256));out.alpha_composite(im,((256-im.width)//2,(256-im.height)//2));out.save(folder/(ident+'.png'));blobs.append(out)
    results={}
    for role in ['vendor','video']:
        model=read(CACHE/'T05'/role/'puppet.json');partfolder=CACHE/'T05'/role
        torso=np.asarray(Image.open(partfolder/'parts/torso.png').convert('RGBA'))[...,3]>=128
        distance=ndi.distance_transform_edt(torso);ay,ax=np.unravel_index(distance.argmax(),distance.shape)
        model['ink_anchor']=[int(ax),int(ay)]
        model['ink_anchor_method']='largest inscribed disk of actual torso/apron alpha, chest-abdomen only'
        rows=[];examples={}
        for height,blobsource in [(300,256),(400,192),(512,160)]:
            scale=height/model['assembled_height'];pos=[900,300]
            paper=pose(model,partfolder,pos,scale,{},CONTENT);pa=np.asarray(paper)[...,3]>=128
            # Chest anchor is expressed in torso-file coordinates, using the same rig affine.
            m=matrices(model,pos,scale,{});p=m['torso']@np.array([*model['ink_anchor'],1]);x,y=np.rint(p[:2]).astype(int)
            for i,blob in enumerate(blobs):
                size=round(blobsource*scale);ink=Image.new('RGBA',CONTENT);ink.alpha_composite(blob.resize((size,size),Image.Resampling.LANCZOS),(x-size//2,y-size//2));ia=np.asarray(ink)[...,3]>=128
                primary=ia.copy();protected=pa&~ia
                rgb=np.asarray(ink);weak=ia&(rgb[...,0]>rgb[...,1].astype(float)*1.6)&(rgb[...,0]>70)
                # Six visible paper pixels must surround the entire attached ink silhouette.
                expanded=ndi.binary_dilation(ia,structure=disk(6));outside=int((expanded&~pa).sum())
                prefix=CACHE/'T05'/f'{role}_{height}_{i:02}'
                for name,a in [('primary',primary),('protected',protected),('weak',weak)]:save_mask(a,Path(str(prefix)+'_'+name+'.png'))
                yy,xx=np.nonzero(ia);bbox=[int(xx.min())-8,int(yy.min())-8,int(xx.max()-xx.min())+17,int(yy.max()-yy.min())+17]
                spec={'primary':str(prefix)+'_primary.png','protected':str(prefix)+'_protected.png','weak':str(prefix)+'_weak.png','content_size':list(CONTENT),'motion_bbox':bbox,'hud_rects':RESERVED}
                c09=run('C09',spec);r=c09['details']['effective_radius'];status='pass' if c09['status']=='pass' and outside==0 else 'fail'
                rows.append({'height':height,'blob':i,'blob_source_extent':blobsource,'effective_radius':r,'paper_border_leak_pixels':outside,'C09':c09,'status':status,'scope':'static actual idle assembly; full-action protection remains pending'})
                if i==0:
                    preview=Image.new('RGBA',CONTENT,(86,91,107,255));preview.alpha_composite(paper);preview.alpha_composite(ink)
                    overlay=np.zeros((936,1776,4),dtype='uint8');overlay[protected]=[66,192,214,80];overlay[primary]=[238,169,85,120];overlay[weak]=[232,74,65,170];preview.alpha_composite(Image.fromarray(overlay))
                    d=ImageDraw.Draw(preview);d.rectangle((x-size//2-6,y-size//2-6,x+size//2+6,y+size//2+6),outline=(255,210,100),width=2)
                    preview.save(BASE/'T05/gallery'/f'{role}_rescue_{height}.png');examples[height]={'paper':paper,'ink':ink}
        # Select a conservative display height only if all six real blob shapes pass.
        passed=[h for h in [300,400,512] if all(r['status']=='pass' for r in rows if r['height']==h)]
        model['rescue']={'human_is_enemy':False,'human_attackable':False,'target':'independent_attached_ink','minimum_candidate_display_height':min(passed) if passed else None,'tested_heights':[300,400,512],'complete_action_validation':'pending','approval':'pending_A2'}
        write_json(partfolder/'puppet.json',model);results[role]={'rows':rows,'candidate_minimum':min(passed) if passed else None}
        # Clean side-by-side rescue visual at the conservative tested candidate height.
        preview_height=min(passed) if passed else 512
        pair=Image.new('RGBA',(1100,650),(86,91,107,255))
        for index,state in enumerate(['ink','rescued']):
            p=pose(model,partfolder,[270+index*550,180],preview_height/model['assembled_height'],{},(1100,650));pair.alpha_composite(p)
            if state=='ink':
                mat=matrices(model,[270,180],preview_height/model['assembled_height'],{});point=mat['torso']@np.array([*model['ink_anchor'],1]);base={300:256,400:192,512:160}[preview_height];size=round(base*preview_height/model['assembled_height']);pair.alpha_composite(blobs[0].resize((size,size)),(round(point[0]-size/2),round(point[1]-size/2)))
        pair.save(BASE/'T05/gallery'/f'{role}_rescue_comparison.png')
    write_json(BASE/'T05/rescue_checks.json',results)
    return results

def enemies():
    gallery=BASE/'T06/gallery';background=Image.open(BASE/'T04/gallery/station_unlit.png').convert('RGBA')
    group=background.copy();occupied=np.zeros((936,1776),bool);rows=[]
    for i,center in enumerate([(620,405),(900,460),(1160,395)]):
        folder=CACHE/'T06'/('tadpole'+str(i));model=read(folder/'enemy.json');body=Image.open(folder/'body_full.png').convert('RGBA');core=Image.open(folder/'core_full.png').convert('RGBA')
        a=np.asarray(body)[...,3]>=128;dist=ndi.distance_transform_edt(a);cy,cx=np.unravel_index(dist.argmax(),dist.shape);radius=dist[cy,cx];factor=90/(2*radius)
        mat=translation(*center)@np.diag([factor,factor,1])@translation(-cx,-cy)
        b=transform(body,mat,CONTENT);c=transform(core,mat,CONTENT);group.alpha_composite(b);group.alpha_composite(c)
        yy,xx=np.ogrid[:1024,:1024];head=((xx-cx)**2+(yy-cy)**2<=radius**2)&a
        h=transform(Image.fromarray((head*255).astype('uint8')).convert('RGBA'),mat,CONTENT)
        # Transform a grayscale shape as grayscale, not the RGBA conversion alpha.
        inv=np.linalg.inv(mat);hm=np.asarray(Image.fromarray((head*255).astype('uint8')).transform(CONTENT,Image.Transform.AFFINE,tuple(inv[:2].ravel()),Image.Resampling.NEAREST))>=128
        overlap=int((occupied&hm).sum());occupied|=hm
        p=CACHE/'T06'/f'group_{i}_primary.png';save_mask(hm,p);empty=CACHE/'T06/group_empty.png';save_mask(np.zeros_like(hm),empty)
        weak=(np.asarray(c)[...,3]>=128);wp=CACHE/'T06'/f'group_{i}_weak.png';save_mask(weak,wp)
        yy,xx=np.nonzero(np.asarray(b)[...,3]>=128);bbox=[int(xx.min())-5,int(yy.min())-5,int(xx.max()-xx.min())+11,int(yy.max()-yy.min())+11]
        c09=run('C09',{'primary':str(p),'protected':str(empty),'weak':str(wp),'motion_bbox':bbox,'content_size':list(CONTENT),'hud_rects':RESERVED})
        rows.append({'enemy':model['id'],'head_display_diameter':90,'group_primary_overlap_pixels':overlap,'C09':c09})
    group.save(gallery/'tadpole_group.png');annotated=group.copy();overlay=np.zeros((936,1776,4),dtype='uint8');overlay[occupied]=[255,172,78,105];annotated.alpha_composite(Image.fromarray(overlay));annotated.save(gallery/'tadpole_group_overlay.png')
    folder=CACHE/'T06/crow';body=Image.open(folder/'body_full.png').convert('RGBA');core=Image.open(folder/'core_full.png').convert('RGBA');model=read(folder/'enemy.json')
    crow=background.copy();mat=translation(900,420)@np.diag([.36,.36,1])@translation(-512,-512);crow.alpha_composite(transform(body,mat,CONTENT));crow.alpha_composite(transform(core,mat,CONTENT));crow.save(gallery/'crow_in_scene.png')
    write_json(BASE/'T06/group_checks.json',{'rows':rows,'all_primary_disjoint':all(r['group_primary_overlap_pixels']==0 for r in rows),'motion_validation':'static group plus +/-5px bounding reservation; in-engine movement and occlusion remain pending'})
    for name in ['crow','tadpole0','tadpole1','tadpole2']:
        checks=read(BASE/'T06'/f'{name}_checks.json');checks['C04']=raw_checks(CACHE/'T06'/name/'body_full.png',True)['C04'];write_json(BASE/'T06'/f'{name}_checks.json',checks)
    return rows

if __name__=='__main__':
    r=rescue();g=enemies();print(json.dumps({'rescue':{k:v['candidate_minimum'] for k,v in r.items()},'group':[row['C09']['status'] for row in g]}))
