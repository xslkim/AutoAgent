"""Rebuild the existing prototype tone family as WAV assets (no new art approval)."""
import hashlib,math,struct,wave
from compiler import ROOT
def ensure_cues():
 out={}
 for name,hz in {'shot':150,'hit':490,'lamp':660,'rescue':880,'reload':320,'hurt':100,'warning':230}.items():
  duration=.1 if name=='shot' else .22;rate=22050;pcm=bytearray()
  for i in range(int(rate*duration)):
   t=i/rate;envelope=math.exp(-t*20);sample=math.sin(t*hz*math.tau)*envelope*.4
   if name=='shot':sample+=math.sin(t*8713)*math.sin(t*5209)*envelope*.3
   pcm.extend(struct.pack('<h',int(max(-1,min(1,sample))*32767)))
  path=ROOT/'gunforge/framework/runtime/audio'/(name+'.wav');path.parent.mkdir(parents=True,exist_ok=True)
  with wave.open(str(path),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes(pcm)
  out[name]={'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':'audio'}
 return out
