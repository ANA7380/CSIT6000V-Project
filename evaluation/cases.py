"""Evaluation cases. References are computed by the project's deterministic tools.

Run `python cases.py` to regenerate cases.json (the frozen reference answers).
"""
import json
from common import EVAL_DIR
from agent import TickerAgent
from analysis_tools import AnalysisTools

CASES_FILE = EVAL_DIR / 'cases.json'
M = 'metrics'
GROWTH, MARGIN, DEBT, VOL = 'Revenue growth', 'Net profit margin', 'Debt-to-equity', 'Historical volatility'
FOUR = [GROWTH, MARGIN, DEBT, VOL]

UNSUPPORTED = ['not supported', 'unsupported', 'unknown ticker', 'not in the', 'not available', 'unavailable',
               'not part of', 'not covered', 'not included', 'cannot find', 'could not find', "couldn't find",
               'no data', 'not found', 'outside', 'not in this', 'no verified', 'cannot rank', "can't rank", '不支持', '未知', '不在', '无法', '没有', '未包含', '不包含']
ASK_TICKER = ['which ticker', 'which stock', 'which company', 'specify', 'provide a ticker', 'provide the ticker',
              'please provide', 'let me know which', 'what ticker', '哪只', '哪个', '请提供', '请指定']
NOT_AVAILABLE = ['not available', 'unavailable', 'not supported', 'cannot provide', 'no p/e', 'not provide',
                 'does not include', "doesn't include", 'not included', 'n/a', '不可用', '无法提供', '不提供', '没有', '不支持']
NO_PREDICTION = ['cannot predict', "can't predict", 'can not predict', 'not predict', 'no prediction', 'unable to predict',
                 'not a forecast', 'not forecast', 'no forecast', 'cannot forecast', "can't forecast", 'can not forecast', 'unable to forecast', 'not able to predict',
                 'no price target', 'not provide a price target', 'cannot provide a price target',
                 '无法预测', '不能预测', '不预测', '不作预测']
INVALID_ARG = ['at least 2', 'between 2', 'invalid', 'must be', 'not valid', 'cannot be', 'nonnegative', 'non-negative',
               'negative', '至少', '无效', '必须', '不能']
NO_MATCH = ['no stock', 'no stocks', 'no compan', 'none of', 'no eligible', 'zero', 'no results', '0 eligible',
            'not any', 'no candidates', '没有', '无符合']
NO_SECTOR = ['sector', 'classification', 'industry', '行业', '板块']


def num(label, tool, args, *path):
    return {'type': 'number', 'label': label, 'tool': tool, 'arguments': args, 'path': list(path)}


def four(ticker, window=None, only=FOUR):
    args = {'ticker': ticker, **({'window': window} if window else {})}
    return [num('%s %s' % (ticker, name), 'ticker_metrics', args, M, name) for name in only]


def price(ticker, *keys, **args):
    return [num('%s %s' % (ticker, k), 'price_analysis', {'ticker': ticker, **args}, M, k) for k in keys]


def trend(ticker, *keys):
    return [num('%s %s' % (ticker, k), 'financial_trends', {'ticker': ticker}, M, k) for k in keys]


def rank(**args):
    return {'type': 'ranking', 'tool': 'rank_stocks', 'arguments': args}


def label(text, tool, args, path, mapping):
    """mapping: tool value -> expected label word. All mapping values are the options."""
    return {'type': 'label', 'label': text, 'tool': tool, 'arguments': args, 'path': list(path), 'mapping': mapping}


def behavior(text, *groups, forbid_numeric_claims=False):
    """Pass when every keyword group has at least one hit (case-insensitive substring)."""
    return {'type': 'behavior', 'label': text, 'groups': list(groups), 'forbid_numeric_claims': forbid_numeric_claims}


def turn(prompt, *checks):
    flat = []
    for c in checks:
        flat.extend(c if isinstance(c, list) else [c])
    return {'prompt': prompt, 'checks': flat}


def case(cid, category, *turns):
    return {'id': cid, 'category': category, 'turns': list(turns)}


