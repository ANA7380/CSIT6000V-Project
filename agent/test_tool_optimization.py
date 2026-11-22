"""Regression tests for batches, evidence integrity, caching and retry bounds."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from chat_agent import ChatAgent, parse_action
from evidence import model_result


def tool(name='ticker_metrics', ticker='700', **args):
    return {'tool': name, 'arguments': dict(ticker=ticker, **args)}


class ToolOptimizationTests(unittest.TestCase):
    def make(self, directory, actions):
        actions = iter(actions)
        def call(*args, **kwargs):
            action = next(actions)
            if isinstance(action, Exception):
                raise action
            content = action if isinstance(action, str) else json.dumps(action)
            return {'choices': [{'message': {'content': content}}]}
        return ChatAgent('http://localhost:8000/v1', Path(directory)/'audit.jsonl', call)

    def events(self, agent):
        return [json.loads(line) for line in agent.log.read_text().splitlines()]

    def test_overview_batch_keeps_both_evidence_cards_and_chart(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [
                {'tools': [tool(), tool('price_analysis')]},
                {'answer': 'Overview [E1] [E2]'}])
            agent.ask('Overview 0700.HK')
            self.assertEqual([e['tool'] for e in agent.evidence], ['ticker_metrics', 'price_analysis'])
            self.assertIsNotNone(agent.last_response['evidence'][1]['chart'])
            self.assertEqual(agent.last_response['stats']['model_calls'], 2)
            self.assertEqual(agent.last_response['stats']['tool_calculations'], 2)
            result = json.loads(agent.messages[-2]['content'].split('\n', 1)[1])
            self.assertEqual([e['id'] for e in result['results']], ['E1', 'E2'])

    def test_batch_validated_before_any_tool_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [
                {'tools': [tool(), {'tool': 'shell', 'arguments': {}}]},
                {'answer': 'Please use supported tools.'}])
            agent.ask('Compare')
            self.assertEqual(agent.evidence, [])
            self.assertFalse(any(e['event'] == 'tool_start' for e in self.events(agent)))

    def test_batch_limits_and_mixed_actions(self):
        for action in [
            {'tools': []}, {'tools': [tool()]*7},
            {'tools': [tool()], 'answer': 'fake'},
            {'tools': [{'tools': [tool()]}]},
            {'tools': [tool(), {'tool': 'rank_stocks', 'arguments': {}}]},
        ]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                parse_action(json.dumps(action))
        with self.assertRaises(ValueError):
            parse_action(json.dumps({'tools': [tool()]}) + '\n{"answer":"fake"}')

    def test_runtime_error_in_batch_preserves_other_results(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [
                {'tools': [tool(ticker='AAPL'), tool(ticker='9988')]},
                {'answer': 'Only the supported company is shown. [E1]'}])
            agent.ask('Compare AAPL and 9988.HK')
            self.assertEqual(agent.evidence[0]['result']['symbol'], '9988.HK')
            self.assertEqual(agent.last_response['stats']['tool_errors'], 1)
            self.assertEqual(agent.last_response['stats']['tool_calculations'], 1)

    def test_same_turn_alias_and_default_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [
                tool(), tool(ticker='0700.HK', window=252),
                {'answer': 'One calculation supports both requests. [E1]'}])
            agent.ask('Metrics 0700.HK')
            self.assertEqual(len(agent.evidence), 1)
            self.assertEqual(agent.last_response['stats']['cache_hits'], 1)
            self.assertEqual(sum(e['event'] == 'metric_calculation' for e in self.events(agent)), 1)
            self.assertTrue(next(e for e in reversed(self.events(agent))
                                 if e['event'] == 'tool_result')['reused'])

    def test_distinct_windows_are_not_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [
                {'tools': [tool(window=60), tool(window=252)]},
                {'answer': 'Two separate windows. [E1] [E2]'}])
            agent.ask('Compare volatility windows')
            self.assertEqual(len(agent.evidence), 2)
            self.assertEqual(agent.last_response['stats']['cache_hits'], 0)
            left, right = [e['result']['metrics']['Historical volatility']['value'] for e in agent.evidence]
            self.assertNotEqual(left, right)

    def test_cache_does_not_cross_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [tool(), {'answer': 'First [E1]'},
                                           tool(), {'answer': 'Again [E2]'}])
            agent.ask('Metrics'); agent.ask('Recalculate')
            self.assertEqual(len(agent.evidence), 2)
            self.assertEqual(agent.last_response['stats']['cache_hits'], 0)

    def test_cached_ranking_does_not_duplicate_history(self):
        request = {'tool': 'rank_stocks', 'arguments': {'top_k': 3, 'window': 60}}
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [request,
                {'tool': 'rank_stocks', 'arguments': {'reuse_previous': True}},
                {'answer': 'Same ranking. [E1]'}])
            agent.ask('Rank')
            self.assertEqual(len(agent.state['ranking_history']), 1)
            self.assertEqual(agent.state['last_ranking_request'], request['arguments'])
            self.assertEqual(agent.last_response['stats']['cache_hits'], 1)

    def test_batch_results_rolled_back_after_transport_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [
                {'tools': [tool(), tool('price_analysis')]}, RuntimeError('offline')])
            old_state = copy.deepcopy(agent.state)
            with self.assertRaises(RuntimeError):
                agent.ask('Overview')
            self.assertEqual(agent.evidence, [])
            self.assertEqual(agent.state, old_state)
            self.assertEqual(len(agent.messages), 1)

    def test_repeated_format_failures_stop_early(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, ['bad JSON']*12)
            with self.assertRaises(RuntimeError):
                agent.ask('Metrics')
            self.assertEqual(sum(e['event'] == 'model' for e in self.events(agent)), 2)

    def test_repeated_format_failures_keep_verified_results(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [tool(), 'bad JSON', 'bad JSON'])
            agent.ask('Metrics')
            self.assertTrue(agent.last_response['fallback'])
            self.assertEqual(agent.last_response['stats']['model_calls'], 3)
            self.assertNotIn('bad JSON', agent.last_response['answer'])
            self.assertEqual(len(agent.last_response['evidence']), 1)

    def test_compact_ranking_keeps_values_and_periods_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = self.make(directory, [])
            raw = agent.dispatch('rank_stocks', {'top_k': 30})
            original = copy.deepcopy(raw)
            shown = model_result(raw)
            self.assertEqual(raw, original)
            for a, b in zip(raw['results'], shown['results']):
                self.assertEqual(a['values'], b['values'])
                self.assertEqual(a['score'], b['score'])
                for label, metric in b['metric_details'].items():
                    expected = {k: v for k, v in a['metric_details'][label].items()
                                if k not in {'value', 'formula', 'inputs', 'source_url'}}
                    self.assertEqual(metric, expected)


if __name__ == '__main__':
    unittest.main()
