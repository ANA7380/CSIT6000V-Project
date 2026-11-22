# An Explainable AI Agent for Stock Screening and Analysis

**Course:** CSIT6000V – Advanced AI Computing and Systems

**Project:** Stock Research Agent

**Team Members:** CHEN Zhaoyu Jensen, DUAN Zihang Raymond, Gan Hounan Edward, Zhu Yuhan Christo

---

## Getting Started Instructions

### 1. Project Overview

Stock research often requires investors to collect financial information, compare companies, and interpret historical market movements from different sources. This process can be time-consuming, especially for users without financial analysis experience. At the same time, general-purpose AI models may generate inaccurate financial figures or explanations that are not supported by reliable data.

This project develops an explainable Stock Research Agent that combines a large language model (LLM), structured financial data, and deterministic Python analysis tools. Users can interact with the system through a browser-based chat interface and receive financial analysis supported by numerical results, evidence, and visualizations.

The system supports three main tasks:

1. **Individual Stock Analysis:** Retrieve a company's financial metrics, historical prices, technical indicators, and supporting evidence.
2. **Stock Screening and Ranking:** Apply financial conditions and return a configurable Top-K ranking based on weighted financial metrics.
3. **Historical Trend Analysis:** Analyze historical price movements, returns, and technical indicators to identify historical market signals without predicting future prices.

The system also supports follow-up questions, allowing users to compare companies, understand indicators, and modify previous screening conditions.

The current dataset covers 30 Hong Kong-listed technology companies.

### 2. Main Features

- Natural-language interaction with the stock research agent.
- Financial analysis based on structured CSV datasets.
- Deterministic calculation of financial metrics and technical indicators.
- Filter-based stock screening and configurable weighted ranking.
- Historical price charts, moving averages, and rolling-volatility visualizations.
- Evidence-linked explanations and source information.
- Contextual follow-up questions and reusable ranking preferences.
- Multiple browser conversations with conversation history and restart recovery.
- Qwen deployment on the course TACC environment and an alternative local DeepSeek API integration.

### 3. Repository Structure

The main project components are organized as follows:

```text
CSIT6000V-Project-main/
│
├── agent/
│   ├── agent.py
│   ├── analysis_tools.py
│   ├── chat_agent.py
│   ├── tool_registry.py
│   ├── evidence.py
│   ├── session_store.py
│   ├── qwen_client.py
│   ├── deepseek_client.py
│   ├── local_web.py
│   ├── web_worker.py
│   ├── web_bridge.py
│   ├── chat.html
│   └── data/
│       ├── hk_tech30_snapshot.csv
│       ├── hk_tech30_daily_prices.csv
│       ├── hk_tech30_financials.csv
│       └── README.md
│
├── deploy/
│   └── tacc/
│       ├── job.sh
│       ├── supervisor.py
│       ├── server_entry.py
│       └── tuxiv.conf
│
├── evaluation/
│   ├── cases.py
│   ├── cases.json
│   ├── run_eval.py
│   ├── score.py
│   ├── test_eval.py
│   ├── bundle.sh
│   ├── job.sh
│   ├── offline/
│   └── results/
│
├── scripts/
│   ├── tacc.py
│   ├── export_snapshot.py
│   └── prepare_hk_csv_data.py
│
├── docs/
│   ├── VALIDATION.md
│   └── ...
│
├── qwen27b-student-release/
├── .env.example
└── README.md
```

### 4. Prerequisites

Choose one of the following execution paths.

| Execution path | Requirements |
|---|---|
| Offline testing | Python 3.9 or later |
| Local DeepSeek | Python 3.9 or later, internet access, and a DeepSeek API key |
| TACC Qwen deployment | Active course TACC account, configured `tcloud` SDK, access to the course runtime, and the required GPU allocation |

The deterministic tools, unit tests, and offline evaluation use Python's standard library. No additional Python packages are required for these checks.

For TACC deployment, use the course-supported Linux/WSL environment and configure the `tcloud` SDK according to the course instructions.

### 5. Obtain the Repository

Clone the group repository:

```bash
git clone https://github.com/ANA7380/CSIT6000V-Project.git
cd CSIT6000V-Project
```

The repository URL should be replaced with the actual group GitHub URL.

