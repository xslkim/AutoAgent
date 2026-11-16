"""Build the six-wave combat candidate with finite ammunition and readable attacks."""
import json,hashlib
from compiler import ROOT,DEFAULT_CACHE,read_package,compile_source,write_build
from versions import publish
from freeze_baseline import dump
from combat_cues import ensure_combat_cues
def build(*, station_candidate=False, source_only=False, crow_windup_ms=720, crow_lunge_ms=280):
 runtime=ROOT/'gunforge/framework/runtime';station=json.loads((runtime/'station/station.json').read_bytes())
 source={'schema_version':1,'id':'paper.assault','ruleset':'directed_action@1','seed':421,'tick_hz':60,'duration_ms':84000,'layout':{'width':1776,'height':936},'entities':{},'events':{},'queries':{},'resources':{},'cues':{},'effects':{},'sections':{},'initial_resources':{'lives':5,'ammo':80,'score':0,'purified':0,'rescued':0},'resource_bounds':{'lives':{'min':0,'max':5},'score':{'min':0},'ammo':{'min':0,'max':80}},'controls':{'ammo_resource':'ammo','shot_interval_ms':150,'assist_px':12},'hud':[{'label':'灯芯','resource':'lives'},{'label':'剩余光弹','resource':'ammo'},{'label':'印记','resource':'score'}]}
 resources=source['resources'];entities=source['entities'];events=source['events'];effects=source['effects']
 encounter = {'waves': {}, 'attacks': {}, 'supports': {}}
 source['encounter'] = encounter
 def resource(id,path,kind='image'):
  resources[id]={'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':kind};return id
 def event(id,trigger,actions,guards=(),limit=1,priority=0):
  events[id]={'trigger':trigger,'actions':{f'a{i}':action for i,action in enumerate(actions)},'order':[f'a{i}' for i in range(len(actions))],'guards':list(guards),'max_firings':limit,'priority':priority}
 def effect(id,kind,duration,color,radius=80,label=None):
  effects[id]={'kind':kind,'duration_ms':duration,'color':color,'radius':radius}
  if label:effects[id]['label']=label
 def entity(template,x,y,w,h,**properties):return {'template':template,'x':x,'y':y,'width':w,'height':h,'properties':properties}
 def frame(at,x,y,scale=1,rotation=0,offset_ms=0):
  timing = {'at_ms':at} if isinstance(at,int) else {'attack_time':at,'offset_ms':offset_ms}
  return {**timing,'x':x,'y':y,'scale':scale,'rotation_rad':rotation}
 presentation={'title':'纸灯城','subtitle':'巷口夜袭 · 战斗候选 R2','instructions':'优先打断蓄力 · 朱印是弱点 · 点灯震退附近怪物','default_sound':True,'debug_shell':False,'layers':{},'puppets':{},'sound_bindings':{'weapon.fired':'shot','weapon.empty':'empty','target.hit':'hit','target.weak_hit':'weak','target.neutralized':'purify','attack.warning':'windup','attack.launched':'attack','player.damaged':'hurt','interaction.activated:lamp':'lamp'},'feedback':{'shot':'shot_spark','hit':'hit_spark','weak':'weak_spark','neutralized':'purify_burst','empty':'empty_feedback'},'support':{'entity':'lamp','label':'射击点灯 · 震墨'},'labels':{'stunned':'震退','section_unit':'波','progress':'净化','result_success':'巷口守住了','result_failure':'灯芯耗尽'}}
 source['presentation']=presentation
 if station_candidate:
  source.update(id='paper.station', duration_ms=95000)
  presentation.update(
   subtitle='第一站 · 夜市巷口',
   instructions='墨潮涌进夜市。守住巷口，救出被困摊主。',
  )
 for layer in station['layers']:
  rid=resource('scene_'+layer['id'],runtime/'station'/layer['file'])
  presentation['layers'][layer['id']]={'resource':rid,'x':layer['pos'][0]-station['content_origin'][0],'y':layer['pos'][1]-station['content_origin'][1],'width':layer['draw_size'][0],'height':layer['draw_size'][1],'z':100+round(layer['z']) if layer.get('blocks_shots') else round(layer['z']*10),'blocker':bool(layer.get('blocks_shots',False))}
 body=resource('crow_body',runtime/'crow/body.png');core=resource('crow_stamp',runtime/'crow/core.png');cover=resource('lamp_ink',runtime/'ink_on_lamp/cover_00.png')
 rig=json.loads((runtime/'vendor/character.json').read_bytes());clips={}
 for name,path in rig['clips'].items():clips[name]=resource('vendor_clip_'+name,runtime/'vendor'/path,'metadata')
 presentation['puppets']['vendor']={'character':resource('vendor_rig',runtime/'vendor/character.json','metadata'),'atlas':resource('vendor_atlas',runtime/'vendor/atlas.png'),'clips':clips}
 for name,data in ensure_combat_cues().items():
  if name in ('reload','bell'):
   continue
  gain = {'shot':-3, 'windup':-4, 'attack':-3, 'hurt':-2, 'lamp':-8}.get(name,-10)
  resources['sound_'+name]=data['resource'];source['cues'][name]={'resource':'sound_'+name,'channel':'warning' if name in ['windup','attack'] else ('weapon' if name in ['shot','empty'] else 'impact'),'duration_ms':data['duration_ms'],'volume_db':gain}
 effect('shot_spark','shot_trace',160,'#ffcf73',34);effect('hit_spark','spark',230,'#ffe5a6',82)
 effect('weak_spark','spark',300,'#ff9379',95,'朱印命中');effect('purify_burst','burst',490,'#ffe5aa',130,'净化')
 effect('empty_feedback','spark',550,'#ffe5a6',0,'光弹已耗尽')
 effect('support_pulse','pulse',850,'#d8ba72',1800,'灯火震墨');effect('support_link','link',700,'#d4b674',100)
 effect('lunge_release','attack_release',max(360,crow_lunge_ms),'#ff655a',90)
 effect('ink_release','attack_release',240,'#ff9460',60)
 effect('player_hurt','player_hit',720,'#ff493e',100,'受到攻击 · 灯芯 -1')
 lamp_layer=next(layer for layer in station['layers'] if layer['id']=='lamp');lx=lamp_layer['pos'][0]-station['content_origin'][0];ly=lamp_layer['pos'][1]-station['content_origin'][1]
 entities['lamp']=entity('activation_source',lx+497,ly+253,200,120,z=80,activation_cooldown_ms=6000,label='灯火支援')
 entities['lamp']['parts']={'body':{'resource':'scene_lamp','source':[497,253,200,120],'x':0,'y':0,'width':1,'height':1}};entities['lamp']['part_order']=['body']
 entities['lamp_cover']=entity('decoration',lx+521,ly+269,151,94,z=81,active=True)
 entities['lamp_cover']['parts']={'body':{'resource':cover,'x':0,'y':0,'width':1,'height':1}};entities['lamp_cover']['part_order']=['body']
 opening = [{'op':'spawn','entity':'lamp'}]
 if station_candidate:
  opening.extend([{'op':'section','section':'arrival'},{'op':'input','enabled':False}])
 event('open',{'at_ms':0},opening)
 event('lamp.pulse',{'on':'interaction.activated:lamp'},[{'op':'vfx','effect':'support_pulse','entity':'lamp'},{'op':'remove','entity':'lamp_cover'}],limit=16)
 titles=['屋檐初袭','左右夹击','截住墨弹','护住摊主','近远交织','巷口合围']
 hints=['红圈蓄满就会出手，优先击破正在蓄力的墨鸦。','怪物会扑向你，蓄力时优先净化。','飞来的墨弹也能击破。','只打居民胸口的墨，点灯可争取时间。','灯火震退墨鸦，飞出的墨弹仍要拦截。','守住最后一波！优先打断近身威胁。']
 counts=[3,4,5,5,6,6]
 support_targets = []
 for wave,count in enumerate(counts):
  sid = f'wave_{wave+1}'
  spawns = {}
  encounter['waves'][sid] = {
   'title':titles[wave], 'index':wave+1,
   'at_ms':1000+wave*13000+(6000+(3000 if wave>=3 else 0) if station_candidate else 0),
   'spawns':spawns, 'hint':hints[wave],
  }
  for index in range(count):
   id=f'w{wave+1}_crow_{index+1}';ranged=wave>=1 and (index+wave)%3==0
   spawns[id] = 800+index*(2800 if wave==0 else 1650)
   support_targets.append(id)
   side=(index+wave)%2;lane=[230,1040,580,1230,400,860][(index+wave)%6]
   y=[170,230,105,295][(index+wave)%4];size=270 if wave<4 else 285
   heavy=wave>=3 and index%3==0
   e=entity('target',-size if not side else 1776,y,size,size,hits=2 if heavy else 1,weak_damage=2,hitstop_ms=80,z=75,label='吐墨鸦' if ranged else '扑击鸦')
   e['parts']={'body':{'resource':body,'x':62/1024,'y':154/1024,'width':917/1024,'height':753/1024},'stamp':{'resource':core,'source':[417,202,132,132],'x':533/1024,'y':400/1024,'width':132/1024,'height':132/1024,'kind':'weak'}}
   e['part_order']=['body','stamp']
   warning_at=2300+(index%2)*220
   release_at=warning_at+crow_windup_ms+(280 if ranged else 0)
   attack_at=release_at if ranged else release_at+crow_lunge_ms
   frames=[frame(0,e['x'],y,.72,-.16 if not side else .16),frame(850,lane,y,1,.03),frame('windup',lane,y+15,1,-.08)]
   if ranged:
    frames.extend([frame('release',lane,y-30,1.12,-.12,offset_ms=-170),frame('release',lane,y,1.17,.08)])
   else:
    impact_x = 760+(index%3-1)*140
    frames.extend([
     frame('release',lane+(-40 if side else 40),y-40,1.13,-.19),
     frame('contact',impact_x,650,2.55,.19 if not side else -.19),
     frame('contact',impact_x,685,2.66,.23 if not side else -.23,offset_ms=100),
    ])
   frames.append(frame('retire',-size-150 if side else 1900,y-80,.82,0))
   e['motion']={'frames':frames,'easing':'smoothstep'};e['bob']={'amplitude_x':6,'amplitude_y':8,'period_ms':1050+index*90,'phase_rad':index*.7}
   entities[id] = e
   attack = {
    'windup': {
     'at_ms':warning_at, 'color':'#ff7764',
     'label':'危险 · 吐墨蓄力' if ranged else '危险 · 即将扑击',
    },
    'release_ms':release_at,
    'retire_ms':attack_at+550,
    'damage':{'resource':'lives','amount':1,'effect':'player_hurt','topic':'player.damaged'},
    'release_effect':'ink_release' if ranged else 'lunge_release',
   }
   if ranged:
    projectile=id+'.ink';entities[projectile]=entity('projectile',0,0,84,84,z=83,label='可拦截墨弹')
    entities[projectile]['parts']={'body':{'resource':body,'x':0,'y':0,'width':1,'height':1}};entities[projectile]['part_order']=['body']
    attack['projectile'] = {
     'entity':projectile, 'x':900, 'y':800, 'flight_ms':1250,
     'color':'#ff9460', 'label':'拦截墨弹',
     'on_intercept':[{'op':'resource_add','resource':'score','amount':25},{'op':'cue','cue':'intercept'}],
    }
   else:
    attack['contact_ms'] = attack_at
   encounter['attacks'][id] = attack
   event(id+'.clear',{'on':'target.neutralized:'+id},[{'op':'resource_add','resource':'score','amount':150 if heavy else 100},{'op':'resource_add','resource':'purified','amount':1}])
 encounter['supports']['support'] = {
  'source':'lamp', 'targets':support_targets, 'range_px':1800,
  'region':[0,80,1776,820], 'duration_ms':1500, 'effect':'support_link', 'max_firings':16,
 }
 entities['resident']=entity('protected',560,350,350,480,z=72)
 entities['resident']['puppet']={'rig':'vendor','target':'resident_ink','target_part':'rescue_ink','idle':'struggle','success':'rescued_bounce','rest':'thank'}
 entities['resident_ink']=entity('target',700,560,65,65,virtual=True,z=73)
 resident_arrival = [{'op':'spawn','entity':'resident'},{'op':'spawn','entity':'resident_ink'}]
 rescue_reward = [{'op':'resource_add','resource':'score','amount':300},{'op':'resource_add','resource':'rescued','amount':1}]
 if station_candidate:
  resident_arrival.append({'op':'section','section':'rescue'})
  rescue_reward.append({'op':'vfx','effect':'rescue_light','entity':'resident_ink'})
 event('resident.arrives',{'at_ms':46000 if station_candidate else 40500},resident_arrival)
 event('resident.rescue',{'on':'target.neutralized:resident_ink'},rescue_reward)
 event('resident.protected',{'on':'target.protected_hit:resident'},[{'op':'resource_add','resource':'score','amount':-100}],limit=128)
 event('player.dying',{'on':'player.damaged'},[{'op':'input','enabled':False}],guards=[{'resource':'lives','compare':'lte','value':0}])
 event('player.failed',{'after':'player.dying','delay_ms':720},[{'op':'fail','result':'overrun'}])
 if station_candidate:
  story = [
   ('arrival','夜市告急','墨潮涌进夜市。守住巷口，给摊主留出逃生时间。'),
   ('lamp_lesson','试射巷灯','射击巷灯会让附近墨鸦停顿。墨鸦也可以直接射击。'),
   ('rescue','摊主被困','瞄准摊主胸口的墨团。纸身是保护区，误射会扣印记。'),
   ('safe_exit','巷口守住了','摊主已获救。灯火照亮了通往下一站的路。'),
   ('missed_rescue','巷口守住了','摊主仍被墨团困住。重试时，记得净化胸口的墨团。'),
  ]
  for index,(key,title,hint) in enumerate(story,7):
   source['sections'][key]={'index':index,'title':title,'hint':hint,'targets':[]}
  effect('lesson_ring','warning',1900,'#e4be73',105,'试射巷灯')
  effect('rescue_light','burst',800,'#ffe6a0',128,'摊主获救')
  event('lesson.lamp',{'at_ms':2300},[
   {'op':'section','section':'lamp_lesson'},{'op':'input','enabled':True},
   {'op':'vfx','effect':'lesson_ring','entity':'lamp'},
  ])
  for id,rescued in [('safe_exit',True),('missed_rescue',False)]:
   event('ending.'+id,{'at_ms':90000},[{'op':'section','section':id},{'op':'input','enabled':False}],
    guards=[{'resource':'lives','compare':'gt','value':0},
            {'resource':'rescued','compare':'gt' if rescued else 'lte','value':0}])
 event('level.clear',{'at_ms':93000 if station_candidate else 82000},[{'op':'complete','result':'clear'}],guards=[{'resource':'lives','compare':'gt','value':0}])
 if source_only:return source
 path=publish(source);loaded,manifest=read_package(path);compiled=compile_source(loaded,source_manifest=manifest);out=write_build(compiled,DEFAULT_CACHE)
 index_name = 'station' if station_candidate else 'assault'
 dump(ROOT/'gunforge/level_design/reviews'/f'{index_name}_build.json',{'source':str(path),'source_revision':path.parent.name,'build_id':compiled['build_id'],'compiled':str(out),'state':'candidate_not_adopted','feedback':'user-gameplay-2026-11-09','target_count':sum(counts),'wave_count':len(counts)})
 print(out);return out
if __name__=='__main__':build()
