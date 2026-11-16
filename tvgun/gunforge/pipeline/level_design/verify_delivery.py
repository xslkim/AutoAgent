"""Rebuild in an independent source directory with a new venv and empty build cache."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from paths import ROOT,CACHE,GODOT
from freeze_baseline import dump,sha


def verify_lantern_city(workspace, out, python, godot, run, manifest):
    """Exercise the normal launcher before any generated assets exist in the copy."""
    launcher = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                'gunforge/start_level_player.ps1', '-Package', 'paper.lantern_city',
                '-Candidate', '-QuitAfter', '1']
    launch_log = run('lantern-city-cold-launch', launcher, timeout=300)
    receipt = 'gunforge/level_design/reviews/lantern_city_build.json'
    build = json.loads((workspace / receipt).read_bytes())
    original = json.loads((ROOT / receipt).read_bytes())
    for key in ('build_id', 'source_revision', 'component_revisions'):
        if build[key] != original[key]:
            raise RuntimeError('Independent two-level build differs: ' + key)
    if build['build_id'].encode() not in launch_log:
        raise RuntimeError('Cold launcher failed to select the exact two-level candidate')
    compiled = Path(build['compiled'])
    if not compiled.resolve().is_relative_to((out / 'empty-build-cache').resolve()):
        raise RuntimeError('Independent build escaped the empty build cache')

    bot = [godot, '--headless', '--path', 'gunforge/framework', '--script',
           'res://tests/night_market_tests.gd', '--', '--build=' + str(compiled),
           '--assets=' + str(workspace), '--failure-retry=true']
    bot_log = run('lantern-city-ten-station-bot', bot, timeout=300)
    gameplay = json.loads(next(line for line in bot_log.decode('utf-8-sig').splitlines()
                               if line.startswith('{')))
    if not gameplay['passed'] or gameplay['build_id'] != build['build_id']:
        raise RuntimeError('Independent ten-station gameplay failed')
    dump(out / 'lantern-city-gameplay.json', gameplay)

    opening = workspace / 'gunforge/games/g01/cinematics/opening_original'
    run('lantern-city-opening-network', [python, 'gunforge/pipeline/level_design/qa_player.py',
        compiled, '--output', out / 'lantern-city-opening-network', '--opening', opening])
    network = json.loads((out / 'lantern-city-opening-network/result.json').read_bytes())
    if not network['passed'] or network['build_id'] != build['build_id']:
        raise RuntimeError('Independent two-level opening/network checks failed')

    run('level-design-regressions', [python, '-m', 'unittest', 'discover', '-s',
        'gunforge/pipeline/level_design', '-p', 'test_*.py'])
    # Rebuild through the same entry point to check repeated launches in this copy.
    run('lantern-city-repeat-launch', launcher, timeout=300)
    repeated = json.loads((workspace / receipt).read_bytes())
    if repeated['build_id'] != build['build_id']:
        raise RuntimeError('Repeated two-level launch changed build identity')

    result = {
        'passed': True,
        'package': 'paper.lantern_city',
        'workspace': str(workspace),
        'run': str(out),
        'build_id': build['build_id'],
        'source_revision': build['source_revision'],
        'component_revisions': build['component_revisions'],
        'source_manifest': manifest,
        'gameplay': gameplay,
        'network': network,
        'scope': 'independent source directory, new Python 3.12.10 venv, pinned dependencies, '
                 'empty build cache, cold and repeated GPU player launch, headless ten-station '
                 'playthrough, opening and local HTTP/UDP checks',
        'pending': ['T12_A5_cinema_review', 'physical_lightgun_monitor_and_tv_retest'],
    }
    return result


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,default=GODOT)
 parser.add_argument('--package', choices=['legacy', 'paper.lantern_city'], default='legacy')
 args=parser.parse_args()
 out=CACHE/'runs'/('delivery-'+str(time.time_ns()));workspace=out/'workspace';workspace.mkdir(parents=True)
 folders=['gunforge/framework','gunforge/games/g01/scripts','gunforge/games/g01/levels','gunforge/games/g01/bible','gunforge/games/g01/assets/stations/g01_st_l1_01_alley','gunforge/level_design','gunforge/pipeline/level_design']
 files=['gunforge/pipeline/build_0b.py','gunforge/start_level_player.ps1','gunforge/start_level_review.ps1','play_level_prototype.cmd','review_levels.cmd','play_combat_candidate.cmd','review_combat_candidate.cmd']
 if args.package == 'paper.lantern_city':
  folders.extend(['gunforge/games/g01/reports/art/T10/assets',
                  'gunforge/games/g01/reports/art/T10/parallax',
                  'gunforge/games/g01/reports/art/T11/full',
                  'gunforge/games/g01/reports/art/T12/actors',
                  'gunforge/games/g01/reports/art/T12/parallax',
                  'gunforge/games/g01/reports/art/T12/screen_shadow',
                  'art2d/assets/paper_lantern_video/export'])
  files.extend(['gunforge/games/g01/reports/art/T10/layouts.json',
                'gunforge/games/g01/reports/art/T10/compositions/square_02.png',
                'gunforge/games/g01/reports/art/T11/boss.json',
                'gunforge/games/g01/reports/art/T12/layouts.json'])
 opening='gunforge/games/g01/cinematics/opening_original'
 files.extend(opening+'/'+name for name in ['paper_lantern_city_opening_game.ogv','opening_subtitles.json'])
 for folder in folders:
  for source in (ROOT/folder).rglob('*'):
   relative=source.relative_to(ROOT)
   if not source.is_file() or any(part in ['.godot','runtime','__pycache__','generated'] for part in relative.parts):continue
   destination=workspace/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
 for name in files:
  destination=workspace/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
 manifest={p.relative_to(workspace).as_posix():sha(p) for p in workspace.rglob('*') if p.is_file()}
 dump(out/'source-manifest.json',manifest)
 env=os.environ.copy();env['GODOT_BIN']=str(args.godot);env['GUNFORGE_LEVEL_CACHE']=str(out/'empty-build-cache');checks=[]
 env.pop('PYTHONPATH', None)
 env['PYTHONNOUSERSITE'] = '1'
 def run(name,command,timeout=120):
  result=subprocess.run([str(x) for x in command],cwd=workspace,env=env,capture_output=True,timeout=timeout)
  log=result.stdout+result.stderr;(out/(name+'.log')).write_bytes(log)
  ok=result.returncode==0 and not any(x in log for x in [b'SCRIPT ERROR:',b'ObjectDB instances leaked',b'resources still in use'])
  checks.append({'name':name,'passed':ok,'log':str(out/(name+'.log'))})
  if not ok:raise RuntimeError(name+': '+log.decode(errors='replace')[-2000:])
  return log
 run('new-venv',['uv','venv',workspace/'.venv','--python','3.12.10'])
 python=workspace/'.venv/Scripts/python.exe'
 run('locked-dependencies',['uv','pip','install','--python',python,'-r','gunforge/pipeline/level_design/requirements.lock'])
 if args.package == 'paper.lantern_city':
  result = verify_lantern_city(workspace, out, python, args.godot, run,
      {'path': str(out/'source-manifest.json'), 'sha256': sha(out/'source-manifest.json')})
  result['checks'] = checks
  dump(out/'index.json', result)
  dump(ROOT/'gunforge/level_design/reviews/lantern_city_delivery_acceptance.json',
       {'passed': True, 'build_id': result['build_id'], 'index': str(out/'index.json'),
        'sha256': sha(out/'index.json'), 'checks': len(checks)})
  print(json.dumps({'passed': True, 'run': str(out), 'checks': len(checks)}))
  return
 # Run the first-station proposal before native assets have been prepared in this copy.
 for package, receipt in [('station-combat','proposal-1794237379343236500.json'),
                          ('station','proposal-1794220453914520000.json'),
                          ('gallery','proposal-1794147515072431400.json')]:
  proposal=workspace/'gunforge/level_design/reviews/agent_proposals'/receipt
  launch_log=run(package+'-proposal-launcher',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','gunforge/start_level_player.ps1','-Proposal',proposal,'-QuitAfter','0.3'])
  comparison=json.loads(run(package+'-proposal-resolution',[python,'gunforge/pipeline/level_design/review_revision.py','preview',proposal]))
  build=json.loads(Path(comparison['candidate']).read_bytes())
  if build['build_id'].encode() not in launch_log or build['source_revision']!=json.loads(proposal.read_bytes())['source_revision']:
   raise RuntimeError('Launcher failed to select the exact '+package+' proposal')
 run('assets',[python,'gunforge/pipeline/build_0b.py'])
 run('godot-import',[args.godot,'--headless','--editor','--import','--quit','--path','gunforge/framework'])
 for name in ['gallery','paper','protection','assault','siege','station','stall']:
  run('build-'+name,[python,'gunforge/pipeline/level_design/build_'+name+'.py'])
  index=json.loads((workspace/'gunforge/level_design/reviews'/(name+'_build.json')).read_bytes())
  original=json.loads((ROOT/'gunforge/level_design/reviews'/(name+'_build.json')).read_bytes())
  if index['build_id']!=original['build_id']:raise RuntimeError('Independent build differs: '+name)
  run('bot-'+name,[args.godot,'--headless','--path','gunforge/framework','--script','res://tests/functional_bot.gd','--','--build='+index['compiled'],'--assets='+str(workspace),'--report='+str(out/(name+'-bot.json'))])
 index=json.loads((workspace/'gunforge/level_design/reviews/assault_build.json').read_bytes())
 run('reviewer',[args.godot,'--path','gunforge/framework','--script','res://tools/level_review.gd','--','--build='+index['compiled'],'--assets='+str(workspace),'--capture='+str(out/'independent-review.png'),'--capture-tick=260','--quit-after-capture'])
 run('player',[args.godot,'--path','gunforge/framework','--script','res://tools/level_player.gd','--','--build='+index['compiled'],'--assets='+str(workspace),'--quit-after=1','--isolated-settings'])
 run('candidate-doubleclick-launcher',['cmd.exe','/c','play_combat_candidate.cmd','-QuitAfter','0.3'])
 run('encounter-package-launcher',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','gunforge/start_level_player.ps1','-Package','orbital.siege','-Candidate','-QuitAfter','0.3'])
 run('station-package-launcher',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','gunforge/start_level_player.ps1','-Package','paper.station','-Candidate','-QuitAfter','0.3'])
 station=json.loads((workspace/'gunforge/level_design/reviews/station_build.json').read_bytes())
 run('station-opening-network',[python,'gunforge/pipeline/level_design/qa_player.py',station['compiled'],'--output',out/'station-opening-network','--opening',workspace/opening])
 run('stall-package-launcher',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','gunforge/start_level_player.ps1','-Package','paper.stall','-Candidate','-QuitAfter','0.3'])
 # Adoption fixture exists exclusively in the independent test workspace, never the live project.
 from versions import patch,adopt
 from checks import check
 from compiler import read
 store=workspace/'gunforge/level_design';gallery=read(store/'reviews/gallery_build.json')
 patched=patch('gallery.intro',gallery['source_revision'],{'base_revision':gallery['source_revision'],'changes':[{'path':'/events/next/trigger/at_ms','expected':2000,'value':2400}]},store)
 warnings=[warning['code'] for warning in check(patched)['warnings']]
 pointer=store/'adopted/gallery.intro.json'
 expected=read(pointer)['source_revision'] if pointer.exists() else None
 adopted=adopt('gallery.intro',patched.parent.name,expected,'ISOLATED AUTOMATED TEST FIXTURE, not real user acceptance','user',store,out/'empty-build-cache',acknowledged_warnings=warnings)
 launch_log=run('adopted-source-launcher',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','gunforge/start_level_player.ps1','-Package','gallery.intro','-QuitAfter','0.3'])
 if adopted['build_id'].encode() not in launch_log:raise RuntimeError('Launcher failed to select isolated adopted source')
 result={'passed':True,'workspace':str(workspace),'run':str(out),'source_manifest':{'path':str(out/'source-manifest.json'),'sha256':sha(out/'source-manifest.json')},'checks':checks,'build_identity':'all seven packages identical to original workspace','adoption_fixture':'isolated copied workspace only; live project adoption not performed','scope':'independent directory, new Python 3.12.10 venv, pinned dependencies, copied approved assets, empty build cache, actual GPU reviewer/player, candidate and adopted launch chains; no hardware claim'}
 dump(out/'index.json',result);dump(ROOT/'gunforge/level_design/reviews/delivery_acceptance.json',{'passed':True,'index':str(out/'index.json'),'sha256':sha(out/'index.json'),'checks':len(checks)})
 print(json.dumps({'passed':True,'run':str(out),'checks':len(checks)}))
if __name__=='__main__':main()
