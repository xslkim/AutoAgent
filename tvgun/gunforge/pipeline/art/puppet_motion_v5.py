"""A2g: civilian skewer grip with an upright, wrist-compensated presentation."""
import math
import numpy as np
from puppet_motion_v4 import Civilian as V4,CLIPS,NAMES,point

class Civilian(V4):
    def __init__(self,model,folder):
        super().__init__(model,folder);self.upright_prop=folder.name=='vendor'
        if self.upright_prop:
            # Annotated bare-bamboo point and palm contact, not fruit centre.
            self.nodes['prop'].update(pivot=[20.,180.],attach=[102.,211.],z=5.9)
            self.local_limits['prop']=[-25,95];self.nodes['prop']['angle_range']=self.local_limits['prop']
    def sample(self,clip,t,rescue=False):
        s=super().sample(clip,t,rescue)
        if self.upright_prop:
            # Native skewer points upward; +8 deg places fruit above/outside hand.
            target=8.+1.5*math.sin(t*math.tau/CLIPS[clip])
            parent=self.world_matrices(s)['forearm_r'];parent_angle=math.degrees(math.atan2(parent[1,0],parent[0,0]));s['angles']['prop']=target-parent_angle;s['prop_world_target_deg']=target
        return s
    def constraints(self,s):
        r=super().constraints(s)
        if self.upright_prop:
            m=self.world_matrices(s);p=self.nodes['prop'];grip=point(m['prop'],p['pivot']);hand=point(m['forearm_r'],p['attach']);fruit=point(m['prop'],[20.,70.]);end=point(m['prop'],[20.,215.]);angle=math.degrees(math.atan2(m['prop'][1,0],m['prop'][0,0]));r['skewer']={'grip_error_source_px':float(np.linalg.norm(grip-hand)),'world_angle_deg':angle,'angle_target_error_deg':abs(angle-s['prop_world_target_deg']),'fruit_above_grip':bool(fruit[1]<grip[1]),'bare_handle_below_grip':bool(end[1]>grip[1]),'fruit_outside_hand':bool(fruit[0]>grip[0])}
        return r
    def metadata(self):
        m=super().metadata();m['version']='civilian-motion-5'
        if self.upright_prop:m['prop']={'object':'tanghulu_civilian_prop','hand':'anatomical left, screen right','grip_in_prop':[20,180],'grip_in_forearm':[102,211],'upright_world_angle_deg':[6.5,9.5],'wrist_compensation':'world target minus forearm world angle','layering':'prop before holding hand; hand covers bare bamboo at grip','attackable':False}
        return m
