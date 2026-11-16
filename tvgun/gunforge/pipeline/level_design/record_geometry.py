import subprocess,time
from record_baseline import BASE,GODOT,Client
from freeze_baseline import REVIEWS,dump,sha
log=(BASE/'geometry.log').open('w',encoding='utf-8');p=subprocess.Popen([str(GODOT),'--headless','--path',str(BASE/'recording_project'),'--','--fixed'],stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(100):
  try:c=Client();break
  except OSError:time.sleep(.1)
 results=[]
 for run in range(2):
  rows=[];c.start();c.steps(210);rows.append(c.call('record_grid'))
  c.shot('lamp');c.steps(40);rows.append(c.call('record_grid'))
  c.shot('resident_ink');rows.append(c.call('record_grid'));c.steps(10);rows.append(c.call('record_grid'))
  c.steps(3);rows.append(c.call('record_grid'))
  c.start();c.steps(1110);rows.append(c.call('record_grid'))
  dest=BASE/f'geometry_{run}.json';dump(dest,rows);results.append(sha(dest));print('geometry run',run,'samples',sum(len(row['samples']) for row in rows),flush=True)
 assert results[0]==results[1],results
 dump(REVIEWS/'baseline_geometry.json',{'passed':True,'sha256':results[0],'directory':str(BASE),'runs':2,'samples_per_run':sum(len(row['samples']) for row in rows),'states':['hard','soft','rescue_0','rescue_10ticks','rescue_13ticks','pickup'],'algorithm':'old resolver, visible alpha row edges +/-1/14/16px plus fixed 144px grid; query only, no shot'})
 c.call('quit');c.finish();p.wait(timeout=10)
finally:
 if p.poll() is None:p.terminate();p.wait(timeout=10)
 log.close()
