# Explainable Stock Research Agent

**Course:** CSIT6000V - Advanced AI Computing and Systems  
**Repository:** [ANA7380/CSIT6000V-Project](https://github.com/ANA7380/CSIT6000V-Project)  
**Team:** CHEN Zhaoyu Jensen, DUAN Zihang Raymond, Gan Hounan Edward, Zhu Yuhan Christo

A conversational research application for financial screening and historical analysis of 30 Hong Kong-listed technology companies. Deterministic Python tools calculate financial metrics, rankings and technical indicators; an LLM selects tools and explains the results with evidence references.

The application supports company analysis, configurable Top-K screening, historical charts, and contextual follow-up questions. It uses a fixed dataset collected on 18 November 2026, with daily prices through 17 November 2026.

The documentation follows the two-part [NSDI '27 artifact README guidance](https://www.usenix.org/conference/nsdi27/call-for-artifacts#readme-instructions): a quick functionality check followed by complete evaluation instructions.

**Evaluation status.** The latest runtime revision passes offline regression tests. The recorded 41/43 model results are from the earlier merged Agent; they are reported separately from the current offline validation. A new 43-case live benchmark and browser visual acceptance test remain pending. The SDK comparison measures operation counts, not a real-platform speedup.

## Getting Started Instructions

### G1. Prerequisites and access

| Path | Requirements | What it checks |
|---|---|---|
| Offline quick start | Git, Python 3.9+, ordinary CPU machine; Linux/WSL recommended | Real CSV calculations, tests, and a scripted interface; no LLM |
| TACC application | Configured course `tcloud` SDK and account, course project runtime/model access, allocation for two GPUs | Qwen, tools, worker, and browser bridge |
| Local live alternative | Python 3.9+, internet access, `DEEPSEEK_API_KEY` | Live DeepSeek with local tools |

The application, offline tests, and evaluation runner use Python's standard library. Git and the course SDK are external tools. Playwright/Chrome are needed only for the optional browser acceptance scripts. Model weights and GPU libraries are supplied by the course TACC environment, not installed by this repository.

Keep API credentials and private keys in the local environment, outside the repository.

```bash
git clone https://github.com/ANA7380/CSIT6000V-Project.git
cd CSIT6000V-Project
python3 --version
git rev-parse HEAD
```

Record the checkout hash with new experiments. These instructions apply to the runtime-review revision, including `docs/RUNTIME_REVIEW.md`, `scripts/reproduce_tacc_eval.py`, and the 77-test Agent suite.

### G2. Quick verification without a model

Run from the repository root:

```bash
python3 -m unittest discover -s agent -v
python3 -m unittest discover -s evaluation -v
python3 -m unittest discover -s scripts \
  -p test_reproduce_tacc_eval.py -v
python3 scripts/export_snapshot.py --check
python3 evaluation/offline/run.py \
  --mode offline --output evaluation/runs/offline-quickcheck
```

Expected results:

| Check | Expected output |
|---|---|
| Agent tests | `Ran 77 tests`, then `OK` |
| Evaluation tests | `Ran 10 tests`, then `OK` |
| Co-located evaluation packaging tests | `Ran 3 tests`, then `OK`; these use mocked commands |
| Snapshot check | 30 company rows, 13,919 price rows, 816 financial rows; hash check succeeds |
| Independent offline evaluation | 42 turns, 0 errors, 48/48 numeric checks and 18/18 ranking checks |

Local offline checks completed in under two minutes; runtime varies by machine. They validate calculation and orchestration behavior, not live LLM quality or TACC latency. Evaluation outputs are saved under the supplied `--output` directory.

### G3. Quick-start example

First run one real deterministic calculation:

```bash
python3 agent/agent.py 0700.HK --window 60 --json \
  --log var/quickstart-metrics.jsonl
```

Expected: a JSON result for `0700.HK` / Tencent, including `Revenue growth`, `Net profit margin`, `Debt-to-equity`, and `Historical volatility`, with values or explicit availability flags, reporting periods, formulas, and source inputs. The calculation audit is saved to the specified JSONL file.

Then exercise the browser-to-backend-to-tool path without a model:

```bash
python3 agent/demo_web.py --port 8765
```

Open `http://127.0.0.1:8765/`. The page explicitly says **OFFLINE SCRIPTED DEMO / No LLM is connected**. Click **Tencent overview + chart**, then **Send**. Expected: core metric tables, evidence IDs, a price/moving-average chart, and a rolling-volatility chart. Start another conversation, use the ranking example, then ask `Keep the same criteria and show the top 10.` The deterministic ranking should update Top-K while retaining its filters.

This fixture verifies the interface and orchestration with real frozen data, not autonomous model behavior. Press Ctrl+C to stop it before starting another local server on the same port. Browser visual acceptance of the latest UI remains pending; HTTP-level tests cover the request/result flow.

### G4. TACC deployment

Use the same Ubuntu/WSL terminal in which your course SDK works:

```bash
command -v tcloud
python3 scripts/tacc.py preflight
python3 scripts/tacc.py submit \
  --mode web --namespace stock-demo --minutes 60
```

Record the actual `JOB_ID` and replace it in subsequent commands:

```bash
python3 scripts/tacc.py status JOB_ID
```

Wait for `MODEL_READY`, `LIVE_SMOKE_PASSED`, and **Chat ready**. Slurm state `R` or `MODEL_READY` alone is insufficient. Queue time and model startup can take several minutes and depend on the platform; do not repeatedly submit while waiting.

```bash
python3 scripts/tacc.py bridge JOB_ID --local-ui
```

Open the printed localhost URL. `--local-ui` uses this checkout's page, including timing details. Ask:

```text
Analyze 0700.HK's historical trend. Show moving averages and RSI.
Do not predict future prices.
```

Expected: a `price_analysis` evidence card, historical charts, SMA and RSI values with dates, and a cited explanation restricted to historical observations. For the committed snapshot, RSI14 is approximately 35.98; SMA20, SMA50, and SMA200 are approximately HKD 396.07, 415.62, and 464.87. Wording can vary. These expected values are dataset checks, not current market quotes.

For a follow-up test, ask:

```text
Rank the top 3 by net profit margin only, with margin at least 10%.
```

Then ask `Keep the same filters and weights, but return the top 5.` Expected: the stored margin filter and single-metric weights remain, while Top-K changes. Inspect the evidence arguments, not only the prose.

Save results and release the allocation:

```bash
python3 scripts/tacc.py download JOB_ID
python3 scripts/tacc.py stop JOB_ID
```

Ctrl+C stops the local bridge only. It does not cancel the GPU job. The application and Qwen share one allocation; `127.0.0.1:42865` is internal to that node. Do not use that loopback address from a separate evaluation job or laptop.

### G5. Local DeepSeek deployment

Configure the key in the terminal environment, then run (replace the example value):

```bash
export DEEPSEEK_API_KEY='YOUR_DEEPSEEK_API_KEY'
python3 agent/local_web.py --provider deepseek --port 8765
```

The default configured model is `deepseek-flash`; `DEEPSEEK_MODEL` overrides it. Requests are sent to DeepSeek and may incur API charges. The same Python tools and fixed data run locally. No GPU is needed for local tool execution.

## Detailed Instructions

### D1. Architecture and repository layout

| Location | Purpose |
|---|---|
| `agent/` | Calculations, six tools, JSON action protocol, evidence, state, transports, web UI/bridge/worker, tests |
| `agent/data/` | The three application CSVs and dataset documentation |
| `data/snapshot_2026-11-18/` | Frozen source snapshot used by independent offline references |
| `deploy/tacc/` | Co-located model/worker startup and supervision |
| `evaluation/cases.json`, `cases.py` | Frozen 43-case model test set and reference construction |
| `evaluation/offline/` | Independent references and deterministic evaluation |
| `evaluation/results/` | Archived per-case model outputs, summaries, and failed checks |
| `evaluation/bridge-baseline/` | Frozen pre-review bridge source for the SDK-operation comparison |
| `scripts/` | Packaging, snapshot checks, scoring/reproduction helpers, local comparison scripts |
| `docs/` | Architecture, deployment, failure/validation records, and runtime review |

The browser sends a request to a Python backend. The LLM returns an allowlisted tool request, a batch of independent read-tool requests, or an answer. The application validates arguments, executes Python tools, and supplies evidence to the model. Tables and charts are generated directly from tool results. The backend keeps conversation context and ranking preferences, and rolls back failed turns.

| Tool | Function |
|---|---|
| `list_tickers` | Supported company/symbol lookup |
| `ticker_metrics` | Four core financial/volatility metrics |
| `financial_trends` | Comparable annual margin change, debt/equity growth, ROE |
| `price_analysis` | Returns, SMAs, Wilder RSI14, MACD, drawdown, rolling volatility, volume ratio |
| `stock_correlation` | Pearson correlation of matched adjusted-close log-return intervals |
| `rank_stocks` | Mandatory financial filters followed by weighted percentile ranking |

The latest protocol allows at most six independent reads in a batch. Rankings run separately because they update preferences. Successful identical requests are reused within one user turn; changed parameters and later turns are recalculated. The total model-call budget is 12. Consecutive format/truncation failures and repeated answer-validation failures have separate bounded repair paths. See `agent/chat_agent.py` and `tool_registry.py` for the executable rules.

### D2. Data and calculation configuration

The snapshot contains 30 companies, 13,919 daily price observations, and 816 financial observations. Coverage and financial reporting dates vary by company. Inputs and provenance are documented in [the dataset notes](agent/data/README.md).

| Core metric | Definition | Favorable ranking direction |
|---|---|---|
| Revenue growth | `(revenue / matching prior-year revenue - 1) * 100` | Higher |
| Net profit margin | `net income / revenue * 100` | Higher |
| Debt-to-equity | `total debt / stockholders equity` | Lower |
| Historical volatility | Sample standard deviation of daily adjusted-close log returns, multiplied by `sqrt(252) * 100` | Lower |

Percent values use whole percentages: `10` means 10%. Debt/equity is a multiple. Default volatility lookback is 252 returns. Default ranking is Top-5 with equal weights across the four core metrics. Filters are applied before percentile scoring; weights are normalized, ties use midranks, and symbol order breaks equal final scores. Only metrics required by positive weights or filters determine missing-data exclusions.

Negative net income remains a valid loss margin. Nonpositive denominators and invalid prices produce unavailable results or errors, not invented values. Required short volatility histories are excluded from rankings. Historical analysis preserves unavailable/short-history flags and reporting periods. There is no price-forecasting model or backtest.

### D3. Cases, baselines, metrics, and configuration

The model suite has **43 cases, 85 checks, and 49 executed turns**. A multi-turn case is counted once; follow-up checks assess the specified turn. The independent offline suite has 30 scenarios and 42 turns and is a separate evaluation.

| Model-case category | Cases | Coverage |
|---|---:|---|
| Individual | 11 | Metrics, name resolution, windows, financial trends, missing/short data |
| Ranking | 9 | Filters, weights, order, empty results, Top-K |
| Historical trend | 10 | Indicators, returns, historical labels, no prediction |
| Follow-up | 6 | Retaining and updating conversation conditions |
| Invalid/incomplete input | 7 | Missing company, unknown ticker, unsupported data, invalid arguments |

The runner supports `agent` and `notools`, providers `qwen` and `deepseek`, and no-tool contexts `none` or `raw`. The `raw` baseline receives selected raw inputs, not computed metrics. It contains full histories for at most two required tickers; ranking cases lack all-company price histories because of context constraints. Baselines therefore have documented information/context limits.

The current configuration uses temperature 0 and max 1,800 output tokens per call. Qwen requests use the configured `qwen3.8-27b` service with thinking disabled. DeepSeek uses the configured model name and JSON output mode. Preserve model, provider, context, usage, and deployment settings with each run. A provider alias or serving implementation may change independently of this repository.

Metrics are: numeric agreement with references; Top-K precision, constraint compliance and exact order; trend-value/label checks; support for numerical claims in explanations; follow-up checks; and runner response time. The heuristic numerical scorer accepts reference rounding within its documented tolerance and ignores sign in some matches. It does not establish that a number belongs to the correct metric or that all prose is semantically supported. Follow-up and invalid-input checks also use keyword/label heuristics. Inspect failed cases and sample passing transcripts.

### D4. Main results and their evidence

**Table 1. Recorded merged Agent results (22 November 2026, historical code).**

| Metric | Qwen Agent | DeepSeek Agent |
|---|---:|---:|
| Model | `qwen3.8-27b` | `deepseek-flash` |
| Cases fully passed | 41/43 (95.3%) | 41/43 (95.3%) |
| Numerical checks | 55/55 | 55/55 |
| Top-K precision | 98.1% | 100% |
| Constraint compliance | 100% | 100% |
| Exact ranking order | 12/13 | 13/13 |
| Trend checks | 17/17 | 17/17 |
| Numerical-claim grounding | 230/236 (97.5%) | 478/488 (98.0%) |
| Follow-up cases | 6/6 | 6/6 |
| Invalid-input cases | 7/7 | 6/7 |
| Mean / median / p90 runner time | 6.6 / 5.9 / 11.0 s | 3.1 / 2.9 / 4.2 s |
| Model calls / tokens per turn | 2.06 / 6,164 | 2.02 / 5,703 |
| Failed turns | 0/49 | 0/49 |

Raw sources are `evaluation/results/merged-agent-qwen/agent-qwen.jsonl` and `evaluation/results/merged-agent-deepseek/agent-deepseek.jsonl`; each directory contains its summary and failed checks. Re-scoring these raw files reproduces the table's metrics. It does not rerun inference. The archived rows do not fully identify historical source and hardware state. Fresh runs should record the checkout and deployment configuration; their generation conditions may differ.

**Table 2. Earlier five-system comparison and current re-scoring (same raw outputs).**

| System | Archived 21 November summary | Current bundled scorer |
|---|---:|---:|
| Qwen Agent | 40/43 (93.0%) | 40/43 (93.0%) |
| Qwen no tools | 5/43 (11.6%) | 5/43 (11.6%) |
| Qwen no tools + raw inputs | 8/43 (18.6%), incomplete | 8/43 (18.6%), incomplete |
| DeepSeek no tools | 3/43 (7.0%) | 3/43 (7.0%) |
| DeepSeek no tools + raw inputs | 13/43 (30.2%) | 14/43 (32.6%) |

The DeepSeek raw-input discrepancy is one behavior check, `trend-09`: the current reference/scorer accepts the existing answer's `I can't forecast` wording; the archived per-check CSV marks that check failed. The raw answer is unchanged. This is a scoring-artifact discrepancy, not a new inference result or model improvement. The current scorer therefore reproduces 14/43 for these raw outputs. The archived summary remains unchanged. The two records are available under `evaluation/results/` and `docs/validation/readme-reproduction/`, respectively.

The Qwen raw-input run includes six transport-error turns associated with context limits. Treat it as incomplete; it cannot establish a reliable completed-run accuracy. Raw files and the aggregate table are under `evaluation/results/`. Do not combine Tables 1 and 2 into a single same-version experiment. Comparisons across providers reflect whole systems and hardware, not an isolated causal effect of tools.

**Table 3. Current runtime-review evidence (23 November 2026, offline).**

| Check | Observed result |
|---|---|
| Agent / evaluation unit tests | 77 / 10 passed |
| Deterministic outputs and model projections | 156 / 156 match the input runtime-review baseline |
| Independent offline evaluation | 48/48 numeric checks, 18/18 rankings, 0 errors across 42 turns |
| SDK calls with 3 pending polls | 9 baseline -> 6 updated |
| SDK calls with 8 pending polls | 19 baseline -> 12 updated |
| Completed-result recheck | 1 extra SDK call -> 0 with a cached reply |

The SDK comparison uses real local HTTP handlers and file-copy fixtures instead of TACC transfers. It demonstrates fewer operations, not a measured platform speedup. Evidence is in `docs/validation/runtime-review/`; [the runtime review](docs/RUNTIME_REVIEW.md) defines each test and timing scope. The reproduction helper also has three offline packaging tests, reported separately from the original runtime-review suite.

**Timing scope.** Tables 1 and 2 report wall time around the evaluation runner's system call, including model/tool processing. They exclude the browser SDK bridge, allocation wait and model startup. In the UI, Agent and End to end are different scopes. Model API time includes service waiting. Polling can overlap inference, so phase times must not be added. A long browser wait is not automatically slow model inference.

### D5. Reproduce the results

Run all commands from the repository root unless noted. Use new output directories for new inference runs: the runner skips completed cases already present and retries designated transport failures. Keep archived JSONL files unchanged.

#### D5.1 Re-score the archived model tables, without a model

```bash
python3 evaluation/score.py \
  evaluation/results/merged-agent-qwen/agent-qwen.jsonl \
  evaluation/results/merged-agent-deepseek/agent-deepseek.jsonl \
  --out-dir evaluation/reproduced/recorded-merged

python3 evaluation/score.py \
  evaluation/results/agent-qwen.jsonl \
  evaluation/results/notools-qwen.jsonl \
  evaluation/results/notools-qwen-raw.jsonl \
  evaluation/results/notools-deepseek.jsonl \
  evaluation/results/notools-deepseek-raw.jsonl \
  --out-dir evaluation/reproduced/recorded-baselines
```

Each output directory contains `summary.md`, `per_check.csv`, and `failures.md`. Expected: Table 1's metrics and Table 2's **current bundled scorer** column, including 14/43 for DeepSeek raw inputs and the raw-Qwen incomplete-run warning. Scoring does not contact a model provider.

#### D5.2 Repeat independent offline checks and the bridge comparison

```bash
python3 evaluation/offline/run.py \
  --mode offline --output evaluation/runs/offline-reproduction

python3 scripts/benchmark_bridge_optimization.py \
  --baseline evaluation/bridge-baseline \
  --output evaluation/runs/bridge-comparison.json
```

Expected: the offline numeric/ranking counts and the SDK-operation counts in Table 3. The frozen bridge baseline is included in the repository. Model-projection differential tests require both complete source versions; their archived JSON includes source hashes, but re-running them is optional and is not a substitute for fresh model evaluation.

#### D5.3 Run a fresh Qwen comparison in one TACC allocation

The reproduction helper packages the model and evaluation in one GPU job, so the runner can reach the allocation-local model. It copies code into a unique package and replaces only the generated package's worker entry point. It does not change the repository's web entry point or public course files.

Inspect a package without submitting, or submit a full run:

```bash
python3 scripts/reproduce_tacc_eval.py package --minutes 60
python3 scripts/reproduce_tacc_eval.py submit --minutes 60
```

The default systems are Agent, no-tool Qwen, and no-tool Qwen with raw inputs, using the same service. For a smaller live acceptance run of the Agent suite only:

```bash
python3 scripts/reproduce_tacc_eval.py submit \
  --systems agent --minutes 60
```

Record the new `JOB_ID`:

```bash
python3 scripts/tacc.py status JOB_ID
```

This is an evaluation job, not a web job. Expect `MODEL_READY`, `EVAL_START=...`, and eventually `EVALUATION_COMPLETE=...`; it does not emit Chat ready or start a browser bridge. On success, the job exits and releases its allocation. If it times out or fails, retain partial files and the job/model logs; do not report an incomplete run as a completed benchmark. Package construction and command wiring pass offline tests; a live TACC validation run remains pending.

```bash
python3 scripts/tacc.py download JOB_ID
```

Outputs appear under `var/tacc-results/JOB_ID/evaluation/`: selected system JSONL files, `audit/`, and `scored/summary.md`, `per_check.csv`, and `failures.md`. Raw outputs are isolated by job ID. Downloaded summaries should use the current checkout label and should not overwrite the historical tables. The helper uses the current conservative serving configuration; see `deployment.json` and the downloaded model log before comparing latency with old runs.

The older `evaluation/job.sh` remains an alternative only when a separately deployed service has a real endpoint reachable from that job. Its `server-url.txt` cannot point to another allocation's `127.0.0.1`.

#### D5.4 Run fresh DeepSeek comparisons locally

Set `DEEPSEEK_API_KEY` in the environment. Optionally set `DEEPSEEK_MODEL` and record the value. Use a new run label, for example:

```bash
python3 evaluation/run_eval.py --system agent --provider deepseek \
  --out-dir evaluation/runs/current-deepseek
python3 evaluation/run_eval.py --system notools --provider deepseek \
  --out-dir evaluation/runs/current-deepseek
python3 evaluation/run_eval.py --system notools --provider deepseek \
  --context raw --out-dir evaluation/runs/current-deepseek

python3 evaluation/score.py \
  evaluation/runs/current-deepseek/agent-deepseek.jsonl \
  evaluation/runs/current-deepseek/notools-deepseek.jsonl \
  evaluation/runs/current-deepseek/notools-deepseek-raw.jsonl \
  --out-dir evaluation/runs/current-deepseek/scored
```

Each case starts an independent conversation; follow-up turns share that case's state. Results record model/provider/context, prompts, answers, tool traces, usage and timings. These runs use an external API and incur usage charges.

### D6. Report cross-references

The following captions connect the reproducible evidence to the project report. Historical model experiments and current offline validation use separate labels.

| README evidence | Corresponding report content | Reproduction path |
|---|---|---|
| D1-D2 | System Architecture; Dataset and Data Processing; Financial Metrics | G2-G4; dataset/source files |
| D3 | Evaluation Methodology; Evaluation Metrics | Frozen cases, runner configuration and scorer |
| Table 1 | Recorded Evaluation Results: Merged Agent, Qwen vs DeepSeek | D5.1 merged raw-file scoring |
| Table 2 | Recorded Evaluation Results: Baseline Comparison, including the historical/re-scored discrepancy | D5.1 baseline raw-file scoring |
| Table 3 | Runtime/tool optimization validation, labeled offline | G2; D5.2; runtime-review records |
| D7 | Failure Analysis and Known Limitations | Failed checks, raw transcripts and audit logs |

New model experiments should be reported separately with their checkout hash and configuration. Offline validation establishes calculation and protocol behavior, not new live-model accuracy or latency.

### D7. Observed failure, limitations, and expected variation

**Concrete observed failure.** In the merged DeepSeek run, `invalid-02` asked `Show the metrics.` without identifying a company. The expected behavior was a clarification question; the model instead selected Tencent and returned its metrics. This is a task-resolution failure, not a demonstrated arithmetic error. The likely cause was an unsupported default-company assumption. The current prompt requires clarification when no company is established, and traces preserve the selected arguments. That mitigation still needs a fresh live regression; a prompt rule alone does not guarantee the behavior is fixed.

Both archived merged runs also failed the short-history label check in `ind-07`. The scorer expected a particular SHORT label; inspect the full response before deciding whether this was omitted information or a wording/scoring mismatch. Qwen's `rank-02` also failed the ranking check. The corresponding `failures.md` and JSONL files distinguish observed behavior from possible scorer mismatches.

Known limits and variation:

1. This is a fixed, limited stock universe. No live refresh, verified sub-sector screening, or future-price forecasting is implemented. Reporting periods, currencies and financial definitions vary across companies.
2. The code validates tool arguments, answer structure and evidence IDs. It does not verify every prose number or qualitative statement. Independent data/semantic review remains necessary.
3. The model suite's references derive from the tools. Independent offline references validate selected calculations, not every upstream source disclosure or all natural-language claims.
4. Model outputs and provider aliases can vary even at temperature 0. Single recorded runs are not repeated-run statistical estimates. Exactly matching historical token counts or latency is not expected.
5. TACC scheduling, startup, hardware, serving settings and SDK traffic affect latency. The new UI exposes phase statistics; it does not prove that transport changes already improved real-platform time.
6. Context limits constrain raw-input baselines. The historical raw-Qwen run is incomplete. Information available to raw/no-context baselines differs and is documented above.
7. The current runtime revision has no new full live benchmark or browser visual acceptance result. Existing historical browser/model checks should not be presented as acceptance of every latest change.

### D8. Troubleshooting and logs

| Symptom | Action |
|---|---|
| TACC state R but bridge fails | Check status; wait for all web readiness markers, especially Chat ready |
| Only MODEL_READY appears | Smoke checks or worker startup may still be running or may have failed; inspect the latest job log |
| Port 8765 is occupied | Stop your old local server, or use bridge `--port 8766` |
| New local code has no effect remotely | Re-submit for worker/Agent changes; only local bridge/UI changes can use an existing job with `--local-ui` |
| A namespace is busy | Stop your previous worker or choose a new namespace; do not run two workers on it |
| DeepSeek 401 / 402 / 429 | Check key / API balance / rate limiting; inspect the actual error |
| Slow answer | Compare model requests, SDK upload/download, and session timing; their scopes can overlap |
| N/A metric or short history | Inspect the evidence's reason and reporting/window flags |
| Runner skips cases | Use a new output directory for a new inference experiment |

Web conversation logs/snapshots are under `stock-chat/NAMESPACE/` in TACC USERDIR; evaluation audits are under the run's `audit/` directory. `scripts/tacc.py download` downloads the job's `stock-research/JOB_ID/` results, not the separate namespace conversation directory. Use the SDK to download that directory separately when investigating interactive turns.

Additional documentation: [evaluation protocol](evaluation/README.md), [failure analysis](evaluation/FAILURE_ANALYSIS.md), [dataset notes](agent/data/README.md), [runtime review](docs/RUNTIME_REVIEW.md), [initial validation record](docs/VALIDATION.md), [technical architecture](docs/项目技术架构报告.md), and [deployment guide](docs/服务器部署指南.md). Validation records identify the revision and scope of each check.

### D9. Group contributions

**CHEN Zhaoyu Jensen (21341500).** Contributed to the evaluation pipeline: the 43-case suite, baseline comparisons, recorded Qwen/DeepSeek experiments, result analysis and failure analysis. Also worked on malformed-response handling and evaluation-related reliability improvements.

**DUAN Zihang Raymond (20910081).** Contributed to project scoping, financial data preparation, core metric calculations, screening/ranking tools and the initial Agent/backend. Integrated the course model service and developed the initial web chat implementation.

**Gan Hounan Edward (21347097).** Contributed to Agent execution and tool integration, including model-tool round-trip reduction, tool arguments and ranking follow-ups. Worked on SDK polling, phase timing, debugging and regression checks to support execution profiling and reliability.

**Zhu Yuhan Christo (21315173).** Contributed the evidence-based Agent workflow, browser interface, multiple conversations and restart snapshots. Implemented the co-located TACC deployment and prepared architecture/deployment documentation, with integration work across frontend and backend components.
