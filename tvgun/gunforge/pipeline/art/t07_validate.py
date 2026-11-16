"""Required counterexamples use returned art, never synthetic substitutes for it."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
import yaml
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
from artlib import GAME,write_json
from checks import run
from paper_ops import component_map

CACHE=Path('D:/gunforge_cache/g01');OUT=CACHE/'T07';REPORT=GAME/'reports/art/T07'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def mask(p):return np.asarray(Image.open(p).convert('L'))>=128
def save(a,name):
    p=OUT/name;Image.fromarray(a.astype('uint8')).save(p);return str(p)

def main():
    global REPORT
    if '--output' in sys.argv:REPORT=Path(sys.argv[sys.argv.index('--output')+1])
    OUT.mkdir(exist_ok=True);REPORT.mkdir(exist_ok=True);rows=[]
    def record(name,source,check,spec,expected='fail'):
        r=run(check,spec);rows.append({'counterexample':name,'source_asset':str(source),'check':check,'expected':expected,'result':r,'verified':r['status']==expected,'spec':spec});return r
    station=CACHE/'T04/station';src=station/'layers/mid_left_full.png';a=np.array(Image.open(src).convert('RGBA'));opaque=a[...,3]>=254
    occlusion=mask(station/'layers/mid_left_occlusion.png');candidate=opaque&occlusion
    ys,xs=np.nonzero(candidate)
    if not len(xs):raise RuntimeError('No genuinely occluded middle-layer pixels')
    cy,cx=int(np.median(ys)),int(xs[np.argmin(abs(ys-np.median(ys)))])
    y1,y2=max(0,cy-12),min(a.shape[0],cy+12);x1,x2=max(0,cx-12),min(a.shape[1],cx+12)
    # The movement-revealed region is no longer covered by the foreground mask.
    moved=occlusion.copy();moved[y1:y2,x1:x2]=False
    extent=save(opaque*255,'middle_expected.png');occ=save(moved*255,'foreground_revealed.png')
    baseline=run('C07b',{'file':str(src),'extent':extent,'occlusion':occ})
    damaged=a.copy();damaged[y1:y2,x1:x2,3]=0;bad=save(damaged,'middle_hole.png')
    record('删除近景后方、运动时将露出的中景纹样',src,'C07b',{'file':bad,'extent':extent,'occlusion':occ})
    rows[-1]['control']=baseline;rows[-1]['hole_rect']=[x1,y1,x2-x1,y2-y1]
    enemy=CACHE/'T06/crow';body=enemy/'alpha_full.png';core=mask(enemy/'core_mask.png');badcore=ndi.shift(core.astype('uint8'),(-430,-430),order=0,cval=0)>0
    # Shift into an empty corner while retaining the actual stamp silhouette.
    if not badcore.any():raise RuntimeError('Invalid empty negative core')
    weak=save(badcore*255,'weak_outside.png');empty=save(np.zeros_like(core),'empty.png')
    spec={'primary':str(body),'protected':empty,'weak':weak,'content_size':[1776,936],'motion_bbox':[400,300,320,320],'hud_rects':[[8,832,244,96]]}
    record('弱点挪到墨身外',enemy/'core_full.png','C09',spec)
    record('弱点挪到墨身外',enemy/'core_full.png','C11',{'body':str(body),'core':weak})
    spec=dict(spec,weak=empty,motion_bbox=[100,835,150,30])
    record('运动包围盒压住生命HUD',body,'C09',spec)
    raw=np.array(Image.open(enemy/'sdf_full.png'));srgb=np.rint((raw.astype(float)/255)**2.2*255).astype('uint8');bad=save(srgb,'sdf_color_transfer.png')
    record('SDF被错误sRGB转换',enemy/'sdf_full.png','C16',{'sdf':bad,'alpha':str(body),'source_color':False})
    record('SDF错误标记为颜色纹理',enemy/'sdf_full.png','C16',{'sdf':str(enemy/'sdf_full.png'),'alpha':str(body),'source_color':True})
    atlas=Image.new('RGBA',(4096,4096));tile=Image.open(GAME/'reports/art/T06/gallery/loop_atlas.png').convert('RGBA')
    for x in range(0,4096,1536):
        for y in range(0,4096,1536):atlas.alpha_composite(tile,(x,y))
    atlas.save(OUT/'oversized_lossless_atlas.png')
    record('4096平方RGBA8无损序列帧图集',OUT/'oversized_lossless_atlas.png','C15',{'textures':[{'size':[4096,4096],'bytes_per_pixel':4,'mipmaps':False}],'limit_bytes':32*1024*1024})
    background=GAME/'reports/art/T04/gallery/station_unlit.png';im=Image.open(background).convert('RGBA');d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',74);d.rectangle((480,190,1440,305),fill=(225,215,190,255));d.text((500,200),'PAPER LANTERN CITY',font=font,fill=(10,10,14,255));im.save(OUT/'background_with_text.png')
    text_result=record('背景加入一行文字',background,'C05',{'file':str(OUT/'background_with_text.png'),'expected_text':''})
    if 'LANTERN' not in text_result.get('details',{}).get('recognized','').upper():raise RuntimeError('OCR must detect the injected text, not merely other frame noise')
    chosen=read(GAME/'reports/art/T05/vendor_rig_checks.json')['chosen'];job=next(j for j in read(GAME/'reports/art/T05/queue.json') if j['id']==chosen)
    sheet=Image.open(job['output']).convert('RGBA');head=Image.open(CACHE/'T05/vendor/parts/head.png').convert('RGBA')
    extra=Image.new('RGBA',(sheet.width+head.width+64,max(sheet.height,head.height+64)));extra.alpha_composite(sheet);extra.alpha_composite(head,(sheet.width+32,32));extra.save(OUT/'parts_sheet_extra_head.png')
    _,components=component_map(extra);parts=[p['id'] for p in yaml.safe_load((GAME/'bible/rigs/humanoid_10.yaml').read_text(encoding='utf-8'))['parts']]
    if len(components)!=11:raise RuntimeError('Extra-head image must actually have 11 disconnected components')
    record('零件图多一个头',job['output'],'C10',{'expected_parts':parts,'parts':parts+['head_extra'],'rig':'humanoid_10'})
    rows[-1]['counterexample_artifact']=str(OUT/'parts_sheet_extra_head.png');rows[-1]['actual_component_count']=len(components)
    version=yaml.safe_load(Path(__file__).with_name('config.yaml').read_text(encoding='utf-8'))['checker_version']
    paths=['checks.py','ocr.cjs','artlib.py','paper_ops.py']
    hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in paths}
    calibration={'checker_version':version,'code_snapshot':hashes,'thresholds_frozen_as_calibrated':False,'thresholds':{'C04':{'delta_E':15,'coverage':.9,'full_asset_approved':0,'full_asset_rejected':0,'reason':'A1 only approved named characteristics; 12 selected references are not full asset labels. 6 references include palette.'},'C12':{'endpoint_difference':.02,'velocity_difference':.02,'approved_loops':0,'rejected_loops':0},'C14':{'score':None,'full_style_approved':0,'full_style_rejected':0,'reason':'No calibrated visual scorer or >=20 approved and rejected samples per category.'}},'partial_anchor_samples':{'scene':5,'resident':4,'ink':2,'ui':1},'A1b_direction_frames':2,'A2_decisions':'pending','rule':'Do not classify unselected images as rejected or feature-only approvals as complete passes.'}
    write_json(REPORT/'negative_checks.json',{'rows':rows,'all_negative_checks_rejected':all(r['verified'] for r in rows),'control_scope':'hole control certifies declared current opaque support only; full hidden geometry still pending'})
    calibration_path=REPORT/'calibration.json'
    if calibration_path.exists():calibration_path=REPORT/'calibration_initial_diagnostic.json'
    write_json(calibration_path,calibration)
    print(json.dumps({'checks':len(rows),'verified':sum(r['verified'] for r in rows),'failures':[r['counterexample']+':'+r['result']['status'] for r in rows if not r['verified']]}))
    if not all(r['verified'] for r in rows):raise RuntimeError('Counterexample failed to reject; do not approve A2')

if __name__=='__main__':main()
