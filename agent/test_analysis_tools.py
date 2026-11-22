import json
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from agent import TickerAgent
from analysis_tools import AnalysisTools, ema
from chat_agent import ChatAgent, SYSTEM
from tool_registry import TOOLS, validate


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.engine = TickerAgent()
        self.tools = AnalysisTools(self.engine)

    def prices(self, values, symbol='0700.HK', volumes=None):
        return [dict(symbol=symbol, date=(date(2024, 1, 1)+timedelta(days=i)).isoformat(),
                     adjusted_close=str(v), volume=str(volumes[i] if volumes else 100)) for i, v in enumerate(values)]

    def test_drawdown_rolling_and_volume(self):
        self.engine.prices = self.prices([100, 120, 90, 108])
        metrics = self.tools.price_analysis('700', window=3, rolling_window=2)['metrics']
        self.assertAlmostEqual(metrics['maximum_drawdown']['value'], -25)
        self.assertEqual(metrics['maximum_drawdown']['peak_date'], '2024-01-02')
        expected = abs(math.log(90/120)-math.log(108/90))/math.sqrt(2)*math.sqrt(252)*100
        self.assertAlmostEqual(metrics['rolling_volatility']['value'], expected)
        self.assertIsNone(metrics['return_1m']['value'])
        self.assertIsNone(metrics['rsi_14']['value'])
        self.engine.prices = self.prices([100]*21, volumes=[100]*20+[300])
        metrics = self.tools.price_analysis('700')['metrics']
        self.assertEqual(metrics['volume_ratio_20']['value'], 3)
        self.assertEqual(metrics['rsi_14']['value'], 50)
        self.assertEqual(metrics['maximum_drawdown']['status'], 'short_history')

    def test_sma_rsi_macd_and_calendar_returns(self):
        self.engine.prices = self.prices(list(range(1, 401)))
        result = self.tools.price_analysis('700')
        metrics = result['metrics']
        self.assertAlmostEqual(metrics['sma_20']['value'], 390.5)
        self.assertEqual(metrics['rsi_14']['value'], 100)
        self.assertAlmostEqual(metrics['macd']['value'], 7)
        self.assertAlmostEqual(metrics['macd']['signal'], 7)
        self.assertAlmostEqual(metrics['macd']['histogram'], 0)
        self.assertEqual(result['trend_comparison']['latest_50_200_crossover'], 'none')
        for months in (1, 3, 6, 12):
            m = metrics[f'return_{months}m']
            self.assertEqual(m['status'], 'ok')
            start_index = (date.fromisoformat(m['start_date'])-date(2024, 1, 1)).days
            self.assertAlmostEqual(m['value'], (400/(start_index+1)-1)*100)
        self.assertEqual(ema([1, 2, 3, 4], 3), [None, None, 2, 3])

    def test_correlation_matches_both_dates(self):
        left = self.prices([100, 110, 99, 108.9])
        right = self.prices([200, 220, 198, 217.8], '9988.HK')
        self.engine.prices = left + right
        result = self.tools.stock_correlation('700', '9988', window=3)['correlation']
        self.assertAlmostEqual(result['value'], 1)
        self.assertEqual(result['returns_used'], 3)
        # The missing day creates a different interval; it must not be aligned by end date alone.
        self.engine.prices = left + [right[0], right[2], right[3]]
        result = self.tools.stock_correlation('700', '9988')['correlation']
        self.assertEqual(result['returns_used'], 1)
        self.assertIsNone(result['value'])

    def test_financial_years_and_currency(self):
        self.engine.financials = []
        for year, revenue, income, equity, debt in [(2024, 100, 10, 100, 40), (2025, 200, 30, 140, 60)]:
            for name, value in [('TotalRevenue', revenue), ('NetIncome', income), ('StockholdersEquity', equity), ('TotalDebt', debt)]:
                self.engine.financials.append(dict(symbol='0700.HK', metric='annual'+name, period_end=f'{year}-12-31',
                                                  period_type='12M', currency='CNY', value=str(value), source_url='fixture'))
        m = self.tools.financial_trends('700')['metrics']
        self.assertAlmostEqual(m['profit_margin_change']['value'], 5)
        self.assertAlmostEqual(m['return_on_equity']['value'], 25)
        self.assertAlmostEqual(m['debt_growth']['value'], 50)
        self.assertAlmostEqual(m['equity_growth']['value'], 40)
        for row in self.engine.financials:
            if row['period_end'] == '2024-12-31':
                row['currency'] = 'USD'
        self.assertTrue(all(m['value'] is None for m in self.tools.financial_trends('700')['metrics'].values()))

    def test_ranking_ties_filters_and_missing(self):
        self.engine.snapshot = {s: {'company_name': s} for s in ['A', 'B', 'C', 'D']}
        def run(symbol, window):
            values = {'A': (10, .5), 'B': (10, 1), 'C': (30, 2), 'D': (None, .2)}
            growth, debt = values[symbol]
            return {'metrics': {name: {'value': v, 'status': 'ok' if v is not None else 'unavailable'} for name, v in
                                [('Revenue growth', growth), ('Net profit margin', 5), ('Debt-to-equity', debt), ('Historical volatility', 20)]}}
        self.engine.run = run
        result = self.tools.rank_stocks(weights={'revenue_growth': 1})
        self.assertEqual([r['symbol'] for r in result['results']], ['C', 'A', 'B'])
        self.assertEqual([r['score'] for r in result['results']], [100, 25, 25])
        self.assertEqual(result['excluded'][0]['symbol'], 'D')
        result = self.tools.rank_stocks(weights={'debt_to_equity': 1}, filters={'revenue_growth': {'min': 0}, 'debt_to_equity': {'max': 1}})
        self.assertEqual([r['symbol'] for r in result['results']], ['A', 'B'])
        self.assertEqual([r['score'] for r in result['results']], [100, 0])
        result = self.tools.rank_stocks(filters={'revenue_growth': {'min': 100}})
        self.assertEqual(result['results'], [])

    def test_bad_inputs(self):
        self.engine.prices = self.prices([100, 0, 105])
        with self.assertRaises(ValueError):
            self.tools.price_analysis('700')
        for args in [{'weights': {'fake': 1}}, {'weights': {'revenue_growth': -1}},
                     {'weights': {'revenue_growth': float('nan')}},
                     {'filters': {'net_profit_margin': {'min': 5, 'max': 1}}}]:
            with self.assertRaises(ValueError):
                self.tools.rank_stocks(**args)
        for name, args in [('price_analysis', {'ticker': '700', 'window': True}),
                           ('list_tickers', {'extra': 1}), ('stock_correlation', {'ticker': '700'}),
                           ('rank_stocks', {'top_k': 31}), ('price_analysis', {'ticker': []})]:
            with self.assertRaises(ValueError):
                validate(name, args)

    def test_entire_universe(self):
        for symbol in self.engine.snapshot:
            for result in [self.tools.price_analysis(symbol), self.tools.financial_trends(symbol)]:
                json.dumps(result, allow_nan=False)
        result = self.tools.rank_stocks()
        self.assertGreater(result['eligible_count'], 0)
        self.assertEqual(len(result['results']), 5)


