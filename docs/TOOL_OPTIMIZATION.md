# Tool 优化与测试报告

日期：2026-11-23。输入：`CSIT6000V-Project-main(2).zip`。

## 已修改的行为

1. **批量工具请求。** 保留原来的单工具 JSON，新增 `{"tools":[...]}`。
   模型已知所有参数时，可一次请求最多六个独立只读工具，例如一只股票的
   `ticker_metrics` + `price_analysis`，或三只股票的这两组分析。
   批次先完成整个协议/参数类型校验，再按顺序执行。代码没有增加并发线程；
   收益来自减少模型往返。公司名需要先查代码时，仍等待 `list_tickers`。
   `rank_stocks` 会改变会话偏好，因此单独调用。批量中的运行时数据错误会
   逐项返回，其他成功结果保留各自的证据 ID、表格和图表。
2. **同轮复用。** 同一个 `ask()` 中，相同工具、标准化代码和参数只计算一次。
   例如 `700` 与 `0700.HK`、省略窗口与 `window=252` 可复用。
   失败结果不缓存；新用户轮次重新计算。复用仍写入工具日志，记录 `reused=true`，
   但不会重复创建证据卡片或排名历史。窗口变化会产生独立计算。
3. **精简排名结果。** 数值集中保留在 `results[].values`；模型看到的
   `metric_details` 不再重复 `value` 和每个指标的 `formula`。日期、期间类型、
   币种、单位、状态、缺失原因、权重、百分位分数及贡献仍保留。
   全部原始计算结果继续进入证据和审计记录，前端仍渲染完整内容。
4. **缩短无效重试。** 连续两次 JSON/协议错误或截断后停止；已有本轮工具
   结果则返回标记了 fallback 的证据结果，否则报错并回滚会话。有效动作会重置
   连续错误计数。总模型调用上限仍为 12，答案引用修复上限仍为两次。
5. **统计。** 成功轮次的 `last_response.stats` 和 `turn_complete` 审计记录增加：
   `model_calls`、`tool_requests`、`tool_calculations`（成功的新计算）、
   `cache_hits`、`tool_errors`、`model_input_chars`。字符数不等于 token 数。
6. **排名追问。** 调整 prompt：用户追问“哪只最好”时，应解释现有明确条件下
   的第一名，引用此前排名，并说明结论受筛选标准限制。这个修改只通过 prompt
   检查，尚未用真实模型确认语义行为。

## 验证结果

原版 Agent 测试为 46 项；新版增加 12 项批量/缓存/错误处理回归。

| 验证 | 结果 | 含义 |
|---|---|---|
| Agent 自动测试 | 58/58 | 包括原有本地网页、worker、会话和部署脚本测试 |
| Evaluation 自动测试 | 10/10 | 评测管线、参考数据及打分函数回归 |
| 原版/新版工具输出 | 156/156 一致 | 30 只股票的两种窗口核心指标与价格分析、年度趋势，以及排名、相关性；比较时排除计算时间戳并固定 Python hash seed |
| 42 个离线轮次 | 0 错误 | 原有独立参考检查；不调用模型 |
| 离线数值检查 | 48/48 | 与离线参考值一致 |
| 离线排名检查 | 18/18 | 与离线参考排名一致 |
| 数据快照检查 | 通过 | CSV 内容与快照清单一致 |
| 新版真实 Qwen/DeepSeek 43 案例 | 尚未运行 | 当前环境无配置好的模型地址或 API Key |

原始对照：[tool-optimization.json](validation/tool-optimization.json)。测试日志和离线
输出位于 [`validation/tool-optimization/`](validation/tool-optimization/)。

### 预设动作对照

脚本为原版预设逐个工具动作，为新版预设批量动作；模型传输被替换为脚本。
这些数字证明协议能够省去中间请求，不是模型自主选择批量工具的成功率。
场景均已提供股票代码，每只股票执行核心指标和价格分析两个工具。

