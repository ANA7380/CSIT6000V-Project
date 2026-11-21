"""Run actual public-network tools in the course Python, independently of the LLM."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'agent'))
from web_tools import WebTools,fetch_url,tls_context
from session_store import atomic_json

def main():
    output=Path(os.environ['STOCK_RESULT_DIR']);tools=WebTools();checks=[]
    tests=[('primary_page',lambda:tools.read_webpage('https://www.microsoft.com/en-us/Investor/')),
           ('external_market',lambda:tools.market_history('AAPL',60)),
           ('symbol_search',lambda:tools.search_stocks('Apple')),
           ('web_search',lambda:tools.web_search('Microsoft MSFT investor relations',3))]
    for name,call in tests:
        start=time.monotonic()
        try:
            result=call();atomic_json(output/(name+'.json'),result)
            checks.append(dict(name=name,passed=True,seconds=time.monotonic()-start,kind=result['kind'],provider=result.get('provider')))
        except Exception as e:checks.append(dict(name=name,passed=False,seconds=time.monotonic()-start,error=type(e).__name__+': '+str(e)))
        atomic_json(output/'network-tools.json',dict(job_id=os.environ['SLURM_JOB_ID'],checks=checks))
        print(json.dumps(checks[-1]),flush=True)
    # Search engines may deny a request. Do not hide search availability from the user.
    return 0 if all(c['passed'] for c in checks) else 1

if __name__=='__main__':raise SystemExit(main())
