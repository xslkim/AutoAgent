"""Build civilian-only paper puppets from inspected generated component sheets."""
import json
import math
import yaml
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps
from scipy import ndimage as ndi
from artlib import GAME,write_json,yprime,effective_radius
from paper_ops import component_map,sheet_diagnostics,isolated_component,alpha_crop,paper_palette
from preview import pose,movie,translation,transform
from checks import run

REPORT=GAME/'reports/art/T05';CACHE=Path('D:/gunforge_cache/g01/T05');SIZE=(1000,1000)

def pins(im):
    a=np.asarray(im.convert('RGBA'));r,g,b=a[...,:3].astype(float).transpose(2,0,1)
    m=(a[...,3]>=128)&(r>g*1.07)&(g>b*1.2)&(g>90)&(r>130)
    labels,n=ndi.label(m);rows=[]
    for label,sl in enumerate(ndi.find_objects(labels),1):
        if sl is None:continue
        yy,xx=np.nonzero(labels[sl]==label);area=len(xx)
        if area<12:continue
        h=sl[0].stop-sl[0].start;w=sl[1].stop-sl[1].start
        diameter=float(math.sqrt(area/math.pi)*2)
        if .5<w/max(1,h)<1.7 and area/max(1,w*h)>.5 and diameter<min(im.size)*.5:
            rows.append({'point':[float(xx.mean()+sl[1].start),float(yy.mean()+sl[0].start)],'diameter':diameter})
    return sorted(rows,key=lambda p:p['point'][1])

def matrices(puppet,position,scale,angles):
    rows={p['id']:p for p in puppet['parts']};out={}
    def get(ident):
        if ident in out:return out[ident]
        p=rows[ident];theta=math.radians(angles.get(ident,0));rotation=np.array([[math.cos(theta),-math.sin(theta),0],[math.sin(theta),math.cos(theta),0],[0,0,1.]])
        head=get(p['parent'])@translation(*p['attach']) if p['parent'] else translation(*position)@np.diag([scale,scale,1])
        out[ident]=head@rotation@translation(-p['pivot'][0],-p['pivot'][1]);return out[ident]
    for ident in rows:get(ident)
    return out

