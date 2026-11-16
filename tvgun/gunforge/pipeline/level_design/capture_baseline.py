"""Capture baseline visual evidence using the actual GPU renderer."""
import json,subprocess,time
from pathlib import Path
from record_baseline import BASE,GODOT,Client
from freeze_baseline import REVIEWS,dump,sha
log=(BASE/'gpu.log').open('w',encoding='utf-8')
p=subprocess.Popen([str(GODOT),'--path',str(BASE/'recording_project'),'--','--fixed'],stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(100):
  if p.poll() is not None:raise RuntimeError('GPU process failed')
  try:c=Client();break
  except OSError:time.sleep(.1)
 else:raise TimeoutError('GPU startup')
 c.start();c.steps(210);c.shot('lamp');c.steps(40)
 files=[]
 for name in ['lit','debug','rescued']:
  if name=='debug':
   # Toggle is a controlled debug property in the isolated recording project.
   c.call('record_debug',value=True)
  if name=='rescued':c.call('record_debug',value=False);c.shot('resident_ink');c.steps(22)
  dest=BASE/(name+'.png');c.call('capture',path=str(dest))
  for _ in range(100):
   if dest.exists() and dest.stat().st_size>1000:break
   time.sleep(.05)
  else:raise RuntimeError('Capture failed')
  files.append({'file':str(dest),'sha256':sha(dest)})
 dump(REVIEWS/'baseline_visuals.json',{'captures':files,'log':str(BASE/'gpu.log'),'actual_gpu':True,'visual_review':'pending'})
 c.call('quit');c.finish();p.wait(timeout=10)
finally:
 if p.poll() is None:p.terminate();p.wait(timeout=10)
 log.close()
