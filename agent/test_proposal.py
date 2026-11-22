import json
import math
import tempfile
import unittest
from pathlib import Path

from chat_agent import ChatAgent
from evidence import GroundingError, validate_answer
from session_store import save_agent, restore_agent
from agent import TickerAgent
from analysis_tools import AnalysisTools


def scripted(actions):
    it=iter(actions)
    return lambda *args,**kwargs: {'choices':[{'message':{'content':json.dumps(next(it))}}]}


class ProposalTests(unittest.TestCase):
    def make(self,folder,actions):
        return ChatAgent('http://localhost:8000/v1',Path(folder)/'audit.jsonl',call=scripted(actions))

    def test_unknown_references_are_rejected_then_repaired(self):
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,[{'answer':'Revenue growth is 999999%. [E999]'},
                              {'tool':'ticker_metrics','arguments':{'ticker':'0700.HK'}},
                              {'answer':'The result is supported by the frozen dataset. [E1]'}])
            output=agent.ask('Show Tencent growth')
            self.assertNotIn('999999',output)
            self.assertFalse(agent.last_response['fallback'])
            events=[json.loads(l) for l in agent.log.read_text().splitlines()]
            self.assertTrue(any(e['event']=='answer_validation_error' for e in events))
            self.assertTrue(all('timestamp' in e and 'turn_id' in e for e in events))
            self.assertTrue(all(e['duration_ms']>=0 for e in events if 'duration_ms' in e))

    def test_numbers_dates_and_tickers_are_allowed_but_invalid_references_rejected(self):
        for answer in ['Revenue is 999999%.', 'Revenue is ９９９９９９%.',
                       'Revenue is ²%.', 'On 2026-01-01.', '0700.HK SMA50/SMA200']:
            self.assertEqual(validate_answer(answer, []), [])
        for answer in ['[E999] profit', 'https://invented.example/data', '   ']:
            with self.assertRaises(GroundingError): validate_answer(answer, [])
        with self.assertRaises(GroundingError):
            validate_answer('Revenue is 27.36%.', [], require_evidence=True)

    def test_bounded_repair_falls_back_to_verified_results(self):
        actions=[{'tool':'ticker_metrics','arguments':{'ticker':'0700.HK'}}]+[{'answer':'Margin is 999999% [E999]'}]*11
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,actions)
            output=agent.ask('Show margin')
            self.assertTrue(agent.last_response['fallback'])
            self.assertNotIn('999999',output)
            self.assertEqual(len(agent.last_response['evidence']),1)

    def test_ranking_preferences_survive_concept_and_top_k_change(self):
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,[{'tool':'rank_stocks','arguments':{'top_k':3,'window':60,
                     'filters':{'net_profit_margin':{'min':10}},'weights':{'revenue_growth':2,'historical_volatility':1}}},
                     {'answer':'The ranking uses your explicit preferences. [E1]'},
                     {'answer':'Volatility describes historical variability.'},
                     {'tool':'rank_stocks','arguments':{'reuse_previous':True,'top_k':5}},
                     {'answer':'The ranking retains your earlier criteria. [E2]'}])
            agent.ask('Rank three');first=agent.state['ranking_history'][0].copy()
            agent.ask('Explain volatility');self.assertEqual(agent.state['ranking_history'][0],first)
            agent.ask('Keep same criteria, now top five')
            args=agent.state['last_ranking_request']
            self.assertEqual(args['top_k'],5);self.assertEqual(args['window'],60)
            self.assertEqual(args['filters'],{'net_profit_margin':{'min':10}})
            self.assertEqual(args['weights'],{'revenue_growth':2,'historical_volatility':1})
            result=agent.evidence[-1]['result']
            for r in result['results']:
                self.assertAlmostEqual(sum(r['contributions'].values()),r['score'])

    def test_failed_model_rolls_back_state_and_can_resume(self):
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,[{'tool':'rank_stocks','arguments':{'top_k':3}},
                               {'answer':'Ranking supported. [E1]'}])
            agent.ask('Rank')
            state=json.dumps(agent.state);count=len(agent.evidence)
            def fail(*args,**kwargs):raise RuntimeError('simulated transport failure')
            agent.call=fail
            with self.assertRaises(RuntimeError):agent.ask('Change ranking')
            self.assertEqual(json.dumps(agent.state),state);self.assertEqual(len(agent.evidence),count)
            self.assertIn('turn_error',agent.log.read_text())
            path=Path(p)/'session.state';save_agent(path,agent)
            resumed=self.make(p,[{'answer':'Earlier ranking is preserved. [E1]'}]);restore_agent(path,resumed)
            self.assertEqual(resumed.state,agent.state)
            self.assertIn('reused earlier result',resumed.ask('Recall previous ranking'))

    def test_chart_matches_prices_and_null_warmup(self):
        engine=TickerAgent();tools=AnalysisTools(engine)
        r=tools.price_analysis('0700.HK',window=60);c=r['chart']
        rows=sorted([r for r in engine.prices if r['symbol']=='0700.HK'],key=lambda r:r['date'])[-61:]
        self.assertEqual(c['dates'],[r['date'] for r in rows])
        self.assertEqual(c['series']['adjusted_close'],[float(r['adjusted_close']) for r in rows])
        self.assertAlmostEqual(c['series']['sma_50'][-1],r['metrics']['sma_50']['value'])
        self.assertEqual(c['rolling_volatility'][-1]['value'],r['metrics']['rolling_volatility']['value'])
        short=tools.price_analysis('9903.HK')['chart']
        self.assertTrue(any(v is None for v in short['series']['sma_200']))
        self.assertTrue(all(len(v)==len(short['dates']) for v in short['series'].values()))

    def test_grounded_crossover_label_and_bounded_repair(self):
        result=AnalysisTools(TickerAgent()).price_analysis('0700.HK',window=60)
        evidence=[{'id':'E1','tool':'price_analysis','arguments':{'ticker':'0700.HK'},'result':result}]
        answer='The latest fifty/200 crossover is none. [E1]'
        self.assertEqual(validate_answer(answer,evidence),['E1'])
        with self.assertRaises(GroundingError):validate_answer(answer,[])
        self.assertEqual(validate_answer('Margin is 200% [E1]',evidence), ['E1'])
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,[{'tool':'price_analysis','arguments':{'ticker':'0700.HK','window':60}},
                               {'answer':'Invalid reference 999999% [E999]'},
                               {'answer':'Invalid reference 999999% [E999]'}])
            output=agent.ask('Show a chart')
            self.assertTrue(agent.last_response['fallback'])
            self.assertNotIn('999999',output)
            events=[json.loads(l) for l in agent.log.read_text().splitlines()]
            self.assertEqual(sum(e['event']=='model' for e in events),3)
            self.assertNotIn('999999',agent.messages[-1]['content'])

    def test_context_budget_preserves_complete_turns_and_state(self):
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,[{'answer':'A conceptual explanation.'}]*15)
            agent.max_context_chars=len(agent.messages[0]['content'])+1200
            for _ in range(15):agent.ask('Explain '+'historical analysis '*30)
            self.assertLess(sum(len(m['content']) for m in agent.messages),agent.max_context_chars)
            self.assertEqual(agent.messages[1]['role'],'user')

    def test_course_qwen_requires_single_leading_system_message(self):
        with tempfile.TemporaryDirectory() as p:
            agent=self.make(p,[{'answer':'A conceptual explanation.'}]*2)
            agent.ask('Explain volatility');agent.ask('Explain margin')
            context=agent._context()
            self.assertEqual([i for i,m in enumerate(context) if m['role']=='system'],[0])
            self.assertIn('SESSION_STATE\n',context[0]['content'])
            self.assertNotIn('SESSION_STATE\n',agent.messages[0]['content'])
            self.assertEqual(agent.messages[1]['role'],'user')

    def test_direct_tool_arguments_rejected(self):
        tools=AnalysisTools(TickerAgent())
        for fn,args in [(tools.rank_stocks,{'top_k':True}),(tools.price_analysis,{'ticker':'700','window':-1}),
                        (tools.stock_correlation,{'ticker':'700','other_ticker':'9988','window':1})]:
            with self.assertRaises(ValueError):fn(**args)


if __name__=='__main__':unittest.main()
