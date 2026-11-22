# An Explainable AI Agent for Stock Screening and Analysis

## 输出校验更新（2026-11-22）

解释正文允许股票代码、数字、日期、列表序号、四舍五入和明确标注的情景计算。不再按数字字符或与证据数字逐项匹配来拒绝整段回答。硬校验仅检查非空回答、引用 ID 存在、本轮调用工具后提供证据引用，以及正文不直接写 URL（来源链接仍由证据卡片展示）。模型仍须按 prompt 引用依据、区分事实与假设；程序不再保证正文数字正确，数值准确率与语义依据需通过参考测评和人工审核确认。工具参数校验、确定性表格与图表计算保持原有行为。部署中的旧进程需要用新代码重新打包启动；恢复旧会话时，首条 system prompt 会替换为本版本 prompt。

新增模拟多轮回归覆盖“先问 Anthropic，再问腾讯并输出股票代码、百分数、列表和情景推导值”，不代表真实 Qwen 对同一对话已复测。

## Deploy on the course server

The recommended server deployment runs Qwen and the Agent in **one GPU allocation**. It uses the provided fix's loopback endpoint `127.0.0.1:42865`; a separate CPU job on another node cannot reach that loopback address.

```bash
# Reuse your configured tcloud SDK (or export TCLOUD_BIN=/path/to/tcloud).
python3 scripts/tacc.py submit --mode web --namespace hk-research --minutes 60
python3 scripts/tacc.py status YOUR_JOB_ID
# Wait for MODEL_READY, LIVE_SMOKE_PASSED, and Chat ready, then:
python3 scripts/tacc.py bridge YOUR_JOB_ID
```

The last command prints the laptop browser URL. Model inference, stock calculations, conversation snapshots and request processing all run on the server. The local bridge uses the authenticated course SDK for file transfer; it does not need direct access to a compute-node HTTP port.

```bash
# Optional CPU-only runtime verification (no GPU/model request):
python3 scripts/tacc.py submit --mode diagnostic --minutes 5
# Save results and release your allocation when finished:
python3 scripts/tacc.py download YOUR_JOB_ID
python3 scripts/tacc.py stop YOUR_JOB_ID
```

See the [server deployment guide](docs/服务器部署指南.md) for configuration, persistent conversation namespaces, process cleanup and troubleshooting. Each submission uses a unique staged folder to avoid overwriting an active WORKDIR. The course's public environment and model files are never edited.

The [Chinese technical architecture report](docs/项目技术架构报告.md) explains the TACC environment, frontend/backend data flow, Agent loop, actual prompts and all six tools. A [standalone HTML reading version](docs/项目技术架构报告.html) includes embedded diagrams.

## Implementation update on the proposal-completion branch

This branch adds deterministic evidence tables, historical price/SMA and rolling-volatility charts, validated numerical presentation, reusable ranking preferences, multiple browser conversations, private restart snapshots, worker progress events, a local browser server, independent offline references and a genuine **no-tool** baseline runner. It keeps the original fixed CSVs and the single-agent architecture.

Start an explicitly scripted preview without any model or key:

```bash
python3 agent/demo_web.py
```

Connect a real model from the repository root:

```bash
# Fill agent/server-url.txt with the actual /v1 URL, or pass it explicitly:
python3 agent/local_web.py --provider qwen --base-url http://ACTUAL_SERVICE_HOST:8000/v1
# Local DeepSeek browser alternative, after exporting DEEPSEEK_API_KEY:
python3 agent/local_web.py --provider deepseek
```

Only use the local Qwen option where its internal service address is reachable. The existing TACC `submit-web.sh` / `web_bridge.py` deployment remains supported. Configure credentials in environment variables; `.env.example` is an example and is not loaded automatically.

Run offline verification from the repository root:

```bash
python3 -m unittest discover -s agent -v
python3 scripts/export_snapshot.py --check
python3 evaluation/run.py --mode offline --output evaluation/runs/offline-001
```

