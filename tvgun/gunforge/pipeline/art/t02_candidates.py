"""Prompt queue and archival for T02 native image generation; no API calls."""
import json
import hashlib
import shutil
import sys
from pathlib import Path
from artlib import ROOT,GAME,write_json

REPORT=GAME/'reports/art/T02'
CACHE=Path('D:/gunforge_cache/g01/T02')
MATERIAL='手工刻纸与纸雕灯游戏美术方向。平面纸片叠层，切口干净，细纸纤维，造型简洁，纸面平整。近景深色剪影，中景清楚，远景温暖透光。1990年代中国小城的日常生活。不要古镇古装、写实摄影、塑料和树脂质感、厚重3D倒角、卷纸。'
PALETTE='严格围绕靛青#141A33、深紫#2A1E3D、暖杏#D9A066、桃粉#C97B84、青绿#4E9A92、月白#B8C4D6、品红#B04A9A、冰蓝#4A90B8。没有纯白，不画白月亮与白色爆闪。光是纸层间低亮暖光，不画大面积发白光源。'
SCENES=[
('st_l1_alley','夜市巷口','两侧卷帘门摊位前后交错，中间保留清楚的亮街台口；塑料凳、折叠桌、二八自行车、电线杆与高音喇叭。最多两盏灯笼，一盏路灯熄灭。','暖杏与桃粉'),
('st_l1_hawthorn','糖葫芦摊','前景一角的摊台成为掩体，另一侧搪瓷杯、蜂窝煤炉和折叠桌，糖葫芦为偏橙暖红。用横向错位构图留出中景台口，最多两盏灯笼，招牌为空。','暖杏与桃粉'),
('st_l1_video','录像厅门口','普通旧居民楼底层卷帘门，录像带盒、空海报框、旧录音机、塑料凳和窗内暗暖光；不要仿古屋檐，侧向台阶作前景掩体，中景门口清晰。','暖杏与桃粉'),
('st_l1_bridge','夜市天桥','简朴混凝土人行天桥横跨画面中上部，栏杆转译成剪纸轮廓；桥下两侧摊位、电线、自行车、折叠桌，清楚的三个深度带。','暖杏与桃粉'),
('st_l2_ticket','影院售票处','旧影院玻璃售票窗口、空价目牌、栏杆、暖水瓶和玻璃汽水瓶，左右错开近景遮挡；售票口与后方通道形成清楚的纵向纸层。','品红与冰蓝，少量暖杏'),
('st_l2_posters','影院海报长廊','墙上空的手绘电影海报框，木长椅、关着的放映门、纸质墙裙。走廊前视保持平面感，左右交错而非对称亮洞，地面不反光。','品红与冰蓝，少量暖杏'),
('st_l2_seats','影院观众席','前排木折叠座椅剪影、中景暗品红银幕、远处侧上方放映窗，低亮冰蓝光束形成对角线。银幕不发白，留明确中景可射台口。','品红与冰蓝'),
('st_l2_projector','影院放映室','胶片放映机、胶片盘、暖水瓶与狭小工作台，窗口的低亮光束从左上斜过；设备轮廓剪纸化，不要复杂写实机械。','深紫、品红与冰蓝'),
('st_l3_waiting','火车站候车室','旧长椅、编织袋、搪瓷缸、站台时钟、空大字标语框与检票栏杆；横向重复长椅产生节奏，避免居中亮洞。','青绿与月白，少量暖杏'),
('st_l3_platform','绿皮火车站台','方正绿皮车厢带低饱和黄色腰线，连续车窗、站台时钟、编织袋、长月台，与画面平行的长水平线。不是欧式蒸汽火车，局部暖杏车窗。','青绿与月白，少量暖杏'),
('st_l3_carriage','绿皮车厢内部','平行画面的车厢侧窗、行李架、编织袋、暖水瓶和搪瓷缸，重复车窗与座位的横向节奏，层叠纸片窗外夜色。','青绿与月白，少量暖杏'),
('st_l3_base','纸灯灯座','由纸雕小城底部过渡到纸灯底座，简单木质框转译为平纸片，暖灯芯在后方提供常驻背光，前景纸层像舞台台口展开。安静怀旧。','青绿与月白，少量暖杏')]
RESIDENTS=[('res_vendor','瘦高卖糖葫芦的人，普通毛衣加暖杏围裙，手持偏橙糖葫芦，友善'),('res_video','微胖录像厅老板，灰青夹克、暖杏衬衫，手持无字录像带盒'),('res_projectionist','中年放映员，青绿工作服、卷起袖口，手持简化胶片盘'),('res_ticket','检票员，普通军绿外套、布鞋，手持无字纸票，朴素'),('res_cyclist','穿桃粉毛衣和普通长裤的骑车居民，手扶简化二八自行车'),('res_passerby','老人路人，暖杏毛衣、青绿色长裤、布鞋，提编织袋，温和')]
INK=[('ink_tadpole','墨蝌蚪，头部是一团直径很大的圆润墨团，细尾巴；只有一只，不画群体'),('ink_crow','墨鸦，吃掉麻雀后形成，厚实墨身，简洁粗羽轮廓和一条墨滴，半展翅'),('ink_rider','墨车夫，墨吞掉二八自行车形成的骑车轮廓，身体是厚实墨团，车轮简化避免细节抢眼'),('ink_sign','墨招牌，墨团从一块无字的镂空招牌后探出，吐墨动作前的中性造型'),('ink_tape','磁带墨，录像带被吞后形成的大墨团，少量宽磁带丝缠绕，不要满身细丝'),('ink_umbrella','墨伞，简化雨伞收拢到一侧，露出宽大墨身；只有一个朱砂印迹')]
UI=[('ui_life','只画一套五根剪纸灯芯：四根低亮暖杏点亮，一根深青熄灭；每根造型清晰，无文字、数字、UI面板，无写实蜡烛。'),('ui_ammo','只画一套六格“光”弹药符号：四格暖杏充满，两格空心青色，纸片构成，排列等距，无文字数字和背景面板。'),('ui_stamp','只画一个朱砂方印框，平面印泥颗粒与不规则边缘，中间完全透明，不带任何文字、图案或数字，朱砂#C8322C。'),('ui_frames','只画一个纸雕风格的深色长方提示条框，暖杏纸切边，中心留透明空白，四角适合九宫格缩放，无字无符号。'),('ui_title','只画标题三个汉字“纸灯城”，必须逐字正确，不加副标题；毛笔但干净可读，暖杏纸雕剪影字形，细纤维与纸切边，透明背景，不发光。'),('ui_crosshair','只画一个纸环准星，细暖杏平面纸环、四个简短切口，中心完全透明，低亮不发白，无字无额外装饰。')]

