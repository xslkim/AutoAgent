"""Compile the reviewed native station through an explicit migration profile."""
import hashlib,json
from compiler import ROOT,DEFAULT_CACHE,digest,read_package,compile_source,write_build
from freeze_baseline import dump
from versions import publish
from cues import ensure_cues

def main():
 game=ROOT/'gunforge/games/g01'
 tones=ensure_cues()
 for source,dest in [('alley_rules.gd','game_rules.gd'),('alley_scene.gd','game_scene.gd'),('alley_pose.gd','game_pose.gd')]:
  if (game/'scripts'/source).read_bytes()!=(ROOT/'gunforge/framework/runtime'/dest).read_bytes():raise ValueError('Run build_0b.py first: stale native module '+dest)
 native=json.loads((game/'levels/alley_0b.json').read_bytes())
 native.pop('schema_version');seed=native.pop('seed')
 waves=native.pop('waves');native['waves']={};native['wave_order']=[]
 for i,wave in enumerate(waves):
  wid=f'wave_{i}';native['wave_order'].append(wid)
  enemies=wave.pop('enemies');wave['enemy_order']=[f'crow_{j}' for j in range(len(enemies))]
  wave['enemies']=dict(zip(wave['enemy_order'],enemies));native['waves'][wid]=wave
 presentation=json.loads((game/'bible/runtime_presentation.json').read_bytes())
 resources={}
 # Native renderer uses this frozen generated pack. Every byte read by it is locked.
 for path in sorted((ROOT/'gunforge/framework/runtime').rglob('*')):
  if path.is_file() and path.suffix in ['.png','.json','.wav','.gd']:
   name='asset_'+hashlib.sha256(path.relative_to(ROOT).as_posix().encode()).hexdigest()[:16]
   resources[name]={'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':'metadata'}
 for path in sorted((game/'bible').glob('*.json')):
  resources['bible_'+path.stem.replace('-','_')]={'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':'metadata'}
 resources.update({'tone_'+key:value for key,value in tones.items()})
 source={'schema_version':1,'id':'paper.alley','ruleset':'g01.paper_lantern@1','seed':seed,'tick_hz':60,'duration_ms':78000,'layout':{'width':1776,'height':936},'entities':{},'events':{},'queries':{},'resources':resources,'cues':{},'initial_resources':{'lives':native['rules']['lives'],'ammo':native['rules']['magazine'],'score':0},'ruleset_data':{'native_level':native,'presentation':presentation}}
 source['cues']={key:{'resource':'tone_'+key,'channel':'warning' if key=='warning' else 'impact','duration_ms':100 if key=='shot' else 220} for key in tones}
 source['controls']={'ammo_resource':'ammo','magazine':native['rules']['magazine'],'reload_ms':round(native['rules']['reload_seconds']*1000),'shot_interval_ms':round(native['rules']['shot_interval']*1000),'assist_px':15}
 source['hud']=[{'label':'光弹','resource':'ammo'},{'label':'灯芯','resource':'lives'},{'label':'得分','resource':'score'}]
 path=publish(source);revision=path.parent.name
 source,manifest=read_package(path);build=compile_source(source,source_manifest=manifest)
 compiled=write_build(build,DEFAULT_CACHE)
 dump(ROOT/'gunforge/level_design/reviews/paper_build.json',{'source':str(path),'source_revision':revision,'build_id':build['build_id'],'compiled':str(compiled),'state':'candidate_not_adopted','migration':'shared scheduler and typed rules plugin; native presentation facade retained'})
 print(compiled)
if __name__=='__main__':main()
