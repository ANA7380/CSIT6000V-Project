"""Score raw transcripts from run_eval.py against cases.json.

  python score.py                      # every results/*.jsonl
  python score.py results/a.jsonl ...  # chosen files
Writes results/summary.md, results/per_check.csv and results/failures.md.
"""
import argparse
import csv
import json
import re
import statistics
from collections import OrderedDict
from pathlib import Path

from common import EVAL_DIR, close_enough, extract_numbers, has_number, numeric_claims, supported, flatten_numbers, mentioned_tickers
import cases as case_module

UNAVAILABLE_WORDS = ['n/a', 'unavailable', 'not available', 'missing', 'insufficient', 'cannot be calculated',
                     'could not be calculated', 'not meaningful', 'no comparable', 'not enough', 'cannot calculate',
                     '无法', '缺失', '不可用', '不足', '缺少', '没有']


def model_view(result):
    """Trim a tool result the way ChatAgent.dispatch does before showing it to the model."""
    view = {k: v for k, v in result.items() if k != 'financial_observations'}
    rolling = view.get('metrics', {}).get('rolling_volatility') if isinstance(view.get('metrics'), dict) else None
    if isinstance(rolling, dict) and 'series' in rolling:
        view = json.loads(json.dumps(view))
        view['metrics']['rolling_volatility']['series'] = view['metrics']['rolling_volatility']['series'][-5:]
    return view


def check_turn(check, answer, names):
    """Return (passed, detail dict) for one check against one answer."""
    kind = check['type']
    # Models often write typographic apostrophes (can’t); keyword lists use plain ones.
    low = answer.lower().replace('\u2019', "'").replace('\u2018', "'")
    if kind == 'number':
        return has_number(answer, check['expected']), {}
    if kind == 'unavailable':
        return any(w in low for w in UNAVAILABLE_WORDS), {}
    if kind == 'behavior':
        ok = all(any(w in low for w in group) for group in check['groups'])
        if ok and check.get('forbid_numeric_claims') and numeric_claims(answer):
            ok = False
        return ok, {}
    if kind == 'label':
        first = re.sub(r'[^A-Za-z]', ' ', answer).split()
        present = [o for o in check['options'] if re.search(r'(?<![A-Za-z])%s(?![A-Za-z])' % o, answer)]
        ok = bool(first) and first[0].upper() == check['expected'] or present == [check['expected']]
        return ok, {}
    if kind == 'ranking':
        expected, k = check['expected'], len(check['expected'])
        got = mentioned_tickers(answer, names)[:k]
        hit = len(set(got) & set(expected))
        detail = {'precision': hit / k if k else 0.0,
                  'compliance': sum(s in check['eligible'] for s in got) / len(got) if got else 0.0,
                  'exact_order': got == expected, 'got': got}
        return hit == k, detail
    raise ValueError('Unknown check type ' + kind)


def latest_records(path):
    rows = OrderedDict()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row['case_id']] = row          # a rerun supersedes the earlier attempt
    return rows


