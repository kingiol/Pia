# Research Workspace Specification

## 1. 目标

Research Workspace 是用户理解一次研究任务、检查证据、观察 Agent 过程、审查风险并做出人工决定的主界面。

它必须让用户回答五个问题：

1. 这次任务为什么被触发？
2. Agent 做了什么？
3. 结论依据哪些证据？
4. 哪些观点存在分歧？
5. 规则和风险审核是否允许下一步？

## 2. 页面信息架构

```text
+--------------------------------------------------------------------+
| Header: Task title | Trigger | As-of | Status | Pause / Export     |
+------------------+---------------------------------+---------------+
| Left: Task list   | Center: Research timeline      | Right: Review   |
| - active          | [Plan] [Agents] [Tools]        | Decision        |
| - recent          | Evidence-linked step cards     | Rule gates      |
| - watchlist       | Bull / Bear debate             | Risk flags      |
|                  | Final synthesis                 | Human approval  |
+------------------+---------------------------------+---------------+
| Bottom: Evidence drawer / raw data / source / freshness / replay    |
+--------------------------------------------------------------------+
```

## 3. 页面区域

### 3.1 Header

展示：

- 研究任务名称；
- 触发原因：用户创建、收盘事件、公告事件、持仓风险；
- 数据时间点 `as_of`；
- 任务状态；
- 暂停、重试、导出和回放入口。

### 3.2 Task List

按状态分组：

- `RUNNING`
- `WAITING_APPROVAL`
- `BLOCKED`
- `COMPLETED`
- `FAILED`

每条任务显示股票、事件、风险等级、更新时间和是否需要用户操作。

### 3.3 Research Timeline

每个步骤卡片至少包含：

- Agent 名称和职责；
- 输入摘要；
- Tool 调用；
- 输出摘要；
- 证据数量；
- 耗时和 token/成本；
- 成功、失败、重试或跳过原因。

用户可以展开原始结构化输出，但默认展示可读摘要。

### 3.4 Evidence Panel

证据卡片字段：

| 字段 | 说明 |
|---|---|
| Source | 数据源、公告、财报或新闻 |
| Observed at | 系统观察时间 |
| As of | 数据对应的业务时间点 |
| Expires at | 证据建议失效时间 |
| Quality | `verified`、`stale`、`partial`、`unavailable` |
| Used by | 使用该证据的 Agent 和结论 |
| Snapshot | 可回放的数据快照 |

证据状态必须显式显示，不能把过期数据伪装成最新信息。

### 3.5 Bull/Bear Debate

采用左右双栏：

```text
+-------------------------+-------------------------+
| Bull Case               | Bear Case               |
| claim                   | claim                   |
| supporting evidence    | supporting evidence     |
| confidence              | confidence               |
| unanswered questions    | unanswered questions    |
+-------------------------+-------------------------+
| Research Manager synthesis / unresolved conflicts  |
+---------------------------------------------------+
```

要求：

- 每个观点至少有一条证据或明确标记为假设；
- 不强行消除分歧；
- 显示未解决问题；
- 由 Research Manager 说明哪些证据决定了最终权重。

### 3.6 Risk Review

Risk Review 以门禁列表展示：

- 数据是否有效；
- 市场环境是否满足；
- 股票池是否合规；
- 持仓和集中度是否满足；
- 止损/最大损失规则是否满足；
- 是否存在停牌、ST、流动性和公告风险；
- 是否需要人工补充信息。

每条门禁显示：

```text
[PASS] market_breadth >= configured threshold
[BLOCK] portfolio concentration exceeds limit
[WARN] news evidence expires in 6 hours
```

### 3.7 Decision Panel

建议状态：

- `BUY_CANDIDATE`
- `SELL_CANDIDATE`
- `HOLD`
- `WATCH`
- `NO_ACTION`

决策卡必须展示：

- 建议状态；
- 置信度和不确定性；
- 目标、触发条件和失效条件；
- 风险等级；
- 规则门禁结果；
- 下一步行动；
- 人工审批按钮。

MVP 的审批按钮只允许：

- `Approve proposal`
- `Reject proposal`
- `Request more research`
- `Mark as watch`

不能出现“直接下单”按钮。

## 4. 交互状态

### 空状态

如果没有活动任务，展示：

- 今日市场数据状态；
- 最近一次收盘复盘；
- 用户关注列表；
- 创建研究任务入口。

### 加载状态

显示当前 Agent、步骤和预计剩余阶段。不要只显示一个无限旋转图标。

### 阻断状态

明确展示：

- 哪条规则阻断；
- 哪个输入缺失或过期；
- 是否可以自动修复；
- 用户需要做什么。

### 失败状态

保留已经完成的 Trace 和证据，提供：

- 重试失败步骤；
- 从断点继续；
- 取消任务；
- 导出失败上下文。

## 5. 前端状态模型

```ts
type ResearchTaskStatus =
  | "QUEUED"
  | "PLANNING"
  | "RUNNING"
  | "REVIEWING"
  | "WAITING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "BLOCKED"
  | "RETRYABLE"
  | "FAILED"
  | "CANCELLED";

type DecisionStatus =
  | "BUY_CANDIDATE"
  | "SELL_CANDIDATE"
  | "HOLD"
  | "WATCH"
  | "NO_ACTION";
```

## 6. 可访问性与效率

- 键盘可在任务列表、Trace、证据和审批之间移动。
- 颜色不能是唯一状态表达方式，必须有文字和图标。
- 长文本默认折叠，证据可按来源和时间筛选。
- 研究任务和证据都支持复制稳定链接。
- 移动端以“结论 -> 风险 -> 证据 -> Trace”顺序折叠展示。

## 7. 验收标准

- 用户能从任务卡定位到触发事件。
- 用户能从结论定位到至少一条证据。
- 用户能看到每个 Agent 的输入、输出和失败原因。
- 用户能看到 Rules Engine 的所有门禁结果。
- `NO_ACTION` 和 `BLOCKED` 任务不显示可批准的买入动作。
- 审批后保存用户、时间、规则版本和数据快照。