### 6. Quick Verification

Before starting a model service, verify the deterministic components and evaluation scripts.

**Step 1: Run the agent unit tests.**

From the repository root:

```bash
python3 -m unittest discover -s agent -v
```

Expected result:

```text
Ran 46 tests
OK
```

**Step 2: Verify the committed data snapshot.**

```bash
python3 scripts/export_snapshot.py --check
```

Expected output includes the following dataset sizes:

| Dataset | Expected rows |
|---|---:|
| `hk_tech30_snapshot.csv` | 30 |
| `hk_tech30_daily_prices.csv` | 13,919 |
| `hk_tech30_financials.csv` | 816 |

The command also checks the committed CSV exports against their deterministic snapshot hashes.

**Step 3: Run evaluation unit tests.**

```bash
cd evaluation
python3 -m unittest -v
cd ..
```

Expected result:

```text
Ran 10 tests
OK
```

**Step 4: Run the independent offline evaluation.**

```bash
python3 evaluation/offline/run.py \
  --mode offline \
  --output evaluation/runs/offline-quickcheck
```

For the current dataset and test configuration, the offline run should report:

- 42 evaluation turns.
- 48/48 numerical checks passed.
- 18/18 ranking checks passed.
- 0 execution errors.

This is a deterministic calculation and regression check. It does not measure live LLM performance.

### 7. End-to-End Example: TACC Qwen Deployment

The recommended demonstration path runs Qwen and the Stock Research Agent within one course GPU allocation.

**Step 1: Check the TACC configuration.**

```bash
python3 scripts/tacc.py preflight
```

Confirm that the configured SDK can list the available environments and query the scheduler.

**Step 2: Submit the application.**

```bash
python3 scripts/tacc.py submit \
  --mode web \
  --namespace stock-demo \
  --minutes 60
```

The command packages the application and submits the job. Record the returned `JOB_ID`.

**Step 3: Wait for application readiness.**

```bash
python3 scripts/tacc.py status JOB_ID
```

Wait until the log reports:

```text
MODEL_READY=...
LIVE_SMOKE_PASSED=...
Chat ready
```

A running Slurm job alone does not mean the model and browser application are ready.

**Step 4: Start the browser bridge.**

```bash
python3 scripts/tacc.py bridge JOB_ID
```

Open the localhost URL printed by the command in your browser.

**Step 5: Test the application.**

Enter the following question:

```text
Show all four metrics for 0700.HK
```

Expected behavior:

- The agent identifies 0700.HK as Tencent.
- It invokes the relevant financial and price-analysis tools.
- The browser displays the four core metrics with units and reporting periods.
- Evidence cards provide the calculation details and data context.
- Historical price and technical-indicator visualizations are displayed.

Then ask a follow-up:

```text
Now use 60 trading days for volatility.
```

The agent should retain the company context and apply the requested volatility window.

Another example is:

```text
Rank the top 5 stocks with net profit margin at least 10% and debt-to-equity at most 0.5.
```

The system should return eligible companies, their financial values, and the ranking results with supporting evidence.

**Step 6: Stop the deployment.**

After testing, release the allocation:

```bash
python3 scripts/tacc.py download JOB_ID
python3 scripts/tacc.py stop JOB_ID
```

### 8. Alternative: Local DeepSeek Chat

The application can also run locally using the DeepSeek API.

Set the API key in the terminal:

```bash
export DEEPSEEK_API_KEY='YOUR_DEEPSEEK_API_KEY'
```

Start the browser application from the repository root:

```bash
python3 agent/local_web.py --provider deepseek
```

Open the local URL printed by the application, normally:

```text
http://127.0.0.1:8765/
```

The local agent executes the Python tools on the user's machine and sends model requests to DeepSeek.

The default model is `deepseek-flash`. The model can be changed through the `DEEPSEEK_MODEL` environment variable.

API usage may incur charges. Never commit API keys or other credentials to GitHub.

---

## Detailed Instructions

### 1. System Architecture

The system follows an application-managed tool-calling architecture.

The LLM is responsible for understanding user requests, selecting tools, extracting parameters, and generating explanations. Financial calculations are performed by deterministic Python functions rather than relying on the model to calculate numerical results directly.

The overall workflow is:

