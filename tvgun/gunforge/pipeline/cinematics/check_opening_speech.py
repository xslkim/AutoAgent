"""Read back newly synthesized speech with installed local Whisper; no downloads."""
import json
import re
import time
import unicodedata
from pathlib import Path
from opening_plan import ROOT

def main():
    deadline=time.time()+7200
    while not (ROOT/'audio/voice_manifest.json').exists():
        if time.time()>deadline:raise RuntimeError('No completed voice manifest')
        time.sleep(30)
    import torch
    torch.set_num_threads(4)
    import whisper
    model=whisper.load_model('small',device='cpu',download_root='/home/xsl/.cache/whisper')
    manifest=json.loads((ROOT/'audio/voice_manifest.json').read_text())
    data=[]
    for i,line in enumerate(manifest['lines']):
        r=model.transcribe(str(ROOT/'audio'/line['file']),language='zh',fp16=False,verbose=False,condition_on_previous_text=False)
        data.append({'line':i+1,'expected':line['text'],'recognized':r['text'],'segments':r['segments']})
        print(i+1,r['text'],flush=True)
    (ROOT/'qa/voice_readback.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print('Speech readback complete',flush=True)

if __name__=='__main__':main()
