"""Run the evaluation cases against one system and save raw transcripts.

Systems
  agent    the project's tool-augmented ChatAgent (proposed system)
  notools  the same LLM transport answering directly, with no tools (baseline)

Examples
  python run_eval.py --system agent   --provider qwen --base-url http://NODE:8000/v1
  python run_eval.py --system notools --provider deepseek
  python run_eval.py --system notools --provider deepseek --context raw
"""
import argparse
import json
import os
import time
from pathlib import Path

from common import EVAL_DIR, AGENT_DIR, flatten_numbers
import cases as case_module
from agent import TickerAgent
from chat_agent import ChatAgent

BASELINE_SYSTEM = (
    'You are a financial analysis assistant for Hong Kong-listed technology stocks '
    '(the 30 Hang Seng TECH constituents). Questions refer to a fixed dataset snapshot collected on '
    '2026-11-18, with daily prices through 2026-11-17. You have no tools. '
    'Use the language of the user\'s latest message. '
    'Reply with ONLY a JSON object of the form {"answer": "your response"}.')
TRANSPORT_MARKERS = ('Cannot reach', 'HTTP', 'invalid JSON', 'no text answer', 'truncated')


class Meter:
    """Wrap a chat transport to count calls, tokens and model time."""

    def __init__(self, call):
        self.call = call
        self.reset()

    def reset(self):
        self.calls, self.seconds, self.prompt_tokens, self.completion_tokens = 0, 0.0, 0, 0

    def __call__(self, messages, base_url, **kwargs):
        start = time.perf_counter()
        try:
            response = self.call(messages, base_url, **kwargs)
        finally:
            self.seconds += time.perf_counter() - start
            self.calls += 1
        usage = response.get('usage') or {}
        self.prompt_tokens += usage.get('prompt_tokens') or 0
        self.completion_tokens += usage.get('completion_tokens') or 0
        return response


class RecordingAgent(ChatAgent):
    """ChatAgent that also keeps its audit events in memory for scoring."""

    def __init__(self, *args, **kwargs):
        self.events = []
        super().__init__(*args, **kwargs)

    def record(self, event):
        self.events.append(event)
        super().record(event)


class AgentSystem:
    def __init__(self, call, base_url, log):
        self.meter = Meter(call)
        self.agent = RecordingAgent(base_url, log, self.meter)

    def ask(self, prompt):
        self.agent.events.clear()
        self.explanation = None
        answer = self.agent.ask(prompt)       # explanation followed by the rendered tool evidence
        self.explanation = (self.agent.last_response or {}).get('answer')
        return answer

    def trace(self):
        events = self.agent.events
        tools = [{'tool': e['tool'], 'arguments': e['arguments'], 'ok': 'error' not in e}
                 for e in events if e['event'] == 'tool_result']
        evidence = []
        for e in events:                      # only what the model was actually shown
            if e['event'] == 'tool_result' and 'result' in e:
                flatten_numbers(e['result'], evidence)
        return {'explanation': self.explanation, 'tool_calls': tools,
                'format_errors': sum(e['event'] == 'model_format_error' for e in events),
                'validation_errors': sum(e['event'] == 'answer_validation_error' for e in events),
                'fallback': bool((self.agent.last_response or {}).get('fallback')),
                'evidence': sorted(set(round(x, 8) for x in evidence))}


class NoToolsSystem:
    def __init__(self, call, base_url, context=''):
        self.meter = Meter(call)
        self.base_url = base_url
        self.messages = [{'role': 'system', 'content': BASELINE_SYSTEM + context}]

    def ask(self, prompt):
        start = len(self.messages)
        self.messages.append({'role': 'user', 'content': prompt})
        try:
            response = self.meter(self.messages, self.base_url, max_tokens=1800, temperature=0)
        except Exception:
            del self.messages[start:]
            raise
        content = response['choices'][0]['message']['content']
        self.messages.append({'role': 'assistant', 'content': content})
        return parse_plain_answer(content)

    def trace(self):
        return {'tool_calls': [], 'format_errors': 0, 'evidence': []}


def parse_plain_answer(content):
    text = content.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get('answer'), str):
            return data['answer']
    except ValueError:
        pass
    return content


FIN_COLUMNS = ['symbol', 'company_name', 'financial_period_end', 'financial_period_type', 'financial_currency',
               'revenue', 'prior_year_revenue', 'prior_year_period_end', 'net_income',
               'balance_sheet_date', 'total_debt', 'stockholders_equity']
PRICE_TOOLS = {'ticker_metrics', 'price_analysis', 'stock_correlation'}


