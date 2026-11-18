import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from deepseek_client import chat


class DeepSeekTests(unittest.TestCase):
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
