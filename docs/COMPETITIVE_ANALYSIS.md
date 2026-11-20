# Pia 竞品分析

2026-11-19 · Pia `main` / `13586d7`。按 A 股个人投资者的实际任务选取代表性产品。Pia 以代码、本次离线验证和 CI 记录为依据。竞品能力来自产品方披露与项目仓库，未做同条件实机对测。公开资料覆盖有限，表格只列有据可查的能力。

## 产品判断

**Pia 最值得验证的切入点是「收盘后，用自己的持仓和规则做一次可回放的决策复盘」。** 目标用户已经有选股和仓位方法，平时用行情终端查信息，再用 Excel 或笔记留痕。Pia 要解决的是两者之间的工作：用当天数据检查自己的持仓规则，解释哪里触发了限制，保存人工选择及其理由，并在下周还能按当时的输入复现判断。用户可以继续用原来的终端查行情和交易。目标用户与试点路径见 [PRD](PRD.md) 和 [试点验证计划](PILOT_VALIDATION_PLAN.md)。

## 代表性产品对比

| 产品 | 已公开的能力 | 与 Pia 的重合和侧重点 |
|---|---|---|
| **同花顺问财** | 条件选股、诊股、策略验证和组合分析。2026 年半年报披露个人端向覆盖盘中跟踪、盘后复盘和公告解读的投研 Agent 升级。[2025 年报](https://static.cninfo.com.cn/finalpage/2026-03-10/1225002186.PDF) · [2026 半年报](https://static.cninfo.com.cn/finalpage/2026-08-22/1225491733.PDF) | 直接覆盖用户查数据、筛选和复盘的入口。Pia 当前仅内置一个候选筛选策略，适合展示候选为何入选、用什么数据以及如何复算。 |
| **东方财富妙想** | 市场复盘、条件选股、行情财务公告查询、报告生成和可点开的来源，妙想 Work 可执行复杂投研任务。[开发者产品说明](https://apps.apple.com/cn/app/%E5%A6%99%E6%83%B3/id6469681957) · [Choice 用户指南](https://choice.eastmoney.com/choicewebfile/UserGuide.pdf) | A 股 AI 投研的直接替代品。Pia 的证据还用来判断输入的时间、质量和适用标的，并与个人规则版本、门禁结果和后续动作保存在同一任务里。 |
| **华泰 AI 涨乐** | 任务助手调度专业智能体，串联选股、持仓复盘、智能盯盘和条件交易。[2026 半年报，第 42 页](https://static.cninfo.com.cn/finalpage/2026-08-29/1225531512.PDF#page=43) | 用同一 App 管账户、盯盘和执行的用户可以直接在券商侧完成。Pia 当前从导入的持仓快照做收盘后研究，结论交给用户复核。 |
| **财搭子** | 持仓诊断、盘中异动拆解、来源和时间标注、模拟账户及策略验证。[官网](https://www.zhicepilot.com/) | 独立 AI 投研产品中场景接近。Pia 的可验证重点是用当时的真实持仓输入和自定义规则复算风险结论。 |
| **TradingAgents-CN** | 多智能体辩论式个股分析、自然语言筛选、项目记忆和模拟交易复盘。[项目文档](https://github.com/hsliuping/TradingAgents-CN#核心功能) | 对希望用 AI 多角度研究个股的用户有直接重合。Pia 当前部分研究节点是模板，模型研究可选。它的强项是记录观点来源，并由程序单独判断证据和个人规则是否满足。 |
| **TradingWorkbench** | A 股 ETF 监控、定时研究、配置和输入哈希、带点时资料的证据包、确定性引用及数字校验。证据不足时，报告可降为 `Not Rated`。[证据与报告门禁](https://github.com/gaaiyun/TradingWorkbench#evidence-和报告门禁) | 最接近 Pia 的研究基础设施参照。Workbench 的证据门禁约束报告能否发布，Pia 的核心路径把个人持仓和规则门禁接到人工选择、事后复盘和离线回放。 |
| **TradingReview** | 本地 A 股复盘，导入券商成交、计算成本和收益曲线、统计纪律执行率，维护个人规则版本并把规则用于 AI 事后复盘。[功能说明](https://github.com/NanoTeaegg/TradingReview#功能页面介绍) | 最接近 Pia 的本地复盘参照。TradingReview 从真实成交切入，适合复盘执行和盈亏。Pia 支持 CSV、XLSX 和手动导入持仓快照，后续动作依靠人工记录。用户可以为没做的交易留下理由，并关联当时的规则和证据。[Pia 实现映射](IMPLEMENTATION.md#implementation-map) |
| **TradingView / 聚宽** | TradingView 提供图表、AI 筛选和行情工具接入。聚宽提供 Python 研究、历史回测和模拟交易。[TradingView AI 筛选](https://www.tradingview.com/support/solutions/43000785770-how-to-use-the-ai-screener/) · [TradingView MCP](https://www.tradingview.com/mcp/docs) · [聚宽官方 API 文档](https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf) | 用来验证策略能否长期执行或快速研究技术信号。Pia 的离线回放回答「这次决策为何被提示或阻断」，策略收益和历史成交模拟需要相应工具。 |

交易日志工具也在逼近规则场景。TradesViz 可把纪律规则落实到成交记录并自动检查，TradeZella 可逐笔回放实际交易，也可用规则做历史回测。Pia 的组合差异取决于**同一条 A 股研究记录**能否同时保留事前规则判断、人工选择和事后所见。单项功能本身的区分度有限。[TradesViz 规则文档](https://www.tradesviz.com/blog/trading-rules/) · [TradeZella 成交回放](https://www.tradezella.com/trade-replay) · [TradeZella 回测](https://help.tradezella.com/en/articles/9854312-what-is-backtesting-in-tradezella)

## Pia 当前有多少证据

| 要素 | 本次核对 |
|---|---|
| **可复现与规则门禁** | 任务创建时冻结 Profile、规则和已确认记忆，取数后写入带内容哈希的 `DecisionContextPack`。证据按时间、标的和质量检查。带完整快照的任务可离线回放，保留原始证据和规则结果。复盘可以追加实际动作和观察结果，用户确认的记忆才能进入以后任务。[能力交付](CAPABILITY_DELIVERY.md) · [回放测试](../tests/test_decision_context.py) · [日志测试](../tests/test_journal.py) |
| **当前研究输出** | 新任务只产生 `WATCH`、`NO_ACTION` 或 `BLOCKED`。用户可继续研究、加入观察或记录不行动原因。默认 `action_eligible=false`，无券商订单写入。部分 Agent 观点来自标注的模板。Local 用本机 SQLite/DuckDB，实时取数及可选模型仍依赖网络，模型路由可按数据类别授权。[README](../README.md) · [能力交付](CAPABILITY_DELIVERY.md) |
| **本次本地验证** | `./scripts/replay.sh` 通过，合成案例因单标的和行业暴露超出规则而返回 `BLOCKED`。回放、决策合成、日志和扫描的 20 项现有专项测试通过。[测试目录](../tests/) |
| **桌面交付** | `13586d7` 的 CI 已通过 Windows x64 与 macOS ARM64 的 Tauri 打包并上传制品。Windows 打包验收与原生通知 smoke、双平台 Sidecar 健康检查均通过。CI 制品与 runner smoke 是当前可见证据，正式签名发布和终端用户的跨会话投递仍待验证。[CI 和制品](https://github.com/kingiol/Pia/actions/runs/44484534353) |
| **真实数据** | 同一提交的 11 月 19 日 AKShare 检查失败。首个样本业务日 11 月 13 日遇到连接重置、上游限流，缺市场快照和日线。其余四个样本日未检查。Tushare 真实主备切换与长期稳定性仍缺证据。规则阻断能避免使用不合格输入，但数据反复缺失会让用户失去日常使用理由。[失败日志](https://github.com/kingiol/Pia/actions/runs/44487938005/job/135436005262) · [真实服务验收项](CAPABILITY_IMPLEMENTATION_STATUS.md#external-gates) |

## 优先验证的三件事

1. **日线是否足够可靠。** 建议先覆盖连续 5–10 个交易日，固定试点标的，分别记录行情覆盖、过期、主备切换及阻断原因。先用授权的真实来源证明收盘后能持续拿到可用数据。工程上复用现有 freshness 与 provenance 验收。[验收标准](ACCEPTANCE.md) · [能力交付](CAPABILITY_DELIVERY.md)
2. **个人规则是否真的节省复盘时间。** 用现有计划中的 10–15 位目标用户，拿相同日期、一份脱敏持仓和一条集中度规则，分别走他们原本的终端加 Excel 或笔记流程，以及 Pia 流程。准备正常、超限和行情过期三个案例，记录首次完成比例、用时、能否解释阻断、是否记下实际动作或不操作原因。沿用首次完成率 ≥ 70%、首次用时中位数 ≤ 10 分钟、≥ 80% 的用户在两分钟内找到证据和规则结果的试点门槛。[试点验证计划](PILOT_VALIDATION_PLAN.md)
3. **留痕是否值得第二周再来。** 第二周让用户找回一条旧记录，现场回放并解释规则有无变化，观察其是否自发回来查看研究或事件。若手工维护持仓成为主要流失点，再验证一类常见券商的只读文件导入或更新能否减少重复录入。若用户能查到门禁却只把 Pia 当报告阅读器，先改进理由、规则与人工选择之间的衔接。[试点验证计划](PILOT_VALIDATION_PLAN.md) · [决策日志设计](DECISION_JOURNAL_DESIGN.md)

现阶段优先投入真实数据可靠性与首次复盘路径的验证。能否形成复用和付费意愿，需要看同一批用户在真实持仓上的第二周行为。
