"""Meaningful offline acceptance tests; all generated fixtures stay outside Git."""
import json
import math
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from artlib import GAME,Ledger,fingerprint,crop_bleed,rgba,encode_sdf,write_json,effective_radius
from checks import run,suite,IDS
from preview import render,movie,gallery,review_form,decisions,whitebox,pose

CACHE=Path('D:/gunforge_cache/g01/T00');REPORT=GAME/'reports/art/T00'

def main():
    CACHE.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    tests=[]
    def expect(name,actual,expected):
        tests.append(dict(name=name,passed=actual==expected,actual=actual,expected=expected))
        if actual!=expected:raise AssertionError(tests[-1])
    def check(c,s):return run(c,s,CACHE)
    yy,xx=np.ogrid[:256,:256];circle=(xx-128)**2+(yy-128)**2<=60**2
    Image.fromarray((circle*255).astype('uint8')).save(CACHE/'alpha.png')
    Image.fromarray(encode_sdf(circle)).save(CACHE/'sdf.png')
    expect('SDF offline roundtrip',check('C16',{'sdf':'sdf.png','alpha':'alpha.png','source_color':False})['status'],'pass')
    expect('SDF wrong color transfer rejected',check('C16',{'sdf':'sdf.png','alpha':'alpha.png','source_color':True})['status'],'fail')
    a=np.zeros((256,256,4),dtype='uint8');a[circle]=[40,60,100,255]
    Image.fromarray(a).save(CACHE/'body.png')
    cropped,origin=crop_bleed(a)
    expect('Crop preserves origin',origin,[60,60])
    expect('RGB bleed preserves alpha',int(cropped[0,0,3]),0)
    expect('RGB bleed retains edge color',list(cropped[0,0,:3]),[40,60,100])
    Image.fromarray(np.zeros((256,256),dtype='uint8')).save(CACHE/'empty.png')
    Image.fromarray(np.full((256,256),255,dtype='uint8')).save(CACHE/'extent.png')
    hole=np.full((256,256,4),255,dtype='uint8');hole[100:120,100:120]=0
    Image.fromarray(hole).save(CACHE/'hole.png')
    expect('Missing middle layer rejected',check('C07b',{'file':'hole.png','extent':'extent.png','occlusion':'empty.png'})['status'],'fail')
    full=Image.new('RGBA',(256,256),(30,40,50,255));full.save(CACHE/'full.png')
    expect('Opaque far layer masks hole in final alpha',check('C07a',{'layers':['full.png','hole.png']})['status'],'pass')
    expect('Valid layer extent passes',check('C07b',{'file':'full.png','extent':'extent.png','occlusion':'empty.png'})['status'],'pass')
    spec={'primary':'alpha.png','protected':'empty.png','weak':'empty.png','content_size':[1776,936],
          'motion_bbox':[400,300,160,160],'hud_rects':[[8,832,244,96]]}
    expect('Valid primary mask',check('C09',spec)['status'],'pass')
    expect('HUD overlap rejected',check('C09',dict(spec,motion_bbox=[40,820,180,100]))['status'],'fail')
    expect('Core outside body rejected',check('C11',{'body':'empty.png','core':'alpha.png'})['status'],'fail')
    expect('Oversized lossless atlas rejected',check('C15',{'textures':[{'size':[4096,4096],'bytes_per_pixel':4}], 'limit_bytes':32_000_000})['status'],'fail')
    expect('Valid estimate does not claim engine pass',check('C15',{'textures':[{'size':[256,256],'bytes_per_pixel':4}], 'limit_bytes':32_000_000})['status'],'pending')
    expect('Extra rig part rejected',check('C10',{'expected_parts':['head','torso'],'parts':['head','torso','extra_head']})['status'],'fail')
    Image.new('RGB',(1920,1080),'white').save(CACHE/'false_screen.png')
    expect('Tracker rejects solid bright false screen',check('C13',{'file':'false_screen.png','full_display_frame':True})['status'],'fail')
    screen=Image.new('RGB',(2000,1160),'black');draw=ImageDraw.Draw(screen)
    draw.rectangle((40,40,1960,1120),fill='white');draw.rectangle((64,64,1936,1096),fill='black')
    screen.save(CACHE/'screen.png')
    screened=check('C13',{'file':'screen.png','full_display_frame':True})
    expect('Tracker frontal control acquires frame',screened['details']['samples'][0]['acquired'],True)
    expect('Tracker preserves every perspective result including stress',len(screened['details']['samples']),4)
    expect('Tracker tests three admissible perspectives',sum(s['within_tracker_geometry_contract'] for s in screened['details']['samples']),3)
    expect('Tracker retains out-of-contract stress',screened['details']['samples'][-1]['role'],'retained_out_of_contract_stress')
    baseline=REPORT/'tracker_baseline.json';historical=REPORT/'tracker_baseline_pre_A2e.json'
    if baseline.exists() and not historical.exists():historical.write_bytes(baseline.read_bytes())
    write_json(REPORT/'tracker_baseline.json',screened)
    expect('Valid color format',check('C01',{'file':'body.png','kind':'color'})['status'],'pass')
    expect('Data texture format rejects RGBA',check('C01',{'file':'body.png','kind':'sdf'})['status'],'fail')
    expect('Brightness ceiling catches full white',check('C03',{'file':'full.png'})['status'],'pass')
    Image.new('RGBA',(256,256),'white').save(CACHE/'white.png')
    expect('Brightness ceiling rejects white',check('C03',{'file':'white.png'})['status'],'fail')
    expect('CIEDE2000 exact palette',check('C04',{'file':'body.png','palette_rgb':[[40,60,100]]})['status'],'pass')
    expect('CIEDE2000 wrong palette',check('C04',{'file':'body.png','palette_rgb':[[255,255,255]]})['status'],'fail')
    expect('Loop still-frame control',check('C12',{'frames':['body.png']*3,'pixel_threshold':.01,'velocity_threshold':.01})['status'],'pass')
    expect('Invalid loop rejected',check('C12',{'frames':['body.png','full.png','full.png'],'pixel_threshold':.01,'velocity_threshold':.01})['status'],'fail')
    with tempfile.TemporaryDirectory() as tmp:
        ledger=Ledger(Path(tmp)/'ledger.sqlite',{'T01':100,'T02':100},7)
        expect('Budget reservation',ledger.reserve('a','T01','r','fp',1,14,{}),True)
        expect('Idempotent reservation',ledger.reserve('a','T01','r','fp',1,14,{}),False)
        try:ledger.reserve('b','T02','r','fp2',1,7,{})
        except ValueError:blocked=True
        else:blocked=False
        expect('In-flight funds enforce run cap',blocked,True)
        ledger.submitted('a','provider-job-1')
        restored=Ledger(Path(tmp)/'ledger.sqlite',{'T01':100,'T02':100},7)
        expect('Restart recovers task for polling',restored.recovery()[0]['action'],'poll')
        ledger.settle('a',1)
        expect('Settlement releases unused reserve',ledger.reserve('b','T02','r','fp2',1,7,{}),True)
        expect('Unknown submission not blindly repeated',ledger.recovery()[0]['action'],'reconcile_before_resubmit')
    config=json.loads((GAME/'assets/ui/hud_layout.json').read_text(encoding='utf-8'))
    for name,color,size,pos,z,parallax in [('far',(40,45,65,255),(1920,1020),(0,0),0,.1),
       ('mid',(160,110,70,255),(800,500),(400,380),1,.5),('near',(20,25,40,255),(650,250),(50,720),2,.9)]:
        Image.new('RGBA',size,color).save(CACHE/f'{name}.png')
    station={'canvas':[1920,1020],'content_origin':[72,42], 'layers':[
        {'id':name,'file':f'{name}.png','pos':pos,'z':z,'parallax':parallax}
        for name,pos,z,parallax in [('far',[0,0],0,.1),('mid',[400,380],1,.5),('near',[50,720],2,.9)]]}
    write_json(CACHE/'station.json',station)
    original={'parts':[{'id':'torso','file':'body.png','pivot':[128,128],'parent':None}]}
    Image.fromarray(cropped).save(CACHE/'cropped.png')
    trimmed={'parts':[{'id':'torso','file':'cropped.png','pivot':[128-origin[0],128-origin[1]],'parent':None}]}
    original_pose=pose(original,CACHE,(200,200),1,{},(400,400))
    cropped_pose=pose(trimmed,CACHE,(200,200),1,{},(400,400))
    black=Image.new('RGBA',(400,400),'black')
    expect('Crop and pivot preserve assembled visual placement',
           bool(np.array_equal(np.asarray(Image.alpha_composite(black,original_pose)),np.asarray(Image.alpha_composite(black,cropped_pose)))),True)
    Image.new('L',(1920,1020),64).save(CACHE/'spill.png')
    lit=dict(station,lights=[{'id':'lamp','space':'mid','spill':'spill.png','color':'#D9A066','intensity':.5}])
    off=render(lit,CACHE,light_states={'lamp':0});on=render(lit,CACHE,light_states={'lamp':1})
    expect('Light state changes visible scene brightness',bool(np.asarray(on)[...,:3].mean()>np.asarray(off)[...,:3].mean()),True)
    items=[];frames=[]
    for cx,cy in [(-60,-30),(-60,30),(60,-30),(60,30)]:
        for sign in [-1,1]:
            frame=render(station,CACHE,(cx,cy),(8*sign,4*sign),hud=config,overlay=True)
            path=CACHE/f'corner_{cx}_{cy}_{sign}.png';frame.save(path)
            expect(f'Corner {cx},{cy},{sign} opaque',bool(np.all(np.asarray(frame)[...,3]==255)),True)
            items.append(dict(id=path.stem,preview=str(path),status='pending',note='Synthetic geometry, not game art'))
    for i in range(30):
        t=i/29*math.tau
        frames.append(render(station,CACHE,(60*math.sin(t),30*math.cos(t)),(8*math.sin(2*t),4*math.cos(2*t)),hud=config,overlay=True))
    movie(frames,CACHE/'motion.mp4')
    items.append(dict(id='motion',preview=str(CACHE/'motion.mp4'),status='pending',note='Offline preview only'))
    whitebox({'slots':[[400,300,160,300]],'covers':[[60,700,600,176]],'lights':[[1200,200,100,150]]},config).save(CACHE/'whitebox.png')
    specs={'C01':{'file':'body.png','kind':'color'},'C02':{'file':'body.png','matte_rgb':[216,210,200]},
           'C03':{'file':'body.png'},'C04':{'file':'body.png','palette_rgb':[[40,60,100]]},
           'C05':{'file':'body.png'},'C06':{'file':'body.png','target':'alpha.png','background':'white.png','state':'normal'},
           'C07a':{'layers':['full.png','hole.png']},'C07b':{'file':'full.png','extent':'extent.png','occlusion':'empty.png'},
           'C08':{'file':'body.png','block_mask':'alpha.png'},'C09':spec,
           'C10':{'rig':'humanoid_10','expected_parts':['head','torso'],'parts':['head','torso']},
           'C11':{'body':'alpha.png','core':'empty.png'},
           'C12':{'frames':['body.png']*3,'pixel_threshold':.01,'velocity_threshold':.01},
           'C13':{'file':'screen.png','full_display_frame':True},
           'C15':{'textures':[{'size':[256,256],'bytes_per_pixel':4}],'limit_bytes':32_000_000},
           'C16':{'sdf':'sdf.png','alpha':'alpha.png','source_color':False}}
    results=suite(specs,CACHE,REPORT/'checks')
    expect('Every checker has explicit status',len(results),len(IDS))
    gallery(items,REPORT/'gallery')
    if not (REPORT/'review.yaml').exists():review_form(items,REPORT/'review.yaml')
    expect('Review schema reads pending decisions',len(decisions(REPORT/'review.yaml')['items']),len(items))
    write_json(REPORT/'verification.json',{'tests':tests,'checks':results,'cache':str(CACHE)})
    print(json.dumps({'tests_passed':len(tests),'gallery':str(REPORT/'gallery/index.html'),'checks':{c:r['status'] for c,r in results.items()}},ensure_ascii=False))

if __name__=='__main__':main()
