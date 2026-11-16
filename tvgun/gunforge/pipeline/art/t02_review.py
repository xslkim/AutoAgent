"""T02 numerical prescreen, comparison rendering and standalone A1 review page."""
import html
import json
import hashlib
import shutil
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageDraw,ImageFont
import yaml
from artlib import GAME,write_json,yprime
from checks import run
from t02_candidates import REPORT,CACHE

TITLES={'ui_life':'五根灯芯','ui_ammo':'六格光弹药','ui_stamp':'朱砂空印框','ui_frames':'提示条框','ui_title':'标题字','ui_crosshair':'纸环准星'}
NOTES={
'st_l1_alley':'生活物件与中景留白可参考；整体偏橙亮，夜底占比不足，光感需收暗。',
'st_l1_hawthorn':'蜂窝煤炉与搪瓷杯有年代感；偏日落亮调，局部装饰仍偏古镇。',
'st_l1_video':'卷帘门、录像带、电视与录音机明确；亮度和舞台留白还需调整。',
'st_l1_bridge':'桥身横向结构清楚；橙色远景过亮，市场檐口装饰偏多。',
'st_l2_ticket':'售票口和胶片标识清楚；玻璃与灯光为方向参考，交互灯正式版需独立层。',
'st_l2_posters':'空海报框便于后期叠字；座椅和门口层级可参考。',
'st_l2_seats':'品红暗银幕和对角光束有辨识度；前排座椅可作掩体。',
'st_l2_projector':'胶片与暖水瓶有生活感；放映机较复杂，正式版需简化与分层。',
'st_l3_waiting':'长椅、编织袋、时钟能交代场景；构图较满，需留目标空间。',
'st_l3_platform':'长月台、方正绿皮车和黄色腰线明确；适合锚定横向节奏。',
'st_l3_carriage':'车窗、行李架的重复节奏成立；窗外景深与座椅需进一步分层。',
'st_l3_base':'纸层台口可参考；灯座和木框主题不够明确，仍读作街景。',
'res_vendor':'毛衣围裙与橙色糖葫芦明确；姿势非严格中性，扣钉和厚度偏强。',
'res_video':'夹克和录像带盒明确；纸偶轮廓友好，衣服折面偏立体。',
'res_projectionist':'工作服和胶片盘清楚；机械圆盘与袖口细节需简化。',
'res_ticket':'检票动作清楚；新增帽子和臂带较像制服，可决定是否保留；军绿偏离限定色板。',
'res_cyclist':'骑车身份明确；自行车辐条太细，正式分件时需简化。',
'res_passerby':'温暖、朴素、纸色清楚；适合参考居民气质，扣钉偏多。',
'ink_tadpole':'大头、单印迹易辨认；毛边与高光需要在实际显示尺寸下检查。',
'ink_crow':'少高光与平面印迹方向；展开羽毛仍偏细，需保留厚实主可伤害区。',
'ink_rider':'可见车轮，但轮廓偏奔马/骑兽，骑自行车的身份不够准确；建议只参考墨质。',
'ink_sign':'装饰性框较强，招牌轮廓不够明确；不宜直接锚定敌人造型。',
'ink_tape':'录像带和磁带丝能辨认；带丝复杂度偏高。',
'ink_umbrella':'收伞与厚墨身明确；可参考主轮廓，后续还需撑伞状态。',
'ui_life':'第二次生成已去掉场景，四亮一灭、数量正确；缩小后的灯芯细节需验证。',
'ui_ammo':'第二次生成已去掉插画，四满两空；矩形轮廓可用于简洁 HUD。',
'ui_stamp':'第二次生成仅保留空印框；墨边略散，正式尺寸需检查。',
'ui_frames':'第二次生成已移除街景；边框很细，缩小后可能不清楚，需验证。',
'ui_title':'执行者目视为“纸灯城”；仅目视核对，自动 OCR 未运行。',
'ui_crosshair':'再次要求去掉光晕后仍残留软光；只参考环形轮廓，不能直接当正式准星。'}
RECOMMENDED={'st_l1_alley','st_l2_seats','st_l3_platform','st_l3_carriage','res_video','res_passerby','ink_crow','ink_umbrella','ui_life','ui_title'}