| 场景 | 原版模型请求 | 新版模型请求 | 原版累计输入字符 | 新版累计输入字符 |
|---|---:|---:|---:|---:|
| 单股概览 | 3 | 2 | 27,817 | 20,421 |
| 两股概览 | 5 | 2 | 63,264 | 27,224 |
| 三股概览 | 7 | 2 | 112,348 | 34,032 |

三组场景的完整证据摘要与图表数量一致。相同股票代码的重复请求，计算数从两次
减为一次、证据卡片从两张减为一张。这个复用没有减少用于提交重复动作的模型调用，
因此不能把缓存命中直接算作端到端延迟下降。

| 排名请求 top_k | 原版模型结果字符 | 新版模型结果字符 | 减少 |
|---|---:|---:|---:|
| 5 | 9,257 | 7,510 | 18.9% |
| 10 | 17,014 | 13,528 | 20.5% |
| 30 | 38,742 | 30,376 | 21.6% |

实际返回数量受可用数据和筛选条件限制。上表不包含 system prompt；新版 prompt
增加了批量协议说明，因此简单单工具场景的总 token 收益需要真实运行判断。
本次不报告真实模型延迟、token 降幅或新版问答准确率；此前目录中的模型成绩属于旧版。

## 复现

在仓库根目录运行：

```bash
python3 -m unittest discover -s agent -v
python3 -m unittest discover -s evaluation -v
python3 scripts/export_snapshot.py --check
python3 evaluation/offline/run.py --mode offline --output evaluation/runs/tool-optimization-offline
```

把本次输入的原始 ZIP 解压到另一个目录，再进行源码对照：

```bash
python3 scripts/benchmark_tool_optimization.py --baseline /absolute/path/to/original/CSIT6000V-Project-main
```

脚本会分别启动隔离的 Python 进程导入两版源码，比较去除 `calculated_at` 后的输出摘要，
并生成对照 JSON。它不会连接模型，无法验证 prompt 的实际执行表现。

真实模型可达后，在对应网络环境运行：

```bash
python3 evaluation/run_eval.py --system agent --provider qwen --base-url "$QWEN_BASE_URL" --out-dir evaluation/runs/tool-optimization-qwen
# 或已配置 DEEPSEEK_API_KEY 时：
python3 evaluation/run_eval.py --system agent --provider deepseek --out-dir evaluation/runs/tool-optimization-deepseek
```

使用新输出目录，避免原有 runner 跳过已完成的旧版案例。基线与新版应使用同一模型、
同一服务配置、相同案例、独立会话和相同 token 上限。人工检查至少：公司名查找后
是否批量调用、比较是否覆盖全部公司、Top-K 追问是否保留约束、错误输入是否适当
澄清，以及“哪只最好”是否按已有条件解释。

## 后续提升优先级

| 优先级 | 方法 | 判断依据与验收 |
|---|---|---|
| 1 | 真实模型 A/B | 先跑同一 43 案例，比较逐例通过率、工具覆盖、fallback、请求数和延迟；不能只比较总平均耗时 |
| 2 | 检查批量协议采用率 | 已知参数的多工具请求中，模型实际用批量的比例；如果采用率低，再考虑增加 `stock_overview` 聚合工具或调整示例 |
| 3 | 明确排名参数结构 | 当前 weights/filters 仅描述为 object；若日志显示频繁键名错误，再增加嵌套参数示例或 JSON Schema，并保留后端校验 |
| 4 | 更有针对性的模型投影 | 若长排名仍昂贵，按任务仅发送所需指标；必须保留筛选所用值、可比期间和缺失标记，防止失去解释依据 |
| 5 | 稳定的公司名解析 | 以维护过的中英文别名表解析唯一匹配，含糊时仍澄清；测量是否值得省去查表轮次 |
| 6 | 数据层索引/缓存 | 仅在工具耗时成为瓶颈时按 symbol 建价格索引、缓存固定快照计算；键应包括数据版本，别让旧结果进入新快照 |

本次选择先减少模型往返；30 只股票的本地计算规模较小，工具线程并行未必带来
明显收益，还会增加状态、证据顺序与日志同步复杂度。新增协议仍需要真实模型验收，
尤其是新增 JSON 包装和更短的错误重试上限可能影响模型恢复率。
