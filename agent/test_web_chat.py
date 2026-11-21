import json
import shutil
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import web_bridge
import web_worker
from chat_agent import ChatAgent


class WebChatTest(unittest.TestCase):
    def test_follow_up_through_bridge_and_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            sessions = {}

            def transfer(command, source, dest, allow_missing=False):
                if command == 'upload':
                    shutil.copy(source, directory)
                else:
                    source = directory / Path(source).name
                    if allow_missing and not source.exists():
                        return False
                    shutil.copy(source, dest)
                return True

            def model(messages, *args, **kwargs):
                question = messages[-1]['content']
                if question == 'List the tickers':
                    action = {'tool': 'list_tickers', 'arguments': {}}
                elif question.startswith('TOOL_RESULT'):
                    self.assertIn('0700.HK', json.loads(question.split('\n', 1)[1])['result'])
                    action = {'answer': 'Includes Tencent. [E1]'}
                else:
                    self.assertIn('List the tickers', [m['content'] for m in messages])
                    action = {'answer': '0700.HK'}
                return {'choices': [{'message': {'content': json.dumps(action)}}]}

            with web_bridge.ThreadingHTTPServer(('127.0.0.1', 0), web_bridge.Bridge) as server:
                server.remote = 'stock-chat/123/'
                server.address = f'127.0.0.1:{server.server_port}'
                server.page = Path(__file__).with_name('chat.html').read_bytes()
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self.addCleanup(thread.join, 2)
                conn = HTTPConnection(server.address)
                try:
                    conn.request('GET', '/')
                    self.assertIn(b'Research with evidence', conn.getresponse().read())
                    with patch.object(web_bridge, 'transfer', transfer), patch.object(
                        web_worker, 'ChatAgent', lambda url, log: ChatAgent(url, log, model)
                    ):
                        for question, answer in [('List the tickers', 'Includes Tencent. [E1]'),
                                                 ('Which ticker was that?', '0700.HK')]:
                            conn.request('POST', '/ask', json.dumps({'session': 'a' * 32, 'question': question}),
                                         {'Content-Type': 'application/json', 'Origin': 'http://' + server.address})
                            turn = json.load(conn.getresponse())['turn']
                            conn.request('GET', '/reply/' + turn)
                            response = conn.getresponse()
                            self.assertEqual(response.status, 202)
                            response.read()
                            web_worker.process(directory / (turn + '.ask'), sessions, 'http://localhost:8000/v1')
                            conn.request('GET', '/reply/' + turn)
                            reply = json.load(conn.getresponse())
                            self.assertEqual(reply['explanation'], answer)
                            self.assertIn('evidence', reply)
                            self.assertTrue(reply['answer'].startswith(answer))
                finally:
                    conn.close()
                    server.shutdown()
