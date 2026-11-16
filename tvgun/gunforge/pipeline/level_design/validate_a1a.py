"""A1a acceptance runner: original behavior and geometry must remain unchanged."""
import argparse,json,subprocess,time
from pathlib import Path
from record_baseline import GODOT,ROOT,BASE
from freeze_baseline import REVIEWS,dump,sha
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=ROOT/'gunforge/framework');options=ap.parse_args()
out=ROOT.parent/'gunforge_cache/level_design/runs'/('a1a-'+str(time.time_ns()));out.mkdir(parents=True,exist_ok=False)
commands=[('timing','timing_tests.gd',[]),('core','core_tests.gd',[]),('snapshot','snapshot_tests.gd',[]),('geometry','geometry_baseline_tests.gd',['--baseline='+str(BASE/'geometry_0.json'),'--output='+str(out/'geometry_comparison.json')]),('replay','replay_baseline_tests.gd',['--baseline='+str(BASE),'--output='+str(out/'replay_comparison.json')])]
results=[]
for name,script,args in commands:
 command=[str(GODOT),'--headless','--path',str(options.project),'--script','res://tests/'+script]
 if args:command+=['--',*args]
 start=time.perf_counter();r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8');duration=time.perf_counter()-start
 path=out/(name+'_checks.log');path.write_text(r.stdout+r.stderr,encoding='utf-8')
 assert r.returncode==0 and 'SCRIPT ERROR' not in r.stderr and 'ERROR:' not in r.stderr,(name,r.stdout,r.stderr)
 results.append({'name':name,'command':command,'exit_code':r.returncode,'wall_seconds':duration,'log':str(path),'sha256':sha(path)})
 print(name,'PASS',round(duration,3),flush=True)
dump(REVIEWS/'a1a_checks.json',{'passed':True,'project':str(options.project),'checks':results,'numeric_comparison':'Legacy Godot JSON encoding roundtrip normalizes parsed numeric types; discrete decisions and sampled geometry strictly match; no numeric/tick tolerance used. Native snapshot restore additionally bit-exact.','limitations':['live actual phone, audio listening and calibrated end-to-end display latency not tested','freeze debug input uses explicit zero-time boundary for backwards compatibility']})
