"""Drive the running first station through the engine's local debug input API."""
import argparse
import json
import socket
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT/'gunforge/games/g01/reports/0B'


class Client:
    def __init__(self, port=19010):
        self.sock = socket.create_connection(('127.0.0.1',port),timeout=8)
        self.stream = self.sock.makefile('rwb')

    def call(self, op, **data):
        self.stream.write((json.dumps({'op':op,**data})+'\n').encode())
        self.stream.flush()
        result = json.loads(self.stream.readline())
        if 'error' in result:
            raise ValueError(result)
        return result

    def state(self):
        return self.call('state')

    def advance(self, seconds):
        frames = round(seconds*60)
        while frames:
            count = min(frames,600)
            self.call('step',frames=count)
            frames -= count

    def event(self, event, point=None):
        data = {'event':event}
        if point:
            data.update(x=point[0]+72,y=point[1]+72)
        return self.call('input',**data)

    def shoot(self, target):
        snapshot = self.state()
        point = snapshot['targets'][target]
        return self.event('SHOT',point)

    def capture(self, name):
        path = REPORT/(name+'.png')
        previous = path.stat().st_mtime_ns if path.is_file() else None
        self.call('capture',path=str(path))
        for _ in range(40):
            if path.is_file() and path.stat().st_mtime_ns!=previous:
                return
            time.sleep(.05)
        raise RuntimeError('Capture timed out')


def run():
    REPORT.mkdir(parents=True,exist_ok=True)
    client = Client()
    client.call('freeze')
    client.call('mode',gun=False)
    phase = client.state()['state']['phase']
    if phase not in ('title','complete'):
        client.advance(100)
        if client.state()['state']['phase']=='continue':
            client.advance(21)
    client.event('START')
    client.advance(3.5)
    hard = client.shoot('crow_0')['state']
    assert hard['enemies'][0]['status']=='alive' and hard['ammo']==5
    client.advance(.2)
    client.shoot('lamp')
    client.advance(.65)
    lit = client.state()
    assert lit['state']['lamp']>=.99
    client.capture('first_station_lit')
    hit = client.shoot('crow_0')['state']
    assert hit['enemies'][0]['status']=='defeated',hit
    client.advance(.3)
    saved = client.shoot('resident_ink')['state']
    assert saved['rescued'], saved
    client.advance(.3)
    client.capture('resident_rescued')
    proof = {'hardened_enemy_rejects_shot':True,'lamp_then_crow':True,'alpha_rescue':True,'waves':[]}
    while client.state()['state']['phase']!='complete':
        snapshot = client.state()
        state = snapshot['state']
        if state['phase']=='continue':
            raise AssertionError('Bot died unexpectedly')
        if state['phase']=='playing':
            targets = snapshot['targets']
            if state['ammo']<=1:
                client.event('RELOAD')
                client.advance(.6)
                continue
            threats = [k for k in targets if k.startswith('crow_') and state['enemies'][int(k[5:])]['status']=='alive']
            if threats:
                if state['lamp']<.9:
                    client.shoot('lamp')
                    client.advance(.7)
                client.advance(.25)
                client.shoot(threats[0])
                client.advance(.2)
            elif 'resident_ink' in targets and not state['rescued']:
                client.shoot('resident_ink')
                client.advance(.2)
            elif 'pickup' in targets:
                client.shoot('pickup')
                client.advance(.2)
            else:
                client.advance(.5)
        else:
            client.advance(.5)
        if len(proof['waves'])<=state['wave']:
            proof['waves'].append(state['wave'])
        if state['total']>100:
            raise AssertionError('Station did not finish')
    done = client.state()
    assert done['state']['lives']==5 and done['state']['wave']==2
    client.capture('station_complete')
    proof['completion'] = done
    client.event('START')
    # A miss-only run must die; COIN restores this same wave.
    for _ in range(180):
        state = client.state()['state']
        if state['phase']=='continue':
            break
        client.advance(.5)
    assert state['phase']=='continue'
    wave = state['wave']
    resumed = client.event('COIN')['state']
    assert resumed['lives']==5 and resumed['ammo']==6 and resumed['score']==0 and resumed['wave']==wave
    proof['death_continue_same_wave'] = True
    (REPORT/'engine_bot.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'lives':done['state']['lives'],'score':done['state']['score'],
                      'duration':done['state']['total'],'wave_count':len(proof['waves'])}))
    client.event('START')


if __name__=='__main__':
    run()
