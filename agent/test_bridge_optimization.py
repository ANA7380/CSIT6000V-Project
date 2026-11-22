"""HTTP-level coverage for SDK polling, commit ordering and old-worker recovery."""
import json
import shutil
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import web_bridge


class QuietBridge(web_bridge.Bridge):
    def log_message(self, *args):
        pass


@contextmanager
def harness():
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        calls = []
        def transfer(command, source, target, allow_missing=False):
            calls.append((command, Path(source).name))
            if command == 'upload':
                shutil.copyfile(source, folder/Path(source).name)
            else:
                source = folder/Path(source).name
                if allow_missing and not source.exists():
                    return False
                shutil.copyfile(source, target)
            return True
        with web_bridge.ThreadingHTTPServer(('127.0.0.1', 0), QuietBridge) as server:
            server.remote = 'stock-chat/test/'
            server.address = '127.0.0.1:%s' % server.server_port
            server.page = b'fixture'
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            conn = HTTPConnection(server.address, timeout=5)
            def post():
                conn.request('POST', '/ask', json.dumps({'session': 'a'*32, 'question': 'Metrics'}),
                    {'Content-Type': 'application/json', 'Origin': 'http://'+server.address})
                response = conn.getresponse()
                return response.status, json.load(response)
            def poll(turn):
                conn.request('GET', '/reply/'+turn)
                response = conn.getresponse()
                return response.status, json.load(response)
            def write(turn, suffix, value):
                (folder/(turn+suffix)).write_text(json.dumps(value))
            try:
                with patch.object(web_bridge, 'transfer', transfer):
                    yield SimpleNamespace(server=server, calls=calls, folder=folder,
                                          post=post, poll=poll, write=write)
            finally:
                conn.close(); server.shutdown(); thread.join(2)


