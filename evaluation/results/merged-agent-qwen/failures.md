# Failed checks

Use these to pick the failure case(s) for the report. Full transcripts are in the results/*.jsonl files and results/audit/.

## agent-qwen: 2 failed check(s)

- **ind-07** turn 1, label `0100.HK volatility history status` (expected `SHORT`)
  - Prompt: Show all four metrics for 0100.HK. Is the volatility based on a full 252-day history?
  - Got: For 0100.HK (MiniMax), the four core metrics are: revenue growth is unavailable because prior-year revenue is missing; net profit margin is -5310.75% for the 3M period ending 2025-12-31, calculated as net income of -1,359,604,000 USD divided by revenue of 25,601,000 USD; debt-to-equity is 0.1020x as of 2026-06-30, calculated as total debt of 137,423,000 USD divided by stockholders' equity of 1,346
- **rank-02** turn 1, ranking `top 5` (expected `['0700.HK', '9999.HK', '2382.HK', '1698.HK']`)
  - Prompt: Return the top 5 stocks with net profit margin at least 10% and debt-to-equity at most 0.5.
  - Got: Four companies met the requested filters: net profit margin at least 10% and debt-to-equity at most 0.5x. The ranking used equal weights across revenue growth, net profit margin, debt-to-equity, and historical volatility. Tencent ranked first with a 27.36% net profit margin, 0.42x debt-to-equity, 10.99% revenue growth, and 33.84% historical volatility. NetEase ranked second with a 23.19% net profi
