import json
import tempfile
import unittest
from pathlib import Path
from chat_agent import ChatAgent, parse_action


class ChatTests(unittest.TestCase):
    def test_two_objects_recover_lookup_before_answer(self):
        broken = '{"tool":"list_tickers","arguments":{}}\n{"answer":"Premature answer","tool_calls":[{"name":"list_tickers","arguments":{}}]}'
        responses = iter([broken, '{"answer":"All tickers retrieved. [E1]"}'])
        def fake(messages, base_url, **kwargs):
            if messages[-1]['content'].startswith('TOOL_RESULT'):
                result = json.loads(messages[-1]['content'].split('\n', 1)[1])
                self.assertEqual(len(result['result']), 30)
                self.assertIn('0700.HK', result['result'])
                self.assertEqual(json.loads(messages[-2]['content']), {'tool': 'list_tickers', 'arguments': {}})
            return {'choices': [{'message': {'content': next(responses)}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder)/'audit.jsonl', fake)
            self.assertTrue(agent.ask('list tickers all of them').startswith('All tickers retrieved. [E1]'))
            events = [json.loads(line) for line in agent.log.read_text().splitlines()]
            self.assertEqual(sum(e['event'] == 'tool_result' for e in events), 1)

    def test_format_error_is_not_tool_failure(self):
        responses = iter(['not JSON', '{"tool":"list_tickers","arguments":{}}', '{"answer":"Done [E1]"}'])
        def fake(messages, base_url, **kwargs):
            if messages[-1]['content'].startswith('MODEL_FORMAT_ERROR'):
                self.assertFalse(json.loads(messages[-1]['content'].split('\n', 1)[1])['tool_executed'])
            return {'choices': [{'message': {'content': next(responses)}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder)/'audit.jsonl', fake)
            self.assertTrue(agent.ask('list tickers').startswith('Done [E1]'))
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
        self.assertEqual(parse_action('{"answer":"line one\nline two"}'), {'answer': 'line one\nline two'})

    def test_tool_roundtrip(self):
        actions = iter([
            {'tool': 'ticker_metrics', 'arguments': {'ticker': '700'}},
            {'answer': 'The company has positive revenue growth in this fixed snapshot. [E1]'},
        ])
        def fake_chat(messages, base_url, **kwargs):
            if messages[-1]['content'].startswith('TOOL_RESULT'):
                result = json.loads(messages[-1]['content'].split('\n', 1)[1])
                self.assertEqual(result['result']['symbol'], '0700.HK')
                self.assertIn('Revenue growth', result['result']['metrics'])
            return {'choices': [{'message': {'content': json.dumps(next(actions))}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', fake_chat)
            self.assertIn('Revenue growth:', agent.ask('Show Tencent metrics'))
            self.assertIsNotNone(agent.last_response['evidence'][0]['metrics'][0]['value'])
            self.assertIn('metric_calculation', agent.log.read_text(encoding='utf-8'))

    def test_invalid_tool_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl')
            for name, args in [('shell', {}), ('ticker_metrics', {'ticker': '700', 'window': True}),
                               ('ticker_metrics', {'ticker': 'AAPL'})]:
                with self.assertRaises(ValueError):
                    agent.dispatch(name, args)

    def test_timings_and_turn_summary_logged(self):
        responses = iter(['{"tool":"list_tickers","arguments":{}}', '{"answer":"Done [E1]"}'])
        def fake(messages, base_url, **kwargs):
            return {'choices': [{'message': {'content': next(responses)}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', fake)
            agent.ask('list tickers')
            events = [json.loads(line) for line in agent.log.read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all('timestamp' in e and e['session_id'] == agent.session_id for e in events))
            for kind in ('model', 'tool_result'):
                self.assertTrue(all(e['duration_ms'] >= 0 for e in events if e['event'] == kind))
            self.assertEqual(sum(e['event'] == 'model' for e in events), 2)
            self.assertEqual((events[-1]['event'], events[-1]['evidence_ids']), ('turn_complete', ['E1']))

    def test_service_error_logged_and_turn_rolled_back(self):
        def broken(messages, base_url, **kwargs):
            raise RuntimeError('Cannot reach the Qwen service or the request timed out.')
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', broken)
            with self.assertRaises(RuntimeError):
                agent.ask('Show Tencent metrics')
            self.assertEqual(len(agent.messages), 1)
            events = [json.loads(line) for line in agent.log.read_text(encoding='utf-8').splitlines()]
            self.assertEqual((events[-1]['event'], events[-1]['error_type']), ('turn_error', 'RuntimeError'))
            self.assertIn('Cannot reach', events[-1]['error'])

    def test_truncated_answer_is_dropped_and_shorter_one_requested(self):
        replies = iter([('{"answer":"a very long answer that was cut', 'length'), ('{"answer":"Short."}', 'stop')])
        def fake(messages, base_url, **kwargs):
            if messages[-1]['content'].startswith('MODEL_FORMAT_ERROR'):
                self.assertIn('cut off', messages[-1]['content'])
                self.assertFalse(any('very long answer' in m['content'] for m in messages))
            content, reason = next(replies)
            return {'choices': [{'message': {'content': content}, 'finish_reason': reason}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl', fake)
            self.assertTrue(agent.ask('Rank the top 10 stocks').startswith('Short.'))

    def test_ranking_result_for_model_omits_source_urls(self):
        from evidence import model_result
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder) / 'audit.jsonl')
            shown = json.dumps(model_result(agent.dispatch('rank_stocks', {'top_k': 10})))
            self.assertNotIn('source_url', shown)
            self.assertLess(len(shown), 20000)
            self.assertEqual(len(json.loads(shown)['results']), 10)
            self.assertIn('source_url', agent.log.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
