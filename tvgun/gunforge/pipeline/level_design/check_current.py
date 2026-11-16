"""Run current engine regressions without overwriting historical 0B evidence."""
import json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qa_0b
from record_baseline import GODOT,ROOT
from freeze_baseline import REVIEWS,dump,sha
out=ROOT.parent/'gunforge_cache/level_design/runs'/('engine-'+str(time.time_ns()));out.mkdir(parents=True,exist_ok=False)
qa_0b.REPORT=out
import qa_0b_http,qa_0b_udp
qa_0b_http.REPORT=out;qa_0b_udp.REPORT=out
log=(out/'engine.log').open('w',encoding='utf-8')
p=subprocess.Popen([str(GODOT),'--path',str(ROOT/'gunforge/framework')],stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(100):
  if p.poll() is not None:raise RuntimeError('Engine stopped; inspect '+str(out/'engine.log'))
  try:c=qa_0b.Client();break
  except OSError:time.sleep(.1)
 else:raise TimeoutError('Engine startup')
 time.sleep(.2)
 qa_0b_http.run('127.0.0.1')
 qa_0b.run()
 qa_0b_udp.run()
 c.call('quit');p.wait(timeout=10)
 dump(REVIEWS/'current_engine_checks.json',{'passed':True,'evidence':str(out),'files':{f.name:sha(f) for f in out.glob('*.json')},'note':'Live legacy demo integration: complete/continue bot, HTTP and UDP. Migration equivalence and new package checks have separate indexes.'})
finally:
 if p.poll() is None:p.terminate();p.wait(timeout=10)
 log.close()
