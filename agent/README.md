# Ticker metrics agent

## Local chat with DeepSeek (start here)

The Python agent and CSV tools run locally. The LLM runs at DeepSeek's API; your messages and selected tool results are sent there. No TACC job is needed. API usage is billed to your DeepSeek account.

On this workstation, open PowerShell in this folder and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local.ps1
```

The launcher asks for your key with hidden input and starts chat. It does not save the key to disk. Type `Show all four metrics for 0700.HK`, then a follow-up such as `Now use 60 trading days for volatility`. Enter `/quit` to exit.

Alternatively set `DEEPSEEK_API_KEY` in your current terminal and run:

```powershell
uv run --no-project python chat_agent.py --provider deepseek
uv run --no-project python chat_agent.py --provider deepseek --prompt "Show Tencent metrics"
```

No additional Python packages are needed. The default provider is DeepSeek, with model `deepseek-flash`; override via the `DEEPSEEK_MODEL` environment variable if needed. The client uses JSON-mode requests and the existing application-managed tool protocol. Credentials are sent only to the official HTTPS endpoint and are not written to the audit log. Logs do contain conversation text and calculation results.

HTTP 401 means check the key; 402 means check API balance; 429 means wait before retrying. Local mocked transport and tool-loop tests do not constitute a live API verification.

Reference: https://api-docs.deepseek.com/quick_start

A deterministic Python agent for the 30 Hong Kong tickers in the supplied CSVs. It accepts a ticker and invokes financial and price calculations at runtime. No LLM, GPU, API key, network request, or third-party Python package is required. Requires Python 3.9 or later.

The `data/` folder contains byte-for-byte copies of the project's three CSVs and their original documentation. Original project data is untouched.

## Run locally or in a TACC terminal

From this folder:

```bash
python agent.py
python agent.py 0700.HK
python agent.py 700 --window 60
python agent.py --list
python agent.py 700 --json
```

On this Windows workstation Python is available through uv; use `uv run --no-project python agent.py` if `python` is unavailable. Interactive mode accepts a ticker, `list`, and `quit`. Unknown tickers produce a clear error. Numeric HKEX codes, leading zeros, and case-insensitive `.HK` suffixes are accepted.

## Submit to the course TACC environment

The included `tuxiv.conf`, `job.sh`, and copied `setup-sdk-account.sh` target the course's existing tcloud/proxy environment, following the local `qwen27b-student-release` package. These are not generic Texas TACC Slurm instructions. The batch launcher now runs the LLM chat agent; start the course model service first. The standalone `agent.py` still works without a model.

1. Configure your tcloud account as described in the existing course package (`tcloud config`, `tcloud init`).
2. In Bash, enter this folder and run `bash setup-sdk-account.sh` if the shared proxy entry point is not already registered.
3. Start the model with `tcloud submit` from the existing `qwen27b-student-release/qwen-public-serve` folder. Record the service job ID and read `slurm_log/qwen-public-serve-JOB_ID.log`. Wait for `Application startup complete` and copy the actual `SERVICE_BASE_URL` value.
4. Return to this agent folder. Set the service URL and question, then submit:

```bash
printf '%s\n' 'http://ACTUAL_SERVICE_HOST:8000/v1' > server-url.txt
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

## How the LLM uses tools

`question.txt → chat_agent.py → TACC Qwen → JSON tool request → Python CSV calculation → Qwen → final answer`

The chat client selects `deepseek_client.py` for local DeepSeek use or the course's unmodified `qwen_client.py` for TACC. The model requests tools via a prompted JSON protocol. `tool_registry.py` supplies the descriptions, argument types, required fields and examples included in the system prompt, and validates each request before dispatch. The dispatcher executes only the allowlisted Python tools and sends their results back to the model. This is application-managed tool calling, not native API `tools` mode. Malformed requests are returned to the LLM for correction, with at most eight steps per turn. The audit log records model messages, token usage, requests, and tool results. Numerical calculations are deterministic; the LLM's summary still requires review against the logged results.

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
- "Rank the top 5 stocks with net margins at least 0% and debt-to-equity at most 1. Weight revenue growth twice as much as low volatility."

For the last example, the tool arguments should use `weights={"revenue_growth":2,"historical_volatility":1}` and `filters={"net_profit_margin":{"min":0},"debt_to_equity":{"max":1}}`. Bounds are inclusive; say "at least" or "at most" for exact inclusive semantics. Ranking keys are `revenue_growth`, `net_profit_margin`, `debt_to_equity`, and `historical_volatility`. Percent values use whole percentages (10 = 10%); debt-to-equity uses multiples (1 = 1x).

