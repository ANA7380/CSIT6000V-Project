# 运行链路复查与优化

日期：2026-11-23。输入：`CSIT6000V-Project-main(2) (2).zip`。

本轮检查了 Agent 工具协议、结果投影、Qwen/DeepSeek 传输、SDK bridge、服务器 worker、
会话快照、本地网页服务、前端脚本、打包/部署入口及评测代码。运行了原有测试和新增
故障恢复/兼容性测试，并对照输入版本比较计算结果。以下区分源码检查、离线验证与
尚未完成的真实平台验收；不能把离线计数当成真实延迟收益。

## 1. 问题与处理

| 发现 | 本轮处理 | 保留的行为 |
|---|---|---|
| 旧 bridge 在结果未完成时先下载不存在的 `.reply`，再下载 `.status`，通常每次查询启动两个 SDK 子进程 | 优先读取 `.status`；新版 worker 在最终状态中封装完整响应，一次下载即可取回结果 | 原 `.reply` 文件继续生成，供旧 bridge 和恢复路径使用 |
| 重复查询已经完成的结果会再次下载 | 本地缓存最近 16 个完成结果，计时固定为首次完成时刻 | 缓存是当前 bridge 进程内的，不删除服务器数据 |
| 缺少分阶段计时，无法区分模型与传输耗时 | 增加模型请求/工具/上传/下载/会话准备与保存计时和 token/错误计数 | 不把 SDK 时间、Agent 时间等重叠阶段相加 |
| 失败轮次回滚了消息和证据，但未恢复下一个证据编号 | 一并恢复编号；重试从正确编号继续 | 失败审计日志保留，以 turn_id 区分失败和重试 |
| 会话恢复失败前已将新对象写入 sessions 缓存 | 恢复成功后才缓存；修复快照后可再次尝试 | 原有效会话快照格式不变 |
| DeepSeek 客户端遇到输出截断就直接抛异常，绕过 Agent 的截断修复 | 将 finish_reason 原样交给 ChatAgent，统一走已有的有界修复/降级流程 | 输出 token 上限、HTTP 超时、API 地址和认证方式不变 |
| 模型结果投影先深复制完整图表、观察数据和滚动序列，再删除大部分 | 先构造精简投影，最后深复制需要的数据 | 对照验证得到相同模型投影；原始证据独立保留 |
| 前端每次重画图表都会新增 ResizeObserver，旧的未显式释放 | 重绘前断开并清空旧观察器 | 图表数据、价格曲线、交互方式不变；新浏览器验收脚本包含此项检查 |
| 页面仍称会自动校验模型正文数字 | 改为如实说明引用校验范围 | 没有增加新的拒绝规则 |
| 窄问题回答经常枚举工具的所有字段 | 提示词要求围绕用户指定的指标解释 | 不减少工具返回的真实数据，不降低输出 token 上限；实际生成长度待模型复测 |

SDK 请求仍采用原有的两阶段上传：完整 `.request` 上传成功后才上传 `.ask` 标记。
没有为了减少一次 SDK 调用而放松提交顺序。也没有修改数据集、财务公式、排名规则、
模型权重、GPU 分配或公共课程环境。

## 2. 查询兼容与恢复

新 worker 先写入 `.reply`，再原子更新 `.status`：

```json
{"event":"reply_ready","request_id":"...","response":{"answer":"...","evidence":[]}}
```

旧 bridge 继续读取 `.reply`。新 bridge 连接旧 worker 时，在 `turn_complete` 或
`turn_error` 后读取 `.reply`；没有状态文件时也尝试旧结果文件。即使状态一直停留在
处理中，每第五次查询仍探测 `.reply`，避免最终状态写入失败导致永久等待。
最终状态写失败时，worker 保留已写入的 `.reply`。

因此并非每一次查询都严格只有一个 SDK 调用：首次状态尚不存在、旧 worker 完成、
定期恢复探测时可能需要两个。减少的是通常处于执行中的重复下载。

本地计时最多保留 256 个请求，完成响应缓存最多 16 个；重新启动 bridge 会清空这些
本地记录，但服务器结果和会话仍在。恢复历史未完成请求时可能没有本地起始计时，
此时 End to end 为 N/A 是正常的，应使用新问题采集完整数据。

## 3. 如何解释计时

