"""Prepare collected data and explicitly sourced updates without altering raw vendor data."""
import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'data'/'snapshot_2026-11-18'
data=json.loads((P/'tables.json').read_text(encoding='utf-8'))
sources=json.loads((P/'raw'/'filing_sources.json').read_text(encoding='utf-8'))
sources['9618']='https://ir.jd.com/news-releases/news-release-details/jdcom-announces-third-quarter-2026-results'
# Values transcribed from issuer tables. Amounts below in millions of stated currency.
# Net income is attributable to parent shareholders, consistent with vendor NetIncome.
updates={
 '0981.HK':dict(date='2026-09-30',published='2026-11-12',currency='USD',revenue=3190.038,prior=2381.822,income=428.405,debt=14904.184,equity=25645.492,note='Debt includes lease liabilities; equity excludes non-controlling interests.'),
 '1347.HK':dict(date='2026-09-30',published='2026-11-05',currency='USD',revenue=987.133,prior=823.078,income=123.435,debt=4018.300,equity=6962.943,note='Prior-year revenue is restated for Huali consolidation. Debt is bank borrowings plus leases; other long-term payables excluded.'),
 '0992.HK':dict(date='2026-06-30',published='2026-08-13',currency='USD',revenue=26943,prior=18830,income=-609,note='Reported loss attributable to equity holders; adjusted profit is not substituted. Balance sheet remains latest collected vendor period.'),
 '1698.HK':dict(date='2026-09-30',published='2026-11-17',currency='CNY',revenue=8941,prior=8463,income=2154,note='Balance sheet remains latest collected vendor period; income statement updated from issuer.'),
 '9618.HK':dict(date='2026-09-30',published='2026-11-17',currency='CNY',revenue=309593,prior=299059,income=6503,note='Net income attributable to ordinary shareholders. Balance sheet remains latest collected vendor period.')
}
for row in data['hk_tech30_snapshot']:
    fs=[f for f in data['hk_tech30_financials'] if f['symbol']==row['symbol']]
    revs=sorted([f for f in fs if f['metric'].endswith('TotalRevenue') and not f['metric'].startswith('trailing')],key=lambda f:(f['period_end'],f['metric'].startswith('quarterly')),reverse=True)
    for key in ('prior_year_revenue','prior_year_period_end','net_income'): row.pop(key,None)
    if revs:
        r=revs[0]; prefix=r['metric'].removesuffix('TotalRevenue')
        row.update(financial_period_end=r['period_end'],financial_period_type=r['period_type'],financial_currency=r['currency'],revenue=r['value'],revenue_series=r['metric'])
        prev=next((f for f in revs if f['metric']==r['metric'] and f['period_type']==r['period_type'] and f['currency']==r['currency'] and f['period_end']==str(int(r['period_end'][:4])-1)+r['period_end'][4:]),None)
        if prev and prev['value']>0: row.update(prior_year_revenue=prev['value'],prior_year_period_end=prev['period_end'])
        inc=next((f for f in fs if f['metric']==prefix+'NetIncome' and f['period_end']==r['period_end'] and f['period_type']==r['period_type'] and f['currency']==r['currency']),None)
        if inc: row.update(net_income=inc['value'])
    row['income_statement_source_url']=row['financial_source_url']
    row['balance_sheet_source_url']=row['financial_source_url']
    row['income_publication_date']=''
    row['net_income_basis']='attributable_to_parent_shareholders_vendor_NetIncome_or_issuer_equivalent'
    row['quote_status']='intraday_delayed_quote_not_daily_close'
    row['latest_filings_check']='not_comprehensively_verified'
    if row['symbol'] in updates:
        u=updates[row['symbol']]; url=sources[row['symbol'][:4]]
        row.update(financial_period_end=u['date'],financial_period_type='3M',financial_currency=u['currency'],revenue=u['revenue']*1e6,prior_year_revenue=u['prior']*1e6,prior_year_period_end=str(int(u['date'][:4])-1)+u['date'][4:],net_income=u['income']*1e6,revenue_series='issuer_quarterlyTotalRevenue',income_statement_source_url=url,income_publication_date=u['published'],financial_verification='issuer_income_statement_supplement',notes=u['note'])
        if 'debt' in u:
            row.update(total_debt=u['debt']*1e6,stockholders_equity=u['equity']*1e6,balance_sheet_date=u['date'],balance_sheet_currency=u['currency'],balance_sheet_source_url=url)
        for key,metric in [('revenue','TotalRevenue'),('income','NetIncome'),('debt','TotalDebt'),('equity','StockholdersEquity')]:
            if key in u:
                data['hk_tech30_financials'].append(dict(symbol=row['symbol'],metric='issuer_quarterly'+metric,period_end=u['date'],period_type='3M',currency=u['currency'],value=u[key]*1e6,publication_date=u['published'],publication_date_status='verified_issuer_release',source_url=url,snapshot_cutoff=row['snapshot_cutoff']))
        data['hk_tech30_financials'].append(dict(symbol=row['symbol'],metric='issuer_quarterlyTotalRevenue',period_end=row['prior_year_period_end'],period_type='3M',currency=u['currency'],value=u['prior']*1e6,publication_date=u['published'],publication_date_status='comparative_in_current_release',source_url=url,snapshot_cutoff=row['snapshot_cutoff']))
    row['balance_sheet_older_than_income']=row.get('balance_sheet_date','')<row.get('financial_period_end','')
assert len(data['hk_tech30_snapshot'])==30
assert len({r['symbol'] for r in data['hk_tech30_snapshot']})==30
ps=data['hk_tech30_daily_prices']
assert len({(r['symbol'],r['date']) for r in ps})==len(ps)
assert all(p['date']<='2026-11-17' and p['close']>0 for p in ps)
assert all(p['low']<=p['close']<=p['high'] for p in ps)
report={'stocks':30,'daily_price_rows':len(ps),'financial_observations':len(data['hk_tech30_financials']),'last_daily_price_date':max(p['date'] for p in ps),'issuer_supplements':list(updates),'metric_calculation':'deferred_to_chat_tools','limitations':['Vendor publication dates unavailable; not a fully point-in-time-verified dataset.','Issuer freshness review is selective, not exhaustive for all 30 companies.','Financial periods vary; use period and source columns before comparing.']}
(P/'prepared_tables.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
(P/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
