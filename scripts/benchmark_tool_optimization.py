"""Compare two local source trees without a model or API key.

Scripted calls measure protocol overhead, not live LLM latency or accuracy.
Usage: python3 scripts/benchmark_tool_optimization.py --baseline /path/to/original
"""
import argparse
import hashlib
import json
import os
import statistics
import time
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k != 'calculated_at'}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def probe(root, batch):
    sys.path.insert(0, str(root / 'agent'))
    from agent import TickerAgent
    from analysis_tools import AnalysisTools
    from chat_agent import ChatAgent
    from evidence import model_result
    engine = TickerAgent()
    tools = AnalysisTools(engine)
    deterministic = []
    # All companies, short and long windows, missing data, charts and annual trends.
    for symbol in engine.snapshot:
        for window in (60, 252):
            deterministic.append(engine.run(symbol, window))
            deterministic.append(tools.price_analysis(symbol, window=window))
        deterministic.append(tools.financial_trends(symbol))
    for kwargs in ({}, {'top_k': 30}, {'window': 60},
                   {'weights': {'net_profit_margin': 1}, 'filters': {
                       'net_profit_margin': {'min': 10}, 'debt_to_equity': {'max': 0.5}}},
                   {'weights': {'revenue_growth': 2, 'historical_volatility': 1}}):
        deterministic.append(tools.rank_stocks(**kwargs))
    deterministic.append(tools.stock_correlation('700', '9988', window=60))
    digest = hashlib.sha256(json.dumps(stable(deterministic), sort_keys=True,
                                      allow_nan=False).encode()).hexdigest()
    projection_digest = hashlib.sha256(json.dumps(stable([model_result(r) for r in deterministic]),
                                        sort_keys=True, allow_nan=False).encode()).hexdigest()
    sample = tools.price_analysis('0700.HK')
    projection_times = []
    for _ in range(100):
        started = time.perf_counter()
        model_result(sample)
        projection_times.append((time.perf_counter()-started)*1000)

    class RecordingAgent(ChatAgent):
        def __init__(self, *args, **kwargs):
            self.events = []
            super().__init__(*args, **kwargs)
        def record(self, event):
            self.events.append(event)
            super().record(event)

    scenarios = []
    with tempfile.TemporaryDirectory() as directory:
        for count in (1, 2, 3):
            requests = [{'tool': name, 'arguments': {'ticker': symbol}}
                        for symbol in ('0700.HK', '9988.HK', '1810.HK')[:count]
                        for name in ('ticker_metrics', 'price_analysis')]
            actions = ([{'tools': requests}] if batch else requests) + [
                {'answer': 'Scripted evidence summary. ' + ' '.join(
                    '[E%d]' % i for i in range(1, len(requests)+1))}]
            iterator = iter(actions)
            def call(*args, **kwargs):
                return {'choices': [{'message': {'content': json.dumps(next(iterator))}}]}
            agent = RecordingAgent('http://localhost:8000/v1',
                                   Path(directory)/('%s.jsonl' % count), call)
            agent.ask('Overview ' + ', '.join(('0700.HK', '9988.HK', '1810.HK')[:count]))
            events = agent.events
            scenarios.append({
                'companies': count,
                'model_calls': sum(e['event'] == 'model' for e in events),
                'tool_calculations': sum(e['event'] == 'metric_calculation' for e in events),
                'model_input_chars': sum(sum(len(m['content']) for m in e['messages'])
                                         for e in events if e['event'] == 'model_start'),
                'evidence_sha256': hashlib.sha256(json.dumps(
                    stable(agent.evidence), sort_keys=True).encode()).hexdigest(),
                'charts': sum(bool(e['result'].get('chart')) for e in agent.evidence),
            })
        requests = [{'tool': 'ticker_metrics', 'arguments': {'ticker': ticker}}
                    for ticker in ('700', '0700.HK')]
        iterator = iter(requests + [{'answer': 'Same company. [E1]'}])
        agent = RecordingAgent('http://localhost:8000/v1', Path(directory)/'duplicate.jsonl', call)
        agent.ask('Metrics 0700.HK')
        duplicate = {'tool_calculations': sum(e['event'] == 'metric_calculation' for e in agent.events),
                     'evidence_cards': len(agent.evidence)}
    payloads = []
    for top_k in (5, 10, 30):
        raw = tools.rank_stocks(top_k=top_k)
        projected = model_result(raw)
        payloads.append({'top_k': top_k,
                         'model_result_chars': len(json.dumps(projected, ensure_ascii=False)),
                         'full_evidence_chars': len(json.dumps(stable(raw), ensure_ascii=False))})
    return {'deterministic_outputs': len(deterministic), 'deterministic_sha256': digest,
            'model_projection_sha256': projection_digest,
            'model_projection_median_ms': statistics.median(projection_times),
            'scripted_scenarios': scenarios, 'duplicate_request': duplicate,
            'ranking_payloads': payloads,
            'source_sha256': {name: hashlib.sha256((root/'agent'/name).read_bytes()).hexdigest()
                              for name in ('chat_agent.py', 'evidence.py', 'tool_registry.py')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path,
                        default=Path('docs/validation/tool-optimization.json'))
    parser.add_argument('--probe', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--batch', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe(args.probe.resolve(), args.batch)))
        return
    if not args.baseline or not (args.baseline/'agent/chat_agent.py').is_file():
        parser.error('--baseline must be the extracted original repository directory')
    root = Path(__file__).resolve().parents[1]
    def run(path, batch=False):
        cmd = [sys.executable, str(Path(__file__).resolve()), '--probe', str(path)]
        if batch:
            cmd.append('--batch')
        # Tool exclusions contain lists built from sets. Fix hash ordering so a
        # cross-process comparison does not mistake order noise for a regression.
        return json.loads(subprocess.check_output(cmd, text=True,
                          env=dict(os.environ, PYTHONHASHSEED='0')))
    baseline, optimized = run(args.baseline.resolve()), run(root, True)
    same = baseline['deterministic_sha256'] == optimized['deterministic_sha256']
    comparison = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'offline-scripted-no-llm',
        'notice': 'Scripted actions do not measure model adoption, answer quality, tokens or live latency. '
                  'Character counts are not token counts. Timestamps excluded from deterministic hashes.',
        'deterministic_outputs_equal': same,
        'model_projections_equal': baseline['model_projection_sha256'] == optimized['model_projection_sha256'],
        'baseline': baseline, 'optimized': optimized,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    if not same:
        raise SystemExit('Deterministic tool output regression detected')


if __name__ == '__main__':
    main()