用户此前提供的一次运行显示 Agent 44.03 秒、End to end 174.11 秒，两者差约
130.07 秒。这说明大量耗时在 Agent 计时之外，但不能仅凭差值断定具体是哪次上传、
排队或下载造成，也不能直接把 44.03 秒称为纯模型推理时间。

新版成功响应中：

| 字段 | 范围 |
|---|---|
| `stats.model_request_ms` | 等待模型 HTTP 请求返回的累计时间，包含服务端等待、处理和传输，并非纯 GPU 推理时间 |
| `stats.tool_ms` | 工具请求处理、参数解析、投影及相关日志等累计时间，包含缓存命中的处理 |
| `stats.prompt_tokens` / `completion_tokens` | 模型 usage 存在且为有效整数时累计，缺失时为 0 |
| `stats.format_errors` / `validation_errors` | 本轮格式/截断错误和答案校验失败次数 |
| `timings.bridge.upload_ms` | 本地两次上传 SDK 调用的累计时间 |
| `timings.bridge.download_ms` | 该请求所有状态/结果下载 SDK 调用的累计时间，包括缺失文件查询 |
| `timings.bridge.request_upload_ms` / `commit_upload_ms` | 分别统计请求体与提交标记上传耗时，是 upload_ms 的组成部分 |
| `timings.bridge.status_download_ms` / `reply_download_ms` | 分别统计状态文件与兼容结果文件下载耗时，是 download_ms 的组成部分 |
| `timings.bridge.sdk_calls` / `polls` | SDK 调用次数与本地结果查询次数 |
| `timings.bridge.outside_agent_ms` | End to end 与原有 Agent duration 的差，不能全部解释为通信时间 |
| `timings.worker.session_prepare_ms` | 读取请求、创建/恢复会话等准备时间；不包含此前等待队列的时间 |
| `timings.worker.agent_call_ms` | 完整 `agent.ask()` 调用时间，包含原有 duration 计时结束之后的渲染和记录 |
| `timings.worker.session_save_ms` | 保存成功会话快照的时间 |
| `timings.worker.before_reply_write_ms` | worker 开始处理到准备写结果之前的时间；不包含最终结果和状态文件写入 |

轮询下载可能与模型请求同时发生，阶段计时不能相加。仍未单独测得的是完整的
SDK 服务端内部时间、worker 排队时间和最终状态写入时间；若这些成为瓶颈，应继续
补充时间点，而不是把差值强行归因于模型。

页面将耗时以秒显示，并提供可展开的“Timing details / 耗时详情”。旧服务器缺少的
字段会省略或显示 N/A。对话导出 JSON 会保留已有的响应统计，便于后续比较。

## 4. 已完成的验证

| 检查 | 本轮结果 |
|---|---|
| 输入版本原有 Agent 测试 | 58 项通过 |
| 新版 Agent 测试 | 77 项通过，含原有测试以及桥接、状态恢复、截断恢复新增测试 |
| Evaluation 测试 | 10 项通过 |
| 工具结果差分 | 156 份确定性结果与输入版本一致，排除计算时间戳并固定 hash seed |
| 模型数据投影差分 | 上述结果的 156 份模型投影一致 |
| 独立离线评测 | 42 轮，0 错误；数值 48/48、排名 18/18 |
| CSV 快照检查 | 通过 |
| Python / Shell / JS 语法 | 44 个 Python 文件、9 个 Shell 文件、网页内联 JS、两个 CJS 脚本通过 |
| 打包检查 | web/diagnostic 包的文件哈希和必要模块检查通过 |
| 本轮真实 Qwen / DeepSeek 评测 | 未运行，没有可用平台连接/凭据 |
| 本轮浏览器视觉与交互验收 | 未完成：本地 Chromium 启动受环境限制；云浏览器无法访问执行环境 localhost。已有历史浏览器通过记录不能替代本轮验收 |

原始日志与结果见 [`validation/runtime-review/`](validation/runtime-review/)。
浏览器验收脚本已扩展以检查计时详情与图表观察器释放，但本轮没有宣称它已通过。

### HTTP 通信调用次数对照

使用真实 HTTP handler，SDK 操作用本地文件复制替代，预设三次/八次处理中查询，
最后发布相同回答和证据。下面是从提交到首次取回结果的调用数，包含两次上传：

| 场景 | 输入版本 | 完整新版 |
|---|---:|---:|
| 三次处理中查询 | 9 次 | 6 次 |
| 八次处理中查询 | 19 次 | 12 次 |
| 再次查询已完成结果 | 额外 1 次 | 额外 0 次 |