def score_system(records, data, reference):
    names = reference.names
    checks, turns, claims_total, claims_ok, answers_with_claims = [], [], 0, 0, 0
    case_pass, followup = {}, []
    for case in data['cases']:
        record = records.get(case['id'])
        if record is None:
            continue
        evidence, prompts, all_ok, last_ok = [], '', True, True
        for index, (spec, turn) in enumerate(zip(case['turns'], record['turns'])):
            answer = turn['answer'] or ''
            prompts += ' ' + spec['prompt']
            for call in spec['reference_calls']:
                flatten_numbers(model_view(reference.call(call['tool'], call['arguments'])), evidence)
            evidence += turn.get('evidence', [])
            turn_ok = True
            for check in spec['checks']:
                passed, detail = (False, {}) if turn['error'] else check_turn(check, answer, names)
                if check['type'] == 'ranking' and turn['error']:
                    detail = {'precision': 0.0, 'compliance': 0.0, 'exact_order': False, 'got': []}
                turn_ok = turn_ok and passed
                checks.append({'case_id': case['id'], 'category': case['category'], 'turn': index + 1,
                               'type': check['type'], 'label': check.get('label', ''),
                               'expected': check.get('expected', ''), 'passed': passed, **detail,
                               'error': turn['error'] or '', 'answer': answer, 'prompt': spec['prompt']})
            claims = numeric_claims(answer, prompts)
            if claims:
                answers_with_claims += 1
                claims_total += len(claims)
                claims_ok += sum(supported(v, d, evidence) for v, d in claims)
            all_ok = all_ok and turn_ok
            last_ok = turn_ok
            turns.append(turn)
        case_pass[case['id']] = all_ok
        if case['category'] == 'followup':
            followup.append(last_ok)

    def rate(rows):
        return (sum(r['passed'] for r in rows), len(rows))

    def mean(values):
        values = list(values)
        return statistics.mean(values) if values else None

    numbers = [c for c in checks if c['type'] == 'number']
    rankings = [c for c in checks if c['type'] == 'ranking']
    trend = [c for c in checks if c['category'] == 'trend']
    latencies = sorted(t['latency_s'] for t in turns if not t['error'])
    categories = OrderedDict()
    for case in data['cases']:
        if case['id'] in case_pass:
            ok, n = categories.get(case['category'], (0, 0))
            categories[case['category']] = (ok + case_pass[case['id']], n + 1)
    return {
        'cases_run': len(case_pass), 'cases_total': len(data['cases']),
        'cases_passed': sum(case_pass.values()),
        'categories': categories,
        'numerical_accuracy': rate(numbers),
        'recommendation_precision': mean(c['precision'] for c in rankings),
        'constraint_compliance': mean(c['compliance'] for c in rankings),
        'exact_order': rate([dict(c, passed=c['exact_order']) for c in rankings]),
        'trend_grounding': rate(trend),
        'explanation_grounding': (claims_ok, claims_total), 'answers_with_claims': answers_with_claims,
        'followup_success': (sum(followup), len(followup)),
        'invalid_handling': rate([c for c in checks if c['category'] == 'invalid']),
        'latency_mean': mean(latencies), 'latency_median': statistics.median(latencies) if latencies else None,
        'latency_p90': latencies[min(len(latencies) - 1, int(0.9 * len(latencies)))] if latencies else None,
        'model_calls': mean(t['model_calls'] for t in turns),
        'tokens': mean(t['prompt_tokens'] + t['completion_tokens'] for t in turns),
        'turn_errors': sum(bool(t['error']) for t in turns),
        'transport_errors': sum(t.get('error_kind') == 'transport' for t in turns),
        'turns': len(turns), 'checks': checks,
    }


def frac(pair):
    ok, n = pair
    return 'n/a' if not n else '%.1f%% (%d/%d)' % (100 * ok / n, ok, n)


def pct(value):
    return 'n/a' if value is None else '%.1f%%' % (100 * value)


def secs(value):
    return 'n/a' if value is None else '%.1f s' % value


ROWS = [
    ('Cases fully passed', lambda s: frac((s['cases_passed'], s['cases_run']))),
    ('Numerical accuracy', lambda s: frac(s['numerical_accuracy'])),
    ('Recommendation quality: Top-K precision', lambda s: pct(s['recommendation_precision'])),
    ('Recommendation quality: constraint compliance', lambda s: pct(s['constraint_compliance'])),
    ('Recommendation quality: exact order', lambda s: frac(s['exact_order'])),
    ('Trend analysis grounding', lambda s: frac(s['trend_grounding'])),
    ('Explanation grounding (figures supported)', lambda s: frac(s['explanation_grounding'])),
    ('Follow-up success', lambda s: frac(s['followup_success'])),
    ('Invalid / incomplete input handling', lambda s: frac(s['invalid_handling'])),
    ('Response time per turn: mean', lambda s: secs(s['latency_mean'])),
    ('Response time per turn: median', lambda s: secs(s['latency_median'])),
    ('Response time per turn: p90', lambda s: secs(s['latency_p90'])),
    ('Model calls per turn', lambda s: 'n/a' if s['model_calls'] is None else '%.2f' % s['model_calls']),
    ('Tokens per turn', lambda s: 'n/a' if s['tokens'] is None else '%.0f' % s['tokens']),
    ('Failed turns (of which transport)', lambda s: '%d (%d) of %d' % (s['turn_errors'], s['transport_errors'], s['turns'])),
]


