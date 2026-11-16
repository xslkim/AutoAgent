"""Record real Godot baseline cases through an isolated debug dispatcher."""
import difflib,hashlib,json,socket,subprocess,time
from pathlib import Path
from freeze_baseline import ROOT,REVIEWS,dump,sha
BASE=ROOT.parent/'gunforge_cache/level_design/baseline-v1'
GODOT=ROOT.parent/'gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe'
class Client:
 def __init__(self):
  self.sock=socket.create_connection(('127.0.0.1',19110),timeout=30);self.file=self.sock.makefile('rwb');self.ops=[]
 def call(self,op,**args):
  request={'op':op,**args};self.file.write((json.dumps(request)+'\n').encode());self.file.flush();reply=json.loads(self.file.readline());assert 'error' not in reply,reply;self.ops.append({'request':request,'response':{k:v for k,v in reply.items() if k not in ['performance','startup']}});return reply
 def state(self):return self.call('state')['state']
 def steps(self,n):return self.call('record_steps',frames=n)['trace'][-1]
 def shot(self,id):return self.call('record_target',id=id)
 def start(self):self.call('record_reset');return self.call('input',event='START')['state']
 def finish(self):self.file.close();self.sock.close()
def record(c,name):
 c.ops=[];c.start();checks={}
 if name=='normal':
  for _ in range(350):
   s=c.state()
   if s['phase']=='complete':break
   assert s['phase']!='continue',s
   if s['phase']=='playing':
    if s['ammo']<=1:c.call('input',event='RELOAD');c.steps(40);continue
    alive=[i for i,e in enumerate(s['enemies']) if e['status']=='alive']
    if alive:
     if s['lamp']<.99:c.shot('lamp');c.steps(40)
     c.steps(16);c.shot('crow_'+str(alive[0]));c.steps(16)
    elif not s['rescued']:
     r=c.shot('resident_ink');c.steps(16 if 'absent' not in r else 30)
    else:c.steps(30)
   else:c.steps(30)
  checks['complete']=c.state()['phase']=='complete';assert checks['complete']
 elif name=='miss_and_continue':
  for _ in range(200):
   if c.state()['phase']=='continue':break
   c.steps(30)
  before=c.state();assert before['phase']=='continue';after=c.call('input',event='COIN')['state'];assert after['wave']==before['wave'] and after['lives']==5 and after['score']==0;checks['continue_same_wave']=True
 elif name=='paper':
  c.steps(210);before=c.state();result=c.shot('resident');assert 'absent' not in result;after=c.state();assert after['lives']==before['lives']-1;checks['D08_life_penalty_reproduced']=True
 elif name=='repeat_rescue':
  c.steps(210);a=c.shot('resident_ink');assert 'absent' not in a;c.steps(10);b=c.shot('resident_ink');assert 'absent' not in b
  assert b['state']['score']==a['state']['score']+300,(a,b);checks['D02_repeat_reward_reproduced']=True
 elif name=='repeat_lamp':
  c.steps(210);a=c.shot('lamp');c.steps(16);b=c.shot('lamp');assert b['state']['score']==a['state']['score']+25;checks['D03_repeat_reward_reproduced']=True
 elif name=='reload':
  for _ in range(6):c.call('input',event='SHOT',x=400,y=100);c.steps(16)
  assert c.state()['ammo']==0;c.call('input',event='SHOT',x=-10,y=100);c.steps(40);assert c.state()['ammo']==6;checks['offscreen_reload']=True
 elif name=='loss':
  c.steps(180);c.call('record_lock',value=False);c.steps(150);a=c.state();c.steps(60);b=c.state();assert a['total']==b['total'] and b['paused'];c.call('record_lock',value=True);c.steps(90);assert not c.state()['paused'];checks['loss_pause_resume']=True
 elif name=='one_miss_per_wave':
  for _ in range(210):
   s=c.state()
   if s['phase']=='complete':break
   assert s['phase']!='continue'
   if s['phase']=='playing' and s['enemies'][1]['status']=='alive':
    c.shot('lamp');c.steps(40);c.shot('crow_1');c.steps(16)
   else:c.steps(30)
  assert c.state()['phase']=='complete' and c.state()['lives']==2;checks['one_miss_each_wave']=True
 else:raise ValueError(name)
 return {'case':name,'checks':checks,'operations':c.ops.copy()}
def main():
 project=BASE/'recording_project'
 old=(BASE/'original/gunforge/framework/main.gd').read_text(encoding='utf-8');new=(project/'main.gd').read_text(encoding='utf-8');patch=BASE/'recording_only.patch';patch.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original/main.gd',tofile='recording/main.gd')),encoding='utf-8')
 index=json.loads((REVIEWS/'baseline_source.json').read_text(encoding='utf-8'));index['recording_patch_sha256']=sha(patch);dump(REVIEWS/'baseline_source.json',index)
 log=(BASE/'engine.log').open('w',encoding='utf-8');proc=subprocess.Popen([str(GODOT),'--headless','--path',str(project),'--','--fixed'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(100):
   if proc.poll() is not None:raise RuntimeError((BASE/'engine.log').read_text())
   try:c=Client();break
   except OSError:time.sleep(.1)
  else:raise TimeoutError('Engine debug server unavailable')
  # Live UDP/HTTP and synthetic desktop entry must not start the frozen title.
  c.call('record_reset');before=c.state();sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.sendto(b'START',('127.0.0.1',19100));sock.close()
  h=socket.create_connection(('127.0.0.1',19100));h.sendall(b'POST /start HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}');c.call('desktop_probe');time.sleep(.2);assert c.state()==before;h.close()
  results=[]
  for name in ['normal','one_miss_per_wave','miss_and_continue','paper','repeat_rescue','repeat_lamp','reload','loss']:
   runs=[]
   for repetition in range(2):
    data=record(c,name);path=BASE/f'{name}_{repetition}.json';dump(path,data);runs.append(sha(path))
   assert runs[0]==runs[1],(name,'non-deterministic baseline')
   results.append({'case':name,'checks':data['checks'],'sha256':runs[0],'runs':2})
   print(name,'PASS',flush=True)
  dump(REVIEWS/'baseline_cases.json',{'passed':True,'input_isolation':['UDP START','HTTP /start','synthetic desktop KEY_ENTER handler'],'cases':results,'directory':str(BASE),'engine_log_sha256':sha(BASE/'engine.log'),'baseline_source_manifest':index['manifest_sha256'],'recording_patch_sha256':sha(patch),'limitations':['headless software renderer: no GPU screenshot or audio listening validation','record_steps refreshes geometry once per tick; records explicitly differ from batched legacy step'],'reproduce':'.venv/Scripts/python.exe gunforge/pipeline/level_design/record_baseline.py'})
  c.call('quit');c.finish();proc.wait(timeout=10)
 finally:
  if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
  log.close()
if __name__=='__main__':main()