对照没有人为 sleep 模拟延迟，不声称实际 TACC 等待时间降低了同样比例。若只升级
本地 bridge、仍使用旧 worker，最终取回结果的路径还需要额外读取旧 `.reply`。
SDK 的两次上传依然存在；若实际慢在上传，不能仅靠减少轮询消除全部额外耗时。

模型投影本地微基准中，固定一份价格分析结果的中位复制时间约从 0.561 ms 降到
0.046 ms。这是微秒/毫秒级 CPU 改进，不能解释或解决数十秒模型等待。

## 5. 使用方法

### A. 先升级本地 bridge，不重启 Qwen

将本包解压到一个新目录，在新目录操作，保留原版本方便回滚。确认旧作业仍在运行：

```bash
tcloud ps
```

在原本地 bridge 终端按 Ctrl+C；不会取消服务器 GPU 作业。然后在新版根目录运行：

```bash
python3 scripts/tacc.py bridge YOUR_RUNNING_JOB_ID --local-ui
```

`--local-ui` 使用新版目录的 `agent/chat.html`，因此可以看到本地通信计时，不必等待
远端页面更新。旧 worker 没有的新统计字段会缺失，这是预期兼容行为。建议发送一个
新的测试问题；已有 pending 请求继续查询，不要重复提交同一个问题。

### B. 启用完整新版

先保存旧结果并停止旧作业，再从新版目录提交：

```bash
python3 scripts/tacc.py download OLD_JOB_ID
python3 scripts/tacc.py stop OLD_JOB_ID
python3 scripts/tacc.py submit --mode web --namespace hk-research-perf --minutes 60
python3 scripts/tacc.py status NEW_JOB_ID
```

等到 MODEL_READY、LIVE_SMOKE_PASSED 和 Chat ready，再运行：

```bash
python3 scripts/tacc.py bridge NEW_JOB_ID --local-ui
```

示例使用新 namespace 进行独立验收。希望恢复原对话时，可在旧 worker 已停止之后
使用原 namespace，并保留浏览器中的 conversation ID。

### C. 验证与复现

```bash
python3 -m unittest discover -s agent -v
python3 -m unittest discover -s evaluation -v
python3 scripts/export_snapshot.py --check
python3 evaluation/offline/run.py --mode offline --output evaluation/runs/runtime-review-offline
```

将本轮输入 ZIP 另行解压，作为 baseline：

```bash
python3 scripts/benchmark_bridge_optimization.py --baseline /absolute/path/to/input/CSIT6000V-Project-main
python3 scripts/benchmark_tool_optimization.py --baseline /absolute/path/to/input/CSIT6000V-Project-main --output docs/validation/runtime-review/tool-equivalence.json
```

浏览器条件可用时，启动 `python3 agent/demo_web.py --port 18765`，另一个终端使用
已安装的 Playwright 和 Chrome 执行 `scripts/browser_smoke.cjs`，按脚本顶部说明配置
`PLAYWRIGHT_MODULE` 和 `CHROME_PATH`。这是离线页面验收，仍不代表模型质量验收。

### D. 实际平台验收

在旧版和新版使用相同模型/硬件配置、相同问题集及相近上下文规模，记录逐题模型
请求数、API 时间、SDK 上传/下载时间、End to end、fallback 和答案是否合格。至少
覆盖单工具趋势、多工具概览、排名追问、无股票对象、错误参数及恢复旧对话。
先进行暖机，再重复测量；不要把模型初次启动、某次调度等待或单次随机输出当作
稳定延迟。原目录已有 41/43 等旧模型成绩不属于这一版。

## 6. 回滚与保留项

回滚本地 bridge：Ctrl+C 关闭新版，从保留的输入目录重新执行旧 bridge。
回滚服务器：停止自己新作业，从保留的输入目录重新提交。会话 schema 仍为 version 1，
有效旧快照可继续恢复。不要删除服务器会话目录来实现回滚。

本轮没有引入单次上传新协议、后台异步日志、跨轮计算缓存或证据裁剪；这些改动
需要额外证明提交完整性、日志可靠性和引用可用性。大规模会话导致快照膨胀、SDK
连接启动成本、长上下文 prefill 等仍可能是后续瓶颈，需要上述新增计时来确认。
