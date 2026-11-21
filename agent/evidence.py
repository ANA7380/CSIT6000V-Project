"""Validate answer structure and evidence references, not numerical semantics.

Numbers, dates, tickers and derived calculations are allowed in model prose.
Tables and charts remain deterministic; prose accuracy requires evaluation/review.
"""
import copy
import json
import re


class GroundingError(ValueError):
    pass


def validate_answer(answer, evidence, requested_ids=None, require_evidence=False):
    if not isinstance(answer, str) or not answer.strip():
        raise GroundingError('Answer must be nonempty text.')
    known = {item['id']: item for item in evidence}
    cited = set(re.findall(r'\[(E\d+)\]', answer)) | set(requested_ids or [])
    if cited - known.keys():
        raise GroundingError('Unknown evidence IDs: ' + ', '.join(sorted(cited - known.keys())))
    if require_evidence and not cited:
        raise GroundingError('Cite available results as [E1], or call a tool before answering this data request.')
    # Numeric accuracy is evaluated against references, not inferred from digit
    # presence: dates, rounding, derived values and scenario assumptions are valid.
    if re.search(r'https?://', answer):
        raise GroundingError('Source links are rendered from tools; do not invent links in prose.')
    return sorted(cited, key=lambda x: int(x[1:]))


def model_result(result):
    out = copy.deepcopy(result)
    out.pop('financial_observations', None)
    out.pop('chart', None)
    if 'metrics' in out and 'rolling_volatility' in out['metrics']:
        rolling = out['metrics']['rolling_volatility']
        rolling['series_points_logged'] = len(rolling.get('series', []))
        rolling['series'] = rolling.get('series', [])[-5:]
    for row in out.get('results', []):
        for m in row.get('metric_details', {}).values():
            for key in ('inputs', 'source_url'):
                m.pop(key, None)
    return out


def metric_rows(result):
    rows = []
    source = result.get('metrics', {})
    if 'correlation' in result:
        source = {'correlation': result['correlation']}
    for name, value in source.items():
        if not isinstance(value, dict):
            continue
        period = {k: value[k] for k in ('period_end', 'prior_period_end', 'period_type',
                  'start_date', 'end_date', 'requested_returns', 'returns_used', 'currency') if k in value}
        rows.append({'name': name, 'value': value.get('value'), 'unit': value.get('unit', ''),
                     'status': value.get('status', 'unavailable'), 'reason': value.get('reason'),
                     'period': period, 'formula': value.get('formula', ''),
                     'source_url': value.get('source_url') or result.get('source_url'),
                     'details': {k: v for k, v in value.items() if k not in
                                 {'value', 'unit', 'status', 'reason', 'formula', 'series'}}})
    return rows


def view(item):
    r = item['result']
    return {'id': item['id'], 'tool': item['tool'], 'arguments': item['arguments'],
            'symbol': r.get('symbol'), 'company': r.get('company'),
            'snapshot_cutoff': r.get('snapshot_cutoff'), 'as_of': r.get('as_of'),
            'metrics': metric_rows(r), 'chart': r.get('chart'),
            'ranking': r.get('results'), 'excluded': r.get('excluded', []),
            'weights': r.get('weights'), 'filters': r.get('filters'),
            'eligible_count': r.get('eligible_count'), 'trend_comparison': r.get('trend_comparison'),
            'lookup': r if item['tool'] == 'list_tickers' else None,
            'caveats': r.get('caveats', []), 'notes': r.get('notes', []),
            'reused': item.get('reused', False)}


def render_text(views, chinese=False):
    lines = ['\n' + ('工具证据与计算结果' if chinese else 'Tool evidence and calculated results')]
    if not views:
        return '\n'.join(lines + ['本轮未执行工具，无新增计算。' if chinese else 'No tools called; no new calculations.'])
    for item in views:
        lines.append(f"[{item['id']}] {item['tool']} {json.dumps(item['arguments'], ensure_ascii=False)}" +
                     (' (reused earlier result)' if item['reused'] else ''))
        if item['snapshot_cutoff']:
            lines.append('Snapshot: ' + item['snapshot_cutoff'])
        if item['as_of']:
            lines.append('Price as of: ' + item['as_of'])
        for row in item['metrics']:
            value = 'N/A' if row['value'] is None else format(row['value'], '.8g')
            lines.append(f"  {row['name']}: {value} {row['unit']} [{row['status']}] " +
                         json.dumps(row['period'], ensure_ascii=False) +
                         (' — ' + row['reason'] if row['reason'] else ''))
            if row['source_url']:
                lines.append('  Source: ' + row['source_url'])
            extra = {k: v for k, v in row['details'].items() if k in ('signal', 'histogram', 'peak_date', 'trough_date', 'price_distance_pct')}
            if extra:
                lines.append('  ' + json.dumps(extra, ensure_ascii=False))
        if item['ranking'] is not None:
            lines.append('Weights: ' + json.dumps(item['weights']))
            for row in item['ranking']:
                lines.append(f"  #{row['rank']} {row['symbol']}: {row['score']:.8g}; " +
                             json.dumps({'values': row['values'], 'percentiles': row['percentile_scores'],
                                         'contributions': row['contributions'], 'periods': {
                                             k: {p: m[p] for p in ('period_end', 'period_type', 'start_date', 'end_date') if p in m}
                                             for k, m in row['metric_details'].items()}}, ensure_ascii=False))
            lines.append('Excluded: ' + json.dumps(item['excluded'], ensure_ascii=False))
        if item['trend_comparison']:
            lines.append('Historical signals: ' + json.dumps(item['trend_comparison']))
        for row in item['metrics']:
            if row['formula']:
                lines.append('  Formula: ' + row['name'] + ' — ' + row['formula'])
            if row['details'].get('inputs'):
                lines.append('  Inputs: ' + json.dumps(row['details']['inputs'], ensure_ascii=False))
        if item['lookup'] is not None:
            lines.append('Lookup: ' + json.dumps(item['lookup'], ensure_ascii=False))
        lines.extend(item['caveats'] + item['notes'])
    lines.append('固定历史快照；指标不构成未来价格预测。' if chinese else 'Fixed historical snapshot; indicators do not predict future prices.')
    return '\n'.join(lines)