See the [Chinese implementation and connection guide](docs/实施说明与接入指南.md), [evaluation protocol](evaluation/README.md) and [validation record](docs/VALIDATION.md). Full Qwen/DeepSeek comparative evaluation remains pending. For the current server deployment and real-model smoke-test status, see the [server validation record](docs/服务器部署实测记录.md). Do not interpret the offline scripted preview or calculation checks as live LLM performance.

The current scope is financial-condition screening within a fixed thirty-company technology universe. Verified sub-sector metadata is unavailable. The UI and prompt explicitly disclose this limitation; a sub-sector filter still requires sourced metadata. Historical analysis does not require a future-price forecasting model.


## Local chat with DeepSeek (start here)

The Python agent and CSV tools run locally. The LLM runs at DeepSeek's API; your messages and selected tool results are sent there. No TACC job is needed. API usage is billed to your DeepSeek account.

From the repository root, run the following in PowerShell.

```powershell
cd agent
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local.ps1
```

The launcher asks for your key with hidden input and starts chat. It does not save the key to disk. Type `Show all four metrics for 0700.HK`, then a follow-up such as `Now use 60 trading days for volatility`. Enter `/quit` to exit.

Alternatively, from the agent folder, set `DEEPSEEK_API_KEY` in your current terminal and run:

```powershell
uv run --no-project python chat_agent.py --provider deepseek
uv run --no-project python chat_agent.py --provider deepseek --prompt "Show Tencent metrics"
```

No additional Python packages are needed. The default provider is DeepSeek, with model `deepseek-flash`; override via the `DEEPSEEK_MODEL` environment variable if needed. The client uses JSON-mode requests and the existing application-managed tool protocol. Credentials are sent only to the official HTTPS endpoint and are not written to the audit log. Logs do contain conversation text and calculation results.

HTTP 401 means check the key; 402 means check API balance; 429 means wait before retrying. Local mocked transport and tool-loop tests do not constitute a live API verification.

Reference: https://api-docs.deepseek.com/quick_start



### Browser chat on your own machine (DeepSeek)

```bash
export DEEPSEEK_API_KEY='YOUR_LOCAL_KEY'
python3 agent/local_web.py --provider deepseek
```

Open the printed `http://127.0.0.1:8765/` URL. It serves the same page as the TACC chat, but the agent and its tools run locally and the model is DeepSeek. Tables and charts are drawn by the page from tool results; the model's explanation is rendered as Markdown after escaping. Conversations and audit logs are written to `agent/logs/web/`.

### Browser chat on TACC

```bash
bash submit-web.sh
```

The script now defaults to one GPU allocation containing both Qwen and the Agent. It stages only the runtime files and invokes the same `scripts/tacc.py` workflow described above. Use `bash submit-web.sh --external-model` only for a separately deployed model whose non-loopback address is reachable from the CPU job. Use the returned **chat job ID** in both commands below. Wait for `Chat ready` in the log before launching the bridge.

```bash
tcloud cat slurm_log/stock-chat-JOB_ID.log
python3 web_bridge.py JOB_ID
```

Open the printed loopback URL (default `http://127.0.0.1:8765/`). Ask “Show all four metrics for 0700.HK”, then “Now use 60 trading days for volatility”. Keep the same page open for follow-ups. The browser saves conversation IDs and display history; New conversation creates a separate session. The worker restores private snapshots from the same job directory after a restart. Use `--port 8766` if the default local port is occupied.

