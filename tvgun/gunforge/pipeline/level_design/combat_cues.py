"""Deterministic prototype paper/ink combat sounds, regenerated from this source."""
import math,struct,wave,hashlib
from compiler import ROOT
def ensure_combat_cues():
 durations={'shot':.10,'hit':.15,'weak':.22,'purify':.38,'windup':.65,'attack':.32,'hurt':.42,'lamp':.72,'reload':.45,'empty':.09,'intercept':.25,'bell':.48}
 out={};rate=22050
 for index,(name,duration) in enumerate(durations.items()):
  values=[];state=12345+index*197;low=0.0
  for i in range(int(rate*duration)):
   t=i/rate;u=t/duration;state=(1664525*state+1013904223)&0xffffffff;noise=state/2147483648-1;low=low*.82+noise*.18
   if name=='shot':sample=(math.sin(math.tau*(240*t-500*t*t))*.55+noise*.45)*math.exp(-t*42)
   elif name=='hit':sample=(math.sin(math.tau*(470*t-700*t*t))*.55+noise*.4)*math.exp(-t*24)
   elif name=='weak':sample=(math.sin(math.tau*880*t)+.35*math.sin(math.tau*1320*t))*math.exp(-t*16)
   elif name in ['purify','lamp']:sample=(math.sin(math.tau*660*t)+.45*math.sin(math.tau*990*t)+.25*math.sin(math.tau*1320*t))*math.exp(-t*(7 if name=='lamp' else 11))
   elif name=='windup':sample=(low*2+math.sin(math.tau*(100*t+75*t*t))*.25)*math.sin(math.pi*u)**.7
   elif name=='attack':sample=(low*3+math.sin(math.tau*(180*t-150*t*t))*.25)*math.sin(math.pi*u)
   elif name=='hurt':sample=(math.sin(math.tau*(85*t-50*t*t))*.7+low*1.3)*math.exp(-t*10)
   elif name=='reload':
    sample=sum((noise*.4+math.sin(math.tau*420*t)*.3)*math.exp(-(t-start)*60) for start in [0,.15,.31] if t>=start)
   elif name=='empty':sample=(noise*.35+math.sin(math.tau*180*t)*.3)*math.exp(-t*65)
   elif name=='bell':
    ring=t if t<.16 else t-.16
    sample=(math.sin(math.tau*1070*ring)+.32*math.sin(math.tau*1689*ring))*math.exp(-ring*22)*min(1,ring/.004)
   else:sample=(math.sin(math.tau*(720*t+900*t*t))*.6+noise*.2)*math.exp(-t*16)
   values.append(sample*min(1,t/.002))
  gain=.45/max(max(abs(value) for value in values),.001)
  pcm=b''.join(struct.pack('<h',int(max(-1,min(1,value*gain))*32767)) for value in values)
  path=ROOT/'gunforge/level_design/generated/audio'/('combat_'+name+'.wav');path.parent.mkdir(parents=True,exist_ok=True)
  with wave.open(str(path),'wb') as file:file.setnchannels(1);file.setsampwidth(2);file.setframerate(rate);file.writeframes(pcm)
  out[name]={'resource':{'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':'audio'},'duration_ms':round(duration*1000)}
 return out