def build(role):
    folder=CACHE/role;folder.mkdir(exist_ok=True);(folder/'parts').mkdir(exist_ok=True)
    gallery=REPORT/'gallery';gallery.mkdir(exist_ok=True)
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'))
    sheets=[j for j in queue if j['id'].startswith(role+'_sheet_')]
    evaluated={j['id']:sheet_diagnostics(j['output']) for j in sheets}
    good=[j for j in sheets if evaluated[j['id']]['count_complete']]
    if not good:raise ValueError('No ten-part sheet for '+role)
    chosen=good[0];im=Image.open(chosen['output']).convert('RGBA');labels,components=component_map(im)
    mapping=evaluated[chosen['id']]['mapping'];parts={};evidence={}
    for ident,row in mapping.items():
        crop=isolated_component(im,row['label'],labels)
        if ident not in {'torso','head'}:
            dots=pins(crop)
            if len(dots)>=2 and dots[-1]['point'][1]-dots[0]['point'][1]>crop.height*.3:
                p,q=dots[0]['point'],dots[-1]['point'];angle=-math.degrees(math.atan2(q[0]-p[0],q[1]-p[1]));crop=crop.rotate(angle,expand=True,resample=Image.Resampling.BICUBIC);crop,_=alpha_crop(crop)
        width,height={'torso':(238 if role=='vendor' else 300,300),'head':(168 if role=='vendor' else 182,185)}.get(ident,(90 if 'arm' in ident else 105,195 if 'shin' in ident else 180))
        crop=crop.resize((width,height),Image.Resampling.LANCZOS)
        dots=pins(crop)
        crop=paper_palette(crop)
        pivot=dots[0]['point'] if dots and ident not in {'torso','head'} else [width/2,20]
        if ident=='head':pivot=[width*.5,height-18]
        if ident=='torso':pivot=[width*.5,16]
        evidence[ident]={'source_component':row,'pivot_method':'copper_color_component' if dots and ident not in {'torso','head'} else 'executor_manual_anatomical_annotation','measured_pin_diameters':[x['diameter'] for x in dots]}
        parts[ident]={'image':crop,'pivot':pivot,'dots':dots}
    tw,th=parts['torso']['image'].size
    nodes=[]
    parent={'torso':None,'head':'torso','upper_arm_l':'torso','upper_arm_r':'torso','forearm_l':'upper_arm_l','forearm_r':'upper_arm_r','thigh_l':'torso','thigh_r':'torso','shin_l':'thigh_l','shin_r':'thigh_r'}
    z={'shin_l':1,'shin_r':1,'thigh_l':2,'thigh_r':2,'upper_arm_l':3,'upper_arm_r':3,'torso':5,'forearm_l':6,'forearm_r':6,'head':7}
    for ident,p in parts.items():
        par=parent[ident];attach=None
        if ident=='head':attach=[tw*.5,15]
        elif ident.startswith('upper_arm'):
            fractions=(.28,.80) if role=='vendor' else (.12,.88)
            attach=[tw*fractions[0 if ident.endswith('_l') else 1],48]
        elif ident.startswith('thigh'):attach=[tw*(.32 if ident.endswith('_l') else .68),th-20]
        elif par:
            src=parts[par];dots=src['dots'];attach=dots[-1]['point'] if len(dots)>=2 else [src['image'].width*.5,src['image'].height-20]
        file='parts/'+ident+'.png';p['image'].save(folder/file)
        nodes.append({'id':ident,'file':file,'parent':par,'pivot':p['pivot'],'attach':attach,'z':z[ident],'rest_deg':0,'angle_range':[-75,75] if 'arm' in ident else [-30,30]})
    puppet={'id':'g01_res_'+role,'rig':'humanoid_10','role':'hostage_or_npc','is_enemy':False,'human_body_attackable':False,'human_attacks_player':False,'enemy_hp':None,'parts':nodes,'origin':[500,230],'actions':['peek','walk','startle','wave_for_help','struggle','rescued_bounce','thank'],'attack_actions':[],'ink_anchor':[tw*.5,th*.45],'approval':'pending_A2','source_sheet':chosen['id']}
    initial=pose(puppet,folder,puppet['origin'],1,{},SIZE);bbox=initial.getbbox();factor=768/(bbox[3]-bbox[1])
    for node in nodes:
        path=folder/node['file'];img=Image.open(path);img=img.resize((max(1,round(img.width*factor)),max(1,round(img.height*factor))),Image.Resampling.LANCZOS);img.save(path)
        node['pivot']=[v*factor for v in node['pivot']]
        if node['attach']:node['attach']=[v*factor for v in node['attach']]
    puppet['ink_anchor']=[v*factor for v in puppet['ink_anchor']]
    puppet['normalization']={'assembled_height_target':768,'uniform_final_factor':factor,'original_part_individual_resizes_recorded':True}
    patch_job=next((j for j in queue if j['id']=='joint_patch' and j['state']=='returned'),None)
    patch_evidence=None
    if patch_job:
        patch,_=alpha_crop(Image.open(patch_job['output']).convert('RGBA'),pad=0)
        pa=np.array(patch);pr,pg,pb=pa[...,:3].astype(float).transpose(2,0,1)
        copper=(pa[...,3]>=128)&(pr>pg*1.15)&(pg>pb*1.15)
        diameter=math.sqrt(copper.sum()/math.pi)*2
        patch_size=max(64,round(38/(diameter/patch.width)))
        patch=patch.resize((patch_size,patch_size),Image.Resampling.LANCZOS)
        pa=np.array(patch);pr,pg,pb=pa[...,:3].astype(float).transpose(2,0,1)
        copper=(pa[...,3]>=128)&(pr>pg*1.15)&(pg>pb*1.15)
        actual_pin=math.sqrt(copper.sum()/math.pi)*2
        for node in nodes:
            path=folder/node['file'];original=Image.open(path).convert('RGBA');a=np.array(original)
            if node['parent']:
                yy,xx=np.ogrid[:original.height,:original.width];px,py=node['pivot'];dist=(xx-px)**2+(yy-py)**2
                sample=(a[...,3]>=128)&(dist>=18**2)&(dist<=35**2)
                target=np.median(a[...,:3][sample],axis=0) if sample.any() else np.array([160,128,100])
                tinted=pa.copy();paper=(~copper)&(pa[...,3]>0)
                brightness=np.mean(pa[...,:3],axis=-1)/150
                tinted[paper,:3]=np.clip(target[None,:]*brightness[paper,None],0,255).astype('uint8')
            padded=Image.new('RGBA',(original.width+80,original.height+80));padded.alpha_composite(original,(40,40))
            node['pivot']=[v+40 for v in node['pivot']]
            if node['attach']:node['attach']=[v+40 for v in node['attach']]
            if node['parent']:padded.alpha_composite(Image.fromarray(tinted),(round(node['pivot'][0]-patch_size/2),round(node['pivot'][1]-patch_size/2)))
            padded.save(path)
        puppet['ink_anchor']=[v+40 for v in puppet['ink_anchor']]
        patch_evidence={'source_job':'joint_patch','paper_overlap_diameter':patch_size,'measured_copper_diameter':actual_pin,'merged_into_existing_ten_parts':True,'paper_color_matching':'local garment annulus; native fiber and copper retained'}
        puppet['joint_patch']=patch_evidence
    prop_job=next((j for j in queue if j['id']==role+'_prop' and j['state']=='returned'),None)
    if role=='video':prop_job=next((j for j in queue if j['id']=='video_prop_clean' and j['state']=='returned'),prop_job)
    if prop_job:
        prop=Image.open(prop_job['output']).convert('RGBA')
        if role=='video':
            # Remove the returned soft external aura by alpha support, retaining native RGB.
            a=np.array(prop);solid=a[...,3]>=250;solid=ndi.binary_fill_holes(solid)
            labels,n=ndi.label(solid);solid=labels==(np.bincount(labels.ravel())[1:].argmax()+1)
            a[...,3]=np.minimum(a[...,3],np.clip(ndi.distance_transform_edt(solid)*255,0,255).astype('uint8'));prop=Image.fromarray(a)
        prop,_=alpha_crop(prop,pad=2);height=220 if role=='vendor' else 150
        prop=prop.resize((round(prop.width*height/prop.height),height),Image.Resampling.LANCZOS);prop.save(folder/'parts/prop.png')
        forearm=Image.open(folder/'parts/forearm_r.png')
        nodes.append({'id':'prop','file':'parts/prop.png','parent':'forearm_r','pivot':[prop.width/2,prop.height*(.78 if role=='vendor' else .65)],'attach':[forearm.width*.5,forearm.height-63],'z':8,'rest_deg':0,'angle_range':[-15,15]})
        parts['prop']={};parent['prop']='forearm_r'
        puppet['prop']={'source_job':prop_job['id'],'role':'ordinary_civilian_object','attackable':False,'external_aura_removed_by_alpha_support':role=='video'}
    poses={'idle':{},'peek':{'torso':-3,'head':8,'upper_arm_l':18},'walk':{'upper_arm_l':20,'upper_arm_r':-20,'thigh_l':14,'thigh_r':-14,'shin_l':-8,'shin_r':8},'startle':{'upper_arm_l':60,'upper_arm_r':-60,'forearm_l':-20,'forearm_r':20},'wave_for_help':{'upper_arm_r':-70,'forearm_r':-55},'struggle':{'upper_arm_l':25,'upper_arm_r':-35,'forearm_l':30,'forearm_r':-30},'rescued_bounce':{'upper_arm_l':20,'upper_arm_r':-20,'head':-5},'thank':{'head':12,'torso':3,'forearm_r':-15}}
    for node in nodes:
        if node['id']=='torso':continue
        for angle in node['angle_range']:poses[node['id']+'_'+str(angle)]={node['id']:angle}
    seam_errors=[];frames=[];pose_records={}
    for name,angles in poses.items():
        position=puppet['origin'].copy()
        if name=='rescued_bounce':position[1]-=16
        out=pose(puppet,folder,position,1,angles,SIZE);out.save(gallery/(role+'_'+name+'.png'))
        mats=matrices(puppet,position,1,angles);alphas={p['id']:np.asarray(transform(Image.open(folder/p['file']).convert('RGBA'),mats[p['id']],SIZE))[...,3]>=128 for p in nodes}
        errors=[];joint_errors={}
        for node in nodes:
            if not node['parent'] or node['id']=='prop':continue
            joint=mats[node['id']]@np.array([*node['pivot'],1]);x,y=np.rint(joint[:2]).astype(int);x1,x2=max(0,x-15),min(1000,x+16);y1,y2=max(0,y-15),min(1000,y+16)
            child=alphas[node['id']][y1:y2,x1:x2];par=alphas[node['parent']][y1:y2,x1:x2]
            gap=float(ndi.distance_transform_edt(~par)[child].min()) if child.any() and par.any() else 99.
            errors.append(gap)
            joint_errors[node['id']]=gap
        seam_errors.extend(errors);pose_records[name]={'max_joint_gap_px':max(errors,default=0),'joint_gaps':joint_errors,'angles':angles}
        if name in ['idle','peek','walk','startle','wave_for_help','struggle','rescued_bounce','thank']:frames.append(out)
    # Diagnostic movie, friendly movements only; no combat animations.
    movieframes=[]
    action_names=['idle','peek','walk','startle','wave_for_help','struggle','rescued_bounce','thank']
    for i in range(112):
        index=(i//14)%len(action_names);a=action_names[index];b=action_names[(index+1)%len(action_names)]
        t=(i%14)/14;t=t*t*(3-2*t)
        angles={n['id']:poses[a].get(n['id'],0)*(1-t)+poses[b].get(n['id'],0)*t for n in nodes}
        bounce=(16*(1-t) if a=='rescued_bounce' else 0)+(16*t if b=='rescued_bounce' else 0)
        position=[puppet['origin'][0]*.6,(puppet['origin'][1]-bounce)*.6]
        image=pose(puppet,folder,position,.6,angles,(600,600));bg=Image.new('RGBA',(600,600),(102,111,122,255));bg.alpha_composite(image);movieframes.append(bg)
    movie(movieframes,gallery/(role+'_actions.mp4'),fps=15)
    paper=pose(puppet,folder,puppet['origin'],1,{},SIZE);paper.save(gallery/(role+'_idle.png'))
    alpha=np.asarray(paper)[...,3]>=128;actual=paper.getbbox();puppet['assembled_bbox']=list(actual);puppet['assembled_height']=actual[3]-actual[1]
    pinch=[v for ident,p in evidence.items() if ident not in {'torso','head'} for v in p['measured_pin_diameters']]
    copper_clear=patch_evidence['measured_copper_diameter']<patch_evidence['paper_overlap_diameter']*.65 if patch_evidence else all(x<65 for x in pinch)
    template=yaml.safe_load((GAME/'bible/rigs/humanoid_10.yaml').read_text(encoding='utf-8'))
    expected=[p['id'] for p in template['parts']]+(['prop'] if 'prop' in parts else [])
    c10=run('C10',{'expected_parts':expected,'parts':list(parts),'pose_seam_errors':seam_errors,'copper_clear':copper_clear,'rig':'humanoid_10'})
    # Keep source-size pin measurements visible; numerical joint test is not a visual approval.
    torso_alpha=np.asarray(Image.open(folder/'parts/torso.png').convert('RGBA'))[...,3]>=128
    ay,ax=np.unravel_index(ndi.distance_transform_edt(torso_alpha).argmax(),torso_alpha.shape)
    puppet['ink_anchor']=[int(ax),int(ay)]
    puppet['ink_anchor_method']='largest inscribed disk of actual torso/apron alpha, chest-abdomen only'
    write_json(folder/'puppet.json',puppet)
    write_json(REPORT/(role+'_rig_checks.json'),{'source_sheets':evaluated,'chosen':chosen['id'],'raw_sheet_complete_rate':len(good)/len(sheets),'semantic_review':'executor inspected all 10 named parts on all 4 originals; human A2 remains pending','C10':c10,'poses':pose_records,'pivots':evidence,'copper_source_spec':{'required_diameter':[36,40],'original_measured_before_uniform_final_scale':pinch,'repair':patch_evidence,'status':'pass' if patch_evidence and 36<=patch_evidence['measured_copper_diameter']<=40 and patch_evidence['paper_overlap_diameter']>=64 else 'pending_visual_scale_confirmation'},'display_min_hostage':'check with actual attached blob at 300; never grant the human an enemy hit area'})
    return {'role':role,'count_complete_rate':len(good)/len(sheets),'max_joint_gap':max(seam_errors),'C10':c10['status'],'height':puppet['assembled_height']}

if __name__=='__main__':
    print(json.dumps([build(role) for role in ['vendor','video']]))
    # The original pose-morph movie is diagnostic history only; publish constrained motion.
    if (REPORT.parent/'T07/revisions/A2c/user_feedback.yaml').exists():
        from prepare_attachments_v3 import main as prepare_attachments
        prepare_attachments()
        if (REPORT.parent/'T07/revisions/A2g/user_feedback.yaml').exists():
            from build_motion_v5 import main as build_constrained_motion
        elif (REPORT.parent/'T07/revisions/A2d/user_feedback.yaml').exists():
            from build_motion_v4 import main as build_constrained_motion
        else:
            from build_motion_v3 import main as build_constrained_motion
    else:
        from build_motion_v2 import main as build_constrained_motion
    build_constrained_motion()
