"""Local HTTP bridge for a running TACC chat job. Requires the configured tcloud CLI."""
import argparse
import json
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


def transfer(*args, allow_missing=False):
    run = subprocess.run(['tcloud', *map(str, args)], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=60)
    output = run.stdout.replace(b'\0', b'').decode(errors='replace').lower()
    if allow_missing and ('no such file' in output or 'does not exist' in output):
        return False
    if run.returncode or any(marker in output for marker in
                             ('[tcloud error]', 'failed to', 'permission denied', 'rsync error')):
        raise RuntimeError('TACC transfer failed. Check tcloud access and the chat job log.')
    return True


class Bridge(BaseHTTPRequestHandler):
    def respond(self, status, data, mime='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') == self.server.address

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'Open the printed localhost URL.'})
        if self.path == '/':
            return self.respond(200, self.server.page, 'text/html; charset=utf-8')
        match = re.fullmatch(r'/reply/([a-f0-9]{32})', self.path)
        if not match:
            return self.respond(404, {})
        try:
            with tempfile.TemporaryDirectory() as temp:
                reply = Path(temp) / (match[1] + '.reply')
                ok = transfer('download', self.server.remote + reply.name, reply, allow_missing=True)
                if not ok:
                    return self.respond(202, {})
                result = json.loads(reply.read_text(encoding='utf-8'))
            self.respond(200, result)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.respond(502, {'error': str(exc)})

    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin') != 'http://' + self.server.address
                or self.headers.get_content_type() != 'application/json'):
            return self.respond(403, {'error': 'Open the printed localhost URL.'})
        if self.path != '/ask':
            return self.respond(404, {})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 100000:
                raise ValueError('Invalid message size.')
            request = json.loads(self.rfile.read(length))
            question, session = request['question'], request['session']
            if not re.fullmatch('[a-f0-9]{32}', session) or not 0 < len(question.strip()) <= 8000:
                raise ValueError('Invalid conversation or question.')
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            return self.respond(400, {'error': str(exc)})
        try:
            turn = uuid4().hex
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / (turn + '.ask')
                path.write_text(json.dumps({'question': question, 'session': session}), encoding='utf-8')
                transfer('upload', path, self.server.remote)
            self.respond(202, {'turn': turn})
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.respond(502, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=int, help='running stock-chat job ID')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    remote = f'stock-chat/{args.job}/'
    with tempfile.TemporaryDirectory() as temp:
        page = Path(temp) / 'chat.html'
        transfer('download', remote + page.name, page)
        html = page.read_bytes()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Bridge) as server:
        server.address = f'127.0.0.1:{server.server_port}'
        server.remote = remote
        server.page = html
        print(f'Open http://{server.address}/ in your browser. Press Ctrl+C to stop.', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f'{exc} Confirm the chat job log says "Chat ready" and tcloud is on PATH.')
