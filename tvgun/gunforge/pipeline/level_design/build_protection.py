"""Third executable whitebox: shield windows, interception and a protected objective."""
import hashlib,json
from compiler import ROOT,DEFAULT_CACHE,digest,read_package,compile_source,write_build
from freeze_baseline import dump
from versions import publish
from build_gallery import event
from cues import ensure_cues

def build():
 def entity(template,x,y,w,h,**properties):return dict(template=template,x=x,y=y,width=w,height=h,properties=properties)
 source={'schema_version':1,'id':'orbital.convoy','ruleset':'protection@1','seed':902,'tick_hz':60,'duration_ms':15000,'layout':{'width':1280,'height':720},'entities':{'convoy':entity('protected',1000,300,150,110),'shield':entity('activation_source',900,500,90,70),'drone':entity('target',200,120,100,90,hits=2,shape='circle'),'bolt_a':entity('projectile',260,330,40,40,vx=180,shape='circle'),'bolt_b':entity('projectile',320,350,40,40,vx=180,shape='circle')},'events':{},'queries':{'bolt_a_distance':{'op':'distance','entity':'bolt_a','other':'convoy','algorithm':'cpu-nearest-v1','space':'content_px'},'bolt_b_distance':{'op':'distance','entity':'bolt_b','other':'convoy','algorithm':'cpu-nearest-v1','space':'content_px'}},'resources':{},'cues':{},'initial_resources':{'hull':2,'merit':0}}
 events=source['events']
 source['resources']={'warning_tone':ensure_cues()['warning']}
 source['cues']={'launch_warning':{'resource':'warning_tone','channel':'warning','duration_ms':220}}
 source['hud']=[{'label':'船体','resource':'hull'},{'label':'功绩','resource':'merit'}]
 events['open']=event({'at_ms':0},[{'op':'spawn','entity':id} for id in ['convoy','shield','drone']]+[{'op':'permission','entity':'drone','kind':'invalid'}])
 events['shield_off']=event({'at_ms':2000},[{'op':'permission','entity':'drone','kind':'weak'}])
 events['shield_on']=event({'at_ms':5000},[{'op':'permission','entity':'drone','kind':'invalid'}])
 events['drone_clear']=event({'on':'target.neutralized:drone'},[{'op':'resource_add','resource':'merit','amount':200}])
 for id,at in [('bolt_a',1000),('bolt_b',6000)]:
  events[id+'_launch']=event({'at_ms':at},[{'op':'spawn','entity':id},{'op':'cue','cue':'launch_warning'}])
  events[id+'_impact']=event({'query':id+'_distance','compare':'lte','value':100},[{'op':'remove','entity':id},{'op':'resource_add','resource':'hull','amount':-1},{'op':'emit','event':'objective.damaged'}])
  events[id+'_impact']['guards']=[{'entity':id,'field':'active','compare':'eq','value':True}]
  events[id+'_intercept']=event({'on':'target.neutralized:'+id},[{'op':'resource_add','resource':'merit','amount':100}])
 events['objective_lost']=event({'on':'objective.damaged'},[{'op':'fail','result':'convoy_lost'}]);events['objective_lost']['guards']=[{'resource':'hull','compare':'lte','value':0}]
 events['objective_saved']=event({'at_ms':12000},[{'op':'resource_add','resource':'merit','amount':500},{'op':'complete','result':'convoy_safe'}]);events['objective_saved']['guards']=[{'resource':'hull','compare':'gt','value':0}]
 events['wrong_target']=event({'on':'target.protected_hit:convoy'},[{'op':'resource_add','resource':'merit','amount':-100}])
 events['shield_switch']=event({'on':'interaction.activated:shield'},[{'op':'permission','entity':'drone','kind':'weak'}])
 path=publish(source);revision=path.parent.name
 source,manifest=read_package(path);compiled=compile_source(source,source_manifest=manifest);out=write_build(compiled,DEFAULT_CACHE)
 dump(ROOT/'gunforge/level_design/reviews/protection_build.json',{'source':str(path),'source_revision':revision,'build_id':compiled['build_id'],'compiled':str(out),'state':'candidate_not_adopted'})
 return out
if __name__=='__main__':print(build())
