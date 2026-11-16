"""Strict source compilation. No rendering, model invocation or mutable adopted output."""
import argparse,hashlib,json,os,tempfile,importlib.util,struct
from importlib.metadata import version
from pathlib import Path
from jsonschema import Draft202012Validator
try:
 from .schema_contract import schema
 from .scene_contract import validate_scene
 from .encounter import expand_encounter
except ImportError:
 from schema_contract import schema
 from scene_contract import validate_scene
 from encounter import expand_encounter
ROOT=Path(__file__).resolve().parents[3]
DEFAULT_CACHE=Path(os.environ.get('GUNFORGE_LEVEL_CACHE',ROOT.parent/'gunforge_cache/level_design')).resolve()
class CompileError(ValueError):pass
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def payload_digest(value):
 def normalize(item):
  if type(item) in [int,float]:return {'@number':struct.pack('<d',float(item)).hex()}
  if isinstance(item,dict):return {key:normalize(value) for key,value in item.items()}
  if isinstance(item,list):return [normalize(value) for value in item]
  return item
 return digest(normalize(value))
def read(path):
 def pairs(items):
  result={}
  for key,value in items:
   if key in result:raise CompileError('duplicate JSON key: '+key)
   result[key]=value
  return result
 try:return json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(CompileError('non-finite number: '+x)))
 except (OSError,json.JSONDecodeError) as e:raise CompileError(str(e)) from e
