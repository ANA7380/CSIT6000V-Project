"""State recovery and timing observability under success and failure."""
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from chat_agent import ChatAgent
from session_store import atomic_json, save_agent
from web_worker import process
import web_worker


def scripted(actions):
    actions = iter(actions)
    def call(*args, **kwargs):
        action = next(actions)
        if isinstance(action, Exception):
            raise action
        return {'choices': [{'message': {'content': json.dumps(action)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
    return call


class RuntimeReviewTests(unittest.TestCase):
    def test_failed_turn_restores_evidence_counter_before_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = ChatAgent('http://localhost:8000/v1', Path(directory)/'audit.jsonl',
                scripted([{'tool': 'ticker_metrics', 'arguments': {'ticker': '700'}},
                          RuntimeError('transport down')]))
            with self.assertRaises(RuntimeError):
                agent.ask('Metrics')
            self.assertEqual(agent.next_evidence, 1)
            agent.call = scripted([{'tool': 'ticker_metrics', 'arguments': {'ticker': '700'}},
                                   {'answer': 'Recovered [E1]'}])
            agent.ask('Retry metrics')
            self.assertEqual(agent.evidence[0]['id'], 'E1')
            self.assertFalse(agent.last_response['fallback'])

    def test_timings_and_usage_include_all_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = ChatAgent('http://localhost:8000/v1', Path(directory)/'audit.jsonl',
                scripted([{'tool': 'ticker_metrics', 'arguments': {'ticker': '700'}},
                          {'answer': 'Metrics [E1]'}]))
            agent.ask('Metrics')
            stats = agent.last_response['stats']
            self.assertEqual((stats['model_calls'], stats['prompt_tokens'], stats['completion_tokens']),
                             (2, 200, 40))
            self.assertGreaterEqual(stats['model_request_ms'], 0)
            self.assertGreaterEqual(stats['tool_ms'], 0)
            self.assertLessEqual(stats['model_request_ms'], agent.last_response['duration_ms'])

    def test_failed_restore_can_retry_after_snapshot_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); sessions = {}; session = 'a'*32
            atomic_json(folder/(session+'.state'), {'version': 999, 'messages': []})
            def factory(base, log):
                return ChatAgent(base, log, scripted([{'answer': 'Recovered session'}]))
            first = folder/('b'*32+'.ask')
            atomic_json(first, {'session': session, 'question': 'Explain volatility'})
            process(first, sessions, 'http://localhost:8000/v1', factory)
            self.assertNotIn(session, sessions)
            self.assertIn('error', json.loads(first.with_suffix('.reply').read_text()))
            clean = factory('http://localhost:8000/v1', folder/'clean.jsonl')
            save_agent(folder/(session+'.state'), clean)
            second = folder/('c'*32+'.ask')
            atomic_json(second, {'session': session, 'question': 'Explain volatility'})
            process(second, sessions, 'http://localhost:8000/v1', factory)
            result = json.loads(second.with_suffix('.reply').read_text())
            self.assertEqual(result['explanation'], 'Recovered session')
            self.assertIn(session, sessions)
            self.assertGreaterEqual(result['timings']['worker']['session_save_ms'], 0)
            status = json.loads(second.with_suffix('.status').read_text())
            self.assertEqual(status['response'], result)

    def test_failed_final_status_write_keeps_durable_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); path = folder/('d'*32+'.ask')
            atomic_json(path, {'session': 'a'*32, 'question': 'Explain volatility'})
            def factory(base, log):
                return ChatAgent(base, log, scripted([{'answer': 'Historical variability.'}]))
            def write(target, value):
                if value.get('event') == 'reply_ready':
                    raise OSError('simulated final-status failure')
                atomic_json(target, value)
            with patch.object(web_worker, 'atomic_json', write):
                process(path, {}, 'http://localhost:8000/v1', factory)
            self.assertFalse(path.exists())
            result = json.loads(path.with_suffix('.reply').read_text())
            self.assertEqual(result['explanation'], 'Historical variability.')
            self.assertEqual(json.loads(path.with_suffix('.status').read_text())['event'], 'turn_complete')


if __name__ == '__main__':
    unittest.main()
