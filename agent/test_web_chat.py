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
                    action = {'answer': 'Includes Tencent.'}
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
                    self.assertIn(b'HK Tech research chat', conn.getresponse().read())
                    with patch.object(web_bridge, 'transfer', transfer), patch.object(
                        web_worker, 'ChatAgent', lambda url, log: ChatAgent(url, log, model)
                    ):
                        for question, answer in [('List the tickers', 'Includes Tencent.'),
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
                            self.assertEqual(json.load(conn.getresponse()), {'answer': answer})
                finally:
                    conn.close()
                    server.shutdown()

    def test_local_server_returns_answer_and_chart(self):
        import time
        import web_local

        def model(messages, *args, **kwargs):
            last = messages[-1]['content']
            action = ({'answer': 'Chart saved.'} if last.startswith('TOOL_RESULT')
                      else {'tool': 'price_chart', 'arguments': {'ticker': '0700.HK', 'window': 30}})
            return {'choices': [{'message': {'content': json.dumps(action)}}]}

        with tempfile.TemporaryDirectory() as temp, web_local.build(
                'deepseek', 'http://localhost:8000/v1', temp, 0, call=model) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join, 2)
            conn = HTTPConnection(server.address)
            try:
                conn.request('GET', '/')
                page = conn.getresponse().read()
                self.assertIn(b'DeepSeek', page)
                self.assertNotIn(b'Qwen', page)
                conn.request('POST', '/ask', json.dumps({'session': 'b' * 32, 'question': 'Chart Tencent'}),
                             {'Content-Type': 'application/json', 'Origin': 'http://' + server.address})
                turn = json.load(conn.getresponse())['turn']
                for _ in range(100):
                    conn.request('GET', '/reply/' + turn)
                    response = conn.getresponse()
                    data = json.load(response)
                    if response.status == 200:
                        break
                    time.sleep(0.05)
                self.assertEqual(data['answer'], 'Chart saved.')
                self.assertEqual(len(data['charts']), 1)
                self.assertTrue(data['charts'][0].startswith('<svg'))
            finally:
                conn.close()
                server.shutdown()
