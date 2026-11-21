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

    def test_timings_and_turn_summary_logged(self):
        responses = iter(['{"tool":"list_tickers","arguments":{}}', '{"answer":"Done"}'])
        def fake(messages, base_url, **kwargs):
            return {'choices': [{'message': {'content': next(responses)}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', fake)
            agent.ask('list tickers')
            events = [json.loads(line) for line in agent.log.read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all('time' in e for e in events))
            for kind in ('model', 'tool_result'):
                self.assertTrue(all(e['seconds'] >= 0 for e in events if e['event'] == kind))
            turn = events[-1]
            self.assertEqual((turn['event'], turn['status'], turn['model_calls'], turn['tool_calls']), ('turn', 'ok', 2, 1))
            self.assertGreaterEqual(turn['seconds'], turn['model_seconds'])

    def test_service_error_logged_and_turn_rolled_back(self):
        def broken(messages, base_url, **kwargs):
            raise RuntimeError('Cannot reach the Qwen service or the request timed out.')
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', broken)
            with self.assertRaises(RuntimeError):
                agent.ask('Show Tencent metrics')
            self.assertEqual(len(agent.messages), 1)
            events = [json.loads(line) for line in agent.log.read_text(encoding='utf-8').splitlines()]
            error = next(e for e in events if e['event'] == 'model_error')
            self.assertEqual(error['error_type'], 'RuntimeError')
            self.assertIn('Cannot reach', error['error'])
            self.assertEqual((events[-1]['event'], events[-1]['status'], events[-1]['model_calls']), ('turn', 'error', 1))

    def test_price_chart_saved_and_markup_kept_out_of_context(self):
        import xml.dom.minidom
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl')
            result = agent.dispatch('price_chart', {'ticker': '700', 'window': 60})
            self.assertNotIn('svg', result)
            self.assertEqual((result['points'], result['status']), (61, 'ok'))
            self.assertEqual(agent.charts, [result['chart_file']])
            xml.dom.minidom.parse(result['chart_file'])
            self.assertNotIn('<svg', agent.log.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
