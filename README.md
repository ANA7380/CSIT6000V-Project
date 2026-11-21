# 联网股票研究 Agent 独立版本

## 输出校验更新（2026-11-22）

解释正文允许股票代码、数字、日期、列表序号、四舍五入和明确标注的情景计算。不再按数字字符或与证据数字逐项匹配来拒绝整段回答。硬校验仅检查非空回答、引用 ID 存在、本轮调用工具后提供证据引用，以及正文不直接写 URL（来源链接仍由证据卡片展示）。模型仍须按 prompt 引用依据、区分事实与假设；程序不再保证正文数字正确，数值准确率与语义依据需通过参考测评和人工审核确认。工具参数校验、确定性表格与图表计算保持原有行为。部署中的旧进程需要用新代码重新打包启动；恢复旧会话时，首条 system prompt 会替换为本版本 prompt。

新增模拟多轮回归覆盖“先问 Anthropic，再问腾讯并输出股票代码、百分数、列表和情景推导值”，不代表真实 Qwen 对同一对话已复测。

本项目与同级的 `CSIT6000V-Project/` 离线版本完全分开，拥有独立的代码、数据、部署脚本、测试记录和 `.git`，不依赖离线项目目录。业务基于提交 `4bb2784`，联网实现见历史提交 `00550df`。新版本可以研究离线 30 家港股之外的公司和股票，原三份 CSV 逐字节保留。模型仍通过一个有界单 Agent 循环选择工具。

## 已确认的服务器网络条件

2026 年 11 月 21 日在 TACC 课程 Python 中实测：DNS 和公网 HTTPS 可用。最初请求全部出现证书链校验失败；显式使用服务器现有 `/etc/ssl/certs/ca-certificates.crt` 后，官方微软页面、Yahoo 行情、GitHub 均成功。新版 `web_tools.tls_context()`优先使用 `STOCK_CA_BUNDLE`、`SSL_CERT_FILE`，否则使用该系统 CA，始终保留证书与主机名校验。

课程 rootfs 还缺少 IANA 时区数据库。新版 job.sh 把宿主 `/usr/share/zoneinfo` 复制进本次私有 `QWEN_RUN_DIR`，设置 `PYTHONTZPATH` 后再运行课程 Python。不会向公共 Python 安装 tzdata，不修改课程公共文件。

原始探测作业 30346、指定系统 CA 的作业 30347，以及新版 CPU 作业 30351 和最终作业 30356 的结果记录在 `docs/validation/` 和下载的 `var/tacc-results/`。搜索服务的单站限制与服务器网络权限是两回事：本次 DuckDuckGo 返回挑战页，Bing RSS 曾返回不相关内容；新版不把这些页面当作有效结果。当前实际通过的搜索回退提供者是 Google News RSS。

## 快速部署

在本项目根目录运行：

```bash
source /home/zyh/桌面/mpi-assignment/env.sh
cd /home/zyh/桌面/fin_project/CSIT6000V-Project-online
python3 scripts/tacc.py preflight
python3 scripts/tacc.py submit --mode web --namespace online-research --minutes 60
python3 scripts/tacc.py status JOB_ID
# 等待 MODEL_READY、LIVE_SMOKE_PASSED、Chat ready
python3 scripts/tacc.py bridge JOB_ID --port 8766
```

浏览器打开输出的本机地址。默认模型地址自动设为计算节点内 `http://127.0.0.1:42866/v1`，与原版默认端口不同；更换端口用 submit 的 `--port`。新版本默认使用 `online-stock-research/JOB_ID` 结果目录和 `online-stock-chat/NAMESPACE` 会话目录，浏览器 localStorage key 也独立。

```bash
python3 scripts/tacc.py download JOB_ID
python3 scripts/tacc.py stop JOB_ID
```

停止本机桥不会取消 GPU 作业。相同 namespace 不能同时运行两个 worker；重启同 namespace 可以恢复服务器会话，浏览器也要保留原会话 ID。

可先执行 CPU 诊断，不申请 GPU，不请求模型：

```bash
python3 scripts/tacc.py submit --mode diagnostic --minutes 5
```

首次账户缺少 proxy 入口时，可先从本目录执行 `bash agent/setup-sdk-account.sh`，使用本项目自带的账户注册脚本。

本机调试需要可达的模型地址：

```bash
python3 agent/local_web.py --provider qwen --base-url http://实际可达地址:端口/v1 --port 8766
# 或在本机环境变量配置 DEEPSEEK_API_KEY 后
python3 agent/local_web.py --provider deepseek --port 8766
```

TACC 上的 Qwen 回环地址不能直接给笔记本上的 local_web 使用。不要在聊天或提交包中填写密钥。

## 能力与工具路由

原有六个离线工具仍保留，不对其输入 CSV 做刷新或混合覆盖：

- list_tickers：仅列出离线数据可用的 30 家公司，不再被解释为整个 Agent 的查询范围。
- ticker_metrics、financial_trends、price_analysis、stock_correlation：按原算法读取离线数据。
- rank_stocks：仍在离线集合内筛选和排名；没有把它伪装成全市场扫描器。

新增四个联网工具，集中在 `agent/web_tools.py`：

