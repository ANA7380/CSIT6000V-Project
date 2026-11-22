"""Check downloaded live-smoke values against the independent frozen-data reference.

Usage: python3 scripts/check_server_results.py var/tacc-results/JOB/live-smoke.json
This verifies calculations and actual tool arguments, not qualitative LLM prose.
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evaluation'))
import reference


def check(path):
    run = json.loads(path.read_text())
    if run.get('state') != 'passed' or run.get('scripted') is not False:
        raise ValueError('Expected a completed, real-model smoke run')
    report = dict(numeric_checks=[], ranking_checks=[], chart_checks=[])
    for turn in run['turns']:
        if turn['response'].get('fallback'):
            raise ValueError('Smoke explanation used fallback')
        for item in turn['response']['evidence']:
            if item.get('reused'):
                continue
            args = item['arguments']
            if item['tool'] == 'rank_stocks':
                actual = [r['symbol'] for r in item['ranking']]
                expected = [r['symbol'] for r in reference.ranking(**args)]
                report['ranking_checks'].append(dict(top_k=args['top_k'], symbols=actual, passed=actual == expected))
            elif item['tool'] in ('ticker_metrics', 'price_analysis'):
                expected = (reference.core if item['tool'] == 'ticker_metrics' else reference.trend)(args['ticker'], args.get('window', 252))
                names = set(expected) if item['tool'] == 'ticker_metrics' else {'sma_20','sma_50','sma_200','maximum_drawdown'}
                for metric in item['metrics']:
                    name = metric['name']
                    if name not in names:
                        continue
                    actual, target = metric['value'], expected[name]
                    passed = actual is target if target is None else isinstance(actual, (int,float)) and math.isclose(actual, target, rel_tol=1e-9, abs_tol=1e-9)
                    report['numeric_checks'].append(dict(metric=name, actual=actual, reference=target, passed=passed))
                if item['tool'] == 'price_analysis':
                    count = len(item['chart']['dates'])
                    report['chart_checks'].append(dict(points=count, passed=count == args['window'] + 1))
    groups = list(report.values())
    report['passed'] = all(groups) and all(c['passed'] for group in groups for c in group)
    if not report['passed']:
        raise ValueError('Independent calculation check failed: ' + json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.result)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)