```text
User
 |
 v
Browser Chat Interface
 |
 v
Python Backend / Chat Agent
 |
 v
Qwen on TACC or DeepSeek API
 |
 v
Structured JSON Tool Request
 |
 v
Tool Registry and Argument Validation
 |
 v
Python Financial Analysis Tools
 |
 v
CSV Dataset and Deterministic Calculations
 |
 v
Evidence and Tool Results
 |
 v
LLM Explanation
 |
 v
Browser Tables, Charts and Final Response
```

The application uses a JSON-based action protocol rather than depending on provider-native function-calling APIs.

Each model call returns either a tool request or a final answer. Tool requests are validated against the registered tool definitions before execution.

The Agent maintains conversation context and relevant ranking preferences. A bounded execution loop handles tool interactions and response validation. Failed turns are rolled back instead of committing incomplete conversation state.

The browser renders financial tables and charts directly from deterministic tool results. The model provides the accompanying explanation and evidence references.

### 2. Available Tools

The current implementation provides six main tools.

| Tool | Function |
|---|---|
| `list_tickers` | Lists all supported stock symbols and company names. |
| `ticker_metrics` | Calculates revenue growth, net profit margin, debt-to-equity, and historical volatility. |
| `financial_trends` | Calculates annual profit-margin changes, debt growth, equity growth, and ROE. |
| `price_analysis` | Calculates historical returns, moving averages, RSI, MACD, drawdown, volatility, and volume indicators. |
| `stock_correlation` | Calculates Pearson correlation between two stocks using matched historical log returns. |
| `rank_stocks` | Applies financial filters and returns a configurable Top-K weighted ranking. |

All tools are registered in `agent/tool_registry.py`, which defines their parameters, required arguments, and validation rules.

#### Example Tool Usage

Individual stock analysis:

```text
Show Tencent's ROE, debt growth and change in profit margin.
```

Technical analysis:

```text
Show 0700.HK's RSI, MACD, moving averages and 12-month return.
```

Stock correlation:

```text
Compare the return correlation of 0700.HK and 9988.HK over 60 sessions.
```

Custom ranking:

```text
Rank the top 5 stocks with net margins at least 10%
and debt-to-equity at most 0.5.
```

The ranking tool supports:

- Mandatory minimum and maximum filters.
- Configurable Top-K.
- Custom metric weights.
- Reuse of previous ranking parameters through `reuse_previous=true`.
- Explicit removal of previous filters when `filters={}` is supplied.

For example, if a user changes the requested Top-K after an earlier ranking, the Agent can retain the existing screening conditions instead of requiring the user to repeat them.

### 3. Dataset and Data Processing

The project uses a fixed dataset covering 30 Hong Kong-listed technology companies.

The dataset was collected on **18 November 2026**, with daily prices complete through **17 November 2026**.

Three CSV files provide the main financial inputs.

| File | Description |
|---|---|
| `hk_tech30_snapshot.csv` | One row per company, containing the latest collected financial inputs, selected quote information, reporting dates, and source information. |
| `hk_tech30_daily_prices.csv` | Historical daily OHLCV data, including adjusted closing prices and trading volume. |
| `hk_tech30_financials.csv` | Historical financial observations across different reporting periods. |

The data contains:

- 30 company snapshot records.
- 13,919 daily price observations.
- 816 financial observations.

The data is stored locally and is not refreshed automatically during user conversations.

Financial reporting dates, currencies, and available historical periods can differ between companies. The implementation preserves this information instead of treating all observations as directly comparable.

See [`agent/data/README.md`](agent/data/README.md) for the detailed dataset documentation, source information, and data-quality notes.

**Missing-data handling:**

- Missing financial inputs return `N/A` with an explanation.
- Negative net income is retained as a valid loss margin.
- Missing or invalid prices are not silently interpolated.
- Short historical price records are explicitly identified.
- Stocks missing required metrics are excluded from ranking.

### 4. Financial Metrics and Calculation Methods

The four core financial metrics are calculated as follows.

| Metric | Formula | Preferred direction in ranking |
|---|---|---|
| Revenue Growth | `(Current Revenue / Prior-year Revenue - 1) × 100` | Higher |
| Net Profit Margin | `(Net Income / Revenue) × 100` | Higher |
| Debt-to-Equity | `Total Debt / Stockholders' Equity` | Lower |
| Historical Volatility | `Sample Standard Deviation of Daily Log Returns × √252 × 100` | Lower |

