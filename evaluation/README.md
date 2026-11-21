# Evaluation

`cases.json` defines 30 scenarios and 42 turns: six individual-stock cases, six ranking cases, six historical-trend cases, six multi-turn preference cases and six invalid/incomplete cases. `calls` are reference operations used **only** for offline checking and selecting common raw data. They are never given to the live model as a plan.

From the repository root:

```bash
python3 evaluation/run.py --mode offline --output evaluation/runs/offline-001
```

This runs deterministic tools, compares 48 values with independent reference calculations and compares 18 rankings. Three invalid-argument cases are expected rejections. Ambiguous risk, unsupported sector and unsupported valuation questions require human review; offline mode does not count them as LLM successes. Output directories must be new or empty.

`reference.py` reads the frozen inputs without importing application calculations. It uses Decimal financial arithmetic, an explicit sample-variance formula, sorted-index percentiles and an independent prefix-peak drawdown definition. It checks consistency with frozen inputs, not the authenticity of every issuer disclosure. Existing unit fixtures separately cover SMA, RSI, MACD, correlation, missing data and edge cases.

## Live comparison

Run this where both the course Qwen endpoint and the external baseline API are reachable. Export credentials locally; never commit them.

```bash
export QWEN_BASE_URL='http://ACTUAL_SERVICE_HOST:8000/v1'
export DEEPSEEK_API_KEY='YOUR_LOCAL_KEY'
python3 evaluation/run.py --mode live --system both --output evaluation/runs/live-001
```

Use `--system agent` or `--system baseline` to run one side; `--case stock-1` selects a smoke test. Provider transports are `agent/qwen_client.py` and `agent/deepseek_client.py`. The baseline uses ordinary chat with **no custom tools**, independently of the DeepSeek tool-agent mode.

The same raw company/price context is saved and supplied to both systems for each scenario. No verified answer or scripted operation is sent to the models. Qwen still has access to the whole frozen dataset through its tools. Some ranking contexts are large; `--max-context-chars` is a conservative character budget, not a tokenizer or a guarantee that a service accepts that context. Set an adequate server context length and document it before interpreting failures. The current evaluation request cap is 1800 output tokens; do not silently change settings between systems.

Artifacts:

- `manifest.json`: mode, models, URL, sampling configuration, case hash and tolerances; no API key.
- `*-context.json`: identical raw data context given to both systems.
- `*-agent-audit.jsonl`: model messages, responses, usage, tool evidence, errors and timings.
- `results.json`: exact prompts, reference values, normalized outputs, raw baseline response and automatic scores.
- `summary.json`: numerical checks, ranking checks, failures and median response time.
- `manual_review.csv`: explanation grounding, trend grounding, contextual success, invalid-input behavior and reviewer notes. Blank cells mean **not reviewed**, not a pass.

Score numerical values using the recorded absolute/relative tolerances; missing values and absent fields are distinct. Ranking membership, order and scores are checked against filters, weights and tie rules. Empty expected rankings are checked too. Qualitative grounding and ambiguous-request handling remain manual: mark a pass only when every company-specific claim has an applicable source, historical direction matches calculated indicators, earlier preferences and references are preserved, and unsupported requests are clarified or rejected. Report reviewer disagreements.

Live timings here measure the command-line system, including model/tool calls, not the browser SDK transfer. Browser replies separately expose `end_to_end_ms`, including file transfers/polling, and `duration_ms` for the Agent. Report them separately. Different model providers compare the overall systems and cannot isolate the causal benefit of tool use.

No full real-model comparative evaluation is included in this branch. Server deployment smoke checks, when run, are documented separately in docs/服务器部署实测记录.md. The saved offline summary and explicitly scripted browser demo must not be presented as live Qwen accuracy or API latency.
