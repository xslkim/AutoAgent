"""Separate hard compilation errors from uncalibrated design heuristics."""
import argparse,json
from pathlib import Path
from compiler import read_package,compile_source,CompileError
def check(entry):
 source,manifest=read_package(entry);build=compile_source(source,source_manifest=manifest)
 warnings=[]
 # These identify review work; no warning is automatically acknowledged.
 if not source.get('hud'):warnings.append({'code':'HUD_UNDECLARED','message':'No generic HUD fields declared; native rules may render their own HUD.'})
 if source.get('ruleset_data',{}).get('native_level'):
  warnings.append({'code':'LEGACY_RULE_POLICY','message':'Lamp refresh/reward and continue score reset preserve the demo; formal game-policy adoption is pending.'})
 if source['layout']['width']/source['layout']['height']!=1776/936:warnings.append({'code':'DISPLAY_PROFILE_UNTESTED','message':'Content aspect differs from the old demo; verify letterboxing and actual device calibration.'})
 warnings.append({'code':'HUMAN_DIFFICULTY_UNCALIBRATED','message':'Diagnostic bots and sampled alpha metrics do not predict human difficulty.'})
 return {'source_revision':build['source_revision'],'build_id':build['build_id'],'hard_errors':[],'warnings':warnings,'warning_state':'open','preview_allowed':True,'human_validation':'pending'}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('entry',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
 try:result=check(args.entry);code=0
 except CompileError as error:result={'hard_errors':[str(error)],'preview_allowed':False};code=1
 data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
 if args.output:args.output.write_text(data,encoding='utf-8')
 print(data);raise SystemExit(code)