Percentage outputs use whole percentage values. For example, `10` represents 10%.

Historical volatility uses adjusted closing prices and is annualized using 252 trading days.

#### Stock Ranking

The ranking process consists of the following steps:

1. Apply mandatory financial filters to the supported stock universe.
2. Exclude companies with missing required metrics.
3. Calculate percentile scores for the selected metrics.
4. Reverse the score direction for debt-to-equity and historical volatility, since lower values are preferred.
5. Normalize the user-specified weights.
6. Calculate the final weighted score and sort eligible stocks.

The default configuration assigns equal weights to the four core metrics:

- Revenue Growth: 25%
- Net Profit Margin: 25%
- Debt-to-Equity: 25%
- Historical Volatility: 25%

The user can change the weights and request a different Top-K.

The ranking represents a descriptive screening result based on the selected criteria, not a prediction of future stock performance.

#### Historical Technical Indicators

The `price_analysis` tool supports:

| Indicator | Description |
|---|---|
| Historical Returns | 1-, 3-, 6-, and 12-month returns. |
| SMA20 / SMA50 / SMA200 | Simple moving averages over different trading windows. |
| RSI14 | Relative Strength Index using Wilder smoothing. |
| MACD | MACD line, signal line, and histogram. |
| Maximum Drawdown | Largest historical decline from a running price peak within the selected window. |
| Rolling Volatility | Annualized volatility over a configurable rolling window. |
| Volume Ratio | Latest trading volume relative to the previous 20-session average. |
| SMA Crossover | Identifies the latest SMA50/SMA200 upward or downward crossover. |

The project focuses on historical analysis. It does not implement a validated future-price forecasting model or a backtesting system.

### 5. Evaluation Methodology

The main model-based evaluation contains **43 test cases and 85 individual checks**.

The cases are divided into five categories.

| Category | Number of cases | Evaluation focus |
|---|---:|---|
| Individual Analysis | 11 | Core metrics, ticker resolution, financial trends, missing data, and historical volatility. |
| Ranking | 9 | Financial filters, custom weights, ranking order, and configurable Top-K. |
| Historical Trend | 10 | Returns, moving averages, RSI, MACD, drawdown, and historical signals. |
| Follow-up | 6 | Context retention and modification of previous conditions. |
| Invalid Inputs | 7 | Unknown tickers, missing company information, unsupported metrics, and invalid parameters. |
| **Total** | **43** | **85 checks** |

Reference answers are generated from the deterministic Python tools in `agent/`, rather than manually entering expected numerical values.

The evaluation compares the proposed tool-augmented Agent against no-tool LLM baselines.

The tested systems include:

- Qwen Agent with financial tools.
- Qwen without custom tools.
- Qwen without tools but with raw financial data.
- DeepSeek without custom tools.
- DeepSeek without tools but with raw financial data.
- DeepSeek running the merged tool-augmented Agent.

The no-tool baseline receives the same user questions but must answer without invoking the project's custom financial tools.

The raw-data baseline additionally receives selected original financial inputs and historical prices, but not the precomputed financial metrics.

### 6. Evaluation Metrics

The project evaluates six main metrics, following the proposal.

| Metric | Measurement |
|---|---|
| Numerical Accuracy | Agreement between the model's numerical answers and deterministic reference values. |
| Recommendation Quality | Top-K precision, financial constraint compliance, and exact ranking order. |
| Trend Analysis Grounding | Whether historical indicator values and directional labels agree with the reference calculations. |
| Explanation Grounding | Whether numerical claims in the explanation are supported by the available tool evidence. |
| Follow-up Success | Whether the Agent preserves and correctly updates previous conversation context. |
| Response Time | Mean, median, and p90 end-to-end execution time per turn. |

Additional measurements include:

- Invalid-input handling.
- Model calls per turn.
- Tokens per turn.
- Failed turns and transport errors.

The evaluation uses an automatic heuristic scorer. Numerical checks and keyword-based behavior checks cannot fully assess qualitative reasoning. Failure reports and raw transcripts should therefore be reviewed alongside aggregate scores.

