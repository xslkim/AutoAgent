"""Minimal JSON Schema contract shared by authoring, compilation and runtime."""
import json
from pathlib import Path

def obj(properties, required=()):
 return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
def ids(item):return {'type':'object','propertyNames':{'pattern':r'^[A-Za-z][A-Za-z0-9_.-]*$'},'additionalProperties':item}
string={'type':'string','minLength':1};number={'type':'number'};integer={'type':'integer'};ms={'type':'integer','minimum':0}
actions=[]
for op,fields in {
 'spawn':{'entity':string},'remove':{'entity':string},
 'set':{'entity':string,'field':string,'value':{}},
 'resource_add':{'resource':string,'amount':integer},
 'emit':{'event':string},'cue':{'cue':string},
 'registered':{'effect':string,'params':{'type':'object'}},
 'stun':{'entity':string,'duration_ms':{'type':'integer','minimum':1}},
 'launch':{'entity':string,'source':string,'x':number,'y':number,'duration_ms':{'type':'integer','minimum':1}},
 'vfx':{'effect':string,'entity':string},'section':{'section':string},'input':{'enabled':{'type':'boolean'}},
 'complete':{'result':string},'fail':{'result':string},
 'permission':{'entity':string,'kind':{'enum':['primary','weak','protected','invalid','blocker','decoration']}}
}.items():actions.append(obj({'op':{'const':op},**fields},['op',*fields]))
next(action for action in actions if action['properties']['op']['const']=='vfx')['properties']['source'] = string
next(action for action in actions if action['properties']['op']['const']=='cue')['properties']['replace_existing'] = {'type':'boolean'}
trigger={'oneOf':[obj({'at_ms':ms},['at_ms']),obj({'after':string,'delay_ms':ms},['after','delay_ms']),obj({'on':string},['on']),obj({'query':string,'compare':{'enum':['gte','gt','eq','lte','lt']},'value':number},['query','compare','value'])]}
entity=obj({'template':string,'x':number,'y':number,'width':{'type':'number','exclusiveMinimum':0},'height':{'type':'number','exclusiveMinimum':0},'properties':{'type':'object'},'resource':string},['template','x','y','width','height'])
condition={'oneOf':[obj({'entity':string,'field':{'enum':['active','visible','value','health','stunned']},'compare':{'enum':['gte','gt','eq','lte','lt']},'value':{'type':['number','boolean']}},['entity','field','compare','value']),obj({'resource':string,'compare':{'enum':['gte','gt','eq','lte','lt']},'value':number},['resource','compare','value']),obj({'query':string,'compare':{'enum':['gte','gt','eq','lte','lt']},'value':number},['query','compare','value'])]}
event=obj({'trigger':trigger,'guards':{'type':'array','items':condition},'actions':ids({'oneOf':actions}),'order':{'type':'array','items':string,'uniqueItems':True},'priority':integer,'max_firings':{'type':'integer','minimum':1}},['trigger','actions','order','max_firings'])
query={'oneOf':[obj({'op':{'enum':['region_contains','mask_sample','distance']},'entity':string,'other':string,'region':{'type':'array','items':number,'minItems':4,'maxItems':4},'resource':string,'space':{'const':'content_px'},'algorithm':string,'threshold_source':string,'sample':{'enum':['center','origin']}},['op','entity','space','algorithm']),obj({'op':{'const':'registered_value'},'name':string,'subject':string,'space':{'const':'scalar'},'algorithm':string,'threshold_source':string},['op','name','space','algorithm'])]}
schema=obj({'schema_version':{'const':1},'id':string,'ruleset':string,'seed':{'type':'integer','minimum':0},'tick_hz':{'enum':[60]},'duration_ms':{'type':'integer','minimum':1},'layout':obj({'width':{'type':'integer','minimum':1},'height':{'type':'integer','minimum':1}},['width','height']),'entities':ids(entity),'events':ids(event),'queries':ids(query),'resources':ids(obj({'path':string,'sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},'kind':{'enum':['image','audio','metadata']}},['path','sha256','kind'])),'cues':ids(obj({'resource':string,'channel':{'enum':['music','ambient','warning','weapon','impact','voice','ui']},'duration_ms':{'type':'integer','minimum':1},'loop':{'type':'boolean'},'volume_db':number},['resource','channel','duration_ms'])),'initial_resources':ids(integer),'hud':{'type':'array','items':obj({'label':string,'resource':string},['label','resource'])},'ruleset_data':{'type':'object'},'controls':obj({'ammo_resource':string,'magazine':{'type':'integer','minimum':1},'reload_ms':ms,'auto_reload':{'type':'boolean'},'shot_interval_ms':ms,'assist_px':{'type':'integer','minimum':0,'maximum':30}})},['schema_version','id','ruleset','seed','tick_hz','duration_ms','layout','entities','events','queries','resources','cues','initial_resources'])
schema.update({'$schema':'https://json-schema.org/draft/2020-12/schema','title':'GunForge minimal 2D level source v1'})
positive_ms={'type':'integer','minimum':1}
scale = {'type':'number','exclusiveMinimum':0}
frame_pose = {'x':number,'y':number,'scale':scale,'scale_x':scale,'scale_y':scale,'rotation_rad':number,
              'opacity':{'type':'number','minimum':0,'maximum':1}}
frame = {'oneOf': [
 obj({'at_ms':ms, **frame_pose},['at_ms','x','y']),
 obj({'attack_time':{'enum':['windup','release','contact','retire']},'offset_ms':integer, **frame_pose},
     ['attack_time','x','y']),
]}
flap=obj({'pivot':{'type':'array','items':number,'minItems':2,'maxItems':2},'amplitude_rad':number,'hz':{'type':'number','exclusiveMinimum':0},'phase_rad':number},['pivot','amplitude_rad','hz'])
part=obj({'resource':string,'source':{'type':'array','items':number,'minItems':4,'maxItems':4},'x':number,'y':number,'width':{'type':'number','exclusiveMinimum':0},'height':{'type':'number','exclusiveMinimum':0},'kind':{'enum':['primary','weak']},'tint':string,'flap':flap},['resource','x','y','width','height'])
entity['properties'].update({'parts':ids(part),'part_order':{'type':'array','items':string,'uniqueItems':True},'motion':obj({'frames':{'type':'array','items':frame,'minItems':2},'easing':{'enum':['linear','smoothstep']}},['frames']),'bob':obj({'amplitude_x':number,'amplitude_y':number,'period_ms':positive_ms,'phase_rad':number},['amplitude_x','amplitude_y','period_ms']),'phases':{'type':'array','items':obj({'id':string,'start_ms':ms,'end_ms':positive_ms,'color':string,'label':string},['id','start_ms','end_ms'])},'puppet':obj({'rig':string,'target':string,'target_part':string,'idle':string,'success':string,'rest':string},['rig','target','target_part','idle','success','rest'])})
query['oneOf'].append(obj({'op':{'const':'entity_age_ms'},'entity':string,'space':{'const':'scalar'},'algorithm':{'const':'entity-clock60-v1'}},['op','entity','space','algorithm']))
effect=obj({'kind':{'enum':['spark','burst','pulse','warning','player_hit','link','shot_trace','attack_release']},'duration_ms':positive_ms,'color':string,'radius':{'type':'number','minimum':0},'label':string},['kind','duration_ms','color'])
layer=obj({'resource':string,'x':number,'y':number,'width':{'type':'number','exclusiveMinimum':0},'height':{'type':'number','exclusiveMinimum':0},'z':integer,'blocker':{'type':'boolean'},'source':{'type':'array','items':number,'minItems':4,'maxItems':4},'tint':string},['resource','x','y','width','height','z'])
layer['properties']['section']=string
parallax={'type':'number','minimum':0,'maximum':1}
layer['properties']['parallax']=parallax
entity['properties']['parallax']=parallax
entity['properties']['mask_permission']=obj({
 'source':string,'resource':string,'threshold':{'type':'number','exclusiveMinimum':0,'maximum':1},
},['source','resource','threshold'])
entity['properties']['hit_resource']=string
part['properties']['hit_resource']=string
part['properties']['hardened_visual']=obj(
 {'resource':string,'x':number,'y':number,'width':scale,'height':scale},['resource','x','y','width','height'])
effect['properties']['kind']['enum'].append('beam_sweep')
effect['properties']['anchor_uv'] = {
 'type':'array','items':{'type':'number','minimum':0,'maximum':1},'minItems':2,'maxItems':2,
}
wave = obj({
 'index':positive_ms,'title':string,'at_ms':ms,'hint':string,'spawns':ids(ms),
},['index','title','at_ms','spawns'])
windup = obj({'at_ms':ms,'color':string,'label':string},['at_ms','color','label'])
damage = obj({'resource':string,'amount':positive_ms,'effect':string,'topic':string},['resource','amount','topic'])
projectile = obj({
 'entity':string,'x':number,'y':number,'flight_ms':positive_ms,
 'color':string,'label':string,'on_intercept':{'type':'array','items':{'oneOf':actions},'minItems':1},
},['entity','x','y','flight_ms'])
attack = obj({
 'windup':windup,'release_ms':positive_ms,'contact_ms':positive_ms,'retire_ms':positive_ms,
 'damage':damage,'release_effect':string,'projectile':projectile,
},['windup','release_ms','retire_ms','damage'])
support = obj({
 'source':string,
 'targets':{'type':'array','items':string,'uniqueItems':True,'minItems':1},
 'duration_ms':positive_ms,'range_px':{'type':'number','exclusiveMinimum':0},
 'region':{'type':'array','items':number,'minItems':4,'maxItems':4},
 'effect':string,'max_firings':positive_ms,
},['source','targets','duration_ms','range_px','max_firings'])
schema['properties']['encounter'] = obj({
 'waves':ids(wave),'attacks':ids(attack),'supports':ids(support),
},['waves'])
schema['properties'].update({'effects':ids(effect),'sections':ids(obj({'title':string,'index':{'type':'integer','minimum':1},'targets':{'type':'array','items':string,'uniqueItems':True},'hint':string},['title','index','targets'])),'resource_bounds':ids(obj({'min':integer,'max':integer})),'presentation':obj({'title':string,'subtitle':string,'instructions':string,'default_sound':{'type':'boolean'},'debug_shell':{'type':'boolean'},'layers':ids(layer),'sound_bindings':{'type':'object','additionalProperties':string},'feedback':obj({'shot':string,'hit':string,'weak':string,'neutralized':string,'empty':string}),'puppets':ids(obj({'character':string,'atlas':string,'clips':ids(string)},['character','atlas','clips'])),'labels':{'type':'object','additionalProperties':string},'support':obj({'entity':string,'label':string},['entity','label'])})})
rgb = {'type':'string','pattern':'^#[a-fA-F0-9]{6}$'}
schema['properties']['sections']['additionalProperties']['properties']['station']={'type':'integer','minimum':1}
schema['properties']['sections']['additionalProperties']['properties']['skippable']={'type':'boolean'}
hud_images = ('life_wick', 'life_wick_empty', 'ammo_light', 'ammo_light_empty', 'score_seal', 'prompt_bar',
              'crosshair', 'continue_panel')
schema['properties']['presentation']['properties'].update({
 'hud_art':obj({'layout':string,'style':string,'images':obj(dict.fromkeys(hud_images,string),hud_images)},
               ['layout','style','images']),
 'stations':{'type':'array','items':string,'minItems':1},
 'camera':obj({'amplitude_x':{'type':'number','minimum':0,'maximum':68},
               'amplitude_y':{'type':'number','minimum':0,'maximum':34}},['amplitude_x','amplitude_y']),
 'additive_z':integer,
 'bottom_wipes':ids(string),
 'dragon':obj({'layout':string,'images':{'type':'object','additionalProperties':string},
               'anchor':string,'mouth':string,'warning_effect':string},['layout','images','anchor','mouth']),
 'entity_tints':ids({'type':'object','additionalProperties':rgb}),
 'entity_state_labels':ids({'type':'object','additionalProperties':string}),
 'activation_glows':ids(obj({'color':rgb,'radius':{'type':'number','exclusiveMinimum':0},'label':string},
                            ['color','radius','label'])),
})
schema['properties']['presentation']['properties']['hud_art']['properties']['lettering']=obj(
 {'title':string,'first_chapter':string,'chapters':ids(string)}, ['title','first_chapter','chapters'])
if __name__=='__main__':
 path=Path(__file__).resolve().parents[2]/'level_design/specs/level-v1.schema.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