def raw_context(case, engine):
    """Raw inputs (never computed metrics) so a tool-less model can attempt the arithmetic.

    Financial inputs for all 30 companies, plus full price history for at most two
    tickers the case needs. Ranking cases therefore lack price data (32K context limit).
    """
    lines = ['\n\nRAW DATASET (inputs only; blank means unavailable):', ','.join(FIN_COLUMNS)]
    for row in engine.snapshot.values():
        lines.append(','.join(str(row.get(c, '')).replace(',', ' ') for c in FIN_COLUMNS))
    tickers = []
    for t in case['turns']:
        for call in t['reference_calls']:
            if call['tool'] in PRICE_TOOLS:
                for key in ('ticker', 'other_ticker'):
                    symbol = call['arguments'].get(key)
                    if symbol and symbol not in tickers:
                        tickers.append(symbol)
    if 0 < len(tickers) <= 2:
        for symbol in tickers:
            lines.append('\nDAILY PRICES %s: date,adjusted_close,volume' % symbol)
            rows = sorted((p for p in engine.prices if p['symbol'] == symbol), key=lambda p: p['date'])
            lines += ['%s,%s,%s' % (p['date'], p['adjusted_close'], p['volume']) for p in rows]
    return '\n'.join(lines)


def transports(provider, base_url):
    if provider == 'deepseek':
        from deepseek_client import chat, BASE_URL
        if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
            raise SystemExit('Set DEEPSEEK_API_KEY in this terminal first.')
        return chat, BASE_URL, os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')
    from qwen_client import chat, normalize_base_url
    url = base_url or os.environ.get('QWEN_BASE_URL') or (AGENT_DIR / 'server-url.txt').read_text(encoding='utf-8-sig')
    return chat, normalize_base_url(url), 'qwen3.8-27b'


def run_case(case, make_system):
    system = make_system(case)
    turns = []
    for t in case['turns']:
        system.meter.reset()
        record = {'prompt': t['prompt'], 'answer': None, 'error': None}
        start = time.perf_counter()
        try:
            record['answer'] = system.ask(t['prompt'])
        except Exception as exc:            # a failed turn is a data point, not a crash
            record['error'] = '%s: %s' % (type(exc).__name__, exc)
            record['error_kind'] = 'transport' if any(m in str(exc) for m in TRANSPORT_MARKERS) else 'agent'
        record['latency_s'] = round(time.perf_counter() - start, 3)
        record.update(model_calls=system.meter.calls, model_seconds=round(system.meter.seconds, 3),
                      prompt_tokens=system.meter.prompt_tokens, completion_tokens=system.meter.completion_tokens)
        record.update(system.trace())
        turns.append(record)
    return turns


def transport_failed(turns):
    return any(t.get('error_kind') == 'transport' for t in turns)


def run(label, cases, make_system, out, meta, only=None, stop_after=3, quiet=False):
    """Run cases, appending one JSON line each. Finished cases are skipped on rerun."""
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if transport_failed(row['turns']):
                done.discard(row['case_id'])       # retry cases the service never answered
            else:
                done.add(row['case_id'])
    consecutive = 0
    for case in cases:
        if case['id'] in done or (only and case['id'] not in only):
            continue
        turns = run_case(case, make_system)
        row = {'system': label, 'case_id': case['id'], 'category': case['category'], 'turns': turns, **meta}
        with out.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        status = 'ERROR' if any(t['error'] for t in turns) else 'ok'
        quiet or print('%-11s %-5s %6.1fs  %d model call(s)' % (case['id'], status, sum(t['latency_s'] for t in turns),
                                                       sum(t['model_calls'] for t in turns)), flush=True)
        consecutive = consecutive + 1 if transport_failed(turns) else 0
        if consecutive >= stop_after:
            raise SystemExit('Stopped: %d consecutive transport errors. Check the model service, then rerun '
                             'the same command to resume.' % stop_after)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--system', choices=['agent', 'notools'], required=True)
    parser.add_argument('--provider', choices=['qwen', 'deepseek'], required=True)
    parser.add_argument('--base-url', help='Qwen service URL; defaults to QWEN_BASE_URL or agent/server-url.txt')
    parser.add_argument('--context', choices=['none', 'raw'], default='none',
                        help='notools only: also give the model the raw dataset inputs')
    parser.add_argument('--out-dir', type=Path, default=EVAL_DIR / 'results')
    parser.add_argument('--only', nargs='*', help='run only these case ids')
    args = parser.parse_args()
    if args.system == 'agent' and args.context != 'none':
        parser.error('--context applies to --system notools only')
    call, base_url, model = transports(args.provider, args.base_url)
    label = '%s-%s' % (args.system, args.provider) + ('-raw' if args.context == 'raw' else '')
    data = case_module.load()
    engine = TickerAgent()
    log_dir = args.out_dir / 'audit'

    def make_system(case):
        if args.system == 'agent':
            return AgentSystem(call, base_url, log_dir / ('%s-%s.jsonl' % (label, case['id'])))
        return NoToolsSystem(call, base_url, raw_context(case, engine) if args.context == 'raw' else '')

    meta = {'provider': args.provider, 'model': model, 'context': args.context,
            'temperature': 0, 'max_tokens': 1800, 'snapshot_cutoff': data['snapshot_cutoff']}
    out = run(label, data['cases'], make_system, args.out_dir / (label + '.jsonl'), meta, args.only)
    print('RESULT_FILE=%s' % out)


if __name__ == '__main__':
    main()