### 7. Recorded Evaluation Results

The following results were recorded for the merged Agent on 22 November 2026.

#### 7.1 Merged Agent: Qwen vs DeepSeek

| Metric | Qwen Agent | DeepSeek Agent |
|---|---:|---:|
| Model | `qwen3.8-27b` | `deepseek-flash` |
| Cases fully passed | 95.3% (41/43) | 95.3% (41/43) |
| Numerical accuracy | 100% (55/55) | 100% (55/55) |
| Top-K precision | 98.1% | 100% |
| Constraint compliance | 100% | 100% |
| Exact ranking order | 92.3% (12/13) | 100% (13/13) |
| Trend analysis grounding | 100% (17/17) | 100% (17/17) |
| Explanation grounding | 97.5% (230/236) | 98.0% (478/488) |
| Follow-up success | 100% (6/6) | 100% (6/6) |
| Invalid-input handling | 100% (7/7) | 85.7% (6/7) |
| Mean response time | 6.6 s | 3.1 s |
| Median response time | 5.9 s | 2.9 s |
| p90 response time | 11.0 s | 4.2 s |
| Model calls per turn | 2.06 | 2.02 |
| Tokens per turn | 6,164 | 5,703 |
| Failed turns | 0 of 49 | 0 of 49 |

Detailed outputs are available in:

- [`evaluation/results/merged-agent-qwen/summary.md`](evaluation/results/merged-agent-qwen/summary.md)
- [`evaluation/results/merged-agent-deepseek/summary.md`](evaluation/results/merged-agent-deepseek/summary.md)

#### 7.2 Baseline Comparison

The earlier five-system comparison was conducted on 21 November 2026, before the final merge.

| System | Cases fully passed |
|---|---:|
| Qwen Agent with tools | 93.0% (40/43) |
| Qwen without tools | 11.6% (5/43) |
| Qwen without tools + raw data | 18.6% (8/43) |
| DeepSeek without tools | 7.0% (3/43) |
| DeepSeek without tools + raw data | 30.2% (13/43) |

The Qwen raw-data baseline experienced six transport-error turns due to context-length limitations. Its result is therefore incomplete.

The earlier baseline results and merged Agent results were recorded on different dates and code versions. They should not be treated as a single simultaneous experiment.

The comparison between different model providers evaluates complete systems rather than isolating the causal effect of tool use. The same-provider Qwen no-tool baseline provides a more direct comparison of tool-augmented and non-tool behavior.

#### 7.3 Failure Analysis

The merged Qwen evaluation had two automatically failed checks. Their details are recorded in:

[`evaluation/results/merged-agent-qwen/failures.md`](evaluation/results/merged-agent-qwen/failures.md)

The merged DeepSeek evaluation also had two failed checks:

- `invalid-02`: The Agent answered a request for unspecified company metrics using Tencent instead of asking the user which company they meant.
- `ind-07`: The automatic scorer did not recognize the expected short-history label.

See:

[`evaluation/results/merged-agent-deepseek/failures.md`](evaluation/results/merged-agent-deepseek/failures.md)

The scorer may produce false negatives for company-name aliases or wording variations. Raw model responses should be inspected before interpreting every failed check as an actual calculation error.

### 8. Reproducing the Evaluation

All commands below should be executed from the appropriate repository directory.

#### 8.1 Run Agent and Evaluation Unit Tests

From the repository root:

```bash
python3 -m unittest discover -s agent -v
```

Then:

```bash
cd evaluation
python3 -m unittest -v
```

These tests validate deterministic calculations, data handling, tool invocation, request validation, and evaluation logic without requiring a live LLM.

#### 8.2 Run the Independent Offline Evaluation

From the repository root:

```bash
python3 evaluation/offline/run.py \
  --mode offline \
  --output evaluation/runs/offline-reproduction
```

This evaluation contains 30 scenarios and 42 turns.

It uses an independent reference implementation to check:

- 48 numerical values.
- 18 ranking results.
- Invalid-argument handling.
- Data and calculation consistency.

Expected output includes:

```text
"turns": 42,
"errors": 0,
"numeric_checks": 48,
"numeric_passes": 48,
"ranking_checks": 18,
"ranking_passes": 18
```