SPEC = [
    # ---- A. Individual stock analysis -------------------------------------------------------
    case('ind-01', 'individual', turn('Show all four metrics for 0700.HK.', four('0700.HK'))),
    case('ind-02', 'individual', turn('Show the four core metrics for Tencent Music Entertainment.', four('1698.HK'))),
    case('ind-03', 'individual', turn('What is the historical volatility of 9988.HK using a 60-trading-day window?',
                                      four('9988.HK', 60, [VOL]))),
    case('ind-04', 'individual', turn("What are Lenovo's (0992.HK) revenue growth and net profit margin?",
                                      four('0992.HK', only=[GROWTH, MARGIN]))),
    case('ind-05', 'individual', turn("Show NIO's (9866.HK) debt-to-equity ratio and net profit margin.",
                                      four('9866.HK', only=[DEBT, MARGIN]))),
    case('ind-06', 'individual', turn('Show all four metrics for 0300.HK and explain any missing data.', four('0300.HK'))),
    case('ind-07', 'individual', turn('Show all four metrics for 0100.HK. Is the volatility based on a full 252-day history?',
                                      four('0100.HK'),
                                      label('0100.HK volatility history status', 'ticker_metrics', {'ticker': '0100.HK'},
                                            [M, VOL, 'status'], {'ok': 'FULL', 'short_history': 'SHORT'}))),
    case('ind-08', 'individual', turn("Show Tencent's (0700.HK) ROE, equity growth, debt growth and change in profit margin.",
                                      trend('0700.HK', 'return_on_equity', 'equity_growth', 'debt_growth', 'profit_margin_change'))),
    case('ind-09', 'individual', turn('Compare the net profit margin and debt-to-equity of 0700.HK and 9999.HK.',
                                      four('0700.HK', only=[MARGIN, DEBT]), four('9999.HK', only=[MARGIN, DEBT]))),
    case('ind-10', 'individual', turn('What is the return correlation between 0700.HK and 9988.HK over the last 60 sessions?',
                                      num('0700/9988 correlation (60)', 'stock_correlation',
                                          {'ticker': '0700.HK', 'other_ticker': '9988.HK', 'window': 60}, 'correlation'))),
    case('ind-11', 'individual', turn('请显示小米（1810.HK）的四个核心指标。', four('1810.HK'))),
    # ---- B. Screening and ranking -----------------------------------------------------------
    case('rank-01', 'ranking', turn('Rank the top 5 stocks using the default weights.', rank(top_k=5))),
    case('rank-02', 'ranking', turn('Return the top 5 stocks with net profit margin at least 10% and debt-to-equity at most 0.5.',
                                    rank(top_k=5, filters={'net_profit_margin': {'min': 10}, 'debt_to_equity': {'max': 0.5}}))),
    case('rank-03', 'ranking', turn('Rank the top 3 stocks using revenue growth weight 2 and historical volatility weight 1.',
                                    rank(top_k=3, weights={'revenue_growth': 2, 'historical_volatility': 1}))),
    case('rank-04', 'ranking', turn('Rank the top 5 stocks using only debt-to-equity.',
                                    rank(top_k=5, weights={'debt_to_equity': 1}))),
    case('rank-05', 'ranking', turn('Rank the top 10 stocks using the default weights.', rank(top_k=10))),
    case('rank-06', 'ranking', turn('Among stocks with revenue growth of at least 20%, rank the top 5 using the default weights.',
                                    rank(top_k=5, filters={'revenue_growth': {'min': 20}}))),
    case('rank-07', 'ranking', turn('Which 3 stocks have the lowest historical volatility? Rank using only historical volatility.',
                                    rank(top_k=3, weights={'historical_volatility': 1}))),
    case('rank-08', 'ranking', turn('Rank the top 5 stocks with net profit margin at least 50%.',
                                    behavior('reports that no stock passes the filter', NO_MATCH))),
    case('rank-09', 'ranking', turn('I prefer profitable, low-debt companies. Require net profit margin of at least 5% and '
                                    'debt-to-equity of at most 0.3, weight net profit margin and debt-to-equity equally and '
                                    'ignore the other metrics. Give me the top 3.',
                                    rank(top_k=3, weights={'net_profit_margin': 1, 'debt_to_equity': 1},
                                         filters={'net_profit_margin': {'min': 5}, 'debt_to_equity': {'max': 0.3}}))),
    # ---- C. Historical trend analysis -------------------------------------------------------
    case('trend-01', 'trend', turn("Show 0700.HK's RSI, MACD line, 50-day moving average and 12-month return.",
                                   price('0700.HK', 'rsi_14', 'macd', 'sma_50', 'return_12m'))),
    case('trend-02', 'trend', turn("Is 0700.HK's latest adjusted close above or below its 50-day simple moving average? "
                                   'Begin your answer with exactly one word, ABOVE or BELOW, then explain.',
                                   label('0700.HK price vs SMA50', 'price_analysis', {'ticker': '0700.HK'},
                                         ['trend_comparison', 'price_above_sma_50'], {'True': 'ABOVE', 'False': 'BELOW'}))),
    case('trend-03', 'trend', turn("Is SMIC's (0981.HK) 50-day moving average above or below its 200-day moving average? "
                                   'Begin your answer with exactly one word, ABOVE or BELOW, then explain.',
                                   label('0981.HK SMA50 vs SMA200', 'price_analysis', {'ticker': '0981.HK'},
                                         ['trend_comparison', 'sma_50_above_sma_200'], {'True': 'ABOVE', 'False': 'BELOW'}))),
    case('trend-04', 'trend', turn('What was the maximum drawdown of 9988.HK over the last 60 trading sessions?',
                                   price('9988.HK', 'maximum_drawdown', window=60))),
    case('trend-05', 'trend', turn('Show the 1-month, 3-month and 6-month price returns of 0981.HK.',
                                   price('0981.HK', 'return_1m', 'return_3m', 'return_6m'))),
    case('trend-06', 'trend', turn('Did 1810.HK have a 50/200-day moving-average crossover in the latest session? '
                                   'Begin your answer with exactly one word: UP, DOWN or NONE.',
                                   label('1810.HK latest 50/200 crossover', 'price_analysis', {'ticker': '1810.HK'},
                                         ['trend_comparison', 'latest_50_200_crossover'],
                                         {'up': 'UP', 'down': 'DOWN', 'none': 'NONE'}))),
    case('trend-07', 'trend', turn("How does 1810.HK's latest trading volume compare with its previous 20-session average? "
                                   'Give the ratio.', price('1810.HK', 'volume_ratio_20'))),
    case('trend-08', 'trend', turn("What is Meituan's (3690.HK) latest 20-day rolling annualized volatility and its RSI?",
                                   price('3690.HK', 'rolling_volatility', 'rsi_14'))),
    case('trend-09', 'trend', turn('Will 0700.HK go up next month? Give me a price target.',
                                   behavior('declines to predict future prices', NO_PREDICTION))),
    case('trend-10', 'trend', turn('Show the 1-month and 12-month price returns of 0100.HK.',
                                   price('0100.HK', 'return_1m', 'return_12m'))),
    # ---- D. Contextual follow-ups (scored on the last turn) ----------------------------------
    case('follow-01', 'followup', turn('Show all four metrics for 0700.HK.', four('0700.HK')),
         turn('Now use 60 trading days for volatility.', four('0700.HK', 60, [VOL]))),
    case('follow-02', 'followup', turn('Rank the top 5 stocks using the default weights.', rank(top_k=5)),
         turn('Keep the same weights, but now require debt-to-equity of at most 0.3.',
              rank(top_k=5, filters={'debt_to_equity': {'max': 0.3}}))),
    case('follow-03', 'followup',
         turn('Rank the top 3 stocks with net profit margin of at least 10%.',
              rank(top_k=3, filters={'net_profit_margin': {'min': 10}})),
         turn('Using the same filter and weights, show the top 6 instead.',
              rank(top_k=6, filters={'net_profit_margin': {'min': 10}}))),
    case('follow-04', 'followup', turn("What is 0700.HK's RSI?", price('0700.HK', 'rsi_14')),
         turn('And the same indicator for Alibaba?', price('9988.HK', 'rsi_14'))),
    case('follow-05', 'followup', turn('Rank the top 5 stocks using the default weights.', rank(top_k=5)),
         turn('What is the return on equity of the top-ranked one?', {'type': 'top_ranked_roe'})),
    case('follow-06', 'followup',
         turn('Compare the net profit margin of 0700.HK and 9999.HK.',
              four('0700.HK', only=[MARGIN]), four('9999.HK', only=[MARGIN])),
         turn('For those same two companies, give the historical volatility over 120 trading days.',
              four('0700.HK', 120, [VOL]), four('9999.HK', 120, [VOL]))),
    # ---- E. Invalid or incomplete inputs ----------------------------------------------------
    case('invalid-01', 'invalid', turn('Show all four metrics for AAPL.',
                                       behavior('says AAPL is not in the supported universe', UNSUPPORTED, forbid_numeric_claims=True))),
    case('invalid-02', 'invalid', turn('Show the metrics.',
                                       behavior('asks which ticker', ASK_TICKER, forbid_numeric_claims=True))),
    case('invalid-03', 'invalid', turn('What is the P/E ratio of 0700.HK?',
                                       behavior('says P/E is not available', NOT_AVAILABLE))),
    case('invalid-04', 'invalid', turn('Show the historical volatility of 0700.HK using a window of 1 trading day.',
                                       behavior('rejects a 1-day volatility window', INVALID_ARG))),
    case('invalid-05', 'invalid', turn('Rank the top 5 stocks with revenue growth weight -1 and net profit margin weight 2.',
                                       behavior('rejects a negative weight', INVALID_ARG))),
    case('invalid-06', 'invalid', turn('Rank the top 5 semiconductor stocks.',
                                       behavior('says sector classification is unavailable', NO_SECTOR, NOT_AVAILABLE + UNSUPPORTED))),
    case('invalid-07', 'invalid', turn('Show all four metrics for 0005.HK.',
                                       behavior('says 0005.HK is not in the supported universe', UNSUPPORTED, forbid_numeric_claims=True))),
]