def make_jobs():
    jobs=[]
    for ident,title,scene,colors in SCENES:
        prompt=f'{MATERIAL} {PALETTE} 制作游戏站点风格候选：{title}。{scene} 主色{colors}。宽幅约1.9:1，正面平视，不做大角度透视；近中远6至10层视觉层次，前景简单遮挡，中景保留足够空白和清晰亮底，远处透光。没有人物、敌人、HUD、准星和任何可辨文字字母；标牌留空。不画朱砂红。整张不透明背景，画到边缘，不画外部展示框。'
        jobs.append(dict(id=ident,title=title,group='stations',prompt=prompt,transparent=False))
    for ident,description in RESIDENTS:
        prompt=f'{MATERIAL} {PALETTE} 一个独立纸居民设定候选：{description}。亮色纸身体，绝不画黑色身体；四分之三侧身，单个全身中性站姿，头身比约1:4.5，剪纸五官简单友善，不画表情细节。身体约十件纸偶分件感、圆形搭接、铜色小纸扣；不要把衣服分解展示。不画墨团，不画红点。真正透明背景，轮廓完整，四周留空，不画棋盘格、地面、投影、文字或标签。'
        jobs.append(dict(id=ident,title=description.split('，')[0],group='residents',prompt=prompt,transparent=True))
    for ident,description in INK:
        prompt=f'游戏墨怪方向候选，单独一只：{description}。平面墨黑#0B0B0E的液态墨造型，轮廓清楚，靠流淌拉丝、渗入纸纤维的毛边和墨滴表现。只有朝光侧极少湿润高光，总面积小于墨身5%，不可整圈勾亮边。只有一枚平的朱砂#C8322C印泥印迹在厚实身体中，不是眼睛不是宝石不是球；边缘一点点暖杏柔光。身体足够厚，缩小仍好认。真正透明背景，不画地面、投影、棋盘格、文字、标注；不画3D树脂玩具，不画血腥恐怖，不画其他红点，不画白色高光。'
        jobs.append(dict(id=ident,title=description.split('，')[0],group='ink',prompt=prompt,transparent=True))
    for ident,description in UI:
        prompt=f'{MATERIAL} {PALETTE} 独立游戏UI方向候选。{description} 真正透明背景，平面设计，完整主体四周留空，不画展示样机、场景、地面、投影、棋盘格。没有指定以外的文字或额外符号。'
        jobs.append(dict(id=ident,title=ident,group='ui',prompt=prompt,transparent=True))
    return jobs

