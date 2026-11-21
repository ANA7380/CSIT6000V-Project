# Evaluation

Tasks 12–14 of the project plan: an evaluation set with verified references, a no-tools
baseline, and scripts that report the six metrics promised in the proposal. Python 3.9+,
standard library only. Nothing here modifies the `agent/` code.

## What is in this folder

| File | Purpose |
|---|---|
| `cases.py`, `cases.json` | 43 cases (85 checks). `cases.json` holds the frozen reference answers. |
| `run_eval.py` | Runs the cases against one system and saves raw transcripts. |
| `score.py` | Scores transcripts; writes `results/summary.md`, `per_check.csv`, `failures.md`. |
| `test_eval.py` | Offline tests (no model, no network). |
| `job.sh`, `tuxiv.conf`, `systems.txt`, `bundle.sh`, `server-url.txt` | TACC batch run against the course Qwen service. |

## The evaluation set

| Category | Cases | What it covers |
|---|---|---|
| `individual` | 11 | Four core metrics, name-to-ticker resolution, custom windows, losses, missing data, short history, ROE, correlation, one Chinese prompt |
| `ranking` | 9 | Default ranking, mandatory filters, custom weights, single-metric ranking, Top-K size, a filter nothing passes, a natural-language preference |
| `trend` | 10 | RSI, MACD, moving averages, returns, drawdown, volume ratio, above/below and crossover signals, refusing to predict prices |
| `followup` | 6 | Two-turn conversations that change a window, a filter, Top-K or the company; scored on the last turn |
| `invalid` | 7 | Unknown tickers, no ticker, unavailable metrics (P/E, sector), invalid window and weight |

Reference answers are not typed by hand. `cases.py` names a tool call and a field for every
check, and `python cases.py` resolves them by calling the deterministic tools in `agent/`
directly (no LLM). A test fails if `cases.json` no longer matches the tools or the data.
The references are therefore only as correct as those tools; they are covered by the
independent numeric fixtures in `agent/test_*.py`.

## Systems compared

| Label | Command | Role |
|---|---|---|
| `agent-qwen` | `--system agent --provider qwen` | Proposed system: tool-augmented agent on the TACC model |
| `notools-deepseek` | `--system notools --provider deepseek` | Proposal baseline: another provider's LLM, no tools |
| `notools-qwen` | `--system notools --provider qwen` | Ablation: same TACC model without tools, isolates the effect of tools |
| `notools-*-raw` | add `--context raw` | Baseline also receives the raw dataset inputs and must do the arithmetic itself |
| `agent-deepseek` | `--system agent --provider deepseek` | Optional: same agent on the other model, isolates the effect of the model |

`--context raw` appends the 30 companies' raw financial inputs, plus the full price history
of at most two tickers a case needs. It never includes computed metrics. Ranking cases get
no price data because 30 price histories do not fit the service's 32K context, so the raw
baseline cannot compute volatility-based rankings.

All runs use temperature 0. The no-tools baselines use max 1,800 output tokens; the agent uses its own limit (`MAX_TOKENS` in `agent/chat_agent.py`, 1,800 until the ranking fix described in `FAILURE_ANALYSIS.md`, 3,000 after). Model name, provider and context
mode are stored in every result line.

## Run it

Offline check first:

```bash
cd evaluation
python -m unittest
```

On TACC (start the Qwen service first, as in the root README):

```bash
cd evaluation
bash bundle.sh
printf '%s\n' 'http://ACTUAL_SERVICE_HOST:8000/v1' > server-url.txt
tcloud submit
tcloud cat "slurm_log/eval-JOB_ID.log"
```

The job runs the three lines of `systems.txt` in order and writes to
`$TACC_USERDIR/stock-eval-results/`. If the service stops or the job hits its time limit,
resubmit: finished cases are skipped and cases the service never answered are retried.
Download and score:

```bash
mkdir -p results
for f in agent-qwen notools-qwen notools-qwen-raw; do
    tcloud download "stock-eval-results/$f.jsonl" "./results/$f.jsonl"
done
python score.py
```

Locally with DeepSeek (API usage is billed to your account):

```bash
export DEEPSEEK_API_KEY=...
python run_eval.py --system notools --provider deepseek
python run_eval.py --system notools --provider deepseek --context raw
python score.py
```

## How each metric is scored

| Proposal metric | How it is measured |
|---|---|
| Numerical accuracy | Share of reference values that appear in the answer. A figure counts if it is a correct rounding of the reference and within 1% (or 0.005). |
| Recommendation quality | Top-K precision (reference tickers among the first K tickers mentioned), constraint compliance (share of those K that pass the mandatory filters), and exact order. |
| Trend analysis grounding | Pass rate of all checks in the `trend` category: indicator values, ABOVE/BELOW and crossover labels, and declining to predict. |
| Explanation grounding | Share of decimal or percentage figures in the answers that match a number in the tool results the model saw or in the reference tool results. |
| Follow-up success | Share of `followup` cases whose last turn passes all its checks. |
| Response time | Wall-clock seconds per turn (mean, median, p90), plus model calls and tokens per turn. |

Invalid-input handling is reported as an extra row.

## Known limitations of the scoring

- It is automatic and heuristic. Read `failures.md` and spot-check passes before quoting numbers.
- Number matching ignores sign and does not check that a figure is attached to the right
  metric; a correct value anywhere in the answer counts.
- Explanation grounding only checks figures, not qualitative claims, and a fabricated
  figure can match evidence by chance (about 2% in the offline test).
- Behaviour checks (invalid inputs, "unavailable", no prediction) are keyword matches in
  English and Chinese and can misjudge unusual wording.
- Label questions ask the model to start with a fixed word (ABOVE/BELOW, UP/DOWN/NONE) so
  they can be scored reliably.
- The agent and the proposal baseline use different models, so that comparison measures
  whole systems. `notools-qwen` is the like-for-like comparison for the effect of tools.
- Response times of different providers are not comparable hardware-for-hardware.
