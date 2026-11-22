"""Count SDK operations through the actual HTTP handlers using local file fixtures.

No TACC, model, network data or artificial latency. This measures calls, not speed.
Usage: python3 scripts/benchmark_bridge_optimization.py --baseline /path/to/original
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch


def probe(root, envelope):
    sys.path.insert(0, str(root/'agent'))
    import web_bridge
    scenarios = []
    class QuietBridge(web_bridge.Bridge):
        def log_message(self, *args):
            pass
    for pending in (3, 8):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); calls = []
            def transfer(command, source, target, allow_missing=False):
                calls.append((command, Path(source).suffix))
                if command == 'upload':
                    shutil.copyfile(source, folder/Path(source).name)
                else:
                    source = folder/Path(source).name
                    if allow_missing and not source.exists():
                        return False
                    shutil.copyfile(source, target)
                return True
            with web_bridge.ThreadingHTTPServer(('127.0.0.1', 0), QuietBridge) as server:
                server.remote = 'stock-chat/benchmark/'
                server.address = '127.0.0.1:%s' % server.server_port
                server.started = {}; server.page = b'fixture'
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                conn = HTTPConnection(server.address, timeout=5)
                try:
                    with patch.object(web_bridge, 'transfer', transfer):
                        conn.request('POST', '/ask', json.dumps({'session': 'a'*32, 'question': 'Metrics'}),
                            {'Content-Type': 'application/json', 'Origin': 'http://'+server.address})
                        response = conn.getresponse(); assert response.status == 202
                        turn = json.load(response)['turn']
                        (folder/(turn+'.status')).write_text(json.dumps({'event': 'model_start'}))
                        for _ in range(pending):
                            conn.request('GET', '/reply/'+turn); response = conn.getresponse()
                            assert response.status == 202; response.read()
                        payload = {'answer': 'The same completed response', 'explanation': 'The same completed response',
                                   'evidence': [], 'duration_ms': 0}
                        (folder/(turn+'.reply')).write_text(json.dumps(payload))
                        terminal = {'event': 'reply_ready', 'response': payload} if envelope else {'event': 'turn_complete'}
                        (folder/(turn+'.status')).write_text(json.dumps(terminal))
                        conn.request('GET', '/reply/'+turn); response = conn.getresponse()
                        assert response.status == 200; result = json.load(response)
                        assert all(result[key] == payload[key] for key in payload)
                        total = len(calls)
                        conn.request('GET', '/reply/'+turn); response = conn.getresponse()
                        assert response.status == 200; response.read()
                        scenarios.append({'pending_polls': pending, 'sdk_calls_to_first_result': total,
                            'sdk_calls_for_completed_recheck': len(calls)-total,
                            'uploads': sum(command == 'upload' for command, _ in calls),
                            'status_downloads': sum(suffix == '.status' for command, suffix in calls if command == 'download'),
                            'reply_downloads': sum(suffix == '.reply' for command, suffix in calls if command == 'download'),
                            'same_answer_and_evidence': True})
                finally:
                    conn.close(); server.shutdown(); thread.join(2)
    return scenarios


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--output', type=Path, default=Path('docs/validation/runtime-review/bridge-benchmark.json'))
    p.add_argument('--probe', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--envelope', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.probe:
        print(json.dumps(probe(args.probe.resolve(), args.envelope))); return
    if not args.baseline or not (args.baseline/'agent/web_bridge.py').is_file():
        p.error('--baseline must name the extracted input repository')
    script = str(Path(__file__).resolve())
    def run(root, envelope=False):
        command = [sys.executable, script, '--probe', str(root.resolve())]
        if envelope: command.append('--envelope')
        return json.loads(subprocess.check_output(command, text=True))
    result = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'offline-http-sdk-fixture',
              'notice': 'SDK calls are local file-copy fixtures. No claim about TACC latency, bandwidth or live model behavior.',
              'baseline': run(args.baseline), 'optimized': run(Path(__file__).resolve().parents[1], True)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