def diagnostics(job,palette):
    source=Path(job['output']);a=np.asarray(Image.open(source).convert('RGBA')).copy()
    checks={'C03':run('C03',{'file':str(source)},Path('.')),
            'C05':run('C05',{'file':str(source),'expected_text':'纸灯城' if job['id']=='ui_title' else ''},Path('.')),
            'C14':{'status':'pending','reason':'尚无锚点，不评分；执行者目视意见：'+NOTES.get(job['id'],'A 版刻意使用强高光与球状红核，只作对比。')}}
    checks['C05']['manual_observation']='执行者目视为纸灯城，非OCR结果' if job['id']=='ui_title' else '执行者预筛未见可辨文字；自动OCR未运行'
    # Exclude permitted cinnabar from palette coverage; inspect it separately in final assets.
    if job['group'] in {'ink','comparison'} or job['id']=='ui_stamp':
        r,g,b=a[...,:3].astype(float).transpose(2,0,1)
        red=(r>g*1.5)&(r>b*1.5)&(r>70)
        a[red,3]=0
    tmp=CACHE/(job['id']+'_palette_input.png');Image.fromarray(a).save(tmp)
    checks['C04']=run('C04',{'file':str(tmp),'palette_rgb':palette},Path('.'))
    if job['id']=='ui_stamp' and not np.any(a[...,3]):
        checks['C04']={'status':'na','reason':'独立朱砂印框排除于普通色板覆盖率；朱砂色域与整帧面积另验收','details':{}}
    im=Image.open(source).convert('RGBA');size=im.size;arr=np.asarray(im)
    return checks,{'size':list(size),'mode':im.mode,'transparent_fraction':float((arr[...,3]==0).mean()),
                   'sha256':job['sha256']}

def review_preview(source,dest):
    im=Image.open(source).convert('RGBA')
    if im.getextrema()[-1][0]<255:
        # Evidence compositing only; original asset alpha is unchanged.
        base=Image.new('RGBA',im.size,(118,124,137,255));im=Image.alpha_composite(base,im)
    im.convert('RGB').save(dest,quality=91)

