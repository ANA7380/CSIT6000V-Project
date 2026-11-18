# Instruction for running locally on Windows using Deepseek API

cd agent
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local.ps1

# Instruction for running on TACC

cd qwen27b-student-release/qwen-public-serve
tcloud submit
==AFTER QWEN STARTED==
cd ../../agent

printf '%s\n' 'http://SERVICE_HOST:8000/v1' > server-url.txt (e.g. ACTUAL_SERVICE_HOST=10.0.0.1)
printf '%s\n' 'Show all four metrics for 0700.HK' > question.txt
tcloud submit

tcloud cat "slurm_log/agent-${JOBID}.log"



# Project Tasks

Based on the proposal: **An Explainable AI Agent for Stock Screening and Analysis**. Tasks are listed in suggested implementation order; completion status is not yet assessed.

| # | Task | Description | Done? | Responsible |
|---|------|-----------|-------|-------------|
| 1 | Define scope and calculation rules | Select 30 technology stocks; agree on date range, metric formulas, ranking weights, and trend indicators. | ✅ | DUAN Zihang Raymond |
| 2 | Build the fixed dataset | Collect and clean financial statements and historical prices; save sources, snapshot date, and missing-data flags. | ✅ | DUAN Zihang Raymond |
| 3 | Implement financial tools | Calculate and verify revenue growth, net profit margin, debt-to-equity, and historical volatility. | ✅ | DUAN Zihang Raymond |
| 4 | Implement screening and ranking | Apply mandatory filters, normalize metrics, calculate weighted scores, and return configurable Top-K with score breakdowns. | ✅ | DUAN Zihang Raymond |
| 5 | Implement historical trend tools | Calculate indicators and generate price charts; explain historical bullish/bearish signals without predicting prices. | X | |
| 6 | Connect the TACC model | Confirm backend access, configure model calls, and validate structured tool requests and parameters. | X | |
| 7 | Build the three agent workflows | Route requests to individual stock analysis, recommendations, or trend analysis; execute the appropriate tools. | X | |
| 8 | Add grounded explanations | Explain performance, risks, rankings, and trends using tool results; display the data date and check numerical consistency. | X | |
| 9 | Add conversation memory | Preserve results and preferences; support comparisons, indicator questions, and revised screening criteria. | X | |
| 10 | Build backend reliability and logging | Handle invalid inputs, missing data, and service/tool errors; log model calls, tool executions, errors, and timings. | X | |
| 11 | Build the web interface | Support natural-language requests, execution progress, metrics, rankings, charts, and follow-up questions. | X | |
| 12 | Create the evaluation set | Cover all three workflows, follow-ups, and invalid/incomplete inputs; verify reference calculations, filters, rankings, and tool outputs. | X | |
| 13 | Implement the baseline | Use another provider's general-purpose LLM without custom tools; keep prompts and applicable company context identical; record model/API settings. | X | |
| 14 | Run and compare evaluations | Report numerical accuracy, recommendation quality, trend grounding, explanation grounding, follow-up success, and response time. | X | |
| 15 | Analyze failures and limitations | Document at least one observed failure, its cause, and mitigation; acknowledge that different models prevent isolating tool-use effects. | X | |
| 16 | Package and demonstrate | Deliver the working app, source repository, evaluation results, tested demo, and reproducible setup instructions. | X | |

## Task 1

30 Technology stocks and its raw data downloaded.
Daily price data covers 2024/11/18 to 2026/11/17, collected on 2026/11/18. Some stocks have shorter histories. Financial reporting periods vary by company.

### Implemented metrics and formulas

These formulas reflect `../agent/agent.py` and `../agent/analysis_tools.py`.

Notation: `P[t]` = adjusted closing price; `V[t]` = trading volume; `r[t] = ln(P[t] / P[t-1])`; `s()` = sample standard deviation (denominator `n - 1`). Percentage formulas below return whole percentages, e.g. `10` means `10%`.

#### Core metrics for ranking

| Metric | Formula | Period / interpretation | Weight |
|---|---|---|
| Revenue growth | `(revenue / prior-year revenue - 1) * 100` | Selected reporting period versus matching prior-year period; higher scores better. | 25% |
| Net profit margin | `net income / revenue * 100` | Selected reporting period; higher scores better. | 25% |
| Debt-to-equity | `total debt / stockholders equity` | Selected balance-sheet date; expressed as a multiple; lower scores better. | 25% |
| Historical volatility | `s(daily log returns) * sqrt(252) * 100` | Defaults to the latest 252 returns (253 prices); lower scores better. | 25% |

#### Ranking calculation

Mandatory filters are applied first. Scores are calculated only among the remaining eligible stocks.

| Step | Formula / rule |
|---|---|
| Metric percentile | `Q = 100 * (count(values below x) + (count(values equal to x) - 1) / 2) / (N - 1)`, where `N` is the eligible stock count. Ties use midranks; a single eligible stock scores 50. |
| Favorable direction | Growth and margin use `Q`; debt-to-equity and volatility use `100 - Q`. |
| Normalize weights | `normalized weight = supplied weight / sum(supplied weights)`; weights must be nonnegative with a positive total. |
| Final score | `sum(normalized weight * favorable percentile)`; defaults to 25% for each of the four core metrics. |
| Output | Descending score, with ticker as tie-breaker; default Top-5. Custom weights can select a subset of the four core metrics. |

