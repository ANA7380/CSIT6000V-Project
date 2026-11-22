"""Local browser UI with DeepSeek or Qwen; same worker, evidence and status protocol.

python3 local_web.py --provider deepseek
python3 local_web.py --provider qwen --base-url http://COMPUTE_NODE:8000/v1
"""
import argparse
import json
import os
import queue
import re
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from chat_agent import ChatAgent
from session_store import atomic_json
from web_bridge import Bridge
from web_worker import process


class LocalHandler(Bridge):
    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'Use the printed localhost URL.'})
        if self.path == '/':
            return self.respond(200, self.server.page, 'text/html; charset=utf-8')
        match = re.fullmatch(r'/reply/([a-f0-9]{32})', self.path)
        if not match:
            return self.respond(404, {})
        path = self.server.folder / (match[1] + '.reply')
        if not path.exists():
            status = path.with_suffix('.status')
            return self.respond(202, json.loads(status.read_text(encoding='utf-8')) if status.exists() else {'event': 'queued'})
        result = json.loads(path.read_text(encoding='utf-8'))
        started = self.server.started.get(match[1])
        if started is not None:
            result['end_to_end_ms'] = (time.perf_counter()-started)*1000
        return self.respond(200, result)

    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin') != 'http://' + self.server.address
                or self.headers.get_content_type() != 'application/json'):
            return self.respond(403, {'error': 'Use the printed localhost URL.'})
        if self.path != '/ask':
            return self.respond(404, {})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 100000:
                raise ValueError('Invalid message size.')
            request = json.loads(self.rfile.read(length))
            session, question = request['session'], request['question']
            if not isinstance(session, str) or not re.fullmatch('[a-f0-9]{32}', session):
                raise ValueError('Invalid conversation ID.')
            if not isinstance(question, str) or not 0 < len(question.strip()) <= 8000:
                raise ValueError('Enter a question of up to 8000 characters.')
            turn = uuid4().hex
            path = self.server.folder / (turn + '.ask')
            self.server.started[turn] = time.perf_counter()
            atomic_json(path, {'session': session, 'question': question})
            atomic_json(path.with_suffix('.status'), {'event': 'queued'})
            self.server.queue.put(path)
            self.respond(202, {'turn': turn})
        except (KeyError, TypeError, ValueError) as exc:
            self.respond(400, {'error': str(exc)})


def make_server(port, folder, factory, base_url):
    folder.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', port), LocalHandler)
    server.address = f'127.0.0.1:{server.server_port}'
    server.page = Path(__file__).with_name('chat.html').read_bytes()
    server.folder, server.started, server.queue = folder, {}, queue.Queue()
    sessions = {}
    def work():
        while True:
            path = server.queue.get()
            try:
                if path is None:
                    return
                process(path, sessions, base_url, factory)
            finally:
                server.queue.task_done()
    server.worker = threading.Thread(target=work, daemon=True)
    server.worker.start()
    # Recover interrupted requests; existing replies are idempotent.
    for path in sorted(folder.glob('*.ask')):
        server.queue.put(path)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['deepseek', 'qwen'], default='deepseek')
    parser.add_argument('--base-url', default=os.environ.get('QWEN_BASE_URL'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / 'logs' / 'web')
    args = parser.parse_args()
    if args.provider == 'deepseek':
        from deepseek_client import chat, BASE_URL
        if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
            parser.error('Set DEEPSEEK_API_KEY in the environment.')
        url = BASE_URL
    else:
        from qwen_client import chat, normalize_base_url
        url = normalize_base_url(args.base_url or Path(__file__).with_name('server-url.txt').read_text().strip())
    factory = lambda base, log: ChatAgent(base, log, call=chat)
    server = make_server(args.port, args.data_dir, factory, url)
    print(f'Open http://{server.address}/ ({args.provider}). Conversations persist in {args.data_dir}.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.queue.put(None)


if __name__ == '__main__':
    main()
