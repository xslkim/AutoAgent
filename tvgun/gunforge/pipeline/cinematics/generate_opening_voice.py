"""Design a new fictional grandpa voice, then condition every line on that new voice."""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from opening_plan import ROOT, LINES, VOICE_STYLE

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'

def main():
    # H3 and TTS share one GPU. Wait for our required collected clips before loading speech.
    needed=['s02_take2','s04_take2','s05_take2','s06_take2','s07_take2','s08','s09']
    until=time.time()+7200
    while not all((ROOT/'sources'/f'{x}.mp4').exists() for x in needed):
        if time.time()>until:raise RuntimeError('Required CG clips did not finish; no GPU changes made')
        print('Voice waiting for H3 clips',flush=True);time.sleep(30)
    def api(path,body=None):
        req=urllib.request.Request('http://127.0.0.1:8189'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as r:
            raw=r.read()
            return json.loads(raw) if raw else {}
    q=api('/queue')
    if q['queue_running'] or q['queue_pending']:raise RuntimeError('GPU busy with another queue; retry after it is idle')
    api('/free',{'unload_models':True,'free_memory':True})
    time.sleep(2)
    import random
    import numpy as np
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM
    modeldir='/home/xsl/models/VoxCPM2'
    model=VoxCPM(voxcpm_model_path=modeldir,enable_denoiser=False,optimize=False)
    sys.path.insert(0,modeldir)
    from tokenization_voxcpm2 import VoxCPM2Tokenizer
    tokenizer=VoxCPM2Tokenizer.from_pretrained(modeldir)
    model.tts_model.text_tokenizer=tokenizer.encode
    out=ROOT/'audio';out.mkdir(exist_ok=True)
    def generate(text,seed,reference=None):
        random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
        audio=model.generate(text=f'({VOICE_STYLE}){text}',reference_wav_path=reference,
            cfg_value=2.0,inference_timesteps=12,normalize=False,denoise=False,retry_badcase=True)
        return np.asarray(audio,dtype=np.float32)
    ref=out/'grandpa_original_design.wav'
    design_text='听见了吗？下雨的时候，老城就是这个声儿。从前啊，夜市一开灯，谁家的窗户都舍不得关。'
    if not ref.exists():
        print('Designing original grandpa voice',flush=True)
        audio=generate(design_text,202611071)
        sf.write(str(ref),audio,48000,subtype='PCM_16')
    data=[]
    for i,line in enumerate(LINES):
        target=out/f'voice_{i+1:02}.wav'
        if not target.exists():
            print('Synthesizing line',i+1,line['text'],flush=True)
            audio=generate(line['text'],2026110710+i,str(ref))
            sf.write(str(target),audio,48000,subtype='PCM_16')
        info=sf.info(str(target));data.append({**line,'file':target.name,'raw_duration':info.duration})
    (out/'voice_manifest.json').write_text(json.dumps({'model':'VoxCPM2 local','origin':'new fictional voice designed from text this run; no preexisting reference audio','style':VOICE_STYLE,'reference_text':design_text,'lines':data},ensure_ascii=False,indent=2))
    print('VOICE COMPLETE',flush=True)

if __name__=='__main__':main()
