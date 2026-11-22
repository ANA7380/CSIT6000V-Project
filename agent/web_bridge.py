"""Local HTTP bridge for a running TACC chat job. Requires the configured tcloud CLI."""
import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


def transfer(*args, allow_missing=False):
    run = subprocess.run([os.environ.get('TCLOUD_BIN', 'tcloud'), *map(str, args)], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=60)
    output = run.stdout.replace(b'\0', b'').decode(errors='replace').lower()
    # A missing optional file is expected during polling. Never mask an access
    # failure just because the SDK printed a missing-file message as well.
    if any(marker in output for marker in ('permission denied', 'authentication failed')):
        raise RuntimeError('TACC transfer failed. Check tcloud access and the chat job log.')
    if allow_missing and ('no such file' in output or 'does not exist' in output):
        return False
    if run.returncode or any(marker in output for marker in
                             ('[tcloud error]', 'failed to', 'permission denied', 'rsync error')):
        raise RuntimeError('TACC transfer failed. Check tcloud access and the chat job log.')
    return True


class BridgeTelemetry:
    """Bounded per-request measurements and completed replies; no SDK credentials."""
    def __init__(self):
        self.lock = threading.RLock()
        self.turns = OrderedDict()
        self.completed = OrderedDict()

    def update(self, turn, **increments):
        with self.lock:
            record = self.turns.setdefault(turn, {'sdk_calls': 0, 'polls': 0,
                'upload_ms': 0.0, 'download_ms': 0.0, 'missing_files': 0})
            for key, value in increments.items():
                record[key] = record.get(key, 0) + value
            self.turns.move_to_end(turn)
            while len(self.turns) > 256:
                self.turns.popitem(last=False)
            return dict(record)

    def start(self, turn):
        with self.lock:
            self.update(turn)
            self.turns[turn]['started'] = time.perf_counter()

    def get_completed(self, turn):
        with self.lock:
            return self.completed.get(turn)

    def finish(self, turn, result):
        with self.lock:
            result = dict(result)
            record = dict(self.turns.get(turn, {}))
            started = record.pop('started', None)
            if started is not None:
                result['end_to_end_ms'] = (time.perf_counter()-started)*1000
                if isinstance(result.get('duration_ms'), (int, float)):
                    record['outside_agent_ms'] = max(0, result['end_to_end_ms']-result['duration_ms'])
            result['timings'] = dict(result.get('timings') or {}, bridge=record)
            # Preserve the original completed-turn latency when the UI checks it
            # again; do not launch another SDK subprocess for an immutable reply.
            self.completed[turn] = result
            self.completed.move_to_end(turn)
            while len(self.completed) > 16:
                self.completed.popitem(last=False)
            return result


class Bridge(BaseHTTPRequestHandler):
    _telemetry_init = threading.Lock()

    def telemetry(self):
        with self._telemetry_init:
            if not hasattr(self.server, 'bridge_telemetry'):
                self.server.bridge_telemetry = BridgeTelemetry()
            return self.server.bridge_telemetry

    def timed_transfer(self, turn, *args, **kwargs):
        started = time.perf_counter()
        missing = 0
        try:
            found = transfer(*args, **kwargs)
            missing = int(not found)
            return found
        finally:
            duration = (time.perf_counter()-started)*1000
            phases = {('upload', '.request'): 'request_upload_ms',
                      ('upload', '.ask'): 'commit_upload_ms',
                      ('download', '.status'): 'status_download_ms',
                      ('download', '.reply'): 'reply_download_ms'}
            increments = {args[0] + '_ms': duration}
            phase = phases.get((args[0], Path(args[1]).suffix))
            if phase:
                increments[phase] = duration
            self.telemetry().update(turn, sdk_calls=1, missing_files=missing, **increments)

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
        turn = match[1]
        telemetry = self.telemetry()
        cached = telemetry.get_completed(turn)
        if cached is not None:
            return self.respond(200, cached)
        poll = telemetry.update(turn, polls=1)['polls']
        try:
            with tempfile.TemporaryDirectory() as temp:
                reply = Path(temp) / (turn + '.reply')
                status = reply.with_suffix('.status')
                found = self.timed_transfer(turn, 'download', self.server.remote + status.name,
                                            status, allow_missing=True)
                data = json.loads(status.read_text(encoding='utf-8')) if found else {'event': 'queued'}
                if not isinstance(data, dict):
                    raise ValueError('Invalid worker status.')
                # New workers publish the final response in this atomic file.
                # Old bridges still use .reply, and old workers still work here.
                if data.get('event') == 'reply_ready' and isinstance(data.get('response'), dict):
                    return self.respond(200, telemetry.finish(turn, data['response']))
                terminal = data.get('event') in {'reply_ready', 'turn_complete', 'turn_error'}
                # Probe periodically even if a worker's progress file is stale,
                # e.g. the final status write failed after .reply was committed.
                if not found or terminal or poll % 5 == 0:
                    ok = self.timed_transfer(turn, 'download', self.server.remote + reply.name,
                                             reply, allow_missing=True)
                    if ok:
                        result = json.loads(reply.read_text(encoding='utf-8'))
                        if not isinstance(result, dict):
                            raise ValueError('Invalid worker reply.')
                        return self.respond(200, telemetry.finish(turn, result))
                self.respond(202, data)
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
            if not isinstance(session, str) or not re.fullmatch('[a-f0-9]{32}', session) or not isinstance(question, str) or not 0 < len(question.strip()) <= 8000:
                raise ValueError('Invalid conversation or question.')
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            return self.respond(400, {'error': str(exc)})
        try:
            turn = uuid4().hex
            self.telemetry().start(turn)
            with tempfile.TemporaryDirectory() as temp:
                payload = Path(temp) / (turn + '.request')
                payload.write_text(json.dumps({'question': question, 'session': session}), encoding='utf-8')
                self.timed_transfer(turn, 'upload', payload, self.server.remote)
                # Publish the commit marker only after payload upload completes.
                marker = Path(temp) / (turn + '.ask')
                marker.write_text(json.dumps({'protocol': 2, 'payload': payload.name}), encoding='utf-8')
                self.timed_transfer(turn, 'upload', marker, self.server.remote)
            self.respond(202, {'turn': turn})
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.respond(502, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=int, help='running stock-chat job ID')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--local-ui', action='store_true',
                        help='Use this checkout\'s chat.html, including timing details, with an older worker')
    args = parser.parse_args()
    remote = f'stock-chat/{args.job}/'
    with tempfile.TemporaryDirectory() as temp:
        connection = Path(temp) / 'connection.json'
        if transfer('download', f'stock-research/{args.job}/connection.json', connection, allow_missing=True):
            config = json.loads(connection.read_text(encoding='utf-8'))
            remote = config.get('remote', '')
            if not re.fullmatch(r'stock-chat/[A-Za-z0-9_-]{1,80}/', remote):
                raise ValueError('Invalid server connection manifest')
        if args.local_ui:
            html = Path(__file__).with_name('chat.html').read_bytes()
        else:
            page = Path(temp) / 'chat.html'
            transfer('download', remote + page.name, page)
            html = page.read_bytes()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Bridge) as server:
        server.address = f'127.0.0.1:{server.server_port}'
        server.started = {}
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