The job supplies the page and runs the agent and its tools. The laptop serves the page on loopback and uses the authenticated SDK to upload a question and poll for its reply. Transfers add a few seconds to each turn. Job-specific messages and audit logs are under `$TACC_USERDIR/stock-chat/JOB_ID/`. This setup uses the documented file-transfer interface. [TACC SDK](https://github.com/turingaicloud/tcloud-sdk) · [TACC SSH FAQ](https://github.com/turingaicloud/quickstart/blob/master/FAQ.md)

Keep the single allocation running. Check it with `tcloud ps -j JOB_ID` if a reply stalls. The legacy external-model mode requires both its CPU job and separate model service. When finished, press Ctrl+C in the bridge terminal and cancel each active allocation with `tcloud cancel -j JOB_ID`.

### Legacy single-question batch job with an external model

The included `tuxiv.conf`, `job.sh`, and copied `setup-sdk-account.sh` target the course's existing tcloud/proxy environment, following the local `qwen27b-student-release` package. These are not generic Texas TACC Slurm instructions. The batch launcher now runs the LLM chat agent; start the course model service first. The standalone `agent.py` still works without a model.

From the agent folder, set the question and submit the batch job.

```bash
printf '%s\n' 'Show all four metrics for 0700.HK' > question.txt
tcloud submit
```

Use the returned job ID:

```bash
tcloud ps -j YOUR_JOB_ID
tcloud cat "slurm_log/agent-YOUR_JOB_ID.log"
```

The LLM answer appears in the client job log. Full results and tool calls are saved under `$TACC_USERDIR/ticker-metrics-results/job-JOB_ID.jsonl`. Batch jobs do not accept interactive stdin; change `question.txt` and resubmit for each new message. Each batch submission is a fresh conversation. Keep the model service running while clients execute, update the URL after restarting it, and stop it afterwards with `tcloud cancel -j SERVICE_JOB_ID`.

In an interactive course compute allocation, source `/mnt/home/public/course-envs/CSIT6000V/project/activate.sh` and run `qwen-python chat_agent.py --provider qwen --base-url http://ACTUAL_SERVICE_HOST:8000/v1` for a multi-turn chat prompt. The service is internal to TACC; this command is not intended to connect directly from your Windows laptop. For proxy issues, use the same `no_proxy` settings as `job.sh`. Cluster execution has not been verified from this workstation.


## Standalone ticker calculations (for playing around)

A deterministic Python agent for the 30 Hong Kong tickers in the supplied CSVs. It accepts a ticker and invokes financial and price calculations at runtime. No LLM, GPU, API key, network request, or third-party Python package is required. Requires Python 3.9 or later.

The [agent data folder](agent/data/) contains byte-for-byte copies of the project's three CSVs and their original documentation. Original project data is untouched.

Run the following from the `agent/` folder, locally or in a TACC terminal.

```bash
python agent.py
python agent.py 0700.HK
python agent.py 700 --window 60
python agent.py --list
python agent.py 700 --json
```

On this Windows workstation Python is available through uv; use `uv run --no-project python agent.py` if `python` is unavailable. Interactive mode accepts a ticker, `list`, and `quit`. Unknown tickers produce a clear error. Numeric HKEX codes, leading zeros, and case-insensitive `.HK` suffixes are accepted.

## Submit to the course TACC environment

Use Bash with your course `tcloud` account configured. On Windows, use your SDK-enabled WSL shell. Follow the [course setup guide](qwen27b-student-release/README.md) for `tcloud config` and `tcloud init`. If the shared proxy entry point is missing, run `bash setup-sdk-account.sh` from `agent/`.

From the repository root, submit the Qwen service. Replace JOB_ID with the returned service job ID.

```bash
cd qwen27b-student-release/qwen-public-serve
tcloud submit
tcloud cat slurm_log/qwen-public-serve-JOB_ID.log
```

Wait for `Application startup complete`. Replace the example URL below with the log's `SERVICE_BASE_URL`.

```bash
cd ../../agent
printf '%s\n' 'http://ACTUAL_SERVICE_HOST:8000/v1' > server-url.txt
```


## How the LLM uses tools

`question.txt → chat_agent.py → TACC Qwen → JSON tool request → Python CSV calculation → Qwen → final answer`

The chat client selects `deepseek_client.py` for local DeepSeek use or the course's unmodified `qwen_client.py` for TACC. The model requests tools via a prompted JSON protocol. `tool_registry.py` supplies the descriptions, argument types, required fields and examples included in the system prompt, and validates each request before dispatch. The dispatcher executes only the allowlisted Python tools and sends their results back to the model. This is application-managed tool calling, not native API `tools` mode. Malformed requests are returned to the LLM for correction, with at most twelve steps per turn. Final prose contains qualitative explanation and evidence IDs; numbers, dates, sources and score breakdowns are rendered by the application, with bounded repair or a clearly marked tool-only fallback. The audit log records model input messages, outputs, token usage, requests, tool results, errors and duration, with session/turn identifiers. Numerical calculations are deterministic; the LLM's summary still requires review against the logged results.

### Available tool groups

| Tool | Parameters | Calculations |
| --- | --- | --- |
| `list_tickers` | None | Supported symbols and company names; use to resolve names |
| `ticker_metrics` | `ticker`, optional `window=252` | Original four metrics |
| `financial_trends` | `ticker` | Annual profit-margin change, debt/equity growth, ROE |
| `price_analysis` | `ticker`, optional `window=252`, `rolling_window=20` | Calendar 1/3/6/12-month returns, SMA20/50/200, RSI14, MACD12/26/9, maximum drawdown, rolling volatility, volume ratio, latest 50/200 crossover |
| `stock_correlation` | `ticker`, `other_ticker`, optional `window=252` | Correlation of log returns over identical date intervals |
| `rank_stocks` | Optional `top_k=5`, `weights`, `filters`, `window=252` | Filtered, weighted percentile ranking using the original four metrics |

New implementations are in `analysis_tools.py`. Examples to type into the existing local chat:

- "Show Tencent's ROE, debt growth and change in profit margin."
- "Show 0700.HK's RSI, MACD, moving averages and 12-month return."
- "What was Tencent's maximum drawdown over 60 trading sessions? Use 20-day rolling volatility."
- "Compare the return correlation of 0700.HK and 9988.HK over 60 sessions."
- "Draw a price chart for Tencent over the last 120 trading days."
- "Rank the top 5 stocks with net margins at least 0% and debt-to-equity at most 1. Weight revenue growth twice as much as low volatility."

For the last example, the tool arguments should use `weights={"revenue_growth":2,"historical_volatility":1}` and `filters={"net_profit_margin":{"min":0},"debt_to_equity":{"max":1}}`. Bounds are inclusive; say "at least" or "at most" for exact inclusive semantics. Ranking keys are `revenue_growth`, `net_profit_margin`, `debt_to_equity`, and `historical_volatility`. Percent values use whole percentages (10 = 10%); debt-to-equity uses multiples (1 = 1x).

`test_analysis_tools.py` covers independent numeric fixtures, all 30 tickers, currency mismatches, missing dates, ties/filters, and mocked model roundtrips for every tool. It does not prove live-model tool selection; live verification requires `DEEPSEEK_API_KEY` in the running process.

`qwen-python chat_agent.py --provider qwen --prompt "Show 9988.HK metrics" --base-url http://ACTUAL_SERVICE_HOST:8000/v1` runs one question without a file. Interactive mode retains conversation history until exit; restart it for a fresh conversation if it becomes long. `ticker.txt` is retained for the earlier direct-calculation workflow but is no longer read by the batch launcher.

## Data and audit logs

Net profit margin uses profit attributable to the parent. Financial ratios use the curated snapshot's selected inputs, including issuer supplements and restated comparatives. They preserve its reporting periods and currencies; financial observations from the long-form CSV are included as audit evidence rather than summed or substituted across incompatible series. This relies on the source snapshot's period matching and currency metadata. Balance-sheet dates are shown separately from income periods.

Volatility uses the latest 253 observations by default, yielding 252 returns. A shorter available history is used and explicitly labeled `short_history`. The actual start/end dates and observation count are shown. Missing/nonpositive prices inside the selected window produce N/A, not an interpolated or skipped return. Missing financial inputs and nonpositive denominators produce N/A with reasons. Negative net income remains a valid loss margin.

The data is a fixed 18 November 2026 snapshot, with completed prices through 17 November. It is not a live feed. Financial statement dates differ by company; vendor reporting labels and debt definitions retain the limitations in [the dataset notes](agent/data/README.md).

The chat log (`logs/chat.jsonl`, or `--log PATH`) stamps every event with a UTC time, the session ID and the turn ID. Model calls and tool executions record `duration_ms`; a turn ends with `turn_complete` (duration, evidence IDs, whether the tool-only fallback was used) or `turn_error` (error type and message), and a failed turn is rolled back. Rejected responses are logged as `model_format_error` (including replies cut off at the output limit) or `answer_validation_error`.

Each successful request appends parameters, calculation time, formulas, inputs, dates, source URLs, underlying financial observations, values, and statuses to `logs/requests.jsonl` (or `--log PATH`). `--json` also prints the full result.

## Verify

Run the test suite from the agent folder.

```bash
python -m unittest -v
```

Tests cover all tickers, normalization, unknown symbols, independent numeric examples, loss margins, unavailable inputs, invalid prices, and short histories.

# Project Tasks

Based on the proposal: **An Explainable AI Agent for Stock Screening and Analysis**. Tasks are listed in suggested implementation order; statuses below distinguish implemented code from pending real-model acceptance. Historical task ownership is retained; this branch does not assign new team responsibilities.

| # | Task | Description | Done? | Responsible |
|---|------|-----------|-------|-------------|
| 1 | Define scope and calculation rules | Select 30 technology stocks; agree on date range, metric formulas, ranking weights, and trend indicators. | ✅ | DUAN Zihang Raymond |
| 2 | Build the fixed dataset | Collect and clean financial statements and historical prices; save sources, snapshot date, and missing-data flags. | ✅ | DUAN Zihang Raymond |
| 3 | Implement financial tools | Calculate and verify revenue growth, net profit margin, debt-to-equity, and historical volatility. | ✅ | DUAN Zihang Raymond |
| 4 | Implement screening and ranking | Apply mandatory filters, normalize metrics, calculate weighted scores, and return configurable Top-K with score breakdowns. | ✅ | DUAN Zihang Raymond |
| 5 | Implement historical trend tools | Calculate indicators and generate price charts; explain historical bullish/bearish signals without predicting prices. | Implemented indicators and charts; live explanation review pending | |
| 6 | Connect the TACC model | Confirm backend access, configure model calls, and validate structured tool requests and parameters. | ✅ | DUAN Zihang Raymond |
| 7 | Build the three agent workflows | Route requests to individual stock analysis, recommendations, or trend analysis; execute the appropriate tools. | Implemented shared tool loop; live routing acceptance pending | |
| 8 | Add grounded explanations | Explain performance, risks, rankings, and trends using tool results; display the data date and check numerical consistency. | Deterministic numbers and citation guard implemented; qualitative review pending | |
| 9 | Add conversation memory | Preserve results and preferences; support comparisons, indicator questions, and revised screening criteria. | Implemented state, conversations and restart snapshots; live follow-up acceptance pending | DUAN Zihang Raymond |
| 10 | Build backend reliability and logging | Handle invalid inputs, missing data, and service/tool errors; log model calls, tool executions, errors, and timings. | Implemented validation, failure rollback, progress and timing logs | |
| 11 | Build the web interface | Support natural-language requests, execution progress, metrics, rankings, charts, and follow-up questions. | Implemented charts, tables and conversation UI; local browser tested | DUAN Zihang Raymond |
| 12 | Create the evaluation set | Cover all three workflows, follow-ups, and invalid/incomplete inputs; verify reference calculations, filters, rankings, and tool outputs. | ✅ | horoling |
| 13 | Implement the baseline | Use another provider's general-purpose LLM without custom tools; keep prompts and applicable company context identical; record model/API settings. | ✅ | horoling |
| 14 | Run and compare evaluations | Report numerical accuracy, recommendation quality, trend grounding, explanation grounding, follow-up success, and response time. | ✅ | horoling |
| 15 | Analyze failures and limitations | Document at least one observed failure, its cause, and mitigation; acknowledge that different models prevent isolating tool-use effects. | ✅ | horoling |
| 16 | Package and demonstrate | Deliver the working app, source repository, evaluation results, tested demo, and reproducible setup instructions. | Runnable app, tests and instructions provided; live demo/final results pending | |

## Task 1

30 Technology stocks and its raw data downloaded.
Daily price data covers 2024/11/18 to 2026/11/17, collected on 2026/11/18. Some stocks have shorter histories. Financial reporting periods vary by company.

### Implemented metrics and formulas

These formulas reflect `agent/agent.py` and `agent/analysis_tools.py`.

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

Stocks missing required metrics or a complete requested volatility window are excluded from ranking. Results expose each company's reporting dates and period types. The dataset lacks sector metadata and inputs for additional valuation metrics. Ranking measures attractiveness under these metrics, not market popularity.

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

Price returns and SMAs require a full lookback. The MACD signal requires 34 observations. Drawdown includes peak and trough dates. For rolling volatility, `rolling_window` sets the estimation window and `window` limits the number of returned points. The full series is logged and the model receives the last five points.

#### Financial trends and stock comparison

| Metric | Formula | Period / interpretation |
|---|---|---|
| Profit-margin change | `(current annual net income / current annual revenue - prior annual net income / prior annual revenue) * 100` | Percentage points, not percentage growth |
| Debt growth | `(current debt / prior-year debt - 1) * 100` | Latest comparable annual pair |
| Equity growth | `(current equity / prior-year equity - 1) * 100` | Latest comparable annual pair |
| Return on equity (ROE) | `annual net income / ((opening equity + closing equity) / 2) * 100` | Annual profit and average equity |
| Two-stock correlation | `sum((x - mean(x)) * (y - mean(y))) / sqrt(sum((x - mean(x))^2) * sum((y - mean(y))^2))` | Pearson correlation of matched log-return intervals; defaults to latest 252 matched intervals; not market beta |

Financial trends require matching annual periods and currencies and may use older observations than the core snapshot. Growth requires a positive prior value; ROE requires positive opening and closing equity. Missing or invalid inputs return unavailable results. Standalone volatility, drawdown, and correlation can report shorter histories explicitly; ranking excludes incomplete required volatility histories.

Annual trends exclude issuer quarterly supplements. Correlation matches both endpoints of each return interval. Invalid prices are rejected, and a constant return series yields undefined correlation.

**Trend prediction status:** Indicator calculations are implemented, but there is no combined up/down/neutral forecast formula or model yet. Future-price prediction is outside the proposal scope; no forecast model or backtest is required for historical signal analysis. Historical indicators alone are not a validated prediction system.

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


## Task 6

User can send and receive message to/from TACC with correct tool calls.


## Task 9

The agent retains bounded recent messages plus explicit ranking history, filters, weights, windows and focused symbols. `reuse_previous=true` preserves unmodified ranking parameters. Browser conversations have independent IDs, local display histories and private server JSON snapshots. Failed turns roll back state. Long-term semantic memory and cross-job migration are outside this implementation.

## Task 11

The browser renders financial tables, rankings, source/period details, historical adjusted-price/SMA and rolling-volatility charts, live worker phase updates and follow-ups. It supports new conversations, switching, reload recovery and JSON export. Model/user prose is rendered as text; numerical tables are built from evidence. Local browser smoke tests cover desktop and mobile behavior. Real TACC browser acceptance remains pending.


## Tasks 12 - 14

The evaluation code is in the [evaluation folder](evaluation/README.md).

Task 12: 43 cases (85 checks) covering individual analysis, ranking, trend, follow-up, and invalid inputs. Reference answers are generated by calling the deterministic tools in `agent/` directly, not typed by hand.

Task 13: a no-tools baseline on DeepSeek, plus the same TACC Qwen model without tools, so the effect of tools can be separated from the effect of the model.

Task 14: all five systems were run on the same 43 cases on 21 November 2026. Full tables are in [evaluation/results/summary.md](evaluation/results/summary.md), every failed check in [failures.md](evaluation/results/failures.md).

| Metric | Qwen agent (tools) | Qwen, no tools | Qwen, no tools + raw data | DeepSeek, no tools | DeepSeek, no tools + raw data |
|---|---|---|---|---|---|
| Cases fully passed | 93.0% (40/43) | 11.6% | 18.6% | 7.0% | 30.2% |
| Numerical accuracy | 100% (55/55) | 0.0% | 3.6% | 0.0% | 34.5% |
| Ranking in exact order | 100% (13/13) | 0.0% | 0.0% | 0.0% | 0.0% |
| Trend analysis grounding | 100% (17/17) | 11.8% | 17.6% | 5.9% | 52.9% |
| Follow-up success | 100% (6/6) | 0.0% | 0.0% | 0.0% | 0.0% |
| Mean response time per turn | 13.2 s | 1.3 s | 5.4 s | 1.1 s | 1.6 s |

The agent column is the third Qwen run, made after the ranking fix. Scoring is automatic and heuristic; spot-check before quoting. Notes on this table:

- The three remaining agent failures: `invalid-04` is real (asked for a 1-day window, the model used 2 days instead of rejecting the request); `ind-07` and `invalid-03` are scorer false negatives, where the answer is correct in words the checks do not cover.
- Results vary between runs. `follow-01` failed in the second run (the model answered without calling the tool) and passed in the first and third.
- "Qwen, no tools + raw data" has 4 cases that the service rejected with HTTP 400 (prompt too long for the 32K context), so that column is incomplete.
- Earlier agent runs are kept for comparison: `results/old-agent-8-steps/` (6 tools, 8-step limit, 38/43) and `results/old-agent-before-ranking-fix/` (12-step limit, 38/43).

**After merging the `complete_raw` branch (22 November 2026).** The table above was measured on the earlier agent, in which the model wrote every figure into its answer. The merged agent renders figures in evidence tables and the model writes a shorter cited explanation, so those Qwen numbers describe the previous version and the Qwen run has to be repeated on TACC. The merged agent was run on the same 43 cases with DeepSeek (`deepseek-flash`) as the model; results are in [evaluation/results/merged-agent-deepseek/](evaluation/results/merged-agent-deepseek/summary.md):

| Agent version, DeepSeek as the model | Cases passed | Numerical accuracy | Exact ranking order | Mean time per turn | Tokens per turn |
|---|---|---|---|---|---|
| `main` before the merge | 93.0% (40/43) | 100% (55/55) | 100% (13/13) | 5.5 s | 13,261 |
| `complete_raw` as pushed | 86.0% (37/43) | 100% (55/55) | 92.3% (12/13) | 2.8 s | 5,673 |
| Merged | 95.3% (41/43) | 100% (55/55) | 100% (13/13) | 3.1 s | 5,703 |

One run each, so differences of one or two cases are within run-to-run variation. Four of the six `complete_raw` failures were scoring errors (the scorer read ticker order from the rendered evidence text and missed three refusal wordings); the scorer now judges wording and ranking order on the model's explanation only. The remaining merged failures are `invalid-02` (asked "Show the metrics." with no company, the model shows Tencent instead of asking) and `ind-07` (scorer false negative).

Task 15: observed failures, their causes and mitigations, scorer errors and limitations are written up in [evaluation/FAILURE_ANALYSIS.md](evaluation/FAILURE_ANALYSIS.md).
