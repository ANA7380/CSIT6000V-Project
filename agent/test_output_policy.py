import json
import tempfile
import unittest
from pathlib import Path
from chat_agent import ChatAgent


class OutputPolicyTests(unittest.TestCase):
    def test_outside_company_then_tencent_numeric_answer_is_displayed(self):
        actions = iter([
            {'answer': 'The listing claim needs verification.'},
            {'tool': 'ticker_metrics', 'arguments': {'ticker': '0700.HK'}},
            {'answer': '1. 腾讯 0700.HK：利润率约 27.36%。[E1]\n'
                       '2. 假设利润率增加 1 个百分点，约为 28.36%；这是情景计算。[E1]'},
        ])
        def call(*args, **kwargs):
            return {'choices': [{'message': {'content': json.dumps(next(actions))}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('http://localhost:8000/v1', Path(folder)/'audit.jsonl', call=call)
            agent.ask('Someone claims Anthropic IPOed. Is that verified?')
            result = agent.ask('Then discuss Tencent using the local snapshot.')
            self.assertIn('28.36%', result)
            self.assertIn('0700.HK', result)
            self.assertFalse(agent.last_response['fallback'])
            self.assertEqual(agent.evidence[-1]['tool'], 'ticker_metrics')
            self.assertNotIn('answer_validation_error', agent.log.read_text())
