"""Finish collected original shots while GPU continues to generate remaining clips."""
import subprocess
import sys
import time
from pathlib import Path
from opening_plan import ROOT, SHOTS
from build_opening import TAKES

BUILD=Path(__file__).with_name('build_opening.py')
deadline=time.time()+7200
for shot in SHOTS:
    if shot['kind']=='h3':
        sid=shot['id'];take=TAKES[sid];name=sid+(f'_take{take}' if take>1 else '')+'.mp4'
        while not (ROOT/'sources'/name).exists():
            if time.time()>deadline:raise RuntimeError('Timed out waiting for '+name)
            print('Picture waiting for',name,flush=True);time.sleep(20)
    subprocess.run([sys.executable,'-u',str(BUILD),'shots','--only',shot['id']],check=True)
while not (ROOT/'audio/voice_manifest.json').exists():
    if time.time()>deadline:raise RuntimeError('Timed out waiting for narration')
    print('Picture complete; waiting for original narration',flush=True);time.sleep(20)
for step in ['audio','video','audit']:
    subprocess.run([sys.executable,'-u',str(BUILD),step],check=True)
print('OPENING COMPLETE',flush=True)
