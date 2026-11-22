#!/usr/bin/env python3
"""Diagnose the stock Agent bridge without browser history; Python 3.9+.

Run with the bridge already serving in another terminal:
    python3 scripts/check_main_web.py --port 8767 --case ok
    python3 scripts/check_main_web.py --port 8767 --case trend
Each run submits exactly one new request and saves its UUID, progress and reply.
Stopping this client does not cancel remote inference or the TACC allocation.
"""
import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4


CASES = {
    'ok': '只回复 OK。',
    'metrics': '展示 0700.HK 的四项核心财务指标，历史波动率使用 60 个日收益率。请调用工具并简短回答。',
    'trend': '分析 0700.HK 的历史走势，展示均线和 RSI，不要预测未来。请调用 price_analysis 工具并简短回答。',
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check_response(case, data):
    if data.get('error'):
        raise RuntimeError('Worker returned an error: ' + str(data['error']))
    text = data.get('explanation') or data.get('answer')
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError('Completed response has no answer.')
    if case == 'ok':
        if 'OK' not in text.upper():
            raise RuntimeError('A reply arrived, but it did not contain the requested OK.')
        return
    tool = 'ticker_metrics' if case == 'metrics' else 'price_analysis'
    matches = [e for e in data.get('evidence', [])
               if e.get('tool') == tool and e.get('symbol') == '0700.HK']
    if not matches:
        raise RuntimeError('Reply arrived without expected tool evidence: ' + tool)
    if case == 'trend':
        fields = {m['name']: m for e in matches for m in e.get('metrics', [])}
        for name in ('sma_20', 'sma_50', 'sma_200', 'rsi_14'):
            metric = fields.get(name, {})
            value = metric.get('value')
            if metric.get('status') != 'ok' or type(value) not in (int, float) or not math.isfinite(value):
                raise RuntimeError('Missing or unavailable expected metric: ' + name)
        if not any((e.get('chart') or {}).get('dates') for e in matches):
            raise RuntimeError('Price chart data is missing.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--case', choices=CASES, default='ok')
    parser.add_argument('--wait', type=float, default=600, help='Total client deadline, seconds')
    parser.add_argument('--output', type=Path, default=Path('var/main-web-check'))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not math.isfinite(args.wait) or args.wait <= 0:
        parser.error('Use a valid port and a positive finite --wait.')
    base = 'http://127.0.0.1:' + str(args.port)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    folder = args.output / (run_id + '-' + args.case)
    folder.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + args.wait
    report = {'case': args.case, 'question': CASES[args.case], 'base_url': base,
              'session': uuid4().hex, 'status': 'running'}
    opener = build_opener(ProxyHandler({}))

    def request(path, payload=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Client deadline exceeded; remote request is NOT cancelled.')
        headers = {'Content-Type': 'application/json', 'Origin': base}
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        try:
            with opener.open(Request(base + path, data=body, headers=headers),
                             timeout=min(130, remaining)) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError('Bridge HTTP %s: %s' % (exc.code, detail)) from exc

    print('OUTPUT=' + str(folder.resolve()), flush=True)
    try:
        print('Submitting ONE fresh request; browser storage is not used.', flush=True)
        code, queued = request('/ask', {'session': report['session'], 'question': report['question']})
        if code != 202 or not isinstance(queued.get('turn'), str):
            raise RuntimeError('Unexpected submit response: ' + str(queued))
        report['request_id'] = turn = queued['turn']
        write_json(folder/'summary.json', report)
        print('REQUEST_ID=' + turn, flush=True)
        with (folder/'progress.jsonl').open('a', encoding='utf-8') as log:
            while True:
                code, data = request('/reply/' + turn)
                event = {k: data[k] for k in ('event', 'step', 'tool', 'error') if k in data}
                event.update(http=code, elapsed_s=round(time.monotonic()-started, 2))
                log.write(json.dumps(event, ensure_ascii=False) + '\n'); log.flush()
                print(json.dumps(event, ensure_ascii=False), flush=True)
                if code == 200:
                    write_json(folder/'response.json', data)
                    check_response(args.case, data)
                    report.update(status='passed', fallback=bool(data.get('fallback')),
                                  stats=data.get('stats'), timings=data.get('timings'))
                    print(data.get('explanation') or data.get('answer'), flush=True)
                    if data.get('fallback'):
                        print('WARNING: Tool data arrived, but the model explanation used fallback.', flush=True)
                    print('PASS: reply and expected structure received; prose accuracy needs review.', flush=True)
                    return 0
                if code != 202:
                    raise RuntimeError('Unexpected reply status: ' + str(code))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Client deadline exceeded; remote request is NOT cancelled.')
                time.sleep(min(3, remaining))
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as exc:
        report.update(status='failed', error=str(exc) or type(exc).__name__)
        print('FAIL: ' + report['error'], file=sys.stderr, flush=True)
        print('Do not resubmit automatically. Keep summary/progress and check the TACC job log.', flush=True)
        return 1
    finally:
        report['elapsed_s'] = round(time.monotonic()-started, 2)
        write_json(folder/'summary.json', report)


if __name__ == '__main__':
    raise SystemExit(main())