class ToolRoutingTests(unittest.TestCase):
    def test_each_catalog_tool_roundtrip(self):
        for name, spec in TOOLS.items():
            with self.subTest(tool=name), tempfile.TemporaryDirectory() as folder:
                calls = iter([{'tool': name, 'arguments': spec['example']}, {'answer': 'Computed from tool result. [E1]'}])
                def fake(messages, base_url, **kwargs):
                    if messages[-1]['content'].startswith('TOOL_RESULT'):
                        data = json.loads(messages[-1]['content'].split('\n', 1)[1])
                        self.assertNotIn('error', data)
                        self.assertEqual(data['tool'], name)
                    return {'choices': [{'message': {'content': json.dumps(next(calls))}}]}
                agent = ChatAgent('https://api.deepseek.com/v1', Path(folder)/'test.jsonl', call=fake)
                self.assertIn(name, SYSTEM)
                self.assertTrue(agent.ask('Test request').startswith('Computed from tool result. [E1]'))

    def test_invalid_request_is_corrected(self):
        actions = iter([{'tool': 'price_analysis', 'arguments': {'ticker': '700', 'window': -1}},
                        {'tool': 'price_analysis', 'arguments': {'ticker': '700'}}, {'answer': 'Done. [E1]'}])
        def fake(*args, **kwargs):
            return {'choices': [{'message': {'content': json.dumps(next(actions))}}]}
        with tempfile.TemporaryDirectory() as folder:
            agent = ChatAgent('https://api.deepseek.com/v1', Path(folder)/'test.jsonl', call=fake)
            self.assertTrue(agent.ask('Show RSI').startswith('Done. [E1]'))
            self.assertIn('error', agent.log.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
