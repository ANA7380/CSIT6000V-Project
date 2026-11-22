"""Independent frozen-data reference calculations. Does not import agent code.

Uses Decimal for financial ratios and explicit return-variance arithmetic. References
verify selected source inputs, not the correctness of upstream financial disclosures.
"""
import csv
from functools import lru_cache
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data' / 'snapshot_2026-11-18'


@lru_cache(maxsize=1)
def load():
    def read(name):
        with (DATA / ('hk_tech30_' + name + '.csv')).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    return {r['symbol']: r for r in read('snapshot')}, read('daily_prices')


def decimal(value):
    try:
        v = Decimal(str(value))
        return v if v.is_finite() else None
    except InvalidOperation:
        return None


@lru_cache(maxsize=256)
def core(symbol, window=252):
    snapshot, all_prices = load()
    r = snapshot[symbol]
    out = {}
    for name, top, bottom, percentage in [
        ('Revenue growth', 'revenue', 'prior_year_revenue', True),
        ('Net profit margin', 'net_income', 'revenue', True),
        ('Debt-to-equity', 'total_debt', 'stockholders_equity', False)]:
        a, b = decimal(r[top]), decimal(r[bottom])
        value = None
        if a is not None and b is not None and b > 0:
            value = a / b - (1 if name == 'Revenue growth' else 0)
            value = float(value * (100 if percentage else 1))
        out[name] = value
    rows = sorted([p for p in all_prices if p['symbol'] == symbol], key=lambda p: p['date'])[-window-1:]
    values = [decimal(p['adjusted_close']) for p in rows]
    out['Historical volatility'] = None
    out['_full_window'] = len(rows) == window+1
    if len(values) >= 3 and all(v is not None and v > 0 for v in values):
        returns = [math.log(float(b/a)) for a, b in zip(values, values[1:])]
        avg = sum(returns)/len(returns)
        variance = sum((v-avg)**2 for v in returns)/(len(returns)-1)
        out['Historical volatility'] = math.sqrt(variance*252)*100
    return out


NAMES = {'revenue_growth': 'Revenue growth', 'net_profit_margin': 'Net profit margin',
         'debt_to_equity': 'Debt-to-equity', 'historical_volatility': 'Historical volatility'}


def ranking(top_k=5, weights=None, filters=None, window=252, **ignored):
    weights = weights if weights is not None else dict.fromkeys(NAMES, 1)
    total = sum(weights.values())
    weights = {k: v/total for k, v in weights.items() if v > 0}
    filters = filters or {}
    candidates = []
    for symbol in load()[0]:
        values = core(symbol, window)
        required = set(weights) | set(filters)
        if any(values[NAMES[k]] is None or k == 'historical_volatility' and not values['_full_window'] for k in required):
            continue
        if any(not bounds.get('min', -math.inf) <= values[NAMES[k]] <= bounds.get('max', math.inf) for k, bounds in filters.items()):
            continue
        candidates.append((symbol, values))
    scores = {s: 0.0 for s, _ in candidates}
    for key, weight in weights.items():
        ordered = sorted(v[NAMES[key]] for _, v in candidates)
        for symbol, values in candidates:
            indices = [i for i, val in enumerate(ordered) if val == values[NAMES[key]]]
            p = 50 if len(ordered) == 1 else sum(indices)/len(indices)/(len(ordered)-1)*100
            scores[symbol] += weight*((100-p) if key in ('debt_to_equity', 'historical_volatility') else p)
    return [{'symbol': s, 'score': scores[s]} for s in sorted(scores, key=lambda s: (-scores[s], s))[:top_k]]


def trend(symbol, window=252):
    rows = sorted([p for p in load()[1] if p['symbol'] == symbol], key=lambda p: p['date'])
    p = [float(r['adjusted_close']) for r in rows]
    out = {f'sma_{n}': sum(p[-n:])/n if len(p) >= n else None for n in (20, 50, 200)}
    selected = p[-window-1:]
    # Independent all-prefix-peak definition rather than the runtime state loop.
    out['maximum_drawdown'] = min((v/max(selected[:i+1])-1)*100 for i, v in enumerate(selected)) if len(selected)>1 else None
    return out


def expected(calls, previous=None):
    facts, ranks = {}, []
    previous = dict(previous or {})
    for call in calls:
        name, args = call['tool'], dict(call.get('arguments', {}))
        if name == 'ticker_metrics':
            values = core(args['ticker'], args.get('window', 252))
            facts.update({args['ticker']+'/'+k: v for k,v in values.items() if not k.startswith('_')})
        elif name == 'price_analysis':
            facts.update({args['ticker']+'/'+k: v for k,v in trend(args['ticker'], args.get('window',252)).items()})
        elif name == 'rank_stocks':
            if args.pop('reuse_previous', False):
                args = dict(previous, **args)
            previous = args
            ranks = ranking(**args)
    return {'facts': facts, 'ranking': ranks, 'previous': previous}
