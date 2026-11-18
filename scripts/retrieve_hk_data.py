"""Retrieve a dated Yahoo Finance snapshot; preserve raw responses and provenance."""
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'snapshot_2026-11-18'
RAW = OUT / 'raw'
RAW.mkdir(parents=True, exist_ok=True)
HK = dt.timezone(dt.timedelta(hours=8))
CUTOFF = dt.datetime.now(HK)
if CUTOFF.date().isoformat() != '2026-11-18':
    raise RuntimeError('This snapshot is pinned to 2026-11-18; update explicitly before refreshing.')
UNIVERSE_SOURCE = 'https://origin-www.hsi.com.hk/eng/indexes/all-indexes/hstech'
COMPANIES = [(20,'SenseTime'),(100,'MiniMax'),(241,'Alibaba Health'),(285,'BYD Electronic'),(300,'Midea Group'),(700,'Tencent'),(981,'SMIC'),(992,'Lenovo Group'),(1024,'Kuaishou'),(1211,'BYD Company'),(1347,'Hua Hong Semiconductor'),(1698,'Tencent Music Entertainment'),(1810,'Xiaomi'),(2015,'Li Auto'),(2382,'Sunny Optical'),(2513,'Z.AI'),(3690,'Meituan'),(6618,'JD Health'),(6690,'Haier Smart Home'),(9618,'JD.com'),(9626,'Bilibili'),(9660,'Horizon Robotics'),(9863,'Leapmotor'),(9866,'NIO'),(9868,'XPeng'),(9888,'Baidu'),(9903,'Iluvatar CoreX'),(9961,'Trip.com'),(9988,'Alibaba'),(9999,'NetEase')]
TYPES = [p+m for p in ('annual','quarterly','trailing') for m in ('TotalRevenue','NetIncome','TotalDebt','StockholdersEquity')]

def fetch(url, filename):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=35) as response:
                data = json.load(response)
            (RAW/filename).write_text(json.dumps({'url':url,'retrieved_at':dt.datetime.now(HK).isoformat(),'response':data},ensure_ascii=False),encoding='utf-8')
            return data
        except Exception:
            if attempt == 2: raise
            time.sleep(1+attempt)

def collect(company):
    code,name = company
    symbol = f'{code:04d}.HK'
    row = dict(hkex_code=f'{code:05d}',symbol=symbol,company_name=name,universe_source=UNIVERSE_SOURCE,snapshot_cutoff=CUTOFF.isoformat(),price_currency='HKD')
    prices,financials,errors = [],[],[]
    chart_url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d&events=div%2Csplits'
    row['price_source_url'] = chart_url
    try:
        result=fetch(chart_url,symbol+'_prices.json')['chart']['result'][0]
        meta=result['meta']; q=result['indicators']['quote'][0]
        adj=result['indicators'].get('adjclose',[{}])[0].get('adjclose',[])
        row['company_name_provider']=meta.get('longName',meta.get('shortName',''))
        row['price_currency']=meta.get('currency','')
        row['quote_time']=dt.datetime.fromtimestamp(meta['regularMarketTime'],HK).isoformat()
        row['latest_quote']=meta.get('regularMarketPrice')
        for i,t in enumerate(result.get('timestamp',[])):
            day=dt.datetime.fromtimestamp(t,HK).date()
            # Exclude the current partial trading session before 16:15 Hong Kong time.
            if day>CUTOFF.date() or (day==CUTOFF.date() and CUTOFF.time()<dt.time(16,15)): continue
            if q['close'][i] is None: continue
            prices.append(dict(symbol=symbol,date=day.isoformat(),currency=row['price_currency'],open=q['open'][i],high=q['high'][i],low=q['low'][i],close=q['close'][i],adjusted_close=adj[i] if i<len(adj) else None,volume=q['volume'][i],source_url=chart_url,snapshot_cutoff=CUTOFF.isoformat()))
        prices.sort(key=lambda x:x['date'])
        if prices:
            row.update(price_date=prices[-1]['date'],close=prices[-1]['close'],history_start=prices[0]['date'],history_rows=len(prices))
    except Exception as e: errors.append('prices: '+str(e))
    query=urllib.parse.urlencode(dict(type=','.join(TYPES),period1=1672531200,period2=int(CUTOFF.timestamp())))
    fund_url=f'https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}?{query}'
    row['financial_source_url']=fund_url
    try:
        result=fetch(fund_url,symbol+'_financials.json')['timeseries']['result'] or []
        for series in result:
            kind=series['meta']['type'][0]
            for item in series.get(kind,[]):
                if item['asOfDate']>CUTOFF.date().isoformat(): continue
                financials.append(dict(symbol=symbol,metric=kind,period_end=item['asOfDate'],period_type=item.get('periodType',''),currency=item.get('currencyCode',''),value=item['reportedValue']['raw'],publication_date='',publication_date_status='not_provided_by_vendor',source_url=fund_url,snapshot_cutoff=CUTOFF.isoformat()))
        # Use most recent revenue observation with comparable prior-year period.
        revenues=sorted([f for f in financials if f['metric'].endswith('TotalRevenue') and not f['metric'].startswith('trailing')],key=lambda f:(f['period_end'],f['metric'].startswith('quarterly')),reverse=True)
        if revenues:
            rev=revenues[0]; prefix=rev['metric'].removesuffix('TotalRevenue')
            row.update(financial_period_end=rev['period_end'],financial_period_type=rev['period_type'],financial_currency=rev['currency'],revenue=rev['value'],revenue_series=rev['metric'])
            previous=[f for f in revenues if f['metric']==rev['metric'] and f['period_type']==rev['period_type'] and f['currency']==rev['currency'] and f['period_end']==str(int(rev['period_end'][:4])-1)+rev['period_end'][4:]]
            if previous and previous[0]['value']>0:
                row.update(prior_year_revenue=previous[0]['value'],prior_year_period_end=previous[0]['period_end'])
            income=next((f for f in financials if f['metric']==prefix+'NetIncome' and f['period_end']==rev['period_end'] and f['period_type']==rev['period_type'] and f['currency']==rev['currency']),None)
            if income:
                row['net_income']=income['value']
        debts=sorted([f for f in financials if f['metric'].endswith('TotalDebt')],key=lambda f:f['period_end'],reverse=True)
        for debt in debts:
            equity=next((f for f in financials if f['metric']==debt['metric'].replace('TotalDebt','StockholdersEquity') and f['period_end']==debt['period_end'] and f['currency']==debt['currency']),None)
            if equity:
                row.update(balance_sheet_date=debt['period_end'],balance_sheet_currency=debt['currency'],total_debt=debt['value'],stockholders_equity=equity['value'])
                break
    except Exception as e: errors.append('financials: '+str(e))
    row['financial_verification']='vendor_data_not_reconciled_to_issuer_filings'
    row['retrieval_errors']=';'.join(errors)
    print(symbol,len(prices),len(financials),row['retrieval_errors'],flush=True)
    return row,prices,financials

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(collect,COMPANIES))
    tables={'hk_tech30_snapshot':[r[0] for r in records],'hk_tech30_daily_prices':[p for r in records for p in r[1]],'hk_tech30_financials':[f for r in records for f in r[2]]}
    (OUT/'tables.json').write_text(json.dumps(tables,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:len(v) for k,v in tables.items()}))
