# Execution Plan

> 本文保留初始 MVP 的 12 周执行安排。2026-11-12 整理的能力增强批次见
> [Capability Roadmap](CAPABILITY_ROADMAP.md)、
> [P0 Implementation Plan](P0_IMPLEMENTATION_PLAN.md) 和
> [P1 Implementation Plan](P1_IMPLEMENTATION_PLAN.md)。
> 新计划不替换原有 MVP 验收与发布门。

## 1. 工作方式

采用 Local-first、小步、可回放、每周可演示的交付方式：

- 每周只承诺一个可运行的垂直切片；
- 先固定契约和验收，再扩大实现；
- 所有 Agent 输出先进入结构化 Schema，再进入 UI；
- 每个阶段结束都做意图、设计、实现、行为和系统五层检查；
- 任何数据或规则不确定性都记录为显式风险，不靠口头记忆。

## 2. 角色

| 角色 | 责任 |
|---|---|
| Product Owner | 范围、优先级、规则和发布决策 |
| Tech Lead | 架构、接口、Tauri 2 集成和技术风险 |
| Agent Engineer | LangGraph、Agent State、Tools、Prompt |
| Data Engineer | 数据源、ETL、质量和快照 |
| Backend Engineer | API、任务、事件、审计 |
| Frontend Engineer | Workspace、SSE、审批和移动端 |
| QA/Validation | 回放、验收、故障和安全验证 |

一人开发时可以由同一人承担多个角色，但评审清单仍需保留。

## 3. 12 周执行表

| 周 | 重点 | 可演示结果 |
|---|---|---|
| W1 | PRD、规则、数据供应商、仓库 | 立项评审包 |
| W2 | Local Agent Runtime 与 Tauri 2 Sidecar | 不依赖 Cloud 的 Agent 启停和 SSE Trace |
| W3 | Raw/Normalized 数据管道 | 指定日期数据快照 |
| W4 | 数据质量和回放 | 失败可识别、快照可重建 |
| W5 | Profile、Portfolio、Rules Schema | 规则门禁命令行演示 |
| W6 | Rules Engine P0 | 通过/阻断/警告矩阵 |
| W7 | Chief + Market + Research Agent | 收盘复盘任务 |
| W8 | News/Technical/Portfolio + Debate | 个股研究任务 |
| W9 | 本地 API、任务状态和审计 | 端到端本地任务 API |
| W10 | Research Workspace | 可读 Trace、证据和风险面板 |
| W11 | Event Engine、通知、重试 | 本地收盘事件自动触发 |
| W12 | 本地安全、备份、运维、试点 | 发布候选版本 |

## 4. 垂直切片

### Slice 1：收盘复盘

范围：

- 拉取日线；
- 计算市场广度；
- 创建 `MarketClose`；
- Market Agent 解释；
- Rules Engine 输出门禁；
- Workspace 展示。

完成标准：

- 无需手工拼接数据；
- 失败有原因；
- 结果可回放；
- 没有买入建议绕过门禁。

### Slice 2：个股研究

范围：

- 股票输入；
- 基本面、技术面、新闻；
- Bull/Bear Debate；
- Research Manager；
- Risk Review。

完成标准：

- 结论至少关联三类证据；
- 过期证据有标记；
- 未解决分歧有展示；
- 输出不是单一 BUY/SELL。

### Slice 3：持仓风险

范围：

- 组合快照；
- 集中度和回撤；
- `PortfolioRiskChanged`；
- 风险 Agent；
- 人工审批。

完成标准：

- 风险事件优先级高于普通扫描；
- 用户能看到实际暴露和规则阈值；
- 建议和审批全量审计。

## 5. 任务拆分模板

每个工程任务必须包含：

```text
Title:
Context:
Scope:
Out of scope:
Inputs / contracts:
Acceptance criteria:
Dependencies:
Operational impact:
Rollback / recovery:
```

## 6. 分支与评审

技术内容使用英文命名：

- branch: `feat/research-workspace`
- commit: `Add evidence panel`
- PR title: `Add rules-first research approval flow`

每个 PR 至少包含：

- 变更目的；
- 影响范围；
- 验收方式；
- 数据迁移或回滚说明；
- 仍未解决的风险。

## 7. 测试策略

### Unit

- Rules Engine 每条 P0 规则；
- Data normalization；
- State transition；
- Event dedupe；
- Permission matrix。

### Integration

- Data Worker -> Snapshot；
- Event -> Task；
- Agent -> Tool -> Evidence；
- Rules -> Decision；
- Approval -> Audit。

### Replay

- 固定数据快照和规则快照；
- 重放同一任务；
- 比较状态、门禁和结论结构；
- 允许 LLM 文本存在非确定性，但不允许规则结果漂移。

### E2E

- 创建研究任务；
- 查看实时 Trace；
- 展开证据；
- 查看阻断；
- 审批/拒绝；
- 导出审计记录。

## 8. 每周检查点

周一：

- 确认本周目标和不可变范围；
- 确认依赖和风险。

周三：

- 演示可运行切片；
- 记录偏差和失败。

周五：

- 通过验收；
- 更新风险和 ADR；
- 决定继续、缩减或暂停。

## 9. 变更控制

以下变更必须重新评审 PRD 和里程碑：

- 引入自动下单；
- 增加实时行情和盘中信号；
- 增加多用户或团队协作；
- 改变规则优先级；
- 允许 Agent 修改 Profile 或 Ruleset；
- 引入新的外部数据授权。
- 将 Cloud Agent、Web、iOS 或 Android 纳入 MVP 发布门。
