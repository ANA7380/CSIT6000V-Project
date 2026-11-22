"""Offline tests: no network, no model. Run with `python -m unittest -v` in this folder."""
import json
import tempfile
import unittest
from pathlib import Path

import cases as case_module
import run_eval
import score
from common import close_enough, extract_numbers, has_number, mentioned_tickers, numeric_claims, supported


def reply(text):
    return {'choices': [{'message': {'content': text}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}


def perfect_answer(turn):
    """An answer that states every reference value; a correct system should say at least this."""
    parts = []
    for check in turn['checks']:
        kind = check['type']
        if kind == 'label':
            parts.insert(0, check['expected'] + '.')
        elif kind == 'number':
            parts.append('%s is %.2f.' % (check['label'], check['expected']))
        elif kind == 'unavailable':
            parts.append('%s is N/A.' % check['label'])
        elif kind == 'ranking':
            parts.insert(0, 'Ranking: ' + ', '.join(check['expected']) + '.')
        else:
            parts.append(' '.join(group[0] for group in check['groups']) + '.')
    return ' '.join(parts)


def oracle(case):
    """Fake model: requests each reference tool, then gives the perfect answer."""
    state = {'turn': -1, 'pending': []}

    def call(messages, base_url, **kwargs):
        last = messages[-1]['content']
        if last.startswith('TOOL_RESULT'):
            state['cite'] = ' [%s]' % json.loads(last.split('\n', 1)[1]).get('id', 'E1')
        if not last.startswith(('TOOL_RESULT', 'MODEL_FORMAT_ERROR')):
            state['cite'] = ''
            state['turn'] += 1
            state['pending'] = list(case['turns'][state['turn']]['reference_calls'])
        if state['pending']:
            ref = state['pending'].pop(0)
            return reply(json.dumps({'tool': ref['tool'], 'arguments': ref['arguments']}))
        return reply(json.dumps({'answer': perfect_answer(case['turns'][state['turn']]) + state['cite']}))
    return call


class HelperTests(unittest.TestCase):
    def test_number_extraction_ignores_dates_and_tickers(self):
        values = [v for v, _, _ in extract_numbers('0700.HK on 2026-11-17: SMA50 415.62, margin 27.36%, loss −5,310.75%')]
        self.assertEqual(values, [415.62, 27.36, -5310.75])

    def test_rounding_tolerance(self):
        self.assertTrue(close_enough(33.8, 1, 33.8439))
        self.assertTrue(close_enough(0.42, 2, 0.4154))
        self.assertFalse(close_enough(0.4, 1, 0.4154))        # too coarse
        self.assertFalse(close_enough(33.9, 1, 33.8439))
        self.assertTrue(has_number('fell 40.24% over 12 months', -40.2387))

    def test_claims_and_support(self):
        claims = numeric_claims('Margin 27.36%, top 5, weight 0.5', 'at most 0.5')
        self.assertEqual(claims, [(27.36, 2)])
        self.assertTrue(supported(27.36, 2, [27.3565]))
        self.assertTrue(supported(25, 0, [0.25]))               # weight as a percentage
        self.assertTrue(supported(184.5, 1, [184504000000.0]))  # billions
        self.assertFalse(supported(31.2, 1, [27.3565]))

    def test_ticker_order_and_name_overlap(self):
        names = {'0700.HK': 'Tencent', '1698.HK': 'Tencent Music Entertainment', '9988.HK': 'Alibaba', '0241.HK': 'Alibaba Health'}
        text = '1. Tencent Music Entertainment 2. Alibaba (9988.HK) 3. 700.HK 4. Alibaba Health'
        self.assertEqual(mentioned_tickers(text, names), ['1698.HK', '9988.HK', '0700.HK', '0241.HK'])


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = case_module.load()
        cls.reference = case_module.Reference()

    def test_committed_references_match_tools(self):
        self.assertEqual(case_module.build(), self.data, 'Run `python cases.py` after changing cases or data.')

    def test_case_ids_unique_and_categories_covered(self):
        ids = [c['id'] for c in self.data['cases']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({c['category'] for c in self.data['cases']},
                         {'individual', 'ranking', 'trend', 'followup', 'invalid'})

    def run_system(self, make_system, folder, label):
        out = Path(folder) / (label + '.jsonl')
        run_eval.run(label, self.data['cases'], make_system, out, {'model': 'fake'}, quiet=True)
        return score.score_system(score.latest_records(out), self.data, self.reference)

    def test_oracle_agent_scores_perfectly(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_system(lambda case: run_eval.AgentSystem(
                oracle(case), 'http://localhost:8000/v1', Path(folder) / 'audit.jsonl'), folder, 'agent-fake')
        failed = [(c['case_id'], c['label']) for c in result['checks'] if not c['passed']]
        self.assertEqual(failed, [])
        self.assertEqual(result['cases_passed'], len(self.data['cases']))
        self.assertEqual(result['followup_success'], (6, 6))
        self.assertEqual(result['recommendation_precision'], 1.0)
        self.assertEqual(result['explanation_grounding'][0], result['explanation_grounding'][1])
        self.assertGreater(result['explanation_grounding'][1], 50)
        self.assertEqual(result['turn_errors'], 0)

    def test_fabricating_baseline_scores_poorly(self):
        def fake(messages, base_url, **kwargs):
            return reply(json.dumps({'answer': 'Tencent (0700.HK) looks strong: margin 31.2%, volatility 19.9%. Top picks: 0005.HK.'}))
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_system(lambda case: run_eval.NoToolsSystem(fake, 'http://x/v1'), folder, 'notools-fake')
        self.assertEqual(result['numerical_accuracy'][0], 0)
        self.assertEqual(result['cases_passed'], 0)
        ok, total = result['explanation_grounding']   # chance matches are possible but must stay rare
        self.assertLess(ok / total, 0.05)
        self.assertLess(result['recommendation_precision'], 0.3)   # 0700.HK is legitimately in some Top-K lists

    def test_transport_errors_resume_and_stop(self):
        def down(messages, base_url, **kwargs):
            raise RuntimeError('Cannot reach the Qwen service or the request timed out.')
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'x.jsonl'
            make = lambda case: run_eval.NoToolsSystem(down, 'http://x/v1')
            with self.assertRaises(SystemExit):
                run_eval.run('x', self.data['cases'], make, out, {}, quiet=True)
            self.assertEqual(len(out.read_text().splitlines()), 3)
            ok = lambda case: run_eval.NoToolsSystem(lambda m, b, **k: reply('{"answer":"ok"}'), 'http://x/v1')
            run_eval.run('x', self.data['cases'], ok, out, {}, quiet=True)
            records = score.latest_records(out)
            self.assertEqual(len(records), len(self.data['cases']))
            self.assertFalse(any(t['error'] for r in records.values() for t in r['turns']))

    def test_raw_context_has_inputs_but_no_computed_metrics(self):
        case = next(c for c in self.data['cases'] if c['id'] == 'ind-01')
        text = run_eval.raw_context(case, self.reference.engine)
        self.assertIn('DAILY PRICES 0700.HK', text)
        self.assertNotIn('27.36', text)
        ranking = next(c for c in self.data['cases'] if c['id'] == 'rank-01')
        self.assertNotIn('DAILY PRICES', run_eval.raw_context(ranking, self.reference.engine))


if __name__ == '__main__':
    unittest.main()