| 工具 | 能力 | 关键边界 |
|---|---|---|
| web_search | 按公司名、股票、上市状态、新闻或业务问题搜索；依次尝试 Brave、Google、Google News RSS、Bing RSS，过滤空结果和明显不相关链接 | 免费页面可能挑战、限流或更改格式；回退到新闻搜索不等于已找到发行人原始披露 |
| read_webpage | 读取任意公开 HTTP(S) 网页可见文本，返回标题、URL、获取时间与摘要；模型可见最多 16000 字符 | 不运行 JavaScript，不提取 PDF，不绕过验证码或付费墙 |
| search_stocks | 查询 Yahoo Finance 的公司/股票代码匹配和相关新闻，支持其他市场 | 匹配可能歧义；没有匹配不能证明未上市，必须核实发行人与交易所 |
| market_history | 对已核实的外部股票代码取两年日复权价格，再运行原历史指标算法并生成图表 | 依赖供应商支持的代码和数据，不保证实时；不从价格臆造财务报表指标 |

market_history 支持 window 2 至 500，默认 60；它控制最多 window+1 个价格点。Yahoo 未提供完整复权价格或存在缺值时明确失败，不静默换成未复权价格或跨缺口计算。时间戳按交易所 IANA 时区转换；去掉仍处于当日正常交易时段的未完成日线。

来源 URL、获取时间、股票匹配和网页摘要由 `evidence.view()`传给前端，页面独立显示来源卡片和网络图表。网页文本不作为 HTML 执行。

## Prompt 与校验的变化

`agent/chat_agent.py` 的 SYSTEM 现明确允许任意公司、股票、交易所和国家，包括私人公司；不得只因不在离线集合中而拒绝研究。每次上下文附加当前 UTC 日期，排名偏好和证据句柄继续持久化。单一首条 system 消息和最多 12 次模型调用的循环保留。课程 Qwen 使用 [`/tokenize` 协议](https://docs.vllm.ai/en/latest/api/vllm/entrypoints/serve/tokenize/protocol/)按相同聊天模板计算实际 token，预留 1800 输出 token 和 128 token 余量；超限时先移除完整旧轮次，必要时压缩工具观察，完整证据和页面结果仍保留。其他提供者继续使用字符预算，不能把字符数等同于 token 数。本版 Qwen 路径要求 vLLM `/tokenize` 可用，缺少该接口时会明确报错，不盲目发送长上下文。

各阶段没有隐藏的额外限制 prompt：

1. System 与 TOOL CATALOG 区分离线工具和联网工具；离线数据限制只描述那几个工具的数据覆盖。
2. TOOL_RESULT 可反馈网络结果与错误，带实际来源和获取时间。
3. SESSION_STATE 仍只提供状态和证据，不作为拒绝外部股票的名单。
4. MODEL_FORMAT_ERROR、ANSWER_VALIDATION_ERROR 要求修正格式或无依据内容，不要求退回 30 家公司。
5. 最终页面明确区分离线快照与网络证据日期。

当前输出校验策略见本文开头的 2026-11-22 更新。此前逐个匹配证据数字的校验已移除，避免日期格式、四舍五入和推导值导致误拦截；不存在的引用等结构性错误仍要求修正。

上市传言、最新报价与市场消息必须先查网络证据，不能直接接受用户前提。业务护城垒等实质判断应读取相关一手页面。允许有明确条件与依据的情景讨论，不保证未来价格，不凭空构造预测值。

## 网络边界

抓取只允许公共 HTTP(S) 地址的 80/443 端口，不接受 URL 内用户名/密码。检查 DNS 解析地址均为公网，每次连接固定到已验证的 IP，TLS 使用原主机名验证证书；每次跳转重新校验。拒绝回环、私网、链路本地和元数据地址。限制响应为 2 MB、最多四次重定向，使用有超时的 GET 请求。

抓取器直接访问公网，不继承 HTTP 代理；本次服务器探测未配置代理。若以后集群改成必须经代理出网，需要独立配置和复验，不能通过关闭 TLS 检查解决。

网页、搜索摘要和来源内容是非可信数据。Prompt 要求忽略其中的指令；工具白名单也不提供 shell、任意代码执行或私网读取能力。审计日志和会话快照会保存查询及工具证据，发布时应按项目数据管理要求处理。

## 示例问题

- `Fetch AAPL historical prices online and show a 60-return moving-average chart.`
- `For the same stock, use a 120-return window.`
- `Search Microsoft MSFT investor relations, then read an official page and cite your evidence.`
- `有人声称 Anthropic 最近上市，请联网核实发行人和上市状态，区分已确认事实与未知信息。`
- `用保留的离线快照分析腾讯，然后另查最新官方消息，分别标注日期。`

完整的探测、失败修复和真实模型验收记录见 [联网版实施与实测记录](docs/联网版实施与实测记录.md)。

## 检查与代码位置

```bash
python3 -m unittest discover -s agent -p 'test_*.py' -v
```

`agent/test_online.py` 当前 18 项测试覆盖精确 token 裁剪、完整证据保留、工具循环、外部股票图表、来源展示、离线计算、偏好继承、挑战页和不相关搜索过滤、私网与重定向拒绝、TLS 校验及数值引用。CPU 作业还执行 `deploy/tacc/network_check.py`，验证真实网络工具。

主要修改点：`agent/chat_agent.py`、`agent/tool_registry.py`、`agent/web_tools.py`、`agent/evidence.py`、`agent/chat.html`；部署仍复用同作业 supervisor 结构。新版有独立的 `scripts/tacc.py` 和 `deploy/tacc/`，不会从原目录隐式导入代码。
