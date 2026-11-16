"""A2c pose-keyed cutout acting, explicit laterality and expression attachments."""
import json,math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from puppet_motion import Civilian as V2,CLIPS,NAMES,smooth,point,rotation
from preview import translation,transform
from t05_puppets import matrices

NAMES={**NAMES,'wave_for_help':'担忧求助 / 右手掌面与腕部摆动','struggle':'受困 / 紧张呼救','rescued_bounce':'获救 / 脱困后放松'}
WAVE_KEYS=[(0,5,16,0),(.18,-3,23,0),(.65,60,65,0),(1.05,100,77,0),(1.38,99,70,-8),(1.73,102,82,8),(2.08,99,70,-8),(2.43,102,82,8),(2.72,100,77,0),(3.14,48,47,0),(3.5,5,16,0)]
def keyed(t,keys):
    for a,b in zip(keys,keys[1:]):
        if t<=b[0]:
            u=smooth((t-a[0])/(b[0]-a[0]));return np.array(a[1:])*(1-u)+np.array(b[1:])*u
    return np.array(keys[-1][1:])

class Civilian(V2):
    def __init__(self,model,folder):
        super().__init__(model,folder);f=folder/'attachments_v3';self.attachments=json.loads((f/'attachments.json').read_text(encoding='utf-8'))
        self.extra={k:Image.open(f/v['file']).convert('RGBA') for k,v in self.attachments.items() if k in ['head','palm']}
        for k,im in self.extra.items():
            a=np.array(im);a[a[...,3]>=128,3]=255;self.extra[k]=Image.fromarray(a)
        # The annotated wrist is the sleeve opening, not the center of the hand skin.
        self.wrists['l']={'vendor':[76.,153.],'video':[87.,133.]}[folder.name]
        self.cuff_cut={'vendor':157,'video':137}[folder.name]
        arm=np.array(self.images['forearm_l']);arm[self.cuff_cut:,:,3]=0;self.wave_forearm=Image.fromarray(arm)
        v1=np.array(self.nodes['forearm_l']['attach'])-self.nodes['upper_arm_l']['pivot'];v2=np.array(self.wrists['l'])-self.nodes['forearm_l']['pivot'];delta=math.degrees(math.atan2(v1[1],v1[0])-math.atan2(v2[1],v2[0]));self.local_limits['forearm_l']=[delta,125+delta]
    def sample(self,clip,t,rescue=False):
        s=super().sample(clip,t,rescue);s['wrist_roll']=0.;s['hand_attachment']='relaxed_original'
        if clip=='wave_for_help':
            keys=WAVE_KEYS
            if rescue:
                # Separate readable hostage staging: preparation/recovery stays outside ink.
                offsets=[25,25,0,0,0,0,0,0,0,10,25]
                keys=[(k[0],k[1]+offsets[i],k[2],k[3]) for i,k in enumerate(WAVE_KEYS)]
            shoulder,elbow,wrist=keyed(t,keys);s['angles']['upper_arm_l']=float(shoulder);s['angles']['forearm_l']=float(elbow);s['wrist_roll']=float(wrist);s['hand_attachment']='right_palm'
        s['expression']='distress' if rescue or clip in ['peek','startle','wave_for_help','struggle'] or (clip=='rescued_bounce' and t<.95) else 'relieved'
        return s
    def drawables(self,s):
        world=self.world_matrices(s);out=[]
        for n in sorted(self.model['parts'],key=lambda n:n['z']):
            ident=n['id'];m=world[ident];im=self.images[ident]
            if ident.startswith('shin_'):
                side=ident[-1];ankle=self.legs[side]['ankle'];upper,foot,cuff=self.feet[side];angle=math.degrees(math.atan2(m[1,0],m[0,0]));fm=m@translation(*ankle)@rotation(s['foot_pitch'][side]-angle)@translation(*(-ankle))
                out.extend([(ident,upper,m,n['z']),(ident+'_foot',foot,fm,n['z']),(ident+'_cuff',cuff,m,n['z'])]);continue
            if ident=='head' and s['expression']=='distress':
                m=m@translation(*n['pivot'])@translation(*(-np.array(self.attachments['head']['pivot'])));im=self.extra['head']
            if ident=='forearm_l' and s['hand_attachment']=='right_palm':
                im=self.wave_forearm
                # Same arm/wrist chain, positive determinant. Palm artwork points UP.
                hm=m@translation(*self.wrists['l'])@rotation(180+s['wrist_roll'])@translation(*(-np.array(self.attachments['palm']['pivot'])))
                out.append(('right_palm',self.extra['palm'],hm,n['z']-.01))
            out.append((ident,im,m,n['z']))
        return sorted(out,key=lambda r:r[3])
    def render(self,s,size=(640,720),scale=.68,offset=None,debug=False,include_front=True):
        if offset is None:offset=np.array([320-self.origin[0]*scale,20.])
        camera=translation(offset[0]-s['camera_x']*scale,offset[1])@np.diag([scale,scale,1]);out=Image.new('RGBA',size);mats={k:camera@m for k,m in self.world_matrices(s).items()}
        for ident,im,m,z in self.drawables(s):
            if include_front or z<=self.nodes['torso']['z']:out.alpha_composite(transform(im,camera@m,size))
        return out,mats
    def rescue_render(self,s,blob,blobsize,scale,size,offset):
        back,mats=self.render(s,size,scale,offset,include_front=False);torso=np.asarray(transform(self.images['torso'],mats['torso'],size))[...,3]>=128;safe=np.clip(ndi.distance_transform_edt(torso)-7,0,1)
        ink=transform(blob,mats['torso']@translation(*self.original['ink_anchor'])@np.diag([blobsize/256,blobsize/256,1])@translation(-128,-128),size);a=np.array(ink);a[...,3]=np.rint(a[...,3]*safe).astype('uint8');ink=Image.fromarray(a)
        cam=translation(offset[0]-s['camera_x']*scale,offset[1])@np.diag([scale,scale,1]);front=Image.new('RGBA',size)
        for ident,im,m,z in self.drawables(s):
            if z>self.nodes['torso']['z']:front.alpha_composite(transform(im,cam@m,size))
        paper=back.copy();paper.alpha_composite(front);combined=back.copy();combined.alpha_composite(ink);combined.alpha_composite(front);visible=np.rint(a[...,3]*(1-np.asarray(front)[...,3]/255)).astype('uint8');return combined,paper,a,visible
    def constraints(self,s):
        result=super().constraints(s);draw=self.drawables(s);result.update(expression=s['expression'],hand_attachment=s['hand_attachment'],min_transform_determinant=min(float(np.linalg.det(m[:2,:2])) for _,_,m,_ in draw),wrist_attachment_error=0.)
        if s['hand_attachment']=='right_palm':
            hm=next(m for k,_,m,_ in draw if k=='right_palm');w=point(self.world_matrices(s)['forearm_l'],self.wrists['l']);result['wrist_attachment_error']=float(np.linalg.norm(point(hm,self.attachments['palm']['pivot'])-w));result['upright_thumb_screen_x_component']=float(hm[0,0])
        return result
    def metadata(self):
        m=super().metadata();m.update(version='civilian-motion-3',laterality={'legacy_l':'screen_left_anatomical_right','legacy_r':'screen_right_anatomical_left'},prop='anatomical left hand (screen right), original rigid attachment',wave={'side':'anatomical_right','attachment':'palm_facing_viewer','upright_thumb':'screen_right','keys':WAVE_KEYS,'mirroring':False,'wrist_in_forearm':self.wrists['l']},expressions={'distress':'GPT alternate head, calling with worried brows','relieved':'original head','rules':'all rescue/peek/startle/help/struggle distressed; rescued changes at 0.95 seconds; thank relieved'},attachment_schema='ten original bones + pose/expression visual attachments; no enemy actions');return m
