import json
import tempfile
import unittest
from pathlib import Path
from chat_agent import ChatAgent, parse_action


class ChatTests(unittest.TestCase):
    def test_two_objects_recover_lookup_before_answer(self):
        broken = '{"tool":"list_tickers","arguments":{}}\n{"answer":"Premature answer","tool_calls":[{"name":"list_tickers","arguments":{}}]}'
        responses = iter([broken, '{"answer":"All tickers retrieved."}'])
        def fake(messages, base_url, **kwargs):
            if messages[-1]['content'].startswith('TOOL_RESULT'):
                result = json.loads(messages[-1]['content'].split('\n', 1)[1])
                self.assertEqual(len(result['result']), 30)
                self.assertIn('0700.HK', result['result'])
                self.assertEqual(json.loads(messages[-2]['content']), {'tool': 'list_tickers', 'arguments': {}})
            return {'choices': [{'message': {'content': next(responses)}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder)/'audit.jsonl', fake)
            self.assertEqual(agent.ask('list tickers all of them'), 'All tickers retrieved.')
            events = [json.loads(line) for line in agent.log.read_text().splitlines()]
            self.assertEqual(sum(e['event'] == 'tool_result' for e in events), 1)

    def test_format_error_is_not_tool_failure(self):
        responses = iter(['not JSON', '{"tool":"list_tickers","arguments":{}}', '{"answer":"Done"}'])
        def fake(messages, base_url, **kwargs):
            if messages[-1]['content'].startswith('MODEL_FORMAT_ERROR'):
                self.assertFalse(json.loads(messages[-1]['content'].split('\n', 1)[1])['tool_executed'])
            return {'choices': [{'message': {'content': next(responses)}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder)/'audit.jsonl', fake)
            self.assertEqual(agent.ask('list tickers'), 'Done')
            events = [json.loads(line) for line in agent.log.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(sum(e['event'] == 'model_format_error' for e in events), 1)
            self.assertEqual(sum(e['event'] == 'tool_result' for e in events), 1)

    def test_ambiguous_answers_rejected(self):
        for text in ['{"answer":"one"}\n{"answer":"two"}',
                     '{"tool":"list_tickers","arguments":{},"answer":"invented"}',
                     '{"tool":"shell","arguments":{}}', '[]']:
            with self.assertRaises(ValueError):
                parse_action(text)
        self.assertEqual(parse_action('```json\n{"answer":"OK"}\n```'), {'answer': 'OK'})

    def test_tool_roundtrip(self):
        actions = iter([
            {'tool': 'ticker_metrics', 'arguments': {'ticker': '700'}},
            {'answer': 'Revenue growth is 10.99% in the fixed snapshot.'},
        ])
        def fake_chat(messages, base_url, **kwargs):
            if len(messages) > 2:
                result = json.loads(messages[-1]['content'].split('\n', 1)[1])
                self.assertEqual(result['result']['symbol'], '0700.HK')
                self.assertIn('Revenue growth', result['result']['metrics'])
            return {'choices': [{'message': {'content': json.dumps(next(actions))}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', fake_chat)
            self.assertIn('10.99%', agent.ask('Show Tencent metrics'))
            self.assertIn('metric_calculation', agent.log.read_text(encoding='utf-8'))

    def test_invalid_tool_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl')
            for name, args in [('shell', {}), ('ticker_metrics', {'ticker': '700', 'window': True}),
                               ('ticker_metrics', {'ticker': 'AAPL'})]:
                with self.assertRaises(ValueError):
                    agent.dispatch(name, args)


if __name__ == '__main__':
    unittest.main()