Stocks missing required metrics or a complete requested volatility window are excluded from ranking. Ranking measures attractiveness under these metrics, not market popularity.

#### Price and trend indicators

| Indicator | Formula / rule | Default window |
|---|---|---|
| Price return | `(end price / start price - 1) * 100`; start is the last observation on or before the calendar-month target date. | 1, 3, 6, and 12 months |
| Simple moving average (SMA) | `mean(last n adjusted closes)` | 20, 50, and 200 sessions |
| Distance from SMA | `(latest price / SMA - 1) * 100` | Each SMA above |
| RSI14 | `100 - 100 / (1 + average gain / average loss)`; uses Wilder smoothing described below. | 14 changes for initialization |
| MACD line | `EMA12(price) - EMA26(price)` | 12 / 26 sessions |
| MACD signal | `EMA9(MACD line)` | 9 MACD observations |
| MACD histogram | `MACD line - signal` | Latest value |
| Maximum drawdown | `min(price / running peak - 1) * 100`, within the selected window; zero or negative. | 252 return intervals |
| Rolling volatility | `s(last n daily log returns) * sqrt(252) * 100` | 20 returns; returns up to 252 rolling points |
| Volume ratio | `latest volume / mean(previous 20 sessions' volumes)`; excludes today's volume from the average. | 20 prior sessions |
| Price above SMA50 | `latest price > SMA50` | Latest session |
| SMA50 above SMA200 | `SMA50 > SMA200` | Latest session |
| Latest SMA50/200 crossover | Let `D = SMA50 - SMA200`: up if `previous D <= 0` and `current D > 0`; down if `previous D >= 0` and `current D < 0`; otherwise none. | Latest versus previous session |

EMA uses `alpha = 2 / (n + 1)` and `EMA[t] = alpha * value[t] + (1 - alpha) * EMA[t-1]`, seeded with the mean of the first `n` observations.

RSI uses `gain = max(price change, 0)` and `loss = max(-price change, 0)`. Initial average gain/loss is the mean of the first 14 changes. Subsequent averages use `(13 * previous average + current gain or loss) / 14`. A flat series returns RSI 50; positive average gain with zero average loss returns 100.

#### Financial trends and stock comparison

| Metric | Formula | Period / interpretation |
|---|---|---|
| Profit-margin change | `(current annual net income / current annual revenue - prior annual net income / prior annual revenue) * 100` | Percentage points, not percentage growth |
| Debt growth | `(current debt / prior-year debt - 1) * 100` | Latest comparable annual pair |
| Equity growth | `(current equity / prior-year equity - 1) * 100` | Latest comparable annual pair |
| Return on equity (ROE) | `annual net income / ((opening equity + closing equity) / 2) * 100` | Annual profit and average equity |
| Two-stock correlation | `sum((x - mean(x)) * (y - mean(y))) / sqrt(sum((x - mean(x))^2) * sum((y - mean(y))^2))` | Pearson correlation of matched log-return intervals; defaults to latest 252 matched intervals; not market beta |

Financial trends require matching annual periods and currencies and may use older observations than the core snapshot. Growth requires a positive prior value; ROE requires positive opening and closing equity. Missing or invalid inputs return unavailable results. Standalone volatility, drawdown, and correlation can report shorter histories explicitly; ranking excludes incomplete required volatility histories.

**Trend prediction status:** Indicator calculations are implemented, but there is no combined up/down/neutral forecast formula or model yet. Trend prediction is separate from ranking and still needs a defined forecast horizon, prediction rule/model, and backtesting. Historical indicators alone are not a validated prediction system.

## Task 2

| File | What one row represents | Contents and purpose |
|---|---|---|
| hk_tech30_snapshot.csv | **One company** | A summary of the latest collected quote, previous daily close, revenue, prior-year revenue, net income, debt, equity, and source dates. Useful for company comparisons and calculating financial ratios. |
| hk_tech30_daily_prices.csv | **One stock on one trading day** | Historical open, high, low, close, adjusted close, and trading volume. Useful for calculating returns, volatility, and price trends. |
| hk_tech30_financials.csv | **One financial metric for one company and reporting period** | Historical revenue, net income, debt, and equity observations, with annual, quarterly, and trailing periods. Useful for selecting comparable periods and examining financial changes over time. |

## Task 3

Revenue growth, net profit margin, debt-to-equity, and historical volatility tools.

## Task 4

Default ranking scores: Final score = 25% x growth score + 25% x margin score + 25% x debt score + 25% x volatility score, where scores are the percentile.

Example prompts:

- Default ranking: Rank the top 5 stocks using the default weights. Show each stock's raw metrics, percentile scores, weights, and final score.

- Mandatory filters: Return the top 5 stocks with net profit margin at least 10% and debt-to-equity at most 0.5.

- Custom weights: Rank the top 3 stocks using revenue growth weight 2 and historical volatility weight 1. Show the normalized weights and score calculation.

- Metric normalization: Rank the top 5 stocks using only debt-to-equity. Show raw debt-to-equity and percentile scores.

- Score breakdown: For the highest-ranked stock, show each metric's weighted contribution and add them up to reproduce its final score.

- Configurable Top-k stocks: Using the same filters and weights, return the top 10 instead of the top 3.