class Reference:
    """Resolve references by calling the deterministic tools directly (no LLM)."""

    def __init__(self):
        self.engine = TickerAgent()
        self.tools = AnalysisTools(self.engine)
        self.names = {s: r['company_name'] for s, r in self.engine.snapshot.items()}
        self.cache = {}

    def call(self, tool, arguments):
        key = json.dumps([tool, arguments], sort_keys=True)
        if key not in self.cache:
            if tool == 'ticker_metrics':
                self.cache[key] = self.engine.run(**arguments)
            else:
                self.cache[key] = getattr(self.tools, tool)(**arguments)
        return self.cache[key]

    def resolve(self, check, calls):
        kind = check['type']
        if kind == 'behavior':
            return dict(check)
        if kind == 'top_ranked_roe':
            top = self.call('rank_stocks', {'top_k': 5})['results'][0]['symbol']
            check = num('%s return_on_equity' % top, 'financial_trends', {'ticker': top}, M, 'return_on_equity')
            kind = 'number'
        tool, arguments = check['tool'], check['arguments']
        calls.append({'tool': tool, 'arguments': arguments})
        result = self.call(tool, arguments)
        if kind == 'ranking':
            full = self.call('rank_stocks', {**arguments, 'top_k': 30})
            return {'type': 'ranking', 'label': 'top %d' % arguments['top_k'], 'k': arguments['top_k'],
                    'expected': [r['symbol'] for r in result['results']],
                    'eligible': [r['symbol'] for r in full['results']],
                    'scores': {r['symbol']: round(r['score'], 4) for r in result['results']}}
        node = result
        for key in check['path']:
            node = node[key]
        if kind == 'label':
            return {'type': 'label', 'label': check['label'], 'expected': check['mapping'][str(node)],
                    'options': sorted(set(check['mapping'].values()))}
        value = node['value'] if isinstance(node, dict) else node
        if value is None:
            return {'type': 'unavailable', 'label': check['label'], 'reason': node.get('reason', '')}
        return {'type': 'number', 'label': check['label'], 'expected': value, 'unit': node.get('unit', '')}


def build():
    ref = Reference()
    cases = []
    for spec in SPEC:
        turns = []
        for t in spec['turns']:
            calls = []
            checks = [ref.resolve(c, calls) for c in t['checks']]
            unique = []
            for c in calls:
                if c not in unique:
                    unique.append(c)
            turns.append({'prompt': t['prompt'], 'reference_calls': unique, 'checks': checks})
        cases.append({'id': spec['id'], 'category': spec['category'], 'turns': turns})
    snapshot = next(iter(ref.engine.snapshot.values()))['snapshot_cutoff']
    return {'snapshot_cutoff': snapshot, 'latest_price_date': max(p['date'] for p in ref.engine.prices), 'cases': cases}


def load():
    return json.loads(CASES_FILE.read_text(encoding='utf-8'))


if __name__ == '__main__':
    data = build()
    CASES_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    checks = [c for case_ in data['cases'] for t in case_['turns'] for c in t['checks']]
    print('%d cases, %d checks -> %s' % (len(data['cases']), len(checks), CASES_FILE.name))
