"""Serve the built TVGun APK and its LAN download QR code."""
import argparse
import hashlib
import io
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import qrcode

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='LAN IPv4 address shown to the phone')
    parser.add_argument('--port', type=int, default=8769)
    args = parser.parse_args()
    apk = ROOT/'android/tvgun.apk'
    version_file = ROOT/'android/out/gen/com/tvgun/gun/Version.java'
    version = re.search(r'DESCRIBE = "([^"]+)"', version_file.read_text(encoding='utf-8')).group(1)
    data = apk.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    name = 'tvgun-' + re.sub(r'[^a-zA-Z0-9._-]', '_', version) + '.apk'
    download = f'http://{args.host}:{args.port}/{name}'
    qr = qrcode.make(download)
    buffer = io.BytesIO()
    qr.save(buffer, format='PNG')
    png = buffer.getvalue()
    output = ROOT/'out/apk-share'
    output.mkdir(parents=True, exist_ok=True)
    (output/'qr.png').write_bytes(png)
    page = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TVGun 手机安装</title><style>
body{{background:#151929;color:#eee4d6;font:18px/1.7 system-ui;margin:0}}
main{{max-width:620px;margin:40px auto;padding:0 24px}}
img{{display:block;width:min(320px,100%);height:auto;margin:24px auto}}
a{{color:#b8dfeb;overflow-wrap:anywhere}}
.button{{display:block;padding:14px;background:#375c67;color:white;border-radius:8px;text-align:center;text-decoration:none}}
small{{overflow-wrap:anywhere;color:#b9bdc8}}</style>
<main><h1>TVGun 手机安装</h1><p>手机与电脑连接同一局域网，扫描二维码下载 APK。</p>
<img src="/qr.png" alt="TVGun APK 下载二维码">
<p><a class="button" href="/{name}">下载 TVGun · {version}</a></p>
<p>下载完成后点开 APK 安装。如果手机询问权限，允许当前浏览器安装应用，再确认安装。</p>
<p>版本 {version} · {len(data)/1024:.1f} KB</p>
<small>SHA-256<br>{checksum}</small>
<p><a href="{download}">{download}</a></p></main></html>"""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_HEAD(self):
            self.respond(head=True)

        def respond(self, head=False):
            path = self.path.split('?',1)[0]
            if path in ('/','/index.html'):
                body, mime = page.encode('utf-8'), 'text/html; charset=utf-8'
            elif path == '/qr.png':
                body, mime = png, 'image/png'
            elif path == '/'+name:
                body, mime = data, 'application/vnd.android.package-archive'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            if path == '/'+name:
                self.send_header('Content-Disposition', f'attachment; filename="{name}"')
            self.end_headers()
            if not head:
                self.wfile.write(body)

    print(f'Install page: http://{args.host}:{args.port}/', flush=True)
    print(f'APK: {download}', flush=True)
    print(f'Version: {version}; SHA256: {checksum}', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
