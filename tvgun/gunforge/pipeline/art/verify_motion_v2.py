"""Derive anatomy and rescue checks from actual FK matrices and rendered alpha."""
import copy,json,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from artlib import GAME,write_json,effective_radius
from puppet_motion import Civilian,CLIPS,point
from preview import transform,translation

CACHE=Path('D:/gunforge_cache/g01');BASE=GAME/'reports/art'
def fast_radius(mask):
    eroded=ndi.distance_transform_edt(mask)>12
    if not eroded.any():return 0.
    opened=ndi.distance_transform_edt(~eroded)<=12
    return math.sqrt(opened.sum()/math.pi)
def main():
    records={};blobs=[Image.open(CACHE/'T05/ink_blobs'/f'blob_{i:02}.png').convert('RGBA') for i in range(6)]
    for b in blobs:
        m=np.asarray(b.resize((107,107),Image.Resampling.LANCZOS))[...,3]>=128
        assert abs(fast_radius(m)-effective_radius(m)[0])<1e-6
    for role,height,blobsize in [('vendor',512,160),('video',300,256)]:
        folder=CACHE/'T05'/role;model=json.loads((folder/'puppet.json').read_text(encoding='utf-8'));c=Civilian(model,folder);scale=height/768
        sample=c.sample('idle',0);broken=copy.deepcopy(sample);broken['angles']['shin_l']-=70
        negative_knee=c.constraints(broken);assert negative_knee['knee_flexion']['l']<0 and negative_knee['ankle_target_errors']['l']>2
        broken=copy.deepcopy(sample);broken['targets']['l'][0]+=10;assert c.constraints(broken)['ankle_target_errors']['l']>9
        rows=[];minradius=1000.;minborder=1000.;outsideweak=0;total=0;worst=[];max_source_joint_gap=0.
        for clip in ['idle','peek','startle','wave_for_help','struggle']:
            for i in range(round(CLIPS[clip]*24)):
                s=c.sample(clip,i/24,rescue=True);world=c.world_matrices(s);anchor=point(world['torso'],model['ink_anchor']);offset=[128-anchor[0]*scale,128-anchor[1]*scale]
                paper,mats=c.render(s,size=(256,256),scale=scale,offset=offset);pa=np.asarray(paper)[...,3]>=128;paper_distance=ndi.distance_transform_edt(pa)
                front=np.zeros_like(pa)
                for node in c.model['parts']:
                    if node['z']>c.nodes['torso']['z']:front|=np.asarray(transform(c.images[node['id']],mats[node['id']],(256,256)))[...,3]>=128
                for j,b in enumerate(blobs):
                    _,paper,a,visible=c.rescue_render(s,b,blobsize,scale,(256,256),offset);pa=np.asarray(paper)[...,3]>=128;paper_distance=ndi.distance_transform_edt(pa)
                    ink=a[...,3]>=128;primary=visible>=128;radius=fast_radius(primary);border=float(paper_distance[ink].min()) if ink.any() else 0.
                    weak=ink&(a[...,0].astype(float)>a[...,1]*1.6)&(a[...,0]>70);bad=int((weak&~primary).sum());minradius=min(minradius,radius);minborder=min(minborder,border);outsideweak=max(outsideweak,bad);total+=1
                    valid=radius>=40 and border>6 and bad==0
                    if not valid:worst.append({'clip':clip,'frame':i,'blob':j,'radius':radius,'paper_clearance':border,'weak_occluded_pixels':bad})
                if i%6==0:
                    # Paper overlap around the real attachment, rendered at source scale.
                    for node in c.model['parts']:
                        if not node['parent'] or node['id']=='prop':continue
                        joint=point(world[node['id']],node['pivot']);camera=translation(48-joint[0],48-joint[1]);child=np.asarray(transform(c.images[node['id']],camera@world[node['id']],(96,96)))[...,3]>=128;par=np.asarray(transform(c.images[node['parent']],camera@world[node['parent']],(96,96)))[...,3]>=128
                        yy,xx=np.ogrid[:96,:96];local=(xx-48)**2+(yy-48)**2<=15**2;zone=child&local
                        gap=float(ndi.distance_transform_edt(~par)[zone].min()) if zone.any() and par.any() else 99.;max_source_joint_gap=max(max_source_joint_gap,gap)
                if i%48==0:print(role+' '+clip+' '+str(i),flush=True)
        for clip,duration in CLIPS.items():
            first,_=c.render(c.sample(clip,0));last,_=c.render(c.sample(clip,duration));difference=float(np.abs(np.asarray(first).astype(float)-np.asarray(last).astype(float)).mean()/255)
            rows.append({'clip':clip,'endpoint_pixel_difference':difference,'loop_position_pass':difference<=.02})
        record={'status':'pass' if not worst and max_source_joint_gap<=2 and all(r['loop_position_pass'] for r in rows) else 'fail','scope':'all actual 24fps frames of ink-attached-eligible clips; six blobs; original minimum sizes. Complete Godot behavior remains pending.','minimum_candidate_display_height':height,'rescue_frames':total//6,'blob_frame_tests':total,'minimum_effective_radius':minradius,'minimum_paper_clearance_px':minborder,'max_weak_point_occluded_pixels':outsideweak,'sampled_source_joint_max_gap_px':max_source_joint_gap,'negative_knee_and_foot_drift_rejected':True,'original_radius_algorithm_equivalence':True,'loop_endpoints':rows,'failures':worst}
        record['render_contract']='Opaque paper interiors; attached ink clipped visibly to torso inset of 7 content pixels. Same visible ink mask defines target; foreground hands remain protected.'
        path=BASE/'T05'/(role+'_rescue_motion_v2.json');old=path.with_name(role+'_rescue_motion_v2_initial_failure.json')
        if path.exists() and not old.exists():shutil.copy2(path,old)
        records[role]=record;write_json(path,record);print(role+' failures '+str(len(worst)),flush=True)
    write_json(BASE/'T05/rescue_motion_checks_v2.json',records)

if __name__=='__main__':main()