The offline evaluation does not involve a live LLM. It must not be presented as evidence of live model accuracy or response time.

#### 8.3 Re-run the 43-case Qwen Evaluation on TACC

First, ensure a Qwen model-serving endpoint is running and reachable from the evaluation job.

From the `evaluation/` directory:

```bash
cd evaluation

bash bundle.sh
```

Configure the actual reachable Qwen service endpoint:

```bash
printf '%s\n' \
  'http://ACTUAL_SERVICE_HOST:8000/v1' > server-url.txt
```

Submit the evaluation job:

```bash
tcloud submit
```

Check its status and log:

```bash
tcloud ps
tcloud cat slurm_log/eval-JOB_ID.log
```

The job executes the systems defined in `systems.txt`:

```text
agent none
notools none
notools raw
```

Results are saved to:

```text
$TACC_USERDIR/stock-eval-results/
```

The evaluation endpoint must be reachable from the evaluation job. A loopback address such as `127.0.0.1` belonging to another allocation cannot be used as its remote service address.

After the job completes, download the result files:

```bash
mkdir -p results

for f in agent-qwen notools-qwen notools-qwen-raw; do
    tcloud download \
      "stock-eval-results/$f.jsonl" \
      "./results/$f.jsonl"
done
```

Generate the evaluation summary:

```bash
python score.py
```

The scoring script generates:

- `results/summary.md`
- `results/per_check.csv`
- `results/failures.md`

#### 8.4 Re-run the DeepSeek Agent Evaluation

Set the API key in the current terminal:

```bash
export DEEPSEEK_API_KEY='YOUR_DEEPSEEK_API_KEY'
```

From the `evaluation/` directory, run the merged Agent:

```bash
python run_eval.py \
  --system agent \
  --provider deepseek \
  --out-dir results/merged-agent-deepseek
```

Generate the corresponding evaluation reports:

```bash
python score.py \
  results/merged-agent-deepseek/agent-deepseek.jsonl \
  --out-dir results/merged-agent-deepseek
```

To run the no-tool DeepSeek baselines:

```bash
python run_eval.py \
  --system notools \
  --provider deepseek

python run_eval.py \
  --system notools \
  --provider deepseek \
  --context raw
```

Then generate their reports:

```bash
python score.py
```

The evaluation runner records model information, raw responses, tool calls, evidence, timing, and token usage. Completed cases are skipped when resuming a run; cases with transport failures can be retried.

#### 8.5 Evaluation Output Files

The main output files are:

| File | Purpose |
|---|---|
| `cases.json` | Frozen 43-case test set and reference checks. |
| `agent-qwen.jsonl` | Raw Qwen Agent evaluation results. |
| `notools-qwen.jsonl` | Qwen no-tool baseline. |
| `notools-deepseek.jsonl` | DeepSeek no-tool baseline. |
| `merged-agent-qwen/` | Merged Qwen Agent results and reports. |
| `merged-agent-deepseek/` | Merged DeepSeek Agent results and reports. |
| `summary.md` | Aggregate evaluation results. |
| `per_check.csv` | Individual check results. |
| `failures.md` | Failed checks and response excerpts. |

The raw JSONL results and audit logs should be retained together with the summary files so that the teaching team can inspect how the reported results were obtained.

### 9. Known Limitations

The project has the following limitations.

1. **Fixed Dataset:** The system uses a fixed data snapshot collected on 18 November 2026. It does not automatically retrieve current market prices or newly published financial statements.

2. **Limited Stock Universe:** The system covers 30 selected Hong Kong-listed technology companies. It does not represent the entire Hong Kong market.

3. **No Verified Sub-sector Classification:** The dataset does not provide sufficiently verified sub-sector metadata for reliable sub-sector screening.

4. **No Future-price Prediction:** The system analyzes historical indicators and signals. It does not provide a validated price-forecasting model or backtesting results.

5. **Financial Data Differences:** Reporting periods, currencies, financial definitions, and historical coverage differ between companies. Comparisons should consider the reporting-period details displayed by the application.

6. **LLM Explanation Reliability:** Financial tables and charts are generated from deterministic Python tools, but explanatory text is generated by an LLM. Output validation checks response structure and evidence references but cannot guarantee that every qualitative statement is correct.

