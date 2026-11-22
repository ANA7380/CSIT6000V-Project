import io
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from deepseek_client import chat


class DeepSeekTests(unittest.TestCase):
    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-secret'})
    @patch('deepseek_client.urlopen')
    def test_truncation_metadata_reaches_agent_repair_policy(self, http):
        response = {'choices': [{'message': {'content': '{"answer":"cut'}, 'finish_reason': 'length'}]}
        http.return_value = io.BytesIO(json.dumps(response).encode())
        self.assertEqual(chat([])['choices'][0]['finish_reason'], 'length')

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-secret'})
    @patch('deepseek_client.urlopen')
    def test_agent_recovers_truncated_deepseek_reply_with_evidence(self, http):
        from chat_agent import ChatAgent
        def response(content, finish='stop'):
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': content},
                                                       'finish_reason': finish}]}).encode())
        http.side_effect = [
            response('{"tool":"ticker_metrics","arguments":{"ticker":"700"}}'),
            response('{"answer":"truncated explanation', 'length'),
            response('{"answer":"Verified result [E1]"}'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            agent = ChatAgent('https://api.deepseek.com/v1', Path(directory)/'audit.jsonl', call=chat)
            agent.ask('Metrics 0700.HK')
            self.assertEqual(agent.last_response['answer'], 'Verified result [E1]')
            self.assertEqual(agent.last_response['stats']['format_errors'], 1)
            self.assertFalse(agent.last_response['fallback'])
            self.assertFalse(any('truncated explanation' in m['content'] for m in agent.messages))
            self.assertNotIn('test-secret', agent.log.read_text())

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-secret'})
    @patch('deepseek_client.urlopen')
    def test_request_and_answer(self, http):
        http.return_value = io.BytesIO(json.dumps({'choices': [{'message': {'content': '{"answer":"hello"}'}}]}).encode())
        result = chat([{'role': 'user', 'content': 'Hello'}])
        request = http.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.deepseek.com/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')
        payload = json.loads(request.data)
        self.assertEqual(payload['thinking'], {'type': 'disabled'})
        self.assertNotIn('test-secret', request.data.decode())
        self.assertIn('hello', result['choices'][0]['message']['content'])

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': ''})
    def test_missing_key(self):
        with self.assertRaisesRegex(ValueError, 'DEEPSEEK_API_KEY'):
            chat([])

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-secret'})
    @patch('deepseek_client.urlopen', side_effect=HTTPError('url', 401, 'bad', {}, None))
    def test_auth_failure(self, http):
        with self.assertRaisesRegex(RuntimeError, '401'):
            chat([])

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-secret'})
    def test_reject_other_endpoint(self):
        with self.assertRaises(ValueError):
            chat([], 'https://example.com/v1')