def write_reports(scores, metas, out_dir):
    names = list(scores)
    lines = ['# Evaluation summary', '', '| Metric | ' + ' | '.join(names) + ' |', '|---|' + '---|' * len(names)]
    lines.append('| Model | ' + ' | '.join(metas[n].get('model', '?') for n in names) + ' |')
    for title, fn in ROWS:
        lines.append('| %s | %s |' % (title, ' | '.join(fn(scores[n]) for n in names)))
    lines += ['', '## Cases fully passed by category', '',
              '| Category | ' + ' | '.join(names) + ' |', '|---|' + '---|' * len(names)]
    categories = []
    for n in names:
        categories += [c for c in scores[n]['categories'] if c not in categories]
    for c in categories:
        lines.append('| %s | %s |' % (c, ' | '.join(frac(scores[n]['categories'].get(c, (0, 0))) for n in names)))
    incomplete = [n for n in names if scores[n]['cases_run'] < scores[n]['cases_total'] or scores[n]['transport_errors']]
    if incomplete:
        lines += ['', '**Incomplete runs (do not report yet):** ' + ', '.join(
            '%s ran %d of %d cases with %d transport error(s)' % (
                n, scores[n]['cases_run'], scores[n]['cases_total'], scores[n]['transport_errors']) for n in incomplete)]
    lines += ['', 'Scoring is automatic and heuristic; see evaluation/README.md for what each metric does and does not measure.', '']
    (out_dir / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')

    fields = ['system', 'case_id', 'category', 'turn', 'type', 'label', 'expected', 'passed',
              'precision', 'compliance', 'exact_order', 'got', 'error']
    with (out_dir / 'per_check.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for n in names:
            for c in scores[n]['checks']:
                writer.writerow(dict(c, system=n, got=' '.join(c.get('got', []))))

    fail = ['# Failed checks', '', 'Use these to pick the failure case(s) for the report. '
            'Full transcripts are in the results/*.jsonl files and results/audit/.', '']
    for n in names:
        failed = [c for c in scores[n]['checks'] if not c['passed']]
        fail += ['## %s: %d failed check(s)' % (n, len(failed)), '']
        for c in failed:
            excerpt = ' '.join((c['error'] or c['answer']).split())[:400]
            fail += ['- **%s** turn %d, %s `%s` (expected `%s`)' % (c['case_id'], c['turn'], c['type'], c['label'], c['expected']),
                     '  - Prompt: %s' % c['prompt'], '  - Got: %s' % excerpt]
        fail.append('')
    (out_dir / 'failures.md').write_text('\n'.join(fail), encoding='utf-8')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='*', type=Path)
    parser.add_argument('--out-dir', type=Path, default=EVAL_DIR / 'results')
    args = parser.parse_args()
    files = args.files or sorted((EVAL_DIR / 'results').glob('*.jsonl'))
    if not files:
        raise SystemExit('No result files. Run run_eval.py first.')
    data, reference = case_module.load(), case_module.Reference()
    scores, metas = OrderedDict(), {}
    for path in files:
        records = latest_records(path)
        if not records:
            continue
        first = next(iter(records.values()))
        scores[first['system']] = score_system(records, data, reference)
        metas[first['system']] = first
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(write_reports(scores, metas, args.out_dir))


if __name__ == '__main__':
    main()
