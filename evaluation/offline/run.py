"""Offline numeric regression, or live Qwen agent vs no-tool DeepSeek baseline.

Offline results are NOT LLM evaluation results. Live runs save exact common context,
provider configuration, raw answers, automatic scores and a manual review worksheet.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'agent'))
from agent import TickerAgent
from analysis_tools import AnalysisTools
from tool_registry import validate
from chat_agent import ChatAgent
from evidence import view
from reference import expected, load

BASELINE_SYSTEM = '''You are a stock research assistant. Answer the user's request using
only DATA_CONTEXT and prior conversation. You have no custom financial tools or code
execution. Do not claim to have used tools. Respect fixed dates and missing data.
Return a JSON object with keys answer (explanation), facts (a dictionary whose keys
are SYMBOL/METRIC and values are numbers or null), ranking (list of objects with
symbol and score), and signals (supported historical descriptions).
Core metric names: Revenue growth, Net profit margin, Debt-to-equity, Historical volatility.
Trend metric names: sma_20, sma_50, sma_200, maximum_drawdown.
Express growth, margins, volatility and drawdown in whole percentages; debt/equity
in multiples. Ranking uses favorable-direction midrank percentiles among eligible
companies, normalized nonnegative weights, filtering first; lower debt and volatility
are preferable. Exclude missing required metrics and insufficient volatility history.
Ask for clarification when risk preferences are ambiguous. Sub-sectors and P/E are
unavailable. Do not predict future prices. Reply in the user's language.'''


def automatic(actual, gold):
    comparisons = []
    for key, expected_value in gold['facts'].items():
        present = key in actual['facts']
        value = actual['facts'].get(key)
        good = present and ((value is None and expected_value is None) or
               (type(value) in (int,float) and expected_value is not None and
                math.isfinite(value) and math.isclose(value, expected_value, rel_tol=1e-6, abs_tol=1e-6)))
        comparisons.append({'key':key,'expected':expected_value,'actual':value,'present':present,'pass':good})
    rank_ok = None
    score_ok = None
    if gold.get('check_ranking'):
        rank_ok = [r['symbol'] for r in actual.get('ranking',[])] == [r['symbol'] for r in gold['ranking']]
        score_ok = rank_ok and all(type(a.get('score')) in (int,float) and math.isclose(a['score'],g['score'],abs_tol=1e-6)
                                  for a,g in zip(actual.get('ranking',[]),gold['ranking']))
    return {'numerical_checks': comparisons,'ranking_order_pass':rank_ok,'ranking_scores_pass':score_ok}


def normalized(evidence):
    facts,ranks={},[]
    for item in evidence:
        result=item['result']
        symbol=result.get('symbol')
        for name,m in result.get('metrics',{}).items():
            facts[symbol+'/'+name]=m.get('value')
        if 'results' in result:
            ranks=[{'symbol':r['symbol'],'score':r['score']} for r in result['results']]
    return {'facts':facts,'ranking':ranks}


def common_context(case):
    """Identical frozen raw inputs are supplied to both systems, without gold values."""
    snapshot,prices=load()
    calls=[c for turn in case['turns'] for c in turn.get('calls',[])]
    symbols={c['arguments']['ticker'] for c in calls if c['arguments'].get('ticker') in snapshot}
    if any(c['tool']=='rank_stocks' for c in calls):symbols=set(snapshot)
    window=max([c['arguments'].get('window',252) for c in calls if c['tool'] in ('ticker_metrics','price_analysis','rank_stocks') and not c['arguments'].get('reuse_previous')] or [60])
    fields=('symbol','company_name','snapshot_cutoff','financial_period_end','prior_year_period_end',
            'financial_period_type','financial_currency','revenue','prior_year_revenue','net_income',
            'balance_sheet_date','balance_sheet_currency','total_debt','stockholders_equity')
    output={'notice':'Fixed snapshot; not live. Sources retained in the repository. Debt definitions and financial reporting periods vary.',
            'companies':[{k:snapshot[s].get(k) for k in fields} for s in sorted(symbols)],'price_history':{}}
    for symbol in sorted(symbols):
        rows=sorted([p for p in prices if p['symbol']==symbol],key=lambda p:p['date'])[-(100000 if any(c['tool']=='price_analysis' and c['arguments'].get('ticker')==symbol for c in calls) else window+1):]
        output['price_history'][symbol]={'dates':[p['date'] for p in rows],
            'adjusted_close':[float(p['adjusted_close']) if p['adjusted_close'] else None for p in rows]}
    return output


def offline_turn(engine,tools,turn,previous):
    evidence=[];error=None
    for call in turn.get('calls',[]):
        args=dict(call['arguments']);name=call['tool']
        try:
            validate(name,args)
            if name=='rank_stocks' and args.pop('reuse_previous',False):args=dict(previous,**args)
            result=engine.run(**args) if name=='ticker_metrics' else getattr(tools,name)(**args)
            evidence.append({'tool':name,'arguments':args,'result':result})
            if name=='rank_stocks':previous=args
        except (ValueError,TypeError,KeyError) as exc:error=str(exc)
    return normalized(evidence),previous,error


def summary(records):
    checks=[c for r in records for c in r.get('scores',{}).get('numerical_checks',[])]
    ranks=[r['scores']['ranking_order_pass'] for r in records if r.get('scores',{}).get('ranking_order_pass') is not None]
    times=[r['duration_ms'] for r in records if not r.get('error')]
    return {'turns':len(records),'errors':sum(bool(r.get('error')) for r in records),
            'numeric_checks':len(checks),'numeric_passes':sum(c['pass'] for c in checks),
            'ranking_checks':len(ranks),'ranking_passes':sum(ranks),
            'median_ms':statistics.median(times) if times else None,
            'explanation_grounding':'manual review pending','trend_grounding':'manual review pending',
            'followup_semantics':'manual review pending; ranking updates scored automatically where applicable'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['offline','live'],default='offline')
    parser.add_argument('--system',choices=['agent','baseline','both'],default='both')
    parser.add_argument('--base-url',default=os.environ.get('QWEN_BASE_URL'))
    parser.add_argument('--cases',type=Path,default=Path(__file__).with_name('cases.json'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',action='append',dest='case_ids')
    parser.add_argument('--max-context-chars',type=int,default=128000)
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):parser.error('Use a new empty output directory; prior runs are never overwritten.')
    if args.mode=='live':
        if args.system in ('agent','both') and not args.base_url:parser.error('Set QWEN_BASE_URL or pass --base-url.')
        if args.system in ('baseline','both') and not os.environ.get('DEEPSEEK_API_KEY'):parser.error('Set DEEPSEEK_API_KEY locally for the no-tool baseline.')
    cases=json.loads(args.cases.read_text());cases=[c for c in cases if not args.case_ids or c['id'] in args.case_ids]
    if not cases:parser.error('No matching cases.')
    args.output.mkdir(parents=True,exist_ok=True)
    manifest={'mode':args.mode,'systems':args.system,'created_at':datetime.now(timezone.utc).isoformat(),
              'qwen_model':'qwen3.8-27b','qwen_base_url':args.base_url,
              'baseline_model':os.environ.get('DEEPSEEK_MODEL','deepseek-flash'),
              'temperature':0,'max_tokens':1800,'cases_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              'numeric_tolerance':{'relative':1e-6,'absolute':1e-6},
              'warning':'Offline mode measures deterministic tools only. Different providers compare whole systems, not isolated tool effects.'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    records=[]
    engine=TickerAgent();tools=AnalysisTools(engine)
    for case in cases:
        previous={};runtime_previous={}
        common=None;baseline_messages=None;agent=None
        if args.mode=='live':
            common=common_context(case)
            text='DATA_CONTEXT\n'+json.dumps(common,ensure_ascii=False,separators=(',',':'))
            (args.output/(case['id']+'-context.json')).write_text(json.dumps(common,ensure_ascii=False))
            if len(text)>args.max_context_chars-10000:
                raise ValueError('Common context exceeds configured budget for '+case['id']+'; use a service with a suitable context budget and increase --max-context-chars.')
            if args.system in ('agent','both'):
                agent=ChatAgent(args.base_url,args.output/(case['id']+'-agent-audit.jsonl'),max_context_chars=args.max_context_chars)
                agent.messages[0]['content']+='\n'+text
            baseline_messages=[{'role':'system','content':BASELINE_SYSTEM+'\n'+text}]
        for i,turn in enumerate(case['turns']):
            if turn.get('behavior'):
                gold={'facts':{},'ranking':[],'previous':previous}
            else:
                gold=expected(turn.get('calls',[]),previous)
                previous=gold['previous']
            gold['check_ranking']=any(c['tool']=='rank_stocks' for c in turn.get('calls',[])) and not turn.get('behavior')
            systems=['offline'] if args.mode=='offline' else (['agent','baseline'] if args.system=='both' else [args.system])
            for system in systems:
                started=time.perf_counter();record={'case':case['id'],'category':case['category'],'turn':i,
                                                    'system':system,'prompt':turn['prompt'],'manual_behavior':turn.get('behavior'),'reference':gold}
                try:
                    if system=='offline':
                        actual,runtime_previous,error=offline_turn(engine,tools,turn,runtime_previous)
                        record['observed_rejection']=error
                        if error and not turn.get('behavior'):raise ValueError(error)
                        record['status']='expected_rejection' if error else 'manual_pending' if turn.get('behavior') else 'computed'
                    elif system=='agent':
                        text=agent.ask(turn['prompt']);record['answer']=text;record['response']=agent.last_response
                        actual=normalized([e for e in agent.evidence if e['id'] in {v['id'] for v in agent.last_response['evidence']}])
                    else:
                        from deepseek_client import chat,BASE_URL
                        baseline_messages.append({'role':'user','content':turn['prompt']})
                        result=chat(baseline_messages,BASE_URL,max_tokens=1800,temperature=0)
                        content=result['choices'][0]['message']['content'];baseline_messages.append({'role':'assistant','content':content})
                        record['raw_response']=result;record['request_messages']=baseline_messages[:-1]
                        actual=json.loads(content)
                        if not isinstance(actual.get('facts'),dict) or not isinstance(actual.get('ranking'),list):raise ValueError('Baseline returned invalid evaluation schema.')
                    record['actual']=actual;record['scores']=automatic(actual,gold)
                except Exception as exc:record['error']=str(exc)
                record['duration_ms']=(time.perf_counter()-started)*1000
                records.append(record)
    (args.output/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,allow_nan=False))
    totals={system:summary([r for r in records if r['system']==system]) for system in sorted({r['system'] for r in records})}
    (args.output/'summary.json').write_text(json.dumps(totals,indent=2))
    with (args.output/'manual_review.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['case','turn','system','explanation_grounding','trend_grounding','followup_success','behavior_success','notes']
        w=csv.DictWriter(f,fields);w.writeheader()
        for r in records:w.writerow({k:r.get(k,'') for k in ('case','turn','system')})
    print(json.dumps(totals,indent=2))
    if any(r.get('error') or any(not c['pass'] for c in r.get('scores',{}).get('numerical_checks',[])) or
           r.get('scores',{}).get('ranking_order_pass') is False or r.get('scores',{}).get('ranking_scores_pass') is False for r in records):
        raise SystemExit(1)


if __name__=='__main__':main()
