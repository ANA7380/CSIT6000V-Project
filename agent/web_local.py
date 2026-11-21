"""Local browser chat: the same page as the TACC bridge, with the agent running on this machine.

    python web_local.py                       # DeepSeek; needs DEEPSEEK_API_KEY
    python web_local.py --provider qwen --base-url http://HOST:8000/v1   # inside TACC only
"""
import argparse
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from agent import ROOT
from chat_agent import ChatAgent


class Local(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, data, mime='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') in self.server.hosts

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'Open the printed localhost URL.'})
        if self.path == '/':
            return self.respond(200, self.server.page, 'text/html; charset=utf-8')
        match = re.fullmatch(r'/reply/([a-f0-9]{32})', self.path)
        if not match or match[1] not in self.server.turns:
            return self.respond(404, {})
        result = self.server.turns[match[1]]
        if result is None:
            return self.respond(202, {})
        del self.server.turns[match[1]]
        self.respond(200, result)

    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin') != 'http://' + str(self.headers.get('Host'))
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
        turn = uuid4().hex
        self.server.turns[turn] = None
        threading.Thread(target=self.server.answer, args=(turn, session, question), daemon=True).start()
        self.respond(202, {'turn': turn})


def build(provider, base_url, log_dir, port, call=None):
    """Create the server; `call` replaces the model transport in tests."""
    if call is None and provider == 'deepseek':
        from deepseek_client import chat as call, BASE_URL as base_url
        if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
            raise ValueError('Set DEEPSEEK_API_KEY first.')
    elif call is None:
        from qwen_client import chat as call
        base_url = base_url or (ROOT / 'server-url.txt').read_text(encoding='utf-8-sig')
    label = 'DeepSeek' if provider == 'deepseek' else 'Qwen'
    page = (ROOT / 'chat.html').read_text(encoding='utf-8')
    page = page.replace('Qwen', label).replace('Sending to TACC…', 'Sending…')
    server = ThreadingHTTPServer(('127.0.0.1', port), Local)
    server.address = f'127.0.0.1:{server.server_port}'
    server.hosts = {server.address, f'localhost:{server.server_port}'}  # loopback names only
    server.page = page.encode('utf-8')
    server.turns, sessions, locks = {}, {}, {}

    def answer(turn, session, question):
        # One conversation answers one question at a time; other conversations are independent.
        with locks.setdefault(session, threading.Lock()):
            try:
                if session not in sessions:
                    sessions[session] = ChatAgent(base_url, Path(log_dir) / (session + '.jsonl'), call=call)
                agent = sessions[session]
                text = agent.ask(question)
                charts = [Path(path).read_text(encoding='utf-8') for path in agent.charts]
                server.turns[turn] = {'answer': text, 'charts': charts}
            except Exception as exc:
                server.turns[turn] = {'error': str(exc)}

    server.answer = answer
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--provider', choices=['deepseek', 'qwen'], default='deepseek')
    parser.add_argument('--base-url', default=os.environ.get('QWEN_BASE_URL'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--log-dir', type=Path, default=ROOT / 'logs' / 'web')
    args = parser.parse_args()
    with build(args.provider, args.base_url, args.log_dir, args.port) as server:
        print(f'Open http://{server.address}/ in your browser. Press Ctrl+C to stop.', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f'Error: {exc}')
