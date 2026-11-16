"""Constrained civilian motion: hip root, two-bone legs, planted soles, free-hand acting."""
import copy,math
import numpy as np
from PIL import Image,ImageDraw
from artlib import effective_radius
from preview import translation,transform
from t05_puppets import pins,matrices

CLIPS={'idle':2.5,'peek':3.,'walk':2.5,'startle':2.,'wave_for_help':3.5,'struggle':3.,'rescued_bounce':3.,'thank':3.}
NAMES={'idle':'站立 / 呼吸','peek':'探身 / 观察','walk':'行走 / 支撑脚落地','startle':'受惊 / 缓冲','wave_for_help':'空手求助 / 抬臂再摆肘','struggle':'受困 / 小幅挣扎','rescued_bounce':'获救 / 蓄力与落地','thank':'感谢 / 鞠躬'}
def smooth(u):
    u=max(0.,min(1.,u));return u*u*u*(u*(u*6-15)+10)
def envelope(t,start,rise,hold,fall):return smooth((t-start)/rise)*(1-smooth((t-start-rise-hold)/fall))
def point(m,p):return (m@np.array([*p,1.]))[:2]
def rotation(deg):
    t=math.radians(deg);return np.array([[math.cos(t),-math.sin(t),0],[math.sin(t),math.cos(t),0],[0,0,1.]])

