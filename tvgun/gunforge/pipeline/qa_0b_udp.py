"""Exercise discovery, sequencing, loss/relock and reload over real UDP sockets."""
import json
import socket
import time

from qa_0b import Client, REPORT


def run():
    client = Client()
    client.call('freeze')
    if client.state()['state']['phase']=='continue':
        client.event('COIN')
    # Restart through the ordinary title/completion event route.
    if client.state()['state']['phase'] not in ('title','complete'):
        client.advance(100)
        if client.state()['state']['phase']=='continue':
            client.advance(21)
    client.call('mode',gun=True)
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1',0))
    sock.settimeout(3)
    sock.sendto(b'TVGUN_DISCOVER',('127.0.0.1',8001))
    discovery, _ = sock.recvfrom(128)
    assert discovery==b'TVGUN_HERE 9000'

    def send(text):
        sock.sendto(text.encode(),('127.0.0.1',9000))
        time.sleep(.065)
        client.call('step',frames=1)  # Consume queued network events at an explicit frozen tick.

    send('HELLO qa-session-0b')
    send('960,540,4,0')
    send('START')
    client.advance(3.5)
    sample = client.state()
    assert sample['gun'] and sample['state']['phase']=='playing'
    lamp = sample['targets']['lamp']
    send(f'{lamp[0]+72},{lamp[1]+72},4,1')
    shot = f'SHOT {lamp[0]+72},{lamp[1]+72},2'
    send(shot)
    after = client.state()['state']
    assert after['ammo']==5, after
    send(shot)
    assert client.state()['state']['ammo']==5
    send('LOST,4')
    send('100,200,4,3')
    client.advance(2.2)
    paused = client.state()['state']
    assert paused['paused']
    send('SHOT 1400,400,5')
    assert client.state()['state']['ammo']==5
    send('960,540,4,6')
    client.advance(.5)
    assert client.state()['state']['paused']
    send('960,540,4,7')
    client.advance(.6)
    assert not client.state()['state']['paused']
    send('SHOT 1400,400,3')
    assert client.state()['state']['ammo']==5
    send('SHOT -100,500,8')
    client.advance(.6)
    assert client.state()['state']['ammo']==6
    frame_seen = False
    sock.settimeout(.3)
    try:
        while True:
            payload, _ = sock.recvfrom(128)
            frame_seen |= payload==b'FRAME 24,48'
    except socket.timeout:
        pass
    assert frame_seen
    report = {'status':'pass','transport':'real local UDP 9000 / discovery 8001',
              'cases':['discovery','P5_FRAME','sequenced_coordinate_and_shot','duplicate_shot',
                       'LOST_and_late_coordinate','automatic_pause','relock_countdown',
                       'old_shot_cannot_cross_loss','offscreen_reload'],
              'actual_phone':'pending'}
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'udp_tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    client.call('mode',gun=False)
    sock.close()
    print(json.dumps(report))


if __name__=='__main__':
    run()
