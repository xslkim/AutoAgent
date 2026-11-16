"""Build the first real neutral package; procedural geometry, no game-specific assets."""
import json,hashlib
from pathlib import Path
from compiler import ROOT,DEFAULT_CACHE,canonical,digest,read_package,compile_source,write_build
from freeze_baseline import dump
from versions import publish
from cues import ensure_cues
source={'schema_version':1,'id':'gallery.intro','ruleset':'gallery@1','seed':421,'tick_hz':60,'duration_ms':12000,'layout':{'width':960,'height':540},'entities':{'target_a':{'template':'target','x':170,'y':180,'width':100,'height':100,'properties':{'shape':'circle'}},'target_b':{'template':'target','x':600,'y':200,'width':100,'height':90,'properties':{'vx':12,'shape':'circle'}},'protected_a':{'template':'protected','x':380,'y':300,'width':100,'height':100,'properties':{}}},'events':{},'queries':{'target_distance':{'op':'distance','entity':'target_a','other':'target_b','space':'content_px','algorithm':'cpu-nearest-v1'}},'resources':{},'cues':{},'initial_resources':{'ammo':4,'score':0},'controls':{'ammo_resource':'ammo','magazine':4,'reload_ms':500,'shot_interval_ms':150,'assist_px':8}}
def event(trigger,actions):return {'trigger':trigger,'actions':{f'a{i}':a for i,a in enumerate(actions)},'order':[f'a{i}' for i in range(len(actions))],'max_firings':1}
source['events']={'open':event({'at_ms':0},[{'op':'spawn','entity':'target_a'},{'op':'spawn','entity':'protected_a'}]),'next':event({'at_ms':2000},[{'op':'spawn','entity':'target_b'}]),'a_clear':event({'on':'target.neutralized:target_a'},[{'op':'resource_add','resource':'score','amount':100}]),'b_clear':event({'on':'target.neutralized:target_b'},[{'op':'resource_add','resource':'score','amount':100},{'op':'complete','result':'clear'}]),'wrong':event({'on':'target.protected_hit:protected_a'},[{'op':'resource_add','resource':'score','amount':-50},{'op':'fail','result':'wrong_target'}])}
def build():
 source['resources']={'warning_tone':ensure_cues()['warning']}
 source['cues']={'target_warning':{'resource':'warning_tone','channel':'warning','duration_ms':220,'volume_db':-17}}
 source['events']['warning']=event({'at_ms':1800},[{'op':'cue','cue':'target_warning'}])
 source['queries']['entry_zone']={'op':'region_contains','entity':'target_b','region':[665,0,295,540],'space':'content_px','algorithm':'cpu-nearest-v1'}
 source['events']['zone_entry']=event({'query':'entry_zone','compare':'gte','value':1},[{'op':'emit','event':'timer.started'}])
 source['events']['zone_entry']['guards']=[{'entity':'target_b','field':'active','compare':'eq','value':True}]
 source['hud']=[{'label':'光弹','resource':'ammo'},{'label':'得分','resource':'score'}]
 path=publish(source);revision=path.parent.name
 loaded,manifest=read_package(path);build=compile_source(loaded,source_manifest=manifest);compiled=write_build(build,DEFAULT_CACHE)
 dump(ROOT/'gunforge/level_design/reviews/gallery_build.json',{'source':str(path),'source_revision':revision,'build_id':build['build_id'],'compiled':str(compiled),'state':'candidate_not_adopted'})
 print(compiled)
 return compiled
if __name__=="__main__":build()