class BridgeOptimizationTests(unittest.TestCase):
    def test_two_phase_upload_keeps_payload_before_marker(self):
        with harness() as h:
            status, body = h.post()
            self.assertEqual(status, 202)
            turn = body['turn']
            self.assertEqual(h.calls, [('upload', turn+'.request'), ('upload', turn+'.ask')])
            self.assertEqual(json.loads((h.folder/(turn+'.ask')).read_text()),
                             {'protocol': 2, 'payload': turn+'.request'})

    def test_pending_poll_downloads_only_status(self):
        with harness() as h:
            _, body = h.post(); turn = body['turn']
            h.write(turn, '.status', {'event': 'model_start'})
            before = len(h.calls)
            for _ in range(3):
                self.assertEqual(h.poll(turn), (202, {'event': 'model_start'}))
            self.assertEqual(h.calls[before:], [('download', turn+'.status')]*3)

    def test_completed_envelope_uses_one_download_and_reply_cache(self):
        with harness() as h:
            _, body = h.post(); turn = body['turn']
            result = {'answer': 'done', 'duration_ms': 0, 'evidence': [],
                      'timings': {'worker': {'session_save_ms': 2}}}
            h.write(turn, '.status', {'event': 'reply_ready', 'response': result})
            before = len(h.calls)
            status, reply = h.poll(turn)
            self.assertEqual(status, 200); self.assertEqual(reply['answer'], 'done')
            self.assertEqual(h.calls[before:], [('download', turn+'.status')])
            self.assertEqual(reply['timings']['bridge']['sdk_calls'], 3)
            phases = reply['timings']['bridge']
            self.assertAlmostEqual(phases['upload_ms'], phases['request_upload_ms']+phases['commit_upload_ms'])
            self.assertAlmostEqual(phases['download_ms'], phases['status_download_ms'])
            self.assertEqual(reply['timings']['worker']['session_save_ms'], 2)
            self.assertGreaterEqual(reply['end_to_end_ms'], reply['duration_ms'])
            self.assertEqual(h.poll(turn), (200, reply))
            self.assertEqual(len(h.calls)-before, 1)

    def test_old_worker_completion_fetches_legacy_reply(self):
        with harness() as h:
            turn = 'b'*32
            h.write(turn, '.status', {'event': 'turn_complete'})
            h.write(turn, '.reply', {'answer': 'legacy result'})
            status, reply = h.poll(turn)
            self.assertEqual(status, 200); self.assertEqual(reply['answer'], 'legacy result')
            self.assertEqual(h.calls, [('download', turn+'.status'), ('download', turn+'.reply')])

    def test_reply_without_any_status_is_recovered(self):
        with harness() as h:
            turn = 'b'*32
            h.write(turn, '.reply', {'answer': 'recovered'})
            self.assertEqual(h.poll(turn)[1]['answer'], 'recovered')

    def test_stale_running_status_periodically_probes_reply(self):
        with harness() as h:
            turn = 'b'*32
            h.write(turn, '.status', {'event': 'model_start'})
            h.write(turn, '.reply', {'answer': 'saved before status failed'})
            for _ in range(4):
                self.assertEqual(h.poll(turn)[0], 202)
            self.assertEqual(h.poll(turn)[0], 200)
            self.assertEqual(sum(name.endswith('.reply') for _, name in h.calls), 1)

    def test_legacy_error_reply_is_returned_as_completed_turn(self):
        with harness() as h:
            turn = 'b'*32
            h.write(turn, '.status', {'event': 'turn_error'})
            h.write(turn, '.reply', {'error': 'model unavailable'})
            status, reply = h.poll(turn)
            self.assertEqual(status, 200); self.assertEqual(reply['error'], 'model unavailable')

    def test_transfer_failure_does_not_cache_a_completed_reply(self):
        with harness() as h:
            turn = 'b'*32
            with patch.object(web_bridge, 'transfer', side_effect=RuntimeError('SDK failure')):
                self.assertEqual(h.poll(turn)[0], 502)
            h.write(turn, '.status', {'event': 'reply_ready', 'response': {'answer': 'retry worked'}})
            self.assertEqual(h.poll(turn)[1]['answer'], 'retry worked')

    def test_failed_payload_upload_does_not_publish_marker(self):
        with harness() as h:
            with patch.object(web_bridge, 'transfer', side_effect=RuntimeError('upload failed')) as call:
                self.assertEqual(h.post()[0], 502)
                self.assertEqual(call.call_count, 1)
            self.assertFalse(list(h.folder.glob('*.ask')))

    def test_optional_missing_file_does_not_mask_access_error(self):
        run = SimpleNamespace(returncode=1, stdout=b'permission denied; no such file')
        with patch.object(web_bridge.subprocess, 'run', return_value=run):
            with self.assertRaisesRegex(RuntimeError, 'TACC transfer failed'):
                web_bridge.transfer('download', 'remote', 'local', allow_missing=True)

    def test_optional_missing_file_remains_normal_polling(self):
        run = SimpleNamespace(returncode=23, stdout=b'No such file or directory; rsync error: code 23')
        with patch.object(web_bridge.subprocess, 'run', return_value=run):
            self.assertFalse(web_bridge.transfer('download', 'remote', 'local', allow_missing=True))

    def test_local_ui_switch_skips_remote_html_download(self):
        calls = []
        def transfer(command, source, target, **kwargs):
            calls.append(source)
            Path(target).write_text(json.dumps({'remote': 'stock-chat/existing/'}))
            return True
        server = MagicMock()
        server.__enter__.return_value = server
        with patch.object(web_bridge, 'transfer', transfer), \
             patch.object(web_bridge, 'ThreadingHTTPServer', return_value=server), \
             patch('sys.argv', ['web_bridge.py', '30934', '--local-ui']):
            web_bridge.main()
        self.assertEqual(calls, ['stock-research/30934/connection.json'])
        self.assertIn(b'Timing details', server.page)
        self.assertEqual(server.remote, 'stock-chat/existing/')


if __name__ == '__main__':
    unittest.main()
