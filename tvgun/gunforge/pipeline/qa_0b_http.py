"""Regression for the Android client's default HTTP control mode."""
import json
import socket
import time
import urllib.error
import urllib.request

from qa_0b import REPORT


def run(host='127.0.0.1'):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f'http://{host}:9000'

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=3) as reply:
            assert reply.status==200
            return json.load(reply)

    state = request('/state')
    assert state['ok'] and 'score' in state
    assert request('/start',{})['ok']
    assert request('/reload',{})['ok']
    assert request('/shot',{'x':960,'y':540})['ok']
    try:
        request('/shot',{'x':'invalid','y':540})
        raise AssertionError('Malformed shot should fail')
    except urllib.error.HTTPError as error:
        assert error.code==400
    # HttpURLConnection may split its headers and body across TCP packets.
    with socket.create_connection((host,9000),timeout=3) as sock:
        sock.sendall(b'POST /reload HTTP/1.1\r\nHost: game\r\nContent-Length: 2\r\n\r\n{')
        time.sleep(.05)
        sock.sendall(b'}')
        stream = sock.makefile('rb')
        status = stream.readline()
        assert b'200 OK' in status
        size = 0
        for line in iter(stream.readline,b'\r\n'):
            if line.lower().startswith(b'content-length:'):
                size = int(line.split(b':',1)[1])
        assert json.loads(stream.read(size))['ok']
    result = {'status':'pass','host':host,'cases':['state','start','reload','shot',
              'malformed_shot_rejected','fragmented_HTTP_body'],'phone_APK_replacement_required':False}
    (REPORT/'http_tests.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    run('192.168.3.28')
