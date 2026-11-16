"""Explicit visual slots for current-view civilian staging; no legacy z split."""
import math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from puppet_motion_v5 import Civilian as V5,CLIPS,NAMES,point
from puppet_motion import rotation
from preview import transform,translation

class Civilian(V5):
    def sample(self,clip,t,rescue=False):
        s=super().sample(clip,t,rescue)
        # Authored lateral gestures stay in front throughout. No inferred angle/Y switching.
        s['occlusion_profile']='current_view_lateral_front'
        return s
    def drawables(self,s):
        source={k:(im,m) for k,im,m,_ in super().drawables(s)}
        # Head is below the foreground limbs; arm roots no longer hidden by the entire torso.
        order=['shin_r','shin_r_foot','shin_r_cuff','thigh_r','shin_l','shin_l_foot','shin_l_cuff','thigh_l','torso','head','upper_arm_r','forearm_r','prop','upper_arm_l','right_palm','forearm_l']
        out=[]
        for ident in order:
            if ident not in source:continue
            im,m=source[ident]
            if ident=='prop':
                # Prop sits between the rear hand and front fingers. Original pixels
                # are partitioned in local holding-forearm space, not repainted.
                continue
            if ident=='forearm_r':
                a=np.array(im);cut=193 if self.folder.name=='vendor' else 183
                back=a.copy();front=a.copy();back[cut:,:,3]=0;front[:cut,:,3]=0
                out.append(('holding_sleeve_back',Image.fromarray(back),m,len(out)))
                pi,pm=source['prop'];out.append(('prop',pi,pm,len(out)))
                out.append(('holding_fingers_front',Image.fromarray(front),m,len(out)));continue
            out.append((ident,im,m,len(out)))
        return out
    def constraints(self,s):
        # V3 expects forearm_l and right_palm, which keep their stable IDs.
        return super().constraints(s)
    def layers(self,s,size,scale,offset):
        cam=translation(offset[0]-s['camera_x']*scale,offset[1])@np.diag([scale,scale,1])
        layers=[(k,transform(im,cam@m,size)) for k,im,m,_ in self.drawables(s)]
        # Sample the original hand only once. Partition AFTER filtering, so two
        # independently filtered alpha edges cannot double-darken the grip seam.
        m=cam@self.world_matrices(s)['forearm_r'];full=np.array(transform(self.images['forearm_r'],m,size))
        front=next(np.asarray(im)[...,3]>=128 for k,im in layers if k=='holding_fingers_front')
        for i,(k,im) in enumerate(layers):
            if k in ['holding_sleeve_back','holding_fingers_front']:
                a=full.copy();a[~front if k=='holding_fingers_front' else front,3]=0;layers[i]=(k,Image.fromarray(a))
        return layers
    def render(self,s,size=(640,720),scale=.68,offset=None,debug=False,include_front=True):
        if not include_front:raise ValueError('Legacy torso-z split disabled; use explicit layers')
        if offset is None:offset=np.array([320-self.origin[0]*scale,20.])
        out=Image.new('RGBA',size)
        for _,im in self.layers(s,size,scale,offset):out.alpha_composite(im)
        cam=translation(offset[0]-s['camera_x']*scale,offset[1])@np.diag([scale,scale,1])
        return out,{k:cam@m for k,m in self.world_matrices(s).items()}
    def rescue_render(self,s,blob,blobsize,scale,size,offset):
        layers=self.layers(s,size,scale,offset);torso=next(im for k,im in layers if k=='torso');safe=np.clip(ndi.distance_transform_edt(np.asarray(torso)[...,3]>=128)-7,0,1)
        cam=translation(offset[0]-s['camera_x']*scale,offset[1])@np.diag([scale,scale,1]);tm=cam@self.world_matrices(s)['torso']
        ink=transform(blob,tm@translation(*self.original['ink_anchor'])@np.diag([blobsize/256,blobsize/256,1])@translation(-128,-128),size);a=np.array(ink);a[...,3]=np.rint(a[...,3]*safe).astype('uint8');ink=Image.fromarray(a)
        paper=Image.new('RGBA',size);combined=paper.copy();remaining=np.ones((size[1],size[0]));after=False
        for ident,im in layers:
            paper.alpha_composite(im);combined.alpha_composite(im)
            if after:remaining*=1-np.asarray(im)[...,3]/255
            if ident=='torso':combined.alpha_composite(ink);after=True
        visible=np.rint(a[...,3]*remaining).astype('uint8')
        return combined,paper,a,visible
