"""T03 request reservations, archival and layout evidence; no API calls."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from PIL import Image, ImageDraw, ImageFont
from artlib import GAME, write_json

REPORT=GAME/'reports/art/T03'
CACHE=Path('D:/gunforge_cache/g01/T03')
REF=GAME/'bible/style_refs'

def prepare():
    if (REPORT/'calls.json').exists():raise FileExistsError('Resume saved T03 calls; never reset attempts')
    REPORT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    hud=json.loads((GAME/'assets/ui/hud_layout.json').read_text(encoding='utf-8'))
    layout={'content_size':[1776,936],'actors':{
        'resident':{'bbox':[650,430,180,330],'ink_center':[740,555],'ink_radius':55},
        'crow':{'bbox':[965,350,300,220],'body_center':[1110,460],'body_radius':58},
        'lamp':{'bbox':[1340,430,120,260],'head_center':[1406,480],'head_radius':47}},
        'covers':[[0,680,350,256],[1500,650,276,286]],
        'note':'Planned placement only; actual art must be annotated separately after generation.'}
    write_json(REPORT/'layout_plan.json',layout)
    im=Image.new('RGB',(1776,936),(80,84,93));d=ImageDraw.Draw(im)
    d.rectangle((360,240,1490,780),fill=(150,146,137))
    for r in layout['covers']:
        x,y,w,h=r;d.rectangle((x,y,x+w,y+h),fill=(28,33,51))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    for key,color,label in [('resident',(222,180,119),'居民 330px'),('crow',(42,42,48),'墨鸦 300px'),('lamp',(156,158,169),'路灯')]:
        x,y,w,h=layout['actors'][key]['bbox'];d.rectangle((x,y,x+w,y+h),fill=color)
        d.text((x,y-35),label,font=font,fill=(220,220,220))
    for key,center,radius in [('resident',[740,555],55),('crow',[1110,460],58),('lamp',[1406,480],47)]:
        x,y=center;d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(8,9,14),outline=(180,64,47),width=3)
    for name,r in hud['reserved'].items():
        if r['when']!='playing':continue
        x,y,w,h=r['rect'];d.rectangle((x,y,x+w,y+h),outline=(205,158,56),width=3)
        d.text((x+3,y+2),'HUD '+name,font=font,fill=(230,206,146))
    d.rectangle((60,60,1716,876),outline=(220,130,70),width=2)
    im.save(REPORT/'whitebox.png')
    jobs=[{'id':'frame_unlit','transparent':False,'references':[str(REPORT/'whitebox.png'),str(REF/'st_l1_alley.png'),str(REF/'res_vendor.png'),str(REF/'ink_rider.png'),str(REF/'st_l3_base.png')],
        'prompt':'''Use case: stylized-concept. Asset: an actual playable side/front-view paper-cut lightgun game screen, NOT concept-art poster. Wide landscape approximately 1776:936; no outer frame, no UI, no words.
Input 1 is a layout whitebox ONLY: use its object positions and safe areas, DO NOT render any rectangles, labels, diagrams or debug marks. Input 2 anchors only the staggered alley composition, NOT its excessive sunset brightness. Input 3 anchors only the vendor's apricot/purple/teal clothing colors, not its thick 3D folds. Input 4 anchors ONLY ink surface, restrained reflections and colors, NOT the rider shape. Input 5 anchors low local warm light, paper layers and colors, not the decorative display border.
Scene: 1990s small Chinese town market alley at NIGHT. Plain roll-up storefronts and simple awnings at the sides; folding table, plastic stools, enamel cup and a thick-spoked bicycle at the edges. Flat stacked cut-paper scenery, subtle fine fibers, clean edges, restrained layering. Indigo #141A33 and deep violet #2A1E3D form about 60 percent; muted apricot #D9A066, dusty pink #C97B84, teal #4E9A92 are local accents. Near foreground is dark and simple. A clear midground street, translucent softly warm distant windows. No broad orange sunset or white light, no antique pagoda roofs. Keep top center, top right and bottom corners visually quiet for HUD added separately.
At roughly x=740 y=600 on a 1776x936 canvas put ONE full-body friendly paper resident, a slim hawthorn vendor, height about 330 pixels, apricot apron, purple sweater and blue trousers. A thick rounded black ink blob about 110 pixels across is attached ONLY to the chest/abdomen centered around (740,555), leaving head, arms, legs and a visible 6-pixel-plus warm paper boundary exposed. It has ONE small FLAT cinnabar stamped mark, not a red eye. Do not turn the whole person black.
At roughly (1110,460) put ONE separate ink CROW, overall wingspan about 300 pixels and height 220, with an unmistakable bird beak and simple broad feather silhouettes. The central black body must be thick, about 110 pixels across. Glossy-wet ink leaning toward a shiny surface, but only a few restrained directional gray-blue reflections, never white, never full bright rim, no plastic/chrome volume. One small FLAT red ink stamp on its central body, not a gemstone.
At the right, one simple streetlamp with its large recognizable lamp head near (1406,480); lamp head about 100 pixels wide, pole to ground around y=690. THIS INTERACTIVE LAMP IS OFF: dark cool lampshade, no warm halo and no pool of light beneath it. Warm windows elsewhere stay subtle and constant. Keep the three targets away from foreground occluders and away from screen edges. Only the resident and crow have flat small red stamps. No extra people or enemies. No text, numbers, logos, score, life bars or crosshair. Muted but readable gameplay, not a cinematic distant view.'''},]
    common='Technical game HUD cut-paper asset. One isolated flat simple shape only. Subtle fine paper fiber, clean cut edge. Muted warm apricot #D9A066 and dark indigo #141A33. No white, glow, bloom, shadow, scenery, lanterns, buildings, characters, text, numbers, panels or presentation mockup. Genuine transparent background with empty margins. '
    ui=[('wick_lit','Exactly ONE lit paper wick icon: a narrow upright apricot paper strip with a small warm-apricot flame-shaped cutout at the top. Entire silhouette fits a tall 36:64 display ratio. No wax candle. Reference image is paper texture/color ONLY, do not copy its five-icon row.',[str(REF/'ui_life.png')]),
        ('wick_out','Exactly ONE extinguished paper wick icon, matching a narrow upright paper strip plus a dark indigo flame-shaped cutout. Same tall 36:64 ratio. No wax candle. Reference image is texture/layout vocabulary ONLY, not the five-icon row.',[str(REF/'ui_life.png')]),
        ('ammo_full','Exactly ONE filled rectangular light-ammo tile, 32:48 aspect ratio. Solid muted apricot flat paper rectangle with tiny clean clipped corners. No central drawing, nothing inside it.',[]),
        ('ammo_empty','Exactly ONE empty rectangular light-ammo tile, 32:48 aspect ratio. A medium teal paper outline with transparent center and tiny clean clipped corners. Outline about 4 pixels at 32x48 display size. Nothing inside it.',[]),
        ('score_frame','Exactly ONE square cinnabar #C8322C stamped outline, empty transparent center. Flat ink granules and slightly imperfect edge, border around 8 percent of square width. No letters or symbols.',[]),
        ('prompt_frame','Exactly ONE very long low rectangular paper notification strip. Width to height about 8.3:1. Deep indigo paper interior about 60 percent opaque and a clean thin muted apricot cut-paper border. Corners very simple and suitable for nine-slice. Empty inside with no drawing.',[])]
    for ident,prompt,refs in ui:jobs.append({'id':ident,'prompt':common+prompt,'transparent':True,'references':refs})
    for j in jobs:j.update(attempt=1,state='planned')
    write_json(REPORT/'queue.json',jobs);write_json(REPORT/'calls.json',{'task_cap':10,'phase_0A_cap':120,'calls':[]})

def reserve(ids):
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'))
    ledger=json.loads((REPORT/'calls.json').read_text(encoding='utf-8'))
    if len(ids)>10 or len(ledger['calls'])+len(ids)>10:raise ValueError('T03 call cap')
    output=[]
    for ident in ids:
        job=next(j for j in queue if j['id']==ident)
        if job['state']!='planned':raise ValueError('Already reserved: reconcile before resubmitting')
        refs=[{'file':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in job['references']]
        params={'prompt':job['prompt'],'transparent_background':job['transparent'],'references':refs}
        fp=hashlib.sha256(json.dumps(params,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
        call={'id':ident,'attempt':job['attempt'],'attempt_id':f"T03:{ident}:a{job['attempt']}",'request_fingerprint':fp,
            'prompt':job['prompt'],'references':refs,'transparent_background':job['transparent'],'state':'submitted',
            'provider':'builtin_image_gen','model':None,'seed':None,'provider_task_id':None,'requested_size':None,
            'cost':None,'cost_status':'not_reported','review_status':'pending'}
        ledger['calls'].append(call);job['state']='submitted';output.append(job)
        (REPORT/(ident+f"_prompt_a{job['attempt']}.txt")).write_text(job['prompt'],encoding='utf-8')
    write_json(REPORT/'queue.json',queue);write_json(REPORT/'calls.json',ledger)
    print(json.dumps(output,ensure_ascii=True))

def archive(rows):
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'));ledger=json.loads((REPORT/'calls.json').read_text(encoding='utf-8'))
    for row in rows:
        job=next(j for j in queue if j['id']==row['id'])
        call=next(c for c in reversed(ledger['calls']) if c['id']==row['id'] and c['state']=='submitted')
        dest=CACHE/(job['id']+f"_a{job['attempt']}.png");shutil.copy2(row['source'],dest)
        record={'state':'returned','source':row['source'],'output':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'actual_size':list(Image.open(dest).size)}
        job.update(record);call.update(record)
    write_json(REPORT/'queue.json',queue);write_json(REPORT/'calls.json',ledger)

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='reserve':reserve(sys.argv[2:])
    elif sys.argv[1]=='archive':archive(json.load(sys.stdin))