def comparisons(queue,out):
    background=ImageOps.fit(Image.open(CACHE/'st_l1_alley.png').convert('RGBA'),(1776,936))
    paths=[]
    for name,ident in [('A','ink_compare_a'),('B','ink_crow')]:
        job=next(j for j in queue if j['id']==ident)
        crow=Image.open(job['output']).convert('RGBA')
        crow=ImageOps.contain(crow,(700,520),Image.Resampling.LANCZOS)
        stage=background.copy();stage.alpha_composite(crow,((1776-crow.width)//2,250))
        path=out/f'comparison_{name}.png';stage.save(path);paths.append(path)
    return paths

def manifest(queue,calls,results):
    """Expand saved reservations into auditable records without another image call."""
    records=[]
    for call in calls:
        job=next(j for j in queue if j['id']==call['id'])
        current=call['attempt']==job['attempt']
        attempt=job if current else next(h for h in job['history'] if h['attempt']==call['attempt'])
        refs=[{'file':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in job.get('references',[])]
        request={'prompt':attempt['prompt'],'transparent_background':job['transparent'],'references':refs}
        fingerprint=hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
        records.append(dict(call,attempt_id=f"T02:{job['id']}:a{call['attempt']}",
            prompt=attempt['prompt'],request_fingerprint=fingerprint,fingerprint_recorded='reconstructed_from_saved_request',
            references=refs,source=attempt['source'],sha256=attempt['sha256'],
            requested_size=None,actual_size=list(Image.open(attempt['output']).size),normalization='none_original_candidate',
            provider='builtin_image_gen',provider_task_id=None,model=None,seed=None,cost_status='not_reported',
            unavailable_fields_reason='Native tool did not expose model, seed, task ID, exact request size or price',
            checks=results[job['id']]['checks'] if current else {'visual':{'status':'fail','reason':'首轮 UI 过度场景化，已替换；数值未重跑'}},
            review_status='pending' if current else 'superseded_by_executor_visual_prescreen'))
    return {'task':'T02','stage':'candidate_only','approved':False,
        'cost':{'amount':None,'status':'not_reported'},'calls':records,'candidates':queue}

def main():
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'))
    assert all(j['state']=='returned' for j in queue)
    output=REPORT/'gallery';output.mkdir(parents=True,exist_ok=True)
    palette=[list(bytes.fromhex(c['hex'][1:])) for c in json.loads((GAME/'bible/palette.json').read_text(encoding='utf-8'))['colors'] if c['hex']!='#C8322C']
    cards=[];all_results={};legacy=[]
    counters=Counter()
    for job in queue:
        ident=job['id'];counters[job['group']]+=1
        print('Checking '+ident,flush=True)
        checks,meta=diagnostics(job,palette)
        all_results[ident]={'checks':checks,'metadata':meta,'visual_note':NOTES.get(ident,'A 版刻意使用强高光与球状红核，只作对比。')}
        original=output/(ident+'_original.png');shutil.copy2(job['output'],original)
        preview=output/(ident+'_preview.jpg');review_preview(original,preview)
        if job['group']!='comparison':
            cards.append({'id':ident,'title':TITLES.get(ident,job['title']),'group':job['group'],
                          'preview':preview.name,'original':original.name,'checks':checks,'metadata':meta,
                          'note':NOTES[ident],'recommended':ident in RECOMMENDED})
        for old in job.get('history',[]):
            dest=output/(ident+f"_rejected_a{old['attempt']}.jpg");review_preview(old['output'],dest)
            legacy.append({'id':ident,'preview':dest.name,'note':'首轮 UI 过度场景化，已修改提示词重出；原稿保留。'})
    comparisons(queue,output)
    write_json(REPORT/'checks.json',all_results)
    calls=json.loads((REPORT/'calls.json').read_text(encoding='utf-8'))['calls']
    assert len(calls)==36 and len(cards)==30
    write_json(REPORT/'manifest.json',manifest(queue,calls,all_results))
    form={'stage':'A1','status':'awaiting_human_review','ink_choice':None,'style_notes':'',
          'items':[{'id':c['id'],'status':'pending','anchor_for':[],'note':''} for c in cards]}
    if not (REPORT/'review.yaml').exists():(REPORT/'review.yaml').write_text(yaml.safe_dump(form,allow_unicode=True,sort_keys=False),encoding='utf-8')
    data=json.dumps(cards,ensure_ascii=False).replace('</','<\\/')
    olddata=json.dumps(legacy,ensure_ascii=False).replace('</','<\\/')
    template=PAGE.replace('__CARDS__',data).replace('__LEGACY__',olddata)
    (output/'index.html').write_text(template,encoding='utf-8')
    # Contact sheet for layout QA. It is a diagnostic, not a replacement asset.
    sheet=Image.new('RGB',(1600,6*290),(238,239,241));draw=ImageDraw.Draw(sheet)
    for index,c in enumerate(cards):
        image=ImageOps.contain(Image.open(output/c['preview']),(300,240))
        x=(index%5)*320;y=(index//5)*290
        sheet.paste(image,(x+(320-image.width)//2,y+25));draw.text((x+8,y+4),c['id'],fill='black')
    sheet.save(REPORT/'contact_sheet.jpg',quality=90)
    fail=Counter(k for r in all_results.values() for k,v in r['checks'].items() if v['status']=='fail')
    write_json(REPORT/'summary.json',{'generated_calls':36,'candidate_items':30,'comparison_composites':2,
        'replaced_ui_attempts':5,'numeric_failed_checks':dict(fail),'cost':None})
    state=json.loads((REPORT.parent/'execution_state.json').read_text(encoding='utf-8'))
    state.update(updated='2026-11-04',T02='awaiting_A1_human_review',builtin_image_calls=39,
                 current_blockers=['A1: choose 6–12 anchors and ink A/B'],next_task='T03_after_A1',unreported_generation_cost=None)
    write_json(REPORT.parent/'execution_state.json',state)
    print(json.dumps({'cards':len(cards),'calls':len(calls),'failures':dict(fail),'next':'A1 human review'}))

def refresh_gallery():
    """Rebuild the review UI from recorded results without generating or checking images."""
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'))
    results=json.loads((REPORT/'checks.json').read_text(encoding='utf-8'))
    cards=[];legacy=[]
    for job in queue:
        ident=job['id']
        if job['group']!='comparison':
            cards.append({'id':ident,'title':TITLES.get(ident,job['title']),'group':job['group'],
                'preview':ident+'_preview.jpg','original':ident+'_original.png',
                'checks':results[ident]['checks'],'metadata':results[ident]['metadata'],
                'note':NOTES[ident],'recommended':ident in RECOMMENDED})
        for old in job.get('history',[]):
            legacy.append({'id':ident,'preview':ident+f"_rejected_a{old['attempt']}.jpg",
                'note':'首轮 UI 过度场景化，已替换。'})
    page=PAGE.replace('__CARDS__',json.dumps(cards,ensure_ascii=False).replace('</','<\\/'))
    page=page.replace('__LEGACY__',json.dumps(legacy,ensure_ascii=False).replace('</','<\\/'))
    (REPORT/'gallery/index.html').write_text(page,encoding='utf-8')
    print(json.dumps({'cards':len(cards),'legacy':len(legacy),'mode':'page_only'}))


PAGE=Path(__file__).with_name('t02_gallery.html').read_text(encoding='utf-8')

if __name__=='__main__':
    import sys
    if '--page-only' in sys.argv:refresh_gallery()
    else:main()
