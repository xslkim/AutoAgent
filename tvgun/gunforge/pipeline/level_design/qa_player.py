"""Actual GPU shared player + loopback Android-compatible HTTP/UDP checks."""
import argparse,json,socket,subprocess,threading,time,urllib.request
from pathlib import Path
from paths import ROOT,GODOT
from compiler import read
def run(build_path,out,opening=None):
 out.mkdir(parents=True,exist_ok=True);build=read(build_path);checks=[]
 log=(out/'player.log').open('wb')
 command=[str(GODOT),'--path',str(ROOT/'gunforge/framework'),'--script','res://tools/level_player.gd','--','--build='+str(build_path),'--assets='+str(ROOT),'--network','--isolated-settings']
 if opening is not None:command.append('--opening-dir='+str(opening))
 process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
 sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);stop=threading.Event();sequence=[0];heartbeat=None
 def send(text):sock.sendto(text.encode(),('127.0.0.1',9000))
 def request(path,data=None):
  payload=None if data is None else json.dumps(data).encode()
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080'+path,data=payload,headers={'Content-Type':'application/json'}),timeout=3) as response:return json.load(response)
 def check(ok,label):
  checks.append({'name':label,'passed':bool(ok)})
  if not ok:raise AssertionError(label)
 def pulse():
  while not stop.is_set():sequence[0]+=1;send(f'960,540,4,{sequence[0]}');stop.wait(.04)
 try:
  for _ in range(150):
   if process.poll() is not None:raise RuntimeError('Player stopped')
   try:state=request('/state');break
   except OSError:time.sleep(.05)
  else:raise TimeoutError('Player startup')
  check(state.get('build_id')==build['build_id'],'exact_build_owned_test_server')
  send('HELLO qa-session-'+str(time.time_ns()));heartbeat=threading.Thread(target=pulse,daemon=True);heartbeat.start();time.sleep(.1)
  check(request('/start',{})['ok'],'http_start')
  if opening is not None:
   for _ in range(80):
    state=request('/state')
    if state.get('opening_seconds',0)>=2.1:break
    time.sleep(.05)
   check(state['lifecycle']=='opening' and state.get('opening_seconds',0)>=2.1,'opening_decodes_and_advances')
   check(not state['shot_input_enabled'] and not request('/shot',{'x':960,'y':540})['ok'],'opening_blocks_gameplay_shots')
   send('START')
   for _ in range(30):
    if request('/state')['lifecycle']=='running':break
    time.sleep(.05)
   check(request('/state')['lifecycle']=='running','udp_start_skips_opening')
  time.sleep(.1);state=request('/state');check(state['lifecycle']=='running','ready_to_running')
  for _ in range(100):
   if state['shot_input_enabled'] and state['visible_targets']:break
   time.sleep(.05);state=request('/state')
  check(state['shot_input_enabled'],'shot_input_enabled_after_opening')
  check(bool(state['visible_targets']),'visible_submission_available')
  point=state['visible_targets'][0]['point'];layout=build['level']['layout'];scale=min(1776/layout['width'],936/layout['height']);origin=[(1776-layout['width']*scale)/2,(936-layout['height']*scale)/2]
  answer=request('/shot',{'x':72+origin[0]+point[0]*scale,'y':72+origin[1]+point[1]*scale})
  check(answer.get('ok') and answer.get('hit'),'http_shot_receipt_after_consumption')
  time.sleep(.2);before=request('/state')['shots'];packet='SHOT 960,540,999999';send(packet);send(packet);time.sleep(.15)
  check(request('/state')['shots']==before+1,'udp_duplicate_shot_consumed_once')
  stop.set();heartbeat.join(1);barrier=sequence[0]+1000;send(f'LOST,{barrier}');time.sleep(.1)
  state=request('/state');check(state['lifecycle']=='paused','lost_tracking_pauses_shared_session')
  before=state['shots'];send(f'SHOT 960,540,{barrier-1}');request('/start',{});time.sleep(.1)
  state=request('/state');check(state['shots']==before and state['lifecycle']=='paused','late_shot_and_start_do_not_clear_tracking_barrier')
  send(f'960,540,4,{barrier+1}');time.sleep(.1);check(request('/state')['lifecycle']=='running','fresh_aim_recovers_while_paused')
  result={'passed':True,'build_id':build['build_id'],'checks':checks,'hardware':'synthetic loopback protocol test; no phone tracking or display latency claim'}
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result
 finally:
  stop.set()
  if heartbeat:heartbeat.join(1)
  if process.poll() is None:process.terminate();process.wait(timeout=10)
  sock.close();log.close()
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('build',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--opening',type=Path);args=parser.parse_args();print(json.dumps(run(args.build,args.output,args.opening)))