class Civilian:
    def __init__(self,model,folder):
        self.folder=folder;self.original=copy.deepcopy(model);self.model=copy.deepcopy(model)
        self.nodes={n['id']:n for n in self.model['parts']};self.images={n['id']:Image.open(folder/n['file']).convert('RGBA') for n in self.model['parts']}
        for ident,image in self.images.items():
            a=np.array(image);a[a[...,3]>=128,3]=255;self.images[ident]=Image.fromarray(a)
        hips=np.mean([self.nodes['thigh_'+s]['attach'] for s in ['l','r']],axis=0)
        torso=self.nodes['torso'];self.origin=np.array(model['origin'],float)+hips-np.array(torso['pivot'])
        torso['pivot']=hips.tolist();self.model['origin']=self.origin.tolist()
        rest=matrices(self.model,self.origin,1,{})
        self.legs={};self.feet={}
        for side in ['l','r']:
            thigh=self.nodes['thigh_'+side];shin=self.nodes['shin_'+side];im=self.images['shin_'+side]
            dots=[d for d in pins(im) if d['point'][1]>shin['pivot'][1]+im.height*.3]
            ankle=np.array(dots[-1]['point'] if dots else [im.width*.5,im.height-80])
            v1=np.array(shin['attach'])-thigh['pivot'];v2=ankle-shin['pivot']
            alpha=np.asarray(im)[...,3]>=128;ys=np.nonzero(alpha)[0]
            self.legs[side]={'ankle':ankle,'L1':float(np.linalg.norm(v1)),'L2':float(np.linalg.norm(v2)),'phi1':math.atan2(v1[1],v1[0]),'phi2':math.atan2(v2[1],v2[0]),'rest':point(rest['shin_'+side],ankle),'sole':float(ys.max()+1-ankle[1])}
            # Procedural ankle articulation within the original shin+foot image.
            # The ten PNG parts are retained; no new artwork or independent foot asset.
            upper=np.array(im);lower=np.array(im);yy=np.arange(im.height)[:,None]
            upper[yy[:,0]>ankle[1]+9,:,3]=0;lower[yy[:,0]<ankle[1]-9,:,3]=0
            cuff=im.copy();ca=np.array(cuff);yy2,xx2=np.ogrid[:im.height,:im.width];ca[(xx2-ankle[0])**2+(yy2-ankle[1])**2>20**2,3]=0
            self.feet[side]=(Image.fromarray(upper),Image.fromarray(lower),Image.fromarray(ca))
        self.ground=max(v['rest'][1]+v['sole'] for v in self.legs.values())
        for leg in self.legs.values():leg['rest'][1]=self.ground-leg['sole']
        sinks=[]
        for side,leg in self.legs.items():
            hip=point(rest['torso'],self.nodes['thigh_'+side]['attach']);v=leg['rest']-hip
            sinks.append(v[1]-math.sqrt(max(1,(leg['L1']+leg['L2']-1.2)**2-v[0]**2)))
        self.rest_sink=max(1.3,max(sinks)+.8)
        self.wrists={}
        for side in ['l','r']:
            node=self.nodes['forearm_'+side];im=self.images['forearm_'+side];dots=[d for d in pins(im) if d['point'][1]>node['pivot'][1]+im.height*.3]
            self.wrists[side]=dots[-1]['point'] if dots else [im.width*.5,im.height-63]
        self.local_limits={'torso':[-10,10],'head':[-12,18],'upper_arm_l':[-40,110],'upper_arm_r':[-45,15],'prop':[-15,15]}
        for side,leg in self.legs.items():
            delta=math.degrees(leg['phi1']-leg['phi2']);self.local_limits['thigh_'+side]=[-75,30];self.local_limits['shin_'+side]=[delta,95+delta]
            v1=np.array(self.nodes['forearm_'+side]['attach'])-self.nodes['upper_arm_'+side]['pivot'];v2=np.array(self.wrists[side])-self.nodes['forearm_'+side]['pivot'];delta=math.degrees(math.atan2(v1[1],v1[0])-math.atan2(v2[1],v2[0]))
            self.local_limits['forearm_'+side]=[delta,125+delta] if side=='l' else [-125+delta,delta]
        for ident,node in self.nodes.items():node['angle_range']=self.local_limits[ident]

    def sample(self,clip,t,rescue=False):
        dur=CLIPS[clip];t=max(0.,min(dur,t));a={'torso':0.,'head':0.,'upper_arm_l':5.,'forearm_l':16.,'upper_arm_r':-3.,'forearm_r':-13.,'prop':0.}
        root=self.origin+np.array([0.,self.rest_sink]);cam=0.;lift=0.;air=False
        targets={s:v['rest'].copy() for s,v in self.legs.items()};planted={'l':True,'r':True};pitch={'l':0.,'r':0.}
        if clip=='idle':
            q=t/dur*math.tau;root[1]+=.4*math.sin(q);a['torso']=.65*math.sin(q);a['head']=-.35*math.sin(q-.25)
        elif clip=='peek':
            e=envelope(t,.2,.65,.8,.9);root[0]+=8*e;root[1]+=4*e;a['torso']=5*e;a['head']=-3*e;a['forearm_l']+=6*e
        elif clip=='walk':
            period=1.25;stride=96.;travel=stride*t/period;root[0]+=travel;cam=travel;root[1]+=4+1.2*math.cos(t/period*math.tau*2)
            a['torso']=1.1*math.sin(t/period*math.tau);a['head']=-a['torso']*.7
            a['upper_arm_l']=5+13*math.sin(t/period*math.tau);a['forearm_l']=22+5*math.sin(t/period*math.tau-.4)
            a['upper_arm_r']=-3-4*math.sin(t/period*math.tau);a['forearm_r']=-16-2*math.sin(t/period*math.tau-.4)
            for side,offset in [('l',0.),('r',.5)]:
                phase=t/period+offset;k=math.floor(phase);q=phase-k;stance=.62
                foot=self.legs[side]['rest'].copy();start=stride*(k-offset+stance/2)
                if q<stance:foot[0]+=start
                else:
                    u=(q-stance)/(1-stance);foot[0]+=start+stride*smooth(u);foot[1]-=28*math.sin(math.pi*u)**2;planted[side]=False;pitch[side]=-9*math.sin(math.pi*u)**2
                targets[side]=foot
        elif clip=='startle':
            e=envelope(t,.15,.12,.1,.85);root[1]+=6*e;a['torso']=-2*e;a['head']=3*envelope(t,.23,.16,.08,.8);a['upper_arm_l']+=27*e;a['forearm_l']+=36*e;a['upper_arm_r']-=7*e;a['forearm_r']-=8*e
        elif clip=='wave_for_help':
            e=envelope(t,.2,.7,1.5,.8);wave=math.sin((t-.9)*math.tau*1.6)*envelope(t,.9,.2,1.15,.2)
            a['upper_arm_l']=5+99*e+2*wave;a['forearm_l']=16+72*e+10*wave;a['torso']=-1.5*e;a['head']=1.2*e;root[1]+=1.5*e
        elif clip=='struggle':
            e=envelope(t,.1,.4,1.8,.6);q=t*math.tau/1.1;root[0]+=4*math.sin(q)*e;root[1]+=(3+1.2*math.sin(q*2))*e;a['torso']=2*math.sin(q)*e;a['head']=-1.2*math.sin(q-.4)*e;a['upper_arm_l']+=12*e+4*math.sin(q)*e;a['forearm_l']+=15*e+5*math.sin(q-.3)*e;a['upper_arm_r']-=4*e
        elif clip=='rescued_bounce':
            crouch=envelope(t,.15,.35,.05,.18);root[1]+=13*crouch
            if .7<=t<1.2:
                u=(t-.7)/.5;lift=32*4*u*(1-u);root[1]-=lift;air=True
                for s in targets:targets[s][1]-=lift;planted[s]=False
            landing=envelope(t,1.2,.09,.02,.48);root[1]+=11*landing;a['upper_arm_l']+=15*envelope(t,.5,.3,.6,.6);a['forearm_l']+=15*envelope(t,.55,.25,.6,.6);a['head']=-2*envelope(t,.6,.3,.7,.6)
        elif clip=='thank':
            e=envelope(t,.25,.65,.65,.95);a['torso']=7*e;a['head']=6*e;a['upper_arm_l']=5-34*e;a['forearm_l']=16+49*e;root[1]+=6*e
        if rescue:
            a['upper_arm_r']-=21
            if clip!='wave_for_help':a['upper_arm_l']+=20
        base=matrices(self.model,root,1,a);angles={};unreachable=[]
        for side,leg in self.legs.items():
            hip=point(base['torso'],self.nodes['thigh_'+side]['attach']);v=targets[side]-hip;distance=float(np.linalg.norm(v));L1,L2=leg['L1'],leg['L2']
            if distance>L1+L2-.001 or distance<abs(L1-L2)+.001:unreachable.append(side)
            reach=np.clip(distance,abs(L1-L2)+.001,L1+L2-.001)
            gamma=math.acos(np.clip((reach*reach-L1*L1-L2*L2)/(2*L1*L2),-1,1))
            theta=math.atan2(v[1],v[0])-math.atan2(L2*math.sin(gamma),L1+L2*math.cos(gamma))
            a['thigh_'+side]=math.degrees(theta-math.radians(a['torso'])-leg['phi1']);a['shin_'+side]=math.degrees(gamma+leg['phi1']-leg['phi2']);angles[side]=math.degrees(gamma)
        return {'clip':clip,'t':t,'root':root,'angles':a,'targets':targets,'planted':planted,'foot_pitch':pitch,'camera_x':cam,'knee_flexion':angles,'unreachable':unreachable,'airborne':air,'rescue':rescue}

    def world_matrices(self,s):return matrices(self.model,s['root'],1,s['angles'])
    def render(self,s,size=(640,720),scale=.68,offset=None,debug=False,include_front=True):
        if offset is None:offset=np.array([320-self.origin[0]*scale,20.])
        camera=translation(offset[0]-s['camera_x']*scale,offset[1])@np.diag([scale,scale,1])
        world=self.world_matrices(s);mats={k:camera@m for k,m in world.items()};out=Image.new('RGBA',size)
        for n in sorted(self.model['parts'],key=lambda p:p['z']):
            if not include_front and n['z']>self.nodes['torso']['z']:continue
            ident=n['id'];m=mats[ident]
            if ident.startswith('shin_'):
                side=ident[-1];ankle=self.legs[side]['ankle'];upper,foot,cuff=self.feet[side]
                world_angle=math.degrees(math.atan2(world[ident][1,0],world[ident][0,0]));counter=s['foot_pitch'][side]-world_angle
                out.alpha_composite(transform(upper,m,size));fm=m@translation(*ankle)@rotation(counter)@translation(*(-ankle));out.alpha_composite(transform(foot,fm,size));out.alpha_composite(transform(cuff,fm,size))
            else:out.alpha_composite(transform(self.images[ident],m,size))
        return out,mats

    def rescue_render(self,s,blob,blobsize,scale,size,offset):
        from scipy import ndimage as ndi
        back,mats=self.render(s,size,scale,offset,include_front=False)
        torso=np.asarray(transform(self.images['torso'],mats['torso'],size))[...,3]>=128
        safe=np.clip(ndi.distance_transform_edt(torso)-7,0,1)
        ink=transform(blob,mats['torso']@translation(*self.original['ink_anchor'])@np.diag([blobsize/256,blobsize/256,1])@translation(-128,-128),size)
        a=np.array(ink);a[...,3]=np.rint(a[...,3]*safe).astype('uint8');ink=Image.fromarray(a)
        front=Image.new('RGBA',size)
        for node in sorted(self.model['parts'],key=lambda n:n['z']):
            if node['z']>self.nodes['torso']['z']:front.alpha_composite(transform(self.images[node['id']],mats[node['id']],size))
        paper=back.copy();paper.alpha_composite(front);combined=back.copy();combined.alpha_composite(ink);combined.alpha_composite(front)
        visible=np.rint(a[...,3]*(1-np.asarray(front)[...,3]/255)).astype('uint8')
        return combined,paper,a,visible

    def constraints(self,s):
        m=self.world_matrices(s);joint_errors={}
        for n in self.model['parts']:
            if n['parent']:joint_errors[n['id']]=float(np.linalg.norm(point(m[n['id']],n['pivot'])-point(m[n['parent']],n['attach'])))
        feet={side:float(np.linalg.norm(point(m['shin_'+side],leg['ankle'])-s['targets'][side])) for side,leg in self.legs.items()}
        knees={};elbows={};bone_drift=[]
        def bend(a,b,c):
            u=b-a;v=c-b;return math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u@v))
        for side,leg in self.legs.items():
            hip=point(m['thigh_'+side],self.nodes['thigh_'+side]['pivot']);knee=point(m['shin_'+side],self.nodes['shin_'+side]['pivot']);ankle=point(m['shin_'+side],leg['ankle'])
            knees[side]=bend(hip,knee,ankle);bone_drift.extend([abs(np.linalg.norm(knee-hip)-leg['L1']),abs(np.linalg.norm(ankle-knee)-leg['L2'])])
            shoulder=point(m['upper_arm_'+side],self.nodes['upper_arm_'+side]['pivot']);elbow=point(m['forearm_'+side],self.nodes['forearm_'+side]['pivot']);wrist=point(m['forearm_'+side],self.wrists[side]);elbows[side]=bend(shoulder,elbow,wrist)*(1 if side=='l' else -1)
        return {'max_attachment_error':max(joint_errors.values()),'max_leg_bone_length_drift':float(max(bone_drift)),'ankle_target_errors':feet,'knee_flexion':knees,'elbow_flexion':elbows,'planted':s['planted'],'unreachable':s['unreachable']}

    def metadata(self):return {'version':'civilian-motion-2','root_pivot':'hips, rebased in memory; original artwork and bind pose preserved','root_pivot_in_torso':self.nodes['torso']['pivot'],'root_origin':self.origin.tolist(),'rest_hip_sink':self.rest_sink,'local_joint_rotation_limits':self.local_limits,'leg_geometry':{s:{'ankle_in_shin':v['ankle'].tolist(),'upper_length':v['L1'],'lower_length':v['L2'],'upper_axis_radians':v['phi1'],'lower_axis_radians':v['phi2']} for s,v in self.legs.items()},'clips':CLIPS,'knee_flexion_limits_deg':[0,95],'elbow_flexion_limits_deg':[0,125],'leg_solver':'two-bone IK, positive knee flexion, world-space stance targets','ankle_articulation':'counterrotate original foot pixels within shin+foot, 18px overlapping cuff; no added rig asset','walk':{'stride_source_px':96,'period_seconds':1.25,'stance_fraction':.62,'ground_reference_moves_with_camera':True},'prop':'rigid grip, held in right hand; free left hand waves','human_attack_actions':[]}
