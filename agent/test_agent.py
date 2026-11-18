import math
import unittest
from agent import TickerAgent


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = TickerAgent()

    def test_all_tickers_and_aliases(self):
        self.assertEqual(self.agent.normalize('00700'), '0700.HK')
        self.assertEqual(self.agent.normalize('700.hk'), '0700.HK')
        for symbol in self.agent.snapshot:
            result = self.agent.run(symbol)
            self.assertEqual(len(result['metrics']), 4)
            for metric in result['metrics'].values():
                self.assertTrue(metric['value'] is None or math.isfinite(metric['value']))
        with self.assertRaises(ValueError):
            self.agent.run('AAPL')
        with self.assertRaises(ValueError):
            self.agent.run('700', 1)

    def test_known_calculations(self):
        row = self.agent.snapshot['0700.HK']
        row.update(revenue='120', prior_year_revenue='100', net_income='-12',
                   total_debt='50', stockholders_equity='200')
        self.agent.prices = [dict(symbol='0700.HK', date=f'2026-01-0{i+1}', adjusted_close=str(p))
                             for i, p in enumerate([100, 110, 99])]
        m = self.agent.run('700', 2)['metrics']
        self.assertAlmostEqual(m['Revenue growth']['value'], 20)
        self.assertAlmostEqual(m['Net profit margin']['value'], -10)
        self.assertAlmostEqual(m['Debt-to-equity']['value'], .25)
        expected = abs(math.log(1.1) - math.log(.9)) / math.sqrt(2) * math.sqrt(252) * 100
        self.assertAlmostEqual(m['Historical volatility']['value'], expected)

    def test_missing_and_invalid_inputs(self):
        row = self.agent.snapshot['0700.HK']
        row.update(prior_year_revenue='', stockholders_equity='0')
        self.agent.prices = [dict(symbol='0700.HK', date=f'2026-01-0{i+1}', adjusted_close=p)
                             for i, p in enumerate(['100', '', '101'])]
        m = self.agent.run('700')['metrics']
        for name in ['Revenue growth', 'Debt-to-equity', 'Historical volatility']:
            self.assertIsNone(m[name]['value'])
            self.assertEqual(m[name]['status'], 'unavailable')

    def test_short_history(self):
        self.agent.prices = [dict(symbol='0700.HK', date=f'2026-01-0{i+1}', adjusted_close=str(p))
                             for i, p in enumerate([100, 101, 102])]
        m = self.agent.run('700')['metrics']['Historical volatility']
        self.assertEqual(m['status'], 'short_history')
        self.assertEqual(m['returns_used'], 2)


if __name__ == '__main__':
    unittest.main()
