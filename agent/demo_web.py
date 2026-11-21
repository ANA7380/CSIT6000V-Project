"""Explicit offline scripted UI fixture. No model calls, no network data requests.

Supports the displayed overview/ranking/trend examples and a Top-K ranking follow-up.
It verifies the UI and orchestration only; it is not an AI quality evaluation.
"""
import argparse
import json
import re
import tempfile
from pathlib import Path

from chat_agent import ChatAgent
from local_web import make_server


def fixture(messages, *args, **kwargs):
    last=messages[-1]['content']
    state=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('SESSION_STATE\n')))
    if last.startswith('TOOL_RESULT\n'):
        item=json.loads(last.split('\n',1)[1])
        if item['tool']=='ticker_metrics' and 'result' in item:
            action={'tool':'price_analysis','arguments':{'ticker':item['result']['symbol'],'window':60}}
        elif 'error' in item:
            action={'answer':'The supplied request could not be executed. Please choose a supported example.'}
        else:
            refs=[e['id'] for e in state['available_evidence'][-2:]]
            action={'answer':'Offline scripted example: inspect the verified tables, reporting dates and historical charts below. This is a fixed snapshot and does not forecast future prices. '+ ' '.join('['+r+']' for r in refs)}
    elif last.startswith(('MODEL_FORMAT_ERROR\n','ANSWER_VALIDATION_ERROR\n')):
        refs=[e['id'] for e in state['available_evidence'][-1:]]
        action={'answer':'Offline scripted example with verified tool evidence. '+' '.join('['+r+']' for r in refs)}
    else:
        question=last.lower()
        symbol=re.search(r'\d{4}\.hk',question)
        ticker=symbol[0].upper() if symbol else '0700.HK'
        if 'rank' in question or 'top' in question or '筛选' in question:
            top=re.search(r'top\s*(\d+)',question)
            args={'top_k':int(top[1]) if top else 5}
            if state['last_ranking_request']:args['reuse_previous']=True
            else:args.update(window=60,filters={'net_profit_margin':{'min':10},'debt_to_equity':{'max':.5}})
            action={'tool':'rank_stocks','arguments':args}
        elif '趋势' in question or 'trend' in question:
            action={'tool':'price_analysis','arguments':{'ticker':ticker,'window':60}}
        elif 'tencent' in question or '腾讯' in question or symbol:
            action={'tool':'ticker_metrics','arguments':{'ticker':ticker,'window':60}}
        else:action={'answer':'This is an offline scripted demo. Choose an overview, ranking or historical-trend example.'}
    return {'model':'offline-scripted-fixture','choices':[{'message':{'content':json.dumps(action,ensure_ascii=False)}}]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--data-dir',type=Path)
    args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='hk-tech-demo-') as temp:
        server=make_server(args.port,args.data_dir or Path(temp),
                           lambda base,log:ChatAgent(base,log,call=fixture),'http://localhost:8000/v1')
        server.page=server.page.replace(b'<header>',b'<p class="warning" role="note">OFFLINE SCRIPTED DEMO / No LLM is connected. Responses are test fixtures; financial calculations use the real frozen CSVs.</p><header>')
        print(f'OFFLINE SCRIPTED DEMO: http://{server.address}/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close();server.queue.put(None)


if __name__=='__main__':main()
