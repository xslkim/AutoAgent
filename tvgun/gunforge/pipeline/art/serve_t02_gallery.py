"""Serve art review artifacts on the local loopback interface."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'gunforge/games/g01'
REPORT = GAME / 'reports/art/T02'
GALLERY = REPORT / 'gallery'


def artifact(path, task='T02'):
    """Use an explicit read-only allowlist rather than serving the workspace."""
    path = unquote(urlsplit(path).path)
    report = GAME / 'reports/art' / task
    gallery = report / 'gallery'
    fixed = {
        '/gallery/': gallery / 'index.html',
        '/bible/style.md': GAME / 'bible/style.md',
        '/docs/ART_TASKS_PAPER_LANTERN_CITY.md': ROOT / 'docs/ART_TASKS_PAPER_LANTERN_CITY.md',
    }
    for name in ('report.md', 'checks.json', 'manifest.json', 'review.yaml', 'contact_sheet.jpg'):
        fixed['/' + name] = report / name
    if task == 'T08':
        for name in ('memory.json', 'asset_checks.json', 'calls.json'):
            fixed['/' + name] = report / name
        fixed['/asset_pack/manifest.json'] = report / 'asset_pack/manifest.json'
    if path in fixed:
        return fixed[path]
    if path.startswith('/gallery/'):
        name = path.removeprefix('/gallery/')
        if name and Path(name).name == name and Path(name).suffix.lower() in {'.html', '.png', '.jpg', '.mp4'}:
            target = (gallery / name).resolve()
            if target.is_relative_to(gallery.resolve()):
                return target
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond()

    def do_HEAD(self):
        self.respond(head=True)

    def respond(self, head=False):
        if self.headers.get('Host') not in {
            f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'
        }:
            self.send_error(403)
            return
        if urlsplit(self.path).path == '/':
            self.send_response(302)
            self.send_header('Location', '/gallery/')
            self.end_headers()
            return
        target = artifact(self.path, self.server.task)
        if target is None or not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if target.suffix == '.yaml':
            mime = 'text/plain'
        if target.suffix == '.md':
            mime = 'text/plain'
        if mime.startswith('text/') or mime == 'application/json':
            mime += '; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if not head:
            self.wfile.write(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--task', choices=['T02','T03','T07','T08'], default='T02')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.task = args.task
    print(f'{args.task} review: http://127.0.0.1:{args.port}/gallery/', flush=True)
    server.serve_forever()
