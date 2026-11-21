# Validation record

Base: `origin/main` at `7a4540a559f9e17fac462844dac15dbd89fe042e`. Validation date: 21 November 2026, Asia/Shanghai. Python 3.10 on Linux; browser smoke checks used headless local Chrome through Playwright. Tests use temporary files and loopback servers, with no real LLM requests.

| Check | Observed result |
|---|---|
| `python3 -m unittest discover -s agent -v` | 32 tests passed; final run about 6.24 seconds |
| Independent offline evaluation | 30 scenarios, 42 turns; 48/48 numerical comparisons and 18/18 ranking order/score comparisons passed |
| Expected invalid-input rejections | Unsupported ticker, negative window and contradictory filters rejected |
| Browser smoke | Overview, price and volatility charts, reload, separate conversations, Top-K follow-up, desktop/mobile layout, escaped HTML and absence of JS errors passed |
| Snapshot consistency | 30 company rows, 13,919 price rows, 816 financial rows; committed application CSV copies equal the frozen inputs |
| Canonical export | Frozen prepared JSON exported to a separate directory; ISO timestamp precision preserved; committed CSV inputs left unchanged |
| Shell and Python syntax | `bash -n` for launch scripts and Python `compileall` passed |
| Missing live configuration | Live evaluation refuses to start without a Qwen URL; it does not generate a success report or fabricate model results |
| Patch whitespace | `git diff --check` passed |

The original sandbox denied loopback socket creation. Tests requiring local HTTP and Chrome ran with that capability enabled. No TACC job was submitted, no API account was billed and no real model quality result is claimed.

Saved machine-readable evidence: [offline summary](validation/offline-summary.json), [full offline results](validation/offline-results.json), [evaluation settings](validation/offline-manifest.json), [data hashes](validation/data-manifest.json), and [browser checks](validation/browser-smoke.json). Offline timing is local computation time, not model response time. Browser answers come from the explicitly labeled scripted fixture.

The browser check exposed and drove fixes for mobile parameter wrapping, the grid minimum width when multiple conversation tabs exist, and chart resizing. Earlier development failures are not counted as final passes.

The regression suite also reproduces the original missing answer-validation guard with a simulated `999999%` model claim. It now verifies rejection/repair, and a bounded fallback that only publishes verified numerical evidence. Free-form qualitative reasoning, spelled-out numeric claims, correct semantic use of a citation, live model task selection, TACC transfer behavior and large-context service limits still require live/manual evaluation.

The offline reference module does not import financial calculation code from the Agent. It independently computes values from the frozen CSV inputs. These checks do not independently certify every external filing or turn the snapshot into a point-in-time backtest dataset.