def read_package(entry):
 root=entry.parent.resolve();source=read(entry)
 if not isinstance(source,dict):raise CompileError('package entry must be an object')
 source=dict(source);includes=source.pop('includes',[])
 if not isinstance(includes,list) or any(not isinstance(x,str) for x in includes):raise CompileError('includes must be relative paths')
 manifest={entry.name:hashlib.sha256(entry.read_bytes()).hexdigest()}
 for name in includes:
  path=(root/name).resolve()
  if not path.is_relative_to(root) or not path.is_file():raise CompileError('invalid fragment path: '+name)
  relative=path.relative_to(root).as_posix()
  if relative in manifest:raise CompileError('duplicate fragment: '+name)
  fragment=read(path)
  if not isinstance(fragment,dict):raise CompileError('fragment must be an object')
  for section,values in fragment.items():
   if section not in ['entities','events','queries','resources','cues'] or not isinstance(values,dict):raise CompileError('invalid fragment section: '+section)
   target=source.setdefault(section,{})
   if not isinstance(target,dict) or set(target)&set(values):raise CompileError('duplicate IDs in fragment: '+name)
   target.update(values)
  manifest[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
 return source,dict(sorted(manifest.items()))
def validate(source, resource_root=ROOT, schema_only=False):
 errors=sorted(Draft202012Validator(schema).iter_errors(source),key=lambda e:str(list(e.path)))
 if errors:raise CompileError('; '.join('/'+'/'.join(map(str,e.path))+': '+e.message for e in errors[:8]))
 # JSON's 1e999 also needs rejection after parsing, including nested property values.
 try:canonical(source)
 except (ValueError,TypeError) as e:raise CompileError('non-finite or unsupported JSON value') from e
 entities=source['entities'];events=source['events'];resources=source['resources'];queries=source['queries']
 catalog=read(ROOT/'gunforge/level_design/specs/capabilities-v1.json')
 if source['ruleset'] not in catalog['rulesets']:raise CompileError('unregistered ruleset: '+source['ruleset'])
 profile=catalog['rulesets'][source['ruleset']]
 if profile.get('supported_sections') and set(source)-set(profile['supported_sections']):raise CompileError('source section not supported by selected rule profile')
 if 'encounter' in source and not profile.get('encounter_authoring'):
  raise CompileError('select a ruleset supporting encounter authoring')
 if schema_only:
  return
 if any(source.get('presentation',{}).get(name) for name in ['layers','puppets']) and not profile.get('layered_2d'):raise CompileError('select a layered 2D presentation profile')
 if 'layout_constraint' in profile and source['layout']!=profile['layout_constraint']:raise CompileError('ruleset renderer requires its declared canvas layout')
 if 'parameters_schema' not in profile and source.get('ruleset_data'):raise CompileError('ruleset has no registered parameter contract')
 if 'parameters_schema' in profile:
  parameter_schema=read(ROOT/profile['parameters_schema'])
  parameter_errors=list(Draft202012Validator(parameter_schema).iter_errors(source.get('ruleset_data',{})))
  if parameter_errors:raise CompileError('ruleset parameters: '+parameter_errors[0].message)
 for id,entry in resources.items():
  path=(resource_root/entry['path']).resolve()
  if not path.is_relative_to(resource_root.resolve()):raise CompileError('resource escapes root: '+id)
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise CompileError('missing or changed resource: '+id)
 for id,entity in entities.items():
  if entity['template'] not in catalog['templates']:raise CompileError('unregistered template: '+entity['template'])
  if 'resource' in entity and (entity['resource'] not in resources or resources[entity['resource']]['kind']!='image'):raise CompileError('entity needs registered image resource: '+id)
  for key,value in entity.get('properties',{}).items():
   expected=catalog['entity_properties'].get(key)
   if expected is None:raise CompileError('unregistered entity property: '+id+'/'+key)
   valid=(value in expected if isinstance(expected,list) else type(value) is str if expected=='string' else type(value) is bool if expected=='boolean' else type(value) in [int,float] if expected=='number' else type(value) is int and (value>=1 if expected=='positive_integer' else True))
   if not valid:raise CompileError('entity property type mismatch: '+id+'/'+key)
 controls=source.get('controls',{})
 for field in source.get('hud',[]):
  if field['resource'] not in source['initial_resources']:raise CompileError('HUD references undeclared resource')
 if 'ammo_resource' in controls:
  ammo = source['initial_resources'].get(controls['ammo_resource'])
  if ammo is None or ammo < 0:
   raise CompileError('ammo policy needs a declared nonnegative counter')
 if ('magazine' in controls and 'ammo_resource' not in controls) or (('reload_ms' in controls or controls.get('auto_reload')) and 'magazine' not in controls):
  raise CompileError('reload policy needs an ammo counter and magazine')
 for id,cue in source['cues'].items():
  if cue['resource'] not in resources or resources[cue['resource']]['kind']!='audio':raise CompileError('cue needs registered audio resource: '+id)
 for id,query in queries.items():
  if 'supported_query_ops' in profile and query['op'] not in profile['supported_query_ops']:raise CompileError('query not implemented by selected ruleset: '+id)
  if query['op']=='registered_value':
   if query['name'] not in profile.get('query_exports',[]) or query['algorithm'] not in profile.get('query_algorithms',[]):raise CompileError('unregistered rule query: '+id)
   continue
  if query['entity'] not in entities:raise CompileError('unknown query entity: '+id)
  if query['op']=='entity_age_ms':continue
  if 'other' in query and query['other'] not in entities:raise CompileError('unknown spatial source: '+id)
  if query['op']=='distance' and query.get('other') not in entities:raise CompileError('distance needs second entity: '+id)
  if query['op']=='region_contains' and ('region' not in query or query['region'][2]<=0 or query['region'][3]<=0):raise CompileError('invalid region: '+id)
  if query['op']=='mask_sample' and (query.get('resource') not in resources or resources[query['resource']]['kind']!='image'):raise CompileError('mask query needs registered image: '+id)
  if query['algorithm']!='cpu-nearest-v1':raise CompileError('unregistered spatial algorithm: '+id)
 for id,event in events.items():
  if not event['actions'] or set(event['order'])!=set(event['actions']):raise CompileError('action order must name every action exactly once: '+id)
  trigger=event['trigger']
  if 'after' in trigger and trigger['after'] not in events:raise CompileError('unknown event dependency: '+id)
  if 'query' in trigger and trigger['query'] not in queries:raise CompileError('unknown query dependency: '+id)
  for guard in event.get('guards',[]):
   if 'entity' in guard and guard['entity'] not in entities:raise CompileError('unknown guard entity: '+id)
   if 'resource' in guard and guard['resource'] not in source['initial_resources']:raise CompileError('unknown guard resource: '+id)
   if 'query' in guard and guard['query'] not in queries:raise CompileError('unknown guard query: '+id)
   if guard.get('field') in ['active','visible','stunned'] and (type(guard['value']) is not bool or guard['compare']!='eq'):raise CompileError('boolean guard needs eq and boolean: '+id)
  equalities={}
  for guard in event.get('guards',[]):
   key=tuple((k,str(v)) for k,v in sorted(guard.items()) if k not in ['compare','value'])
   if guard['compare']=='eq':
    if key in equalities and equalities[key]!=guard['value']:raise CompileError('statically contradictory guards: '+id)
    equalities[key]=guard['value']
  for action in event['actions'].values():
   if 'supported_ops' in profile and action['op'] not in profile['supported_ops']:raise CompileError('effect not implemented by selected ruleset: '+id)
   if action['op']=='registered':
    definition=profile.get('effects',{}).get(action['effect'])
    if definition is None or list(Draft202012Validator(definition).iter_errors(action['params'])):raise CompileError('unregistered effect or invalid parameters: '+id)
   if 'entity' in action and action['entity'] not in entities:raise CompileError('unknown action entity: '+id)
   if action['op'] in ('launch','vfx') and 'source' in action and action['source'] not in entities:
    raise CompileError('unknown action source: '+id)
   if action['op']=='vfx' and action['effect'] not in source.get('effects',{}):raise CompileError('unknown visual effect: '+id)
   if action['op']=='section' and action['section'] not in source.get('sections',{}):raise CompileError('unknown section: '+id)
   if action['op']=='cue' and action['cue'] not in source['cues']:raise CompileError('unknown cue: '+id)
   if action['op']=='resource_add' and action['resource'] not in source['initial_resources']:raise CompileError('unknown resource counter: '+id)
   if action['op']=='permission' and entities[action['entity']]['template']=='protected' and action['kind'] in ['primary','weak']:raise CompileError('protected target cannot become damageable: '+id)
   if action['op']=='set' and action['field'] not in ['x','y','visible','active','vx','vy','health','value']:raise CompileError('invalid or unimplemented public property: '+id)
   if action['op']=='set':
    field=action['field'];value=action['value']
    allowed=(type(value) in [int,float]) if field in ['x','y','vx','vy','health','value'] else type(value) is bool
    if not allowed:raise CompileError('public property type mismatch: '+id)
 validate_scene(source,resource_root,CompileError)
 visiting=set();done={}
 def absolute(id):
  if id in visiting:raise CompileError('event dependency cycle: '+id)
  if id in done:return done[id]
  visiting.add(id);t=events[id]['trigger'];value=None
  if 'at_ms' in t:value=t['at_ms']
  elif 'after' in t:
   parent=absolute(t['after']);value=None if parent is None else parent+t['delay_ms']
  visiting.remove(id);done[id]=value;return value
 for id in sorted(events,key=lambda key:(-events[key].get('priority',0),key)):absolute(id)
 return done
def compile_source(source, resource_root=ROOT, source_manifest=None):
 validate(source,resource_root,schema_only='encounter' in source)
 profile=read(ROOT/'gunforge/level_design/specs/capabilities-v1.json')['rulesets'][source['ruleset']]
 expanded=json.loads(canonical(source));origin={}
 if 'encounter' in expanded:
  origin.update(expand_encounter(expanded,CompileError))
 if 'compiler_plugin' in profile:
  path=(ROOT/profile['compiler_plugin']).resolve()
  if not path.is_relative_to(ROOT/'gunforge/level_design/rulesets'):raise CompileError('compiler plugin outside trusted rulesets')
  spec=importlib.util.spec_from_file_location('trusted_level_expander',path);plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)
  try:expanded,origin=plugin.expand(expanded)
  except (ValueError,KeyError,TypeError) as error:raise CompileError('rule compiler: '+str(error)) from error
 times=validate(expanded,resource_root);hz=expanded['tick_hz'];compiled=json.loads(canonical(expanded));mapping={}
 for id,event in compiled['events'].items():
  at=times[id]
  if at is not None:
   tick=(at*hz+999)//1000
   if tick>source['duration_ms']*hz//1000:raise CompileError('event outside allowed duration: '+id)
   event['at_tick']=tick
   mapping[id]={'pointer':origin.get(id,'/events/'+id+'/trigger'),'declared_absolute_ms':at,'tick':tick,'quantization_error_ms_numerator':tick*1000-at*hz,'denominator':hz}
  else:mapping[id]={'pointer':origin.get(id,'/events/'+id+'/trigger'),'dynamic':True}
 compiled['event_order']=list(times)
 windows={}
 for eid in sorted(compiled['event_order'],key=lambda eid:(times[eid] if times[eid] is not None else float('inf'),eid)):
  event=compiled['events'][eid]
  if 'at_tick' not in event or event.get('guards'):continue
  for aid in event['order']:
   action=event['actions'][aid]
   if action['op']=='spawn':windows[action['entity']]=(times[eid],event['at_tick'])
   if action['op']=='remove' and action['entity'] in windows:
    start,quantized=windows[action['entity']]
    if times[eid]>start and event['at_tick']==quantized:raise CompileError('quantized zero-tick active window: '+action['entity'])
 compiled['deadline_tick']=source['duration_ms']*hz//1000
 compiled['review_end_tick']=plugin.review_end_tick(source) if 'compiler_plugin' in profile and hasattr(plugin,'review_end_tick') else compiled['deadline_tick']
 if compiled['deadline_tick']==0:raise CompileError('zero-tick duration')
 source_manifest=source_manifest or {"level.json":hashlib.sha256(canonical(source)).hexdigest()}
 source_revision=digest(source_manifest)
 tool_lock={'compiler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'schema_sha256':digest(schema),'capability_catalog_sha256':hashlib.sha256((ROOT/'gunforge/level_design/specs/capabilities-v1.json').read_bytes()).hexdigest(),'runtime_sha256':hashlib.sha256((ROOT/'gunforge/framework/core/level_runtime.gd').read_bytes()).hexdigest(),'validator':version('jsonschema'),'godot':'4.6.3','spatial':'cpu-nearest-v1'}
 profile=read(ROOT/'gunforge/level_design/specs/capabilities-v1.json')['rulesets'][source['ruleset']]
 profile_files=profile.get('module_files',[])+([profile['parameters_schema']] if 'parameters_schema' in profile else [])
 tool_lock['profile_files']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in profile_files}
 tool_lock['contract_files']={'scene_contract.py':hashlib.sha256(Path(__file__).with_name('scene_contract.py').read_bytes()).hexdigest()}
 if 'encounter' in source:
  tool_lock['contract_files']['encounter.py']=hashlib.sha256(Path(__file__).with_name('encounter.py').read_bytes()).hexdigest()
 core_files=(ROOT/'gunforge/framework/core').iterdir()
 tool_lock['core_files']={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(core_files) if path.is_file() and path.suffix in ('.gd','.gdshader')}
 payload_hash=payload_digest({'level':compiled,'source_map':mapping,'source_manifest':source_manifest})
 build_id=digest({'source_revision':source_revision,'tool_lock':tool_lock,'payload_sha256':payload_hash})
 return {'format':'gunforge-compiled-level-v1','source_revision':source_revision,'build_id':build_id,'payload_sha256':payload_hash,'payload_algorithm':'numeric-f64le-v1','tool_lock':tool_lock,'source_manifest':source_manifest,'source_map':mapping,'level':compiled,'capability_status':'compiler contract only; runtime acceptance tracked separately'}
def write_build(build,cache):
 dest=cache/'builds'/build['build_id'];dest.mkdir(parents=True,exist_ok=True);target=dest/'level.json';data=canonical(build)+b'\n'
 if target.exists():
  if target.read_bytes()!=data:raise CompileError('immutable build collision')
  return target
 fd,tmp=tempfile.mkstemp(dir=dest,prefix='.level-',suffix='.tmp')
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  # Exclusive link fails instead of overwriting another writer's immutable build.
  try:os.link(tmp,target)
  except FileExistsError:
   if target.read_bytes()!=data:raise CompileError('concurrent build collision')
 finally:Path(tmp).unlink(missing_ok=True)
 return target
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);ap.add_argument('--cache',type=Path,default=Path(os.environ.get('GUNFORGE_LEVEL_CACHE',ROOT.parent/'gunforge_cache/level_design')));a=ap.parse_args()
 try:
  source,manifest=read_package(a.source)
  print(write_build(compile_source(source,source_manifest=manifest),a.cache))
 except CompileError as e:raise SystemExit(str(e))
