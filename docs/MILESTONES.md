# Milestones

时间基线：建议从 2026-11-09（周一）开始，按 12 周 Local-first MVP 计划执行。日期可以根据人员和数据供应商调整，但里程碑的完成定义不应被弱化。

## M0：立项与决策冻结

**时间：2026-11-09 至 2026-11-13**

目标：把产品边界变成团队共识。

交付物：

- PRD 评审通过；
- MVP 股票池、数据范围和规则清单；
- 数据供应商候选与授权状态；
- 首发平台锁定为 Tauri 2 Desktop；
- Cloud Agent、Web、iOS、Android 明确列为后续扩展；
- 伦理、合规和人工审批边界确认；
- 开发环境和代码仓库初始化。

完成定义：

- P0 需求无未决冲突；
- 所有 P0 规则有自然语言和结构化表达；
- 明确“允许做什么”和“禁止做什么”。

## M1：Tauri 2 Local Runtime

**时间：2026-11-16 至 2026-11-20**

目标：让 Tauri Desktop 在没有 Cloud Agent 的情况下启动并运行本地 Agent。

交付物：

- Python Agent 最小启动器；
- LangGraph 单任务流程；
- SSE Trace；
- SQLite/DuckDB 快照；
- Tauri 2 Sidecar 集成记录；
- `local` Agent Runtime 作为 MVP 默认模式；
- macOS/Windows 开发机启动和退出验证；
- Cloud Execution Plane 的扩展边界记录。

完成定义：

- 能启动、暂停、恢复和退出 Agent；
- Agent Trace 可实时显示；
- Worker 崩溃可被检测；
- 形成 Tauri 2 集成 ADR，记录 Sidecar 生命周期、平台限制和降级方案。

## M2：数据基线

**时间：2026-11-23 至 2026-12-04**

目标：建立可回放的日线数据和质量层。

交付物：

- 交易日历、股票、指数、行业、日线和基础财务表；
- Raw/Normalized/Snapshot 三层管道；
- 数据质量检查；
- 数据源失败告警；
- Provider Adapter、Normalizer 和 Contract Tests；
- 最小数据回放脚本。

完成定义：

- 指定日期可重建同一市场快照；
- 每条数据包含来源、as-of 和质量；
- 关键字段完整率达到 PRD 目标。

## M3：Rules Engine 与 Portfolio

**时间：2026-12-07 至 2026-12-18**

目标：把用户交易纪律变成可执行门禁。

交付物：

- Profile、Ruleset、Portfolio Schema；
- Data/Market/Universe/Portfolio/Instrument Gate；
- 规则版本和快照；
- 规则测试矩阵；
- `NO_ACTION`、`BLOCKED`、`WATCH` 输出。

完成定义：

- 所有 P0 规则有单元测试；
- 规则失败不能生成可审批买入建议；
- 旧任务不受规则新版本影响。

## M4：Agent Workflow

**时间：2026-12-21 至 2027-01-08**

目标：完成收盘复盘和个股研究闭环。

交付物：

- Chief、Market、Sector、Stock、Technical、Portfolio、News Agent；
- Agent State 和结构化输出；
- Tool 权限矩阵；
- Bull/Bear Debate；
- Research Manager 汇总；
- 失败重试和人工接管。

完成定义：

- 一个收盘事件可以创建任务并完成全流程；
- 每个结论都能定位到 Agent、Tool 和 Evidence；
- 失败任务能从断点继续。

## M5：Research Workspace

**时间：2027-01-11 至 2027-01-22**

目标：让用户能理解、审查和批准研究结果。

交付物：

- Task List；
- Research Timeline；
- Evidence Panel；
- Bull/Bear Debate；
- Risk Review；
- Decision Panel；
- SSE 实时更新；
- 移动端折叠布局。

完成定义：

- 用户在 2 分钟内找到结论来源；
- `BLOCKED` 和 `NO_ACTION` 不显示错误的批准动作；
- 审批产生不可变审计记录。

## M6：Event Engine 与通知

**时间：2027-01-25 至 2027-02-05**

目标：让系统主动工作。

交付物：

- `MarketClose`、`PortfolioRiskChanged`、`FilingPublished`；
- 去重、冷却、优先级和重试；
- 站内通知和 Web Push；
- 事件回放和失败告警；
- Provider 路由、健康检查和故障切换。

完成定义：

- 同一事件不重复创建任务；
- 高优先级风险事件可打断普通扫描；
- 数据质量异常会阻断受影响任务。

## M7：安全、运营与试点

**时间：2027-02-08 至 2027-02-19**

目标：达到可控试点发布条件。

交付物：

- 认证、密钥管理和权限审计；
- 备份、恢复和监控；
- 安全测试与 Prompt Injection 测试；
- 试点用户手册；
- 发布检查单；
- 试点复盘模板。

完成定义：

- 通过 `docs/ACCEPTANCE.md` 的 P0 清单；
- 完成一次故障演练和一次数据回放；
- 试点用户可独立完成研究和审批。

## 里程碑依赖

```text
M0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7
                 \              /
                  -> security --
```

M5 可以在 M6 前完成；M7 必须依赖 M2-M6 的核心闭环。Cloud Agent、Web、iOS 和 Android 另立扩展里程碑，不进入本计划的发布门。
