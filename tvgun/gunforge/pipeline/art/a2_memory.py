"""CPU texture allocation estimate of referenced prototypes; no disk-size proxy."""
import json
from pathlib import Path
from PIL import Image
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2g';CACHE=Path('D:/gunforge_cache/g01')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def allocation(path,mips=True,bpp=None):
    im=Image.open(path);w,h=im.size;bpp=bpp or (1 if im.mode=='L' else 4);base=w*h*bpp;total=base
    if mips:
        while w>1 or h>1:w=max(1,w//2);h=max(1,h//2);total+=w*h*bpp
    return {'file':str(path),'size':list(im.size),'mode':im.mode,'assumed_gpu_bytes_per_pixel':bpp,'mipmaps':mips,'base_bytes':base,'allocated_bytes':total}
def main():
    station=read(CACHE/'T04/station/station.json');s=[]
    for l in station['layers']:s.append(allocation(CACHE/'T04/station'/l['file']))
    for light in station['lights']:
        for key in ['spill','glow']:
            if light.get(key):s.append(allocation(CACHE/'T04/station'/light[key],bpp=1 if key=='spill' else 4))
    # All referenced crop textures, deduplicated by path; source/full diagnostic images excluded.
    c=[]
    for role in ['vendor','video']:
        f=CACHE/'T05'/role;m=read(f/'puppet.json')
        c += [allocation(f/n['file']) for n in m['parts']]
        for k in ['distress_head.png','right_palm.png']:c.append(allocation(f/'attachments_v3'/k))
    for enemy in ['crow','tadpole0']:
        f=CACHE/'T06'/enemy;m=read(f/'enemy.json');c += [allocation(f/v['file'],bpp=1 if key=='sdf' else 4) for key,v in m['files'].items()]
    c += [allocation(CACHE/'T05/ink_blobs'/f'blob_{i:02}.png') for i in range(6)]
    categories={'station_and_lights':{'textures':s,'budget_bytes':48*1024**2},'both_residents_two_enemies_six_blobs':{'textures':c,'budget_bytes':32*1024**2}}
    for name,r in categories.items():
        r['estimated_bytes']=sum(t['allocated_bytes'] for t in {t['file']:t for t in r['textures']}.values());r['estimate_within_budget']=r['estimated_bytes']<=r['budget_bytes'];r['status']='pending_engine_import' if r['estimate_within_budget'] else 'fail_offline_estimate'
    write_json(REV/'texture_memory_estimate.json',{'categories':categories,'scope':'uncompressed RGBA8/R8 exact mip-chain estimate, not actual GPU usage; instances share textures; no sequence atlas used by procedural reference','not_included':['runtime_render_targets','post_processing','font_cache','T08_not_yet_generated_UI_and_pickups','second_station_transition'],'single_station_partial_total_bytes':sum(r['estimated_bytes'] for r in categories.values()),'actual_C15':'pending_Godot_import_and_peak_measurement'});print(json.dumps({k:{x:v for x,v in r.items() if x!='textures'} for k,r in categories.items()}))
if __name__=='__main__':main()
