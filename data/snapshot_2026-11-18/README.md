# Hong Kong technology stocks: collected snapshot

Collected on 18 November 2026, approximately 15:38 Hong Kong time. Exact initial cutoff and per-request retrieval timestamps are retained in the CSVs and raw JSON respectively. Issuer supplements were reviewed later the same afternoon and were published before the cutoff.

## Files

- `hk_tech30_snapshot.csv`: one row per company, latest collected intraday quote, last completed daily close, financial inputs, reporting periods, source URLs, and quality flags.
- `hk_tech30_daily_prices.csv`: 13,919 daily OHLCV observations, up to two years per stock, ending 17 November 2026. New listings have shorter histories. Adjusted close is supplied separately.
- `hk_tech30_financials.csv`: 816 financial observations. Annual, quarterly, and trailing vendor observations are preserved alongside explicitly prefixed issuer supplements. Do not sum overlapping periods or combine vendor and issuer rows as if they were separate business activity.
- `raw/`: original responses and downloaded issuer documents. `validation.json` contains coverage checks.

CSV format is UTF-8 with BOM and comma delimiters. Blank numeric cells mean unavailable, never zero. Import `hkex_code` as text to retain its five-digit leading zeros; the `symbol` column includes `.HK` and is suitable as a stable join key. Monetary amounts are in full currency units, not thousands or millions. Financial currencies can differ from the HKD quote currency.

## Universe

The 30 names were transcribed from the official Hang Seng TECH constituent table returned by web search for https://origin-www.hsi.com.hk/eng/indexes/all-indexes/hstech on 18 November 2026. The web search copy was dated September 2026; a direct origin-server fetch failed. Therefore effective membership has not been independently reconciled against every subsequent index notice. This is an index-based universe, not an assertion that these are the 30 best investments, and rows are ordered by HKEX code rather than investment merit or market capitalization.

The October 2026 methodology amendment proposes a larger index for the November review. This dataset deliberately retains the 30-company scope; it does not incorporate future announced constituents. Methodology: https://www.hsi.com.hk/content/dam/wpb/hsil/index/methodologies/en_hk/hstech/IM_hstech.pdf

## Dates and freshness

- `latest_quote` and `quote_time`: actual intraday provider quote and timestamp on 18 November; delayed, not a final daily close.
- `close` and `price_date`: most recent completed daily bar, 17 November. Collection occurred before the 18 November market close.
- `financial_period_end` and `financial_period_type`: the latest income period collected for that company. The financial feed can lag issuer announcements.
- `income_publication_date`: populated only for the five reviewed issuer supplements. Vendor statement publication dates are unavailable; period end is not publication date.
- `balance_sheet_date`: date of the debt/equity inputs, which can be older than the income statement. `balance_sheet_older_than_income` exposes this difference.

The dataset is the latest obtained from the queried feeds plus five newer primary-source supplements, not a guarantee that every company's latest disclosure anywhere online has been incorporated. Vendor-only rows have not been reconciled to issuer filings, and unknown publication dates prevent certification as a point-in-time research dataset. Do not use it for a historical backtest without further publication-date validation.

## Calculations belong to runtime tools

The CSVs contain collected prices, financial inputs, dates, and provenance. Revenue growth, net profit margin, debt-to-equity, and historical volatility are not precomputed or stored here. Their derived window/status fields have also been removed. Preparation scripts do not calculate these four metrics.

During chat, the planned Python tools will select comparable financial periods or a requested price window, validate inputs, calculate the requested metric, and return the value, formula, input references, dates, and missing-data status. Tool execution and parameters must be logged. These runtime tools are still an implementation task; this dataset update does not implement them.

Keep matching financial periods and currencies when calculating growth and margins. `net_income` follows vendor `NetIncome` or issuer profit attributable to parent shareholders, not adjusted profit. Debt definitions need harmonization: SMIC's supplemented debt includes leases; Hua Hong's includes bank borrowings and leases but excludes other long-term payables. Equity inputs exclude non-controlling interests. Vendor quarterly labels are not independent confirmation of reporting frequency for semiannual reporters.

On-demand calculation means calculating when a request arrives. It does not make this fixed snapshot a live market feed. A separate retrieval/refresh tool is needed for fresh data; results must display the actual data dates. Independently verified metric reference answers may be created later under evaluation fixtures, separately from the input dataset.

## Issuer updates

Five companies have newer income statements transcribed from original releases, with original vendor observations retained:

- SMIC, 2026 Q3, published 12 November: https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1112/2026111200682.pdf
- Hua Hong, 2026 Q3, published 5 November: https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1105/2026110500668.pdf . Prior-year revenue uses the release's restated comparative after Huali consolidation.
- Lenovo, FY2026/27 Q1, published 13 August: https://investor.lenovo.com/en/financial/results/press_2627_q1.pdf . Uses reported attributable loss, not adjusted net income.
- Tencent Music, 2026 Q3, published 17 November: https://ir.tencentmusic.com/2026-11-17-Tencent-Music-Entertainment-Group-Announces-Third-Quarter-2026-Unaudited-Financial-Results
- JD.com, 2026 Q3, published 17 November: https://ir.jd.com/news-releases/news-release-details/jdcom-announces-third-quarter-2026-results . Direct PDF download returned HTTP 403; the issuer's web page was inspected through web search/open.

SMIC and Hua Hong also have supplemented balance sheets. The other three retain their separately dated vendor balance sheets. Financial-source columns distinguish these inputs.

## Reproduction

`scripts/retrieve_hk_data.py` collects and retains vendor responses; its snapshot date is intentionally pinned. `scripts/prepare_hk_csv_data.py` applies the documented primary-source supplements and prepares the output tables. The original frozen responses should be retained: requesting the same URLs later may return revised or newer data. Final CSV exports were authored through Artifact Tool and checked by reopening them with Python's CSV reader.
