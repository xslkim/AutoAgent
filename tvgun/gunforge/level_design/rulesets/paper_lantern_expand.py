"""Trusted rule compiler: native compatibility timings become shared scheduler events.

Thresholds keep the frozen floating-second clock. Authored content still has one
authority: ruleset_data; generated events point back to those exact fields.
"""
def expand(source):
 native=source['ruleset_data']['native_level'];origin={};events=source['events'];queries=source['queries']
 if set(native['wave_order'])!=set(native['waves']):raise ValueError('wave order does not match IDs')
 for wave in native['waves'].values():
  if set(wave['enemy_order'])!=set(wave['enemies']):raise ValueError('enemy order does not match IDs')
  if any(enemy['deadline']<=enemy['at'] for enemy in wave['enemies'].values()):raise ValueError('enemy deadline precedes spawn')
 if source['entities']:raise ValueError('native anatomical entities are defined by its locked asset binding; use presentation parameters')
 if source['initial_resources']!={'lives':native['rules']['lives'],'ammo':native['rules']['magazine'],'score':0}:raise ValueError('native initial resources must agree with the authoritative rule parameters')
 expected_controls={'ammo_resource':'ammo','magazine':native['rules']['magazine'],'reload_ms':round(native['rules']['reload_seconds']*1000),'shot_interval_ms':round(native['rules']['shot_interval']*1000),'assist_px':15}
 if source.get('controls')!=expected_controls:raise ValueError('native controls are derived from ruleset_data/native_level/rules')
 if not native['wave_order']:raise ValueError('a native station needs at least one wave')
 if len(native['wave_order'])>min(len(source['ruleset_data']['presentation']['lamp']['cover_order']),len(source['ruleset_data']['presentation']['pickup']['types'])):raise ValueError('missing wave presentation binding')
 if source['duration_ms']!=round(native['duration']*1000):raise ValueError('native target duration disagrees with source duration_ms')
 known=set().union(*(set(w['enemies']) for w in native['waves'].values()))
 def query(name,subject=None):
  key='rule.'+name+('.'+subject if subject else '')
  value={'op':'registered_value','name':name,'space':'scalar','algorithm':'legacy-float60-v1'}
  if subject:value['subject']=subject
  queries.setdefault(key,value);return key
 def guard(name,value=1,subject=None):return {'query':query(name,subject),'compare':'eq','value':value}
 def event(id,q,threshold,effect,params,guards,pointer,priority):
  if id in events:raise ValueError('authored event collides with generated ID: '+id)
  events[id]={'trigger':{'query':q,'compare':'gte','value':threshold},'guards':guards,'actions':{'apply':{'op':'registered','effect':effect,'params':params}},'order':['apply'],'priority':priority,'max_firings':1}
  origin[id]=pointer
 event('rule.reload',query('reload_due'),1,'reload_done',{},[guard('playing')],'/ruleset_data/native_level/rules/reload_seconds',10000)
 for index,wid in enumerate(native['wave_order']):
  wave=native['waves'][wid];base='/ruleset_data/native_level/waves/'+wid
  if wave['duration']>600:raise ValueError('native station wave exceeds supported 600 second range')
  for field in ['resident_at','pickup_at']:
   if wave[field]>=wave['duration']:raise ValueError('native interaction begins after wave end')
  for j,eid in enumerate(wave['enemy_order']):
   enemy=wave['enemies'][eid];guards=[guard('playing'),guard('wave',index)]
   if enemy['deadline']>wave['duration']:raise ValueError('threat deadline after wave end')
   prefix='rule.'+wid+'.'+eid
   event(prefix+'.spawn',query('local_clock'),enemy['at'],'enemy_spawn',{'enemy':eid},guards+[guard('enemy_waiting',subject=eid)],base+'/enemies/'+eid+'/at',9000-j*10)
   event(prefix+'.warning',query('local_clock'),enemy['deadline']-native['rules']['warning_seconds'],'enemy_warning',{'enemy':eid},guards+[guard('enemy_alive',subject=eid),guard('enemy_unwarned',subject=eid)],base+'/enemies/'+eid+'/deadline',8999-j*10)
   event(prefix+'.expire',query('local_clock'),enemy['deadline'],'enemy_expire',{'enemy':eid},guards+[guard('enemy_alive',subject=eid)],base+'/enemies/'+eid+'/deadline',8998-j*10)
  event('rule.'+wid+'.end',query('local_clock'),wave['duration'],'wave_end',{},[guard('playing'),guard('wave',index)],base+'/duration',100)
 event('rule.next_wave',query('state_clock'),native['rules']['wave_gap'],'next_wave',{},[guard('gap')],'/ruleset_data/native_level/rules/wave_gap',50)
 event('rule.complete',query('state_clock'),3,'level_complete',{},[guard('transition')],'/ruleset_data/native_level/duration',40)
 event('rule.continue_timeout',query('state_clock'),native['rules']['continue_seconds'],'return_title',{},[guard('continue')],'/ruleset_data/native_level/rules/continue_seconds',30)
 for item in queries.values():
  if item.get('subject') and item['subject'] not in known:raise ValueError('unknown registered query subject')
 for item in events.values():
  for action in item['actions'].values():
   if action['op']=='registered' and action['params'].get('enemy') not in known and 'enemy' in action['params']:raise ValueError('unknown registered effect subject')
 return source,origin

def review_end_tick(source):
 native=source['ruleset_data']['native_level']
 def ticks(seconds):
  if not 0<=seconds<=3600:raise ValueError('unsupported legacy time threshold')
  elapsed=0.0;count=0
  while elapsed<seconds:elapsed+=1/60;count+=1
  return max(1,count)
 return sum(ticks(w['duration']) for w in native['waves'].values())+(len(native['wave_order'])-1)*ticks(native['rules']['wave_gap'])+ticks(3)
