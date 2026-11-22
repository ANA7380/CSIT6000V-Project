"""Run under course Python after the co-located model becomes ready."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agent'))
from chat_agent import ChatAgent
from session_store import atomic_json
from qwen_client import chat


def smoke(result, base_url):
    started = time.perf_counter()
    probe = chat([{'role':'user','content':'37加58等于多少？只输出数字。'}], base_url, max_tokens=32, temperature=0)
    if probe['choices'][0]['message']['content'].strip() != '95':
        raise RuntimeError('Live model arithmetic readiness probe failed')
    agent = ChatAgent(base_url, result/'live-smoke-audit.jsonl')
    turns = [
        ('Show all four financial metrics for 0700.HK, using 60 daily returns for volatility.', 'ticker_metrics'),
        ('Rank the top 3 stocks using only net_profit_margin with weight 1; require net_profit_margin at least 10%.', 'rank_stocks'),
        ('Keep the same filters and weights, but return the top 5 instead.', 'rank_stocks'),
        ('Show the historical price chart and moving averages for 0700.HK using a 60-return window. Do not predict future prices.', 'price_analysis'),
    ]
    observations = []
    for question, tool in turns:
        answer = agent.ask(question)
        if not any(e['tool'] == tool and not e.get('reused') for e in agent.last_response['evidence']):
            raise RuntimeError('Live smoke did not execute required tool: ' + tool)
        if tool == 'rank_stocks' and 'top 5' in question:
            args = agent.state['last_ranking_request']
            if args.get('top_k') != 5 or args.get('filters') != {'net_profit_margin':{'min':10}} or args.get('weights') != {'net_profit_margin':1}:
                raise RuntimeError('Ranking follow-up did not preserve preferences')
        observations.append(dict(question=question, answer=answer, response=agent.last_response))
        atomic_json(result/'live-smoke.json', {'state':'running', 'turns':observations})
    atomic_json(result/'live-smoke.json', {'state':'passed', 'scripted':False,
                 'model':probe.get('model','qwen3.8-27b'), 'duration_ms':(time.perf_counter()-started)*1000,
                 'probe':probe, 'turns':observations})
    print('LIVE_SMOKE_PASSED=' + str(result/'live-smoke.json'), flush=True)


def main():
    result = Path(os.environ['STOCK_RESULT_DIR'])
    config = json.loads((result/'deployment.json').read_text())
    base = os.environ['QWEN_BASE_URL']
    if config['smoke']:
        smoke(result, base)
    if config['mode'] == 'smoke':
        return
    # Import only after live checks; shared-folder lock prevents namespace overlap.
    from web_worker import main as worker_main
    worker_main()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        atomic_json(Path(os.environ['STOCK_RESULT_DIR'])/'agent-error.json', {'error':str(exc),'type':type(exc).__name__})
        raise
