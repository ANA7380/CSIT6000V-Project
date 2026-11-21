"""CPU-only course-runtime diagnostics; no model calls and no GPU requested."""
import json
import os
import platform
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from agent import TickerAgent
from analysis_tools import AnalysisTools
from session_store import atomic_json


def main():
    result=Path(os.environ['STOCK_RESULT_DIR'])
    engine=TickerAgent();tools=AnalysisTools(engine)
    rank=tools.rank_stocks(top_k=5)
    chart=tools.price_analysis('0700.HK',window=60)['chart']
    tests=unittest.defaultTestLoader.discover(str(ROOT/'agent'))
    run=unittest.TextTestRunner(verbosity=2).run(tests)
    record={'success':run.wasSuccessful(),'tests':run.testsRun,'failures':len(run.failures),'errors':len(run.errors),
            'python':sys.version,'executable':sys.executable,'hostname':platform.node(),
            'model_calls':0,'gpu_requested':False,'companies':len(engine.snapshot),
            'price_rows':len(engine.prices),'financial_rows':len(engine.financials),
            'ranking':[r['symbol'] for r in rank['results']], 'chart_points':len(chart['dates'])}
    atomic_json(result/'diagnostics.json',record)
    print('DIAGNOSTICS_'+('PASSED' if run.wasSuccessful() else 'FAILED')+'='+str(result/'diagnostics.json'),flush=True)
    return 0 if run.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