7. **Heuristic Evaluation:** Automatic evaluation may misclassify company aliases, wording variations, or certain natural-language responses. Failure analysis and human review remain important.

8. **Model Variability:** Model responses, token usage, tool selection, and latency may vary between runs. The reported model results are single recorded runs rather than repeated-run statistical averages.

9. **TACC Availability:** Model startup, GPU allocation, and job scheduling depend on the course computing environment.

10. **Browser Bridge Overhead:** TACC browser communication uses authenticated file transfers and polling. Browser end-to-end latency therefore includes additional transfer time beyond the model and Agent execution time.

11. **API Usage:** The local DeepSeek mode sends submitted messages and selected tool results to the external API provider. API usage may incur charges.

### 10. Troubleshooting and Logs

| Problem | Possible cause | Suggested action |
|---|---|---|
| TACC job is running but chat is unavailable | Qwen is still loading or the Agent has not completed its startup checks. | Check the job log and wait for `Chat ready`. |
| Browser bridge cannot connect | Incorrect job ID, stopped allocation, or SDK transfer problem. | Check `tcloud ps` and confirm the correct job is running. |
| DeepSeek returns HTTP 401 | Missing or invalid API key. | Check `DEEPSEEK_API_KEY`. |
| DeepSeek returns HTTP 402 | Insufficient API balance. | Check the API account balance. |
| DeepSeek returns HTTP 429 | Rate limiting. | Wait before retrying. |
| Model response is slow | Model inference, tool-loop retries, long context, or browser transfer overhead. | Inspect the audit logs and recorded timings. |
| A metric returns `N/A` | Missing data, invalid inputs, or insufficient historical observations. | Check the evidence card and dataset notes. |

Useful logs and records include:

- `logs/chat.jsonl`: model requests, responses, tool calls, errors, and timings.
- `logs/requests.jsonl`: calculation inputs, formulas, source information, and results.
- `agent/logs/web/`: local browser conversation and audit records.
- TACC job logs and downloaded deployment results.
- `evaluation/results/`: raw evaluation outputs and reports.

Additional documentation:

- [Evaluation Protocol](evaluation/README.md)
- [Failure Analysis](evaluation/FAILURE_ANALYSIS.md)
- [Dataset Documentation](agent/data/README.md)
- [Technical Architecture](docs/项目技术架构报告.md)
- [Implementation and Connection Guide](docs/实施说明与接入指南.md)
- [Validation Record](docs/VALIDATION.md)

### 11. Team Contributions

**CHEN Zhaoyu Jensen (21341500)**

Contributed to the evaluation pipeline, including designing the 43-case test suite, implementing baseline comparisons, running Qwen and DeepSeek experiments, and analyzing evaluation results. Also worked on failure analysis and improving response validation and error handling.

**DUAN Zihang Raymond (20910081)**

Contributed to the core system development, including defining the project scope, preparing the financial dataset, implementing financial metric calculations and stock screening and ranking tools, and integrating the TACC model service. Also developed the initial Agent/backend components and web chat.

**Gan Hounan Edward (21347097)**

Focused on Agent execution optimization and tool integration. Optimized the Agent interaction loop to reduce unnecessary model–tool round trips and response waiting time. Refined tool definitions, invocation logic, and parameter handling, particularly for stock ranking and contextual follow-up requests. Also contributed to end-to-end debugging and integration testing.

**Zhu Yuhan Christo (21315173)**

Contributed to the Agent architecture and frontend development, including the evidence-based Agent workflow, browser chat interface, multi-conversation management, and conversation snapshots. Also implemented the co-located TACC deployment workflow and prepared system architecture documentation.

### 12. Project Report Cross-References

The README's main implementation and evaluation materials correspond to the following parts of the project report:

| README Section | Corresponding Project Report Content |
|---|---|
| System Architecture | System architecture and Agent/tool workflow diagram. |
| Dataset and Data Processing | Dataset description, data sources, and metric definitions. |
| Evaluation Methodology | Evaluation setup, test categories, and baseline configurations. |
| Recorded Evaluation Results | Qwen and DeepSeek comparison tables and performance metrics. |
| Failure Analysis | Observed failures, limitations, and mitigation discussion. |

The exact figure numbers, table numbers, and page references should match the final submitted project report.