### Additional calculation conventions

- Financial trends use the latest available comparable annual vendor observations for each metric. These may have different end dates, and may be older than the latest snapshot. They require identical currencies and annual period types; issuer quarterly supplements are not mixed in. Growth requires positive prior values; ROE requires positive opening and closing equity. Missing comparable observations produce N/A. ROE is annual profit divided by average opening/closing equity. Margin change is in percentage points, not percent growth.
- Returns use calendar-month offsets from the latest price date, with the last observation on or before the target date. A missing full lookback yields N/A. All price indicators use adjusted close. SMA requires a full window. RSI uses Wilder smoothing with 14-change seeds; a completely flat series is defined as 50. MACD uses SMA-seeded EMA12/26 and EMA9 of the MACD line (34 observations for a signal). Historical indicators describe the past and do not predict returns.
- Drawdown is a nonpositive percentage, with peak/trough dates and an explicit short-history status. Its window counts daily return intervals, so 252 requests up to 253 prices. Rolling volatility uses sample standard deviation of log returns and 252-session annualization. `rolling_window` sets its estimation window; `window` limits the number of returned rolling points. Full series are logged; only the last five points are sent to the LLM to limit context size.
- Volume ratio compares the latest volume with the previous 20 sessions, excluding today. Correlation matches both the start and end dates of each return, preventing mismatched one-day/multi-day comparisons. Invalid prices are rejected without interpolation; constant return series have undefined correlation.
- Ranking applies mandatory filters first and calculates percentile scores only among the remaining eligible companies. Growth/margin score higher when larger; debt/volatility score higher when smaller. Ties use midranks; a single candidate scores 50. Weights are normalized to sum to one. Missing required metrics and incomplete requested volatility histories are excluded. Equal final scores are ordered by ticker. Reporting dates/types are exposed per company; the score does not remove those comparability limitations. There is no sector metadata or support for valuation metrics requiring missing data.

`test_analysis_tools.py` covers independent numeric fixtures, all 30 tickers, currency mismatches, missing dates, ties/filters, and mocked model roundtrips for every tool. It does not prove live-model tool selection; live verification requires `DEEPSEEK_API_KEY` in the running process.

`qwen-python chat_agent.py --provider qwen --prompt "Show 9988.HK metrics" --base-url http://ACTUAL_SERVICE_HOST:8000/v1` runs one question without a file. Interactive mode retains conversation history until exit; restart it for a fresh conversation if it becomes long. `ticker.txt` is retained for the earlier direct-calculation workflow but is no longer read by the batch launcher.

## Calculation choices

| Metric | Definition |
| --- | --- |
| Revenue growth | `(revenue / prior-year revenue - 1) * 100`, same reporting period one year earlier |
| Net profit margin | `net_income / revenue * 100`; attributable-to-parent profit, including losses |
| Debt-to-equity | `total_debt / stockholders_equity`, displayed as a multiple |
| Historical volatility | Sample standard deviation of daily adjusted-close log returns, multiplied by `sqrt(252) * 100` |

Financial ratios use the curated snapshot's selected inputs, including issuer supplements and restated comparatives. They preserve its reporting periods and currencies; financial observations from the long-form CSV are included as audit evidence rather than summed or substituted across incompatible series. This relies on the source snapshot's period matching and currency metadata. Balance-sheet dates are shown separately from income periods.

Volatility uses the latest 253 observations by default, yielding 252 returns. A shorter available history is used and explicitly labeled `short_history`. The actual start/end dates and observation count are shown. Missing/nonpositive prices inside the selected window produce N/A, not an interpolated or skipped return. Missing financial inputs and nonpositive denominators produce N/A with reasons. Negative net income remains a valid loss margin.

The data is a fixed 18 November 2026 snapshot, with completed prices through 17 November. It is not a live feed. Financial statement dates differ by company; vendor reporting labels and debt definitions retain the limitations in `data/README.md`.

Each successful request appends parameters, calculation time, formulas, inputs, dates, source URLs, underlying financial observations, values, and statuses to `logs/requests.jsonl` (or `--log PATH`). `--json` also prints the full result.

## Verify

```bash
python -m unittest -v
```

Tests cover all tickers, normalization, unknown symbols, independent numeric examples, loss margins, unavailable inputs, invalid prices, and short histories.
