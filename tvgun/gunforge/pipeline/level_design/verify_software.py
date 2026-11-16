"""One-command reproducible software acceptance. Each run has immutable evidence paths."""
import argparse,copy,hashlib,json,platform,subprocess,sys,time
from pathlib import Path
from paths import ROOT,CACHE,GODOT
from compiler import read,read_package,compile_source,write_build
from freeze_baseline import dump,sha
from checks import check

def verify_r2_migration(build, output):
 old_revision = '28f580405bdd4eb96ca2dc29069f21abf5c7fc4537aa97a7d8cd9fe6809f51c4'
 old_source, manifest = read_package(ROOT/'gunforge/level_design/packages/paper.assault/revisions'/old_revision/'level.json')
 baseline = compile_source(old_source,source_manifest=manifest)['level']
 migrated = read(Path(build['compiled']))['level']
 emitter = baseline['presentation']['support']['entity']
 for query_id in list(baseline['queries']):
  if query_id.endswith('.onscreen'):
   renamed = query_id.removesuffix('.onscreen')+'.support_region'
   baseline['queries'][renamed] = baseline['queries'].pop(query_id)
 for event_id, event in baseline['events'].items():
  if not event_id.endswith('.support'):
   continue
  for guard in event['guards']:
   if guard.get('query','').endswith('.onscreen'):
    guard['query'] = guard['query'].removesuffix('.onscreen')+'.support_region'
  for action in event['actions'].values():
   if action['op']=='vfx':
    action['source'] = emitter
 mismatches = sorted(key for key in baseline.keys() | migrated.keys() if baseline.get(key)!=migrated.get(key))
 dump(output,{'passed':not mismatches,'baseline_source':old_revision,'candidate_source':build['source_revision'],
              'compared_fields':sorted(baseline),'mismatches':mismatches,
              'normalization':['support region query IDs','previously implicit support-effect emitter']})
 if mismatches:
  raise RuntimeError('R2 migration changed runtime data: '+', '.join(mismatches))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--skip-legacy-network',action='store_true');parser.add_argument('--baseline',type=Path,default=CACHE/'baseline-v1');args=parser.parse_args()
 out=CACHE/'runs'/('software-'+str(time.time_ns()));out.mkdir(parents=True,exist_ok=False);results=[]
 def run(name,command,timeout=120):
  print('Checking '+name,flush=True);started=time.monotonic()
  try:
   p=subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,timeout=timeout)
   log=p.stdout+p.stderr;code=p.returncode
  except subprocess.TimeoutExpired as error:log=(error.stdout or b'')+(error.stderr or b'')+b'\nTIMEOUT';code=-1
  path=out/(name+'.log');path.write_bytes(log)
  # Godot can report runtime script errors without an unsuccessful OS exit.
  passed=code==0 and not any(x in log for x in [b'SCRIPT ERROR:',b'ObjectDB instances leaked',b'resources still in use'])
  result={'name':name,'exit_code':code,'passed':passed,'seconds':time.monotonic()-started,'log':str(path),'sha256':sha(path)};results.append(result)
  if not passed:print(log.decode('utf-8',errors='replace')[-5000:]);raise RuntimeError('Failed '+name)
 def godot(name,script,build=None,extra=(),gpu=False,timeout=120):
  command=[GODOT]+([] if gpu else ['--headless'])+['--path',ROOT/'gunforge/framework','--script','res://'+script,'--']
  if build:command += ['--build='+build['compiled'],'--assets='+str(ROOT),'--report='+str(out/(name+'.json'))]
  run(name,command+list(extra),timeout)
 status={'passed':False,'run':str(out),'host':platform.platform(),'python':sys.version,'godot':str(GODOT),'results':results,'hardware':'not tested','user_adoption':'not performed'}
 try:
  run('python-contracts',[sys.executable,'-m','unittest','discover','-s','gunforge/pipeline/level_design','-p','test_*.py'])
  run('native-assets',[sys.executable,'gunforge/pipeline/build_0b.py'])
  builds={}
  for name in ['gallery','paper','protection','assault','siege','station','stall']:
   run('build-'+name,[sys.executable,'gunforge/pipeline/level_design/build_'+name+'.py'])
   builds[name]=read(ROOT/'gunforge/level_design/reviews'/(name+'_build.json'))
   dump(out/(name+'-design-checks.json'),check(Path(builds[name]['source'])))
   source,manifest=read_package(Path(builds[name]['source']));rebuilt=write_build(compile_source(source,source_manifest=manifest),out/'fresh-build-cache')
   if builds[name]['source_revision']!=Path(builds[name]['source']).parent.name or read(rebuilt)['source_revision']!=builds[name]['source_revision']:raise RuntimeError('Source directory/manifest identity mismatch')
   if rebuilt.read_bytes()!=Path(builds[name]['compiled']).read_bytes():raise RuntimeError('Fresh-cache rebuild differs')
  verify_r2_migration(builds['assault'],out/'assault-r2-migration.json')
  for name in ['core','timing','snapshot','defect']:
   godot(name,'tests/'+name+'_tests.gd',extra=['--report='+str(out/(name+'.json'))])
  godot('gallery-runtime','tests/level_runtime_tests.gd',builds['gallery'])
  godot('sampled-visibility','tests/visibility_tests.gd')
  godot('loader-integrity','tests/loader_tests.gd',builds['gallery'])
  godot('gallery-session','tests/session_tests.gd',builds['gallery'])
  godot('audio-envelopes','tests/audio_tests.gd',builds['gallery'])
  godot('protection-branches','tests/protection_tests.gd',builds['protection'])
  godot('assault-mechanics','tests/assault_tests.gd',builds['assault'])
  godot('assault-no-input','tests/functional_bot.gd',builds['assault'],extra=['--idle','--expected=overrun'])
  godot('station-no-input','tests/functional_bot.gd',builds['station'],extra=['--idle','--expected=overrun'])
  godot('stall-light-windows','tests/stall_tests.gd',builds['stall'])
  godot('stall-no-input','tests/functional_bot.gd',builds['stall'],extra=['--idle','--expected=timeout'])
  godot('siege-encounter-branches','tests/encounter_tests.gd',builds['siege'])
  godot('native-shared-schedule','tests/native_bridge_tests.gd',builds['paper'])
  if args.baseline.is_dir():
   godot('paper-baseline-replay','tests/replay_baseline_tests.gd',extra=['--baseline='+str(args.baseline),'--output='+str(out/'paper-baseline-replay.json'),'--expected-fixes','--compiled='+builds['paper']['compiled']])
  else:status['baseline_replay']='not available; baseline archive missing'
  source,manifest=read_package(Path(builds['gallery']['source']));fixture=copy.deepcopy(source);fixture['id']='benchmark.session_90s';fixture['duration_ms']=90000
  fixture_path=out/'benchmark-source.json';dump(fixture_path,fixture);data,manifest=read_package(fixture_path);fixture_build=write_build(compile_source(data,source_manifest=manifest),out/'fresh-build-cache')
  godot('seek-90s','tests/seek_benchmark.gd',{'compiled':str(fixture_build)})
  for name,build in builds.items():
   godot(name+'-bot','tests/functional_bot.gd',build)
   if name in ['assault','station']:
    godot(name+'-full-replay','tests/combat_replay_tests.gd',build,extra=['--recording='+str(out/(name+'-bot.json.input.bin'))])
   godot(name+'-review-ui','tools/level_review.gd',build,extra=['--reviews='+str(out/name/'test-comments'),'--evidence='+str(out/name/'evidence'),'--review-smoke'],gpu=True)
   capture_tick = ['--capture-tick=126'] if name=='siege' else []
   godot(name+'-review-capture','tools/level_review.gd',build,extra=['--capture='+str(out/(name+'-review.png')),'--quit-after-capture',*capture_tick],gpu=True)
   godot(name+'-player','tools/level_player.gd',build,extra=['--quit-after=1'],gpu=True)
   run(name+'-player-network',[sys.executable,'gunforge/pipeline/level_design/qa_player.py',build['compiled'],'--output',out/(name+'-network')])
  if not args.skip_legacy_network:run('legacy-live-http-udp',[sys.executable,'gunforge/pipeline/level_design/check_current.py'])
  status['passed']=True;status['builds']=builds
 finally:
  status['source_hashes']={p.relative_to(ROOT).as_posix():sha(p) for folder in ['gunforge/framework/core','gunforge/framework/tools','gunforge/framework/tests','gunforge/level_design/rulesets','gunforge/pipeline/level_design'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.gd','.json']}
  status['files']={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}
  dump(out/'index.json',status);dump(ROOT/'gunforge/level_design/reviews/software_acceptance.json',{'passed':status['passed'],'index':str(out/'index.json'),'sha256':sha(out/'index.json'),'run':str(out),'checks':len(results)})
 print(json.dumps({'passed':True,'run':str(out),'checks':len(results)}))
if __name__=='__main__':main()
