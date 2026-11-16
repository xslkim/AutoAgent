"""Persistent, resumable local H3 jobs; never resubmit an accepted unknown job."""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from opening_plan import ROOT, SHOTS, STYLE

API='http://127.0.0.1:8189'
def request(path, body=None, timeout=60):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(API+path,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read())

def workflow(shot, take=1):
    p={
      '1':{'class_type':'UNETLoader','inputs':{'unet_name':'minimax_h3_fl2va_pruned_int8_convrot.safetensors','weight_dtype':'default'}},
      '2':{'class_type':'LoraLoaderModelOnly','inputs':{'model':['1',0],'lora_name':'minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors','strength_model':1.0}},
      '3':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors','type':'minimax','device':'default'}},
      '4':{'class_type':'VAELoader','inputs':{'vae_name':'minimax_h3_video_vae_int8_convrot.safetensors'}},
      '5':{'class_type':'VAELoader','inputs':{'vae_name':'minimax_h3_audio_vae_fp32.safetensors'}},
      '6':{'class_type':'MiniMaxH3ImageToVideo','inputs':{'clip':['3',0],'vae':['4',0],'prompt':STYLE+'\n'+shot['motion'],'width':1152,'height':640,'length':158}},
      '7':{'class_type':'RandomNoise','inputs':{'noise_seed':2026110700+int(shot['id'][1:])}},
      '8':{'class_type':'KSamplerSelect','inputs':{'sampler_name':'res_multistep'}},
      '9':{'class_type':'BasicScheduler','inputs':{'model':['2',0],'scheduler':'simple','steps':8,'denoise':1.0}},
      '10':{'class_type':'BasicGuider','inputs':{'model':['2',0],'conditioning':['6',0]}},
      '11':{'class_type':'SamplerCustomAdvanced','inputs':{'noise':['7',0],'guider':['10',0],'sampler':['8',0],'sigmas':['9',0],'latent_image':['6',1]}},
      '12':{'class_type':'VAEDecode','inputs':{'samples':['11',0],'vae':['4',0]}},
      '13':{'class_type':'VAEDecodeAudio','inputs':{'samples':['11',0],'vae':['5',0]}},
      '14':{'class_type':'CreateVideo','inputs':{'images':['12',0],'audio':['13',0],'fps':24.0}},
      '15':{'class_type':'SaveVideo','inputs':{'video':['14',0],'filename_prefix':'g01_original_20261107/'+shot['id'],'format':'auto','codec':'auto'}}}
    if shot['frame']:
        source=ROOT/'keyframes'/f"{shot['frame']}.png"
        # Copy our new keyframe into the model's input folder, without borrowing any old media.
        target=Path('/home/xsl/aivideo/ComfyUI/input/g01_original_20261107')/source.name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(source.read_bytes())
        p['16']={'class_type':'LoadImage','inputs':{'image':'g01_original_20261107/'+source.name}}
        p['6']['inputs']['first_frame']=['16',0]
    if shot['id']=='s04' and take>=2:
        source=ROOT/'keyframes/spill_end.png'
        target=Path('/home/xsl/aivideo/ComfyUI/input/g01_original_20261107/spill_end.png')
        target.write_bytes(source.read_bytes())
        p['17']={'class_type':'LoadImage','inputs':{'image':'g01_original_20261107/spill_end.png'}}
        p['6']['inputs']['last_frame']=['17',0]
        p['6']['inputs']['prompt']=STYLE+'\nLocked camera. Animate ONLY the transition from the first frame to the last frame: the shallow inkstone tips gently to the right, one small black puddle spills and reaches the lamp base. Exact same dark rainy NIGHT outside, exact same dim paper city and lamp light. All other objects remain absolutely stationary. DO NOT turn on the city lamp yet. No new objects, no hands. This is a small ordinary accident. Quiet ceramic knock and a little ink trickle.'
    if shot['id']=='s07' and take>=2:
        p['6']['inputs']['last_frame']=['16',0]
        p['6']['inputs']['prompt']=STYLE+'\n首尾画面完全相同，固定机位，保持纸雕夜景的亮度和配色不变。只让左边的纸偶居民缓慢招手一次，右边居民往自行车方向迈两小步后停住；线上的一只纸麻雀只轻轻扑翼。人物仍是原本的两位，不增减，不攻击。整个背景、天空、建筑、电线、自行车完全静止。严禁太阳、日出、月亮、光球或新光源，严禁变白天，严禁光照变亮，画面曝光锁定。只有很轻的自行车铃和纸张细响，没有人说话，没有配乐。'
    if shot['id']=='s06' and take>=2:
        for node,name in [('16','spill_end'),('17','workbench_lit')]:
            source=ROOT/'keyframes'/f'{name}.png'
            target=Path('/home/xsl/aivideo/ComfyUI/input/g01_original_20261107')/source.name
            target.write_bytes(source.read_bytes())
            p[node]={'class_type':'LoadImage','inputs':{'image':'g01_original_20261107/'+source.name}}
        p['6']['inputs']['first_frame']=['16',0];p['6']['inputs']['last_frame']=['17',0]
        p['6']['inputs']['prompt']=STYLE+'\n固定机位，夜晚工作台。只让右侧纸雕灯内的暖杏背光从暗到微亮，按末帧的克制亮度逐层透出。灯内建筑和纸层的形状不变，不能变成白天或日出。窗外一直是相同的深靛青雨夜，不允许有太阳、月亮或新物件。砚台保持已经倾倒的姿态，墨迹保持原位，桌面、椅子和录音机完全不动。不要推镜，不要切镜，不要重建场景。微小电流声、雨声，无人声、无音乐。'
    p['7']['inputs']['noise_seed'] += (take-1)*10000
    p['15']['inputs']['filename_prefix'] += f'_take{take}'
    return p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--shots',default='s02,s05');ap.add_argument('--take',type=int,default=1);args=ap.parse_args()
    (ROOT/'jobs').mkdir(parents=True,exist_ok=True);(ROOT/'sources').mkdir(exist_ok=True)
    for shot in SHOTS:
        if shot['id'] not in args.shots.split(',') or shot['kind']!='h3':continue
        sid=shot['id'] + (f'_take{args.take}' if args.take>1 else ''); record=ROOT/'jobs'/f'{sid}.json'; output=ROOT/'sources'/f'{sid}.mp4'
        if output.exists():print(sid,'already collected',flush=True);continue
        if record.exists():
            job=json.loads(record.read_text());pid=job.get('prompt_id')
            if not pid:raise RuntimeError(f'{sid}: unknown submission state; inspect manually')
        else:
            w=workflow(shot,args.take);(ROOT/'jobs'/f'{sid}_workflow.json').write_text(json.dumps(w,ensure_ascii=False,indent=2))
            job={'shot':sid,'status':'submitting','prompt_id':None,'model':'MiniMax H3 local int8','seed':w['7']['inputs']['noise_seed'],'media_origin':'newly_generated_this_run','started_unix':time.time()}
            record.write_text(json.dumps(job,indent=2))
            result=request('/prompt',{'prompt':w,'client_id':'paper-lantern-original-20261107'})
            if 'prompt_id' not in result:raise RuntimeError(result)
            pid=result['prompt_id'];job.update(prompt_id=pid,status='accepted');record.write_text(json.dumps(job,indent=2))
            print(sid,'accepted',pid,flush=True)
        while True:
            h=request('/history/'+pid)
            if pid in h:
                entry=h[pid];(ROOT/'jobs'/f'{sid}_history.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2))
                if entry['status']['status_str']!='success':
                    job['status']='failed';record.write_text(json.dumps(job,indent=2));raise RuntimeError(entry['status'])
                media=entry['outputs']['15']['images'][0]
                origin=Path('/home/xsl/aivideo/ComfyUI/output')/media['subfolder']/media['filename']
                output.write_bytes(origin.read_bytes())
                job.update(status='collected',output=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),metadata=media.get('metadata'),finished_unix=time.time())
                record.write_text(json.dumps(job,ensure_ascii=False,indent=2));print(sid,'collected',output.stat().st_size,flush=True);break
            print(sid,'rendering',int(time.time()-job['started_unix']),'seconds',flush=True);time.sleep(20)

if __name__=='__main__':main()
