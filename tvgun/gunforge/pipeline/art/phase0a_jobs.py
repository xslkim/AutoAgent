"""Persistent native-image requests for T04–T06; aggregate call limits never reset."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from PIL import Image
import yaml
from artlib import GAME, write_json

BASE=GAME/'reports/art'
CONFIG=Path(__file__).with_name('config.yaml')

def read(path,default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def add(task,jobs):
    folder=BASE/task;folder.mkdir(parents=True,exist_ok=True)
    queue=read(folder/'queue.json',[])
    for job in jobs:
        if any(x['id']==job['id'] for x in queue):raise ValueError('Never overwrite queued request '+job['id'])
        job.setdefault('references',[]);job.setdefault('transparent',True)
        job.setdefault('attempt',1);job.setdefault('asset_key',job['id']);job['state']='planned'
        queue.append(job)
    write_json(folder/'queue.json',queue)

def reserve(task,ids):
    config=yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    folder=BASE/task;queue=read(folder/'queue.json',[])
    ledger=read(folder/'calls.json',{'task':task,'calls':[]})
    phase=sum(len(read(BASE/t/'calls.json',{'calls':[]})['calls']) for t in ['T02','T03','T04','T05','T06'])
    if len(ids)>config['generation']['per_batch_call_cap']:raise ValueError('Batch call cap')
    if phase+len(ids)>config['generation']['phase_0A_call_cap']:raise ValueError('0A call cap')
    if len(ledger['calls'])+len(ids)>config['task_call_caps'][task]:raise ValueError('Task call cap')
    selected=[]
    for ident in ids:
        job=next(j for j in queue if j['id']==ident)
        if job['state']!='planned':raise ValueError('Reconcile submitted request before retrying')
        if sum(c['asset_key']==job['asset_key'] for c in ledger['calls'])>=config['retry_limits']['total']:raise ValueError('Asset attempt cap')
        refs=[{'file':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in job['references']]
        params={'prompt':job['prompt'],'transparent_background':job['transparent'],'references':refs}
        record={'id':ident,'asset_key':job['asset_key'],'attempt':job['attempt'],'attempt_id':f'{task}:{ident}:a{job["attempt"]}',
                'request_fingerprint':hashlib.sha256(json.dumps(params,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest(),
                **params,'state':'submitted','provider':'builtin_image_gen','model':None,'seed':None,'provider_task_id':None,
                'requested_size':None,'cost':None,'cost_status':'not_reported','review_status':'pending'}
        ledger['calls'].append(record);job['state']='submitted';selected.append(job)
        (folder/(ident+'_prompt.txt')).write_text(job['prompt'],encoding='utf-8')
    write_json(folder/'queue.json',queue);write_json(folder/'calls.json',ledger)
    update_counts();print(json.dumps(selected,ensure_ascii=True))

def archive(task,rows):
    folder=BASE/task;queue=read(folder/'queue.json',[]);ledger=read(folder/'calls.json',{'calls':[]})
    cache=Path('D:/gunforge_cache/g01')/task;cache.mkdir(parents=True,exist_ok=True)
    for row in rows:
        job=next(j for j in queue if j['id']==row['id']);call=next(c for c in reversed(ledger['calls']) if c['id']==row['id'] and c['state']=='submitted')
        if row.get('error'):
            job.update(state='error',error=row['error']);call.update(state='error',error=row['error']);continue
        dest=cache/(job['id']+f'_a{job["attempt"]}.png');shutil.copy2(row['source'],dest)
        record={'state':'returned','source':row['source'],'output':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'actual_size':list(Image.open(dest).size)}
        job.update(record);call.update(record)
    write_json(folder/'queue.json',queue);write_json(folder/'calls.json',ledger);update_counts()

def update_counts():
    state=read(BASE/'execution_state.json',{})
    counts={t:len(read(BASE/t/'calls.json',{'calls':[]})['calls']) for t in ['T01','T02','T03','T04','T05','T06']}
    if not (BASE/'T01/calls.json').exists():
        initial=read(BASE/'T01/attempts.json',{})
        counts['T01']=len(initial.get('attempts',initial if isinstance(initial,list) else [])) if isinstance(initial,dict) else len(initial)
    state.update(builtin_image_calls=sum(counts.values()),phase_0A_calls=sum(v for t,v in counts.items() if t!='T01'),task_image_calls=counts)
    write_json(BASE/'execution_state.json',state)

if __name__=='__main__':
    if sys.argv[1]=='add':add(sys.argv[2],json.load(sys.stdin))
    elif sys.argv[1]=='reserve':reserve(sys.argv[2],sys.argv[3:])
    elif sys.argv[1]=='archive':archive(sys.argv[2],json.load(sys.stdin))
