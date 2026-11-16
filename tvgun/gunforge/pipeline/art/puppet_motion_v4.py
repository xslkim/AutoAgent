"""A2d: authored geometric elbow flexion, independent of sprite bind axes."""
import math
import numpy as np
from scipy.interpolate import PchipInterpolator
from puppet_motion_v3 import Civilian as V3,CLIPS as OLD_CLIPS,NAMES,point

CLIPS={**OLD_CLIPS,'wave_for_help':4.5}
NAMES={**NAMES,'wave_for_help':'求助与放下 / 肘部逐渐舒展'}
# Shoulder rotation, ACTUAL shoulder-elbow-wrist bend, wrist roll; degrees.
# These are stylized project pose choices, not universal anatomical limits.
WAVE_KEYS=[(0,3,6,0),(.25,3,8,0),(.70,58,63,0),(1.12,100,88,0),(1.45,99,81,-8),(1.80,102,93,8),(2.15,99,81,-8),(2.50,102,93,8),(2.78,100,88,0),(3.08,79,70,0),(3.42,44,37,0),(3.78,15,12,0),(4.15,3,6,0),(4.5,3,6,0)]
WAVE_CURVE=PchipInterpolator(np.array(WAVE_KEYS)[:,0],np.array(WAVE_KEYS)[:,1:],axis=0)

class Civilian(V3):
    def sample(self,clip,t,rescue=False):
        source_t=t*OLD_CLIPS[clip]/CLIPS[clip]
        s=super().sample(clip,source_t,rescue);s['t']=t
        if clip=='wave_for_help':
            # Continuous velocity through in-between keys, shape-preserving on
            # the monotone lowering path. Avoid stop-start easing at every key.
            shoulder,bend,wrist=WAVE_CURVE(np.clip(t,0,CLIPS[clip]))
            # Raise the whole upper arm slightly away from attached ink at rest;
            # never preserve clearance by kinking the elbow backwards/outwards.
            if rescue:shoulder+=22*(1-min(1,max(0,(shoulder-3)/50)))
            s['angles']['upper_arm_l']=float(shoulder)
            s['angles']['forearm_l']=float(bend+self.local_limits['forearm_l'][0])
            s['wrist_roll']=float(wrist);s['geometric_elbow_target']=float(bend)
        elif clip in ['idle','peek','walk','rescued_bounce']:
            # Rest/walk poses also use a near-straight relaxed elbow. Dedicated
            # startle/struggle/thank gestures retain their deliberate flexion.
            legacy=s['angles']['forearm_l'];bend=6+max(0,legacy-16)*.5
            s['angles']['forearm_l']=float(bend+self.local_limits['forearm_l'][0]);s['geometric_elbow_target']=float(bend)
        return s
    def constraints(self,s):
        r=super().constraints(s)
        if 'geometric_elbow_target' in s:r['elbow_target_error_deg']=abs(r['elbow_flexion']['l']-s['geometric_elbow_target'])
        return r
    def metadata(self):
        m=super().metadata();m.update(version='civilian-motion-4',clips=CLIPS)
        m['wave'].update(keys=WAVE_KEYS,interpolation='shape-preserving cubic Hermite (PCHIP), continuous velocity; monotonic extension during lowering',elbow_keys='measured geometric shoulder-elbow-wrist flexion, converted using individual bind-axis offset',lowered_elbow_deg=6,lowering_interval=[2.78,4.15],rest_hold=[4.15,4.5],rescue_clearance='shoulder abduction only near lowered pose; no extra elbow kink')
        return m
