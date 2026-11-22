# Failed checks

Use these to pick the failure case(s) for the report. Full transcripts are in the results/*.jsonl files and results/audit/.

## agent-deepseek: 2 failed check(s)

- **ind-07** turn 1, label `0100.HK volatility history status` (expected `SHORT`)
  - Prompt: Show all four metrics for 0100.HK. Is the volatility based on a full 252-day history?
  - Got: MiniMax (0100.HK) — all four core metrics from the 252-day request [E1]: 1. Revenue growth: unavailable — the prior-year revenue input is missing, so no growth rate could be computed (revenue for the 3M period ended 2025-12-31 was USD 25.601M) [E1]. 2. Net profit margin: about -5,310.75% (net income USD -1,359.604M ÷ revenue USD 25.601M × 100), 3M period ended 2025-12-31 [E1]. This is a derived ca
- **invalid-02** turn 1, behavior `asks which ticker` (expected ``)
  - Prompt: Show the metrics.
  - Got: Tencent (0700.HK) core metrics as of the snapshot cutoff 2026-11-18 [E1]: - Revenue growth: 10.99% — derived as (revenue 204.785bn CNY / prior-year revenue 184.504bn CNY − 1) × 100, for the 3-month period ended 2026-06-30 versus 2025-06-30 [E1]. - Net profit margin: 27.36% — derived as net income 56.022bn CNY / revenue 204.785bn CNY × 100, same 3-month period [E1]. - Debt-to-equity: 0.42x — derive
