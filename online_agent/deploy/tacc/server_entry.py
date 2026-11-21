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
        ('Use the retained offline snapshot to show all four financial metrics for 0700.HK using 60 daily returns.', ['ticker_metrics']),
        ('Now research Apple, which is outside that offline dataset. Fetch AAPL historical price and moving-average charts online using a 60-return window. Clearly distinguish its data date from the offline snapshot.', ['market_history']),
        ('Read https://www.microsoft.com/en-us/Investor/ and briefly explain what this official investor-relations page provides. Cite the retrieved page; do not rely on model memory.', ['read_webpage']),
        ('Search the public web for Microsoft MSFT investor relations. Show the relevant discovery sources, distinguishing search results from verified page contents.', ['web_search']),
    ]
    observations = []
    for question, required_tools in turns:
        answer = agent.ask(question)
        executed={e['tool'] for e in agent.last_response['evidence'] if not e.get('reused')}
        if not set(required_tools).issubset(executed):
            raise RuntimeError('Live smoke did not execute required tools: '+str(required_tools))
        if agent.last_response['fallback']:
            raise RuntimeError('Live smoke used explanation fallback; inspect live-smoke audit')
        if 'market_history' in required_tools:
            evidence=next(e for e in agent.last_response['evidence'] if e['tool']=='market_history' and not e.get('reused'))
            if evidence['symbol']!='AAPL' or len(evidence['chart']['dates'])!=61:
                raise RuntimeError('External symbol/price window did not match the request')
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
    from context_check import verify
    verify(base, result)
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
