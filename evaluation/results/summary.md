# Evaluation summary

| Metric | agent-qwen | notools-deepseek-raw | notools-deepseek | notools-qwen-raw | notools-qwen |
|---|---|---|---|---|---|
| Model | qwen3.8-27b | deepseek-flash | deepseek-flash | qwen3.8-27b | qwen3.8-27b |
| Cases fully passed | 93.0% (40/43) | 30.2% (13/43) | 7.0% (3/43) | 18.6% (8/43) | 11.6% (5/43) |
| Numerical accuracy | 100.0% (55/55) | 34.5% (19/55) | 0.0% (0/55) | 3.6% (2/55) | 0.0% (0/55) |
| Recommendation quality: Top-K precision | 100.0% | 34.7% | 0.0% | 16.8% | 0.0% |
| Recommendation quality: constraint compliance | 100.0% | 39.4% | 0.0% | 34.7% | 0.0% |
| Recommendation quality: exact order | 100.0% (13/13) | 0.0% (0/13) | 0.0% (0/13) | 0.0% (0/13) | 0.0% (0/13) |
| Trend analysis grounding | 100.0% (17/17) | 52.9% (9/17) | 5.9% (1/17) | 17.6% (3/17) | 11.8% (2/17) |
| Explanation grounding (figures supported) | 96.8% (605/625) | 48.2% (147/305) | 33.3% (4/12) | 25.1% (42/167) | n/a |
| Follow-up success | 100.0% (6/6) | 0.0% (0/6) | 0.0% (0/6) | 0.0% (0/6) | 0.0% (0/6) |
| Invalid / incomplete input handling | 71.4% (5/7) | 71.4% (5/7) | 28.6% (2/7) | 57.1% (4/7) | 42.9% (3/7) |
| Response time per turn: mean | 13.2 s | 1.6 s | 1.1 s | 5.4 s | 1.3 s |
| Response time per turn: median | 10.4 s | 1.4 s | 1.0 s | 1.9 s | 1.3 s |
| Response time per turn: p90 | 24.2 s | 2.3 s | 1.5 s | 16.0 s | 1.7 s |
| Model calls per turn | 2.16 | 1.00 | 1.00 | 1.00 | 1.00 |
| Tokens per turn | 8504 | 7689 | 224 | 9623 | 221 |
| Failed turns (of which transport) | 0 (0) of 49 | 0 (0) of 49 | 0 (0) of 49 | 6 (6) of 49 | 0 (0) of 49 |

## Cases fully passed by category

| Category | agent-qwen | notools-deepseek-raw | notools-deepseek | notools-qwen-raw | notools-qwen |
|---|---|---|---|---|---|
| individual | 90.9% (10/11) | 18.2% (2/11) | 0.0% (0/11) | 0.0% (0/11) | 0.0% (0/11) |
| ranking | 100.0% (9/9) | 11.1% (1/9) | 0.0% (0/9) | 11.1% (1/9) | 0.0% (0/9) |
| trend | 100.0% (10/10) | 50.0% (5/10) | 10.0% (1/10) | 30.0% (3/10) | 20.0% (2/10) |
| followup | 100.0% (6/6) | 0.0% (0/6) | 0.0% (0/6) | 0.0% (0/6) | 0.0% (0/6) |
| invalid | 71.4% (5/7) | 71.4% (5/7) | 28.6% (2/7) | 57.1% (4/7) | 42.9% (3/7) |

**Incomplete runs (do not report yet):** notools-qwen-raw ran 43 of 43 cases with 6 transport error(s)

Scoring is automatic and heuristic; see evaluation/README.md for what each metric does and does not measure.