def prepare():
    REPORT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    if (REPORT/'queue.json').exists():raise FileExistsError('Queue already exists; resume it without resetting attempts')
    jobs=make_jobs()
    for job in jobs:
        job.update(state='planned',attempt=1,cost={'amount':None,'status':'not_reported'})
        (REPORT/(job['id']+'_prompt.txt')).write_text(job['prompt'],encoding='utf-8')
    write_json(REPORT/'queue.json',jobs)
    write_json(REPORT/'calls.json',{'T02_cap':36,'phase_0A_cap':120,'calls':[]})
    (GAME/'bible/style.md').write_text('# 纸灯城风格词草案\n\n状态：T02 A1 待审核，尚无已选锚点。\n\n## 材质与造型\n\n'+MATERIAL+'\n\n## 色板\n\n'+PALETTE+'\n\n## 构图\n\n夜市横向交错、影院纵向层级与对角光束、火车站平行长线。纸层近暗远亮，中景是目标台口。\n\n## 墨与朱砂\n\n默认少高光湿墨与平面朱砂印迹。A/B 对比由审核人决定，候选不是已审核锚点。\n\n## 执行\n\n每项独立 GPT 调用；透明素材保留真实 alpha；实际尺寸记录后归一化；未知费用不记零。\n\n## 避免\n\n纯白、白月亮、古装古镇、树脂塑料、厚重3D倒角、复杂目标镂空、额外红点、背景烘焙文字。\n',encoding='utf-8')
    state=json.loads((REPORT.parent/'execution_state.json').read_text(encoding='utf-8'));state['T02']='in_progress_style_candidates';write_json(REPORT.parent/'execution_state.json',state)

def reserve(ids):
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'));calls=json.loads((REPORT/'calls.json').read_text(encoding='utf-8'))
    if len(ids)>10 or len(calls['calls'])+len(ids)>36:raise ValueError('T02 call budget exceeded')
    selected=[]
    for ident in ids:
        job=next(j for j in queue if j['id']==ident)
        if job['state']!='planned':raise ValueError('Already reserved/generated; reconcile before resubmitting')
        job['state']='submitted';selected.append(job)
        calls['calls'].append({'id':ident,'attempt':job['attempt'],'state':'submitted','cost':None})
    write_json(REPORT/'queue.json',queue);write_json(REPORT/'calls.json',calls)
    print(json.dumps(selected,ensure_ascii=True))

def archive(rows):
    queue=json.loads((REPORT/'queue.json').read_text(encoding='utf-8'));calls=json.loads((REPORT/'calls.json').read_text(encoding='utf-8'))
    for row in rows:
        job=next(j for j in queue if j['id']==row['id'])
        call=next(c for c in reversed(calls['calls']) if c['id']==row['id'] and c['state']=='submitted')
        if row.get('error'):
            job.update(state='error',error=row['error']);call['state']='error';continue
        src=Path(row['source']);dest=CACHE/(job['id']+(f"_a{job['attempt']}" if job['attempt']>1 else '')+'.png');shutil.copy2(src,dest)
        job.update(state='returned',source=str(src),output=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        call.update(state='returned',output=str(dest))
    write_json(REPORT/'queue.json',queue);write_json(REPORT/'calls.json',calls)

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='queue':print(json.dumps(json.loads((REPORT/'queue.json').read_text(encoding='utf-8')),ensure_ascii=True))
    elif sys.argv[1]=='reserve':reserve(sys.argv[2:])
    elif sys.argv[1]=='archive':archive(json.load(sys.stdin))
