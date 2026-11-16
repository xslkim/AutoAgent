"""Inspect current v5 drawing policy; this does not certify visual correctness."""
import hashlib,json
from pathlib import Path
from collections import defaultdict
from artlib import GAME,write_json
from puppet_motion_v5 import Civilian,CLIPS
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2j';CACHE=Path('D:/gunforge_cache/g01/T05')
def main():
    result={'implementation':'civilian-motion-5','visual_acceptance':False,'purpose':'audit actual drawing lists, not infer correct depth from numeric joint attachment','characters':{}}
    for role in ['vendor','video']:
        folder=CACHE/role;source=folder/'puppet.json';m=json.loads(source.read_text(encoding='utf-8'));c=Civilian(m,folder);per_clip={};all_signatures=set();frames=0
        for rescue in [False,True]:
            for clip,dur in CLIPS.items():
                signatures=set()
                for i in range(round(dur*24)):
                    s=c.sample(clip,i/24,rescue=rescue);draw=c.drawables(s);signature=tuple((k,float(z)) for k,_,_,z in draw);signatures.add(signature);all_signatures.add(signature);frames+=1
                per_clip[clip+('_rescue' if rescue else '')]={'sampled_frames':round(dur*24),'distinct_draw_orders':len(signatures)}
        groups=defaultdict(list)
        for n in c.model['parts']:groups[n['z']].append(n['id'])
        result['characters'][role]={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sampled_frames':frames,'sampled_clips':per_clip,'draw_orders':[list(s) for s in sorted(all_signatures)],'shared_z_groups':{str(z):v for z,v in groups.items() if len(v)>1},'upper_arms_always_below_torso':all(c.nodes['upper_arm_'+s]['z']<c.nodes['torso']['z'] for s in ['l','r']),'forearms_always_above_torso':all(c.nodes['forearm_'+s]['z']>c.nodes['torso']['z'] for s in ['l','r']),'head_always_above_forearms':all(c.nodes['head']['z']>c.nodes['forearm_'+s]['z'] for s in ['l','r']),'rescue_split_rule':'z <= torso.z then ink then z > torso.z','warning':'source sequence has same-z parts; no semantic near/far state, no authored local pixel-ownership contract; these facts identify risks, not which every individual pose must use'}
    code=Path(__file__).parent;result['source_code_sha256']={n:hashlib.sha256((code/n).read_bytes()).hexdigest() for n in ['t05_puppets.py','puppet_motion.py','puppet_motion_v3.py','puppet_motion_v4.py','puppet_motion_v5.py']};write_json(REV/'current_occlusion_audit.json',result);print(json.dumps({k:{'frames':v['sampled_frames'],'distinct_orders':len(v['draw_orders'])} for k,v in result['characters'].items()}))
if __name__=='__main__':main()
