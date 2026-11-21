# Failure analysis and limitations (task 15)

Based on the evaluation runs of 21 November 2026: 43 cases, five systems. Transcripts are in
`results/`, every failed check in `results/failures.md`. Case ids below refer to `cases.json`.

## Observed failures of the tool-augmented agent

### 1. Top-10 ranking never produced an answer (`rank-05`)

**What happened.** "Rank the top 10 stocks using the default weights." The model called
`rank_stocks` correctly on its first step, then failed to deliver an answer in two separate runs:

| Run | Step limit | Model calls | Rejected responses | Output tokens | Ended with |
|---|---|---|---|---|---|
| Earlier agent | 8 | 8 | 7 | 12,616 | Step limit reached |
| After raising the limit | 12 | 11 | 9 | 16,216 | HTTP 400 from the model service |

**Cause.** Two things compounded.

- The tool result for ten stocks was about 30 KB, most of it one long source URL repeated
  for every metric of every stock.
- The system prompt asks for every tool value to be listed again at the end of the answer.
  For ten stocks the answer exceeded the 1,800 output-token limit, so the JSON was cut off
  and rejected. Each retry produced the same long answer, was cut off again, and stayed in
  the conversation until the 32K context overflowed.

Raising the step limit from 8 to 12 did not help; it only moved the failure from "step limit"
to "context overflow". The first diagnosis (not enough steps) was wrong.

**Mitigation (implemented).**

- Source URLs are removed from the ranking result shown to the model and kept in the audit
  log. The ten-stock result shrinks from about 30 KB to about 17 KB.
- The output limit is raised from 1,800 to 3,000 tokens.
- A response cut off at the output limit is now dropped from the conversation and the model
  is asked for a shorter answer, instead of being told its JSON was malformed.

### 2. A follow-up was answered without calling the tool (`follow-01`)

**What happened.** Turn 1 asked for Tencent's four metrics (252-day volatility: 33.84%).
Turn 2: "Now use 60 trading days for volatility." In one of two runs the model made no tool
call and answered "33.84% (annualized, based on 60 daily returns from 2026-08-21 to
2026-11-17)". The correct 60-day value is 32.55%. The model reused the old number and
attached a plausible new window to it.

**Cause.** Model behaviour. Nothing in the application forces a tool call when a parameter
changes; it relies on the instruction "Always call the appropriate tool before reporting
metrics". The same case passed in the other run, so the behaviour is not deterministic even
at temperature 0 across service restarts.

**Mitigation (not implemented).** Check each final answer against the tool results of that
turn and reject an answer that reports figures when no tool was called in the turn. The
scorer already has this evidence check (`explanation grounding`); moving it into the agent
would turn a silent wrong answer into a retry.

### 3. An invalid parameter was silently replaced (`invalid-04`)

**What happened.** "Show the historical volatility of 0700.HK using a window of 1 trading
day." The tool requires at least 2 returns. The model used 2 and reported 53.17% from three
prices, in both runs.

**Cause.** The validation error tells the model the allowed range, and the model chose to
satisfy the range rather than report that the request cannot be met. The number is correctly
calculated but answers a different question, and a two-return volatility is not meaningful.

**Mitigation (not implemented).** Instruct the model to refuse out-of-range parameters and
state the allowed range, and raise the minimum window to a statistically sensible value.

### 4. Multi-stock questions exhaust the step budget (observed in manual testing)

"How have Guangdong companies' stocks performed recently?" used all 8 steps: one lookup,
four per-stock trend calls and three rejected responses. The dataset has no region or sector
field, so the model chose the companies from its own knowledge and included Xiaomi, which is
based in Beijing. A second attempt with the same question declined instead and listed the
30 supported stocks.

**Mitigation.** Partly implemented: line breaks inside JSON strings are accepted, which
removes the rejected responses, and the limit is 12 steps. Not implemented: a tool that
analyses several tickers in one call, and region or sector metadata.

## Scorer errors found by reading the failures

Automatic scoring reported five failed cases for the agent. Reading the transcripts showed
that not all were real.

| Case | Verdict | Explanation |
|---|---|---|
| `trend-09` | False negative, fixed | The answer said "I can’t predict" with a typographic apostrophe; the keyword list had a plain one. The scorer now normalizes apostrophes. |
| `invalid-03` | False negative, open | The answer said "I can’t provide the P/E ratio … not one of the metrics available". The keyword list has "cannot provide" and "not available" but not these wordings. |
| `ind-07` | False negative, open | The answer said "No, the volatility is not based on a full 252-day history … short_history". The check looks for the uppercase label `SHORT`, which the prompt never asked the model to use. |

So the measured 88.4% (38/43) understates the agent: two of the five reported failures are
correct answers. Keyword-based behaviour checks are the weakest part of the scoring and need
manual review before any number is quoted.

## Limitations of the evaluation

- **Different models prevent isolating the effect of tools.** The proposal's baseline is
  another provider's model (DeepSeek) without tools, so a difference between it and the agent
  mixes the effect of tools with the effect of the model. To address this, the same Qwen
  model was also run without tools: 11.6% of cases passed, against 88.4% with tools. That
  comparison is like-for-like; the DeepSeek comparison is system against system.
- **Giving the baseline raw data is not the same as giving it tools.** With the raw financial
  inputs in the prompt, DeepSeek reached 34.5% numerical accuracy and Qwen 3.6%. Ranking
  cases could not include price histories, because 30 histories do not fit in a 32K context,
  so the raw baselines cannot compute volatility-based rankings at all.
- **The "Qwen, no tools + raw data" column is incomplete.** Four cases were rejected by the
  service with HTTP 400 because the prompt exceeded the context; they count as failures.
- **One run per system.** `follow-01` passing in one run and failing in the next shows
  run-to-run variation. The reported percentages have no confidence interval.
- **Reference answers come from the tools under test.** They are correct only if the tools
  are; the tools are checked by independent numeric fixtures in `agent/test_*.py`, not by a
  second data source.
- **Response times are not comparable across providers.** Qwen ran on shared course GPUs,
  DeepSeek on a commercial API. The agent's 12.9 s per turn against about 1.3 s without
  tools is comparable only within Qwen.

## Limitations of the system

- **Fixed snapshot.** Data was collected on 18 November 2026 and is not refreshed. Vendor
  figures were not reconciled against issuer filings except for five companies.
- **Narrow data.** Four financial inputs per company. No valuation ratios, cash flow, sector
  or region. Six of the 30 stocks lack an input for ranking and are always excluded.
- **No prediction.** Trend tools describe history. There is no forecast rule and no backtest.
- **Grounding is prompted, not enforced.** The answer format and the "tools called" section
  depend on the model following instructions; failure 2 shows it does not always do so.
- **Charts are not visible to the model.** It can only describe the summary numbers returned
  with a chart.
