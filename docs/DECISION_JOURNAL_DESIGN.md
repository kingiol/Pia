# Decision Journal / Personal Investment Memory Design

## 1. 设计结论

`Decision Journal` 不应该成为第二套 notes 系统，也不应该新建一张重复 `decisions` 的大表。

第一版复用现有事实模型：

```text
research_tasks
  -> decisions
      -> evidence
      -> rule_snapshots
      -> market/data_snapshots
      -> approvals
      -> task_retrospectives
          -> derived memory candidates
              -> confirmed memory candidates
```

产品上提供三种视图：

```text
Journal  = 历史事实时间线
Patterns = 跨任务统计和候选模式
Memory   = 用户确认后可复用的长期记忆
```

核心不变量：

1. 当时的判断和后来观察严格分开。
2. 规则、数据快照和证据时间点不可被事后修改。
3. `NOT_TAKEN` 是合法的用户行为，不自动解释为错误。
4. 没有结果记录不计入成功率，也不等于零收益。
5. 系统生成的记忆默认是 `CANDIDATE`，只有用户确认后才能进入未来研究上下文。
6. Memory 永远不能自动生成买卖指令或修改用户规则。

## 2. 用户价值

当前产品已经能回答“这次研究得出了什么”。Decision Journal 要补上三个跨任务问题：

- 我过去在什么条件下反复做出相同判断？
- 我的规则和实际行为是否一致？
- 哪些经验值得带入下一次研究，哪些只是一次偶然结果？

因此它服务的是有经验、重视纪律和可复盘性的个人投资者。它不是收益排行榜，也不是用短期涨跌给历史决策打分的自动裁判。

## 3. MVP 范围

### 3.1 必须支持

- 跨任务 Decision timeline。
- 按股票、行业、Decision Intent、规则、时间和 Outcome 状态筛选。
- 展示每条记录当时的判断、证据、规则快照、数据快照和审批。
- 在任务下追加多个 Retrospective。
- 以明确窗口统计后续表现，例如 `T+5`、`T+20` 和用户实际行为。
- 统计规则满足/违反、建议采纳/拒绝、`BUY_CANDIDATE`/`WATCH`/`NO_ACTION` 后续观察。
- 生成带来源、样本量、时间窗口和置信度的 Memory candidate。
- 用户确认、修改、拒绝或归档 candidate。
- 新任务只读取 `CONFIRMED` memory。
- Local SQLite 与 Cloud PostgreSQL 使用同一领域接口和用户隔离规则。

### 3.2 明确不做

- 不引入向量数据库或复杂 embedding 检索。
- 不自动把所有任务总结成“投资人格”。
- 不把上涨结果直接标记为预测正确。
- 不把 `NO_ACTION` 的错过收益直接计为损失。
- 不根据 Memory 自动改变规则、仓位或提交订单。
- 不在第一版做跨用户比较、公开排行榜或社交分享。
- 不先新建 `decision_records` 事实表。

## 4. 领域模型

### 4.1 Decision Record

代码层由现有 `research_tasks + decisions` 组成，必要时通过聚合查询返回统一投影：

```text
decision_record = {
  task_id,
  user_id,
  subject: {symbol, name, sector?},
  intent: decision.status,
  rationale: decision.rationale_json,
  risk_level,
  next_action,
  decision_created_at,
  decision_snapshot: {
    rule_snapshot_id,
    data_snapshot_id,
    target_as_of,
    evidence_ids[]
  },
  approvals[]
}
```

`Decision Record` 的身份是任务级历史事实。后续结果只通过关联的 `Retrospective` 添加。

### 4.2 Observed Outcome / Retrospective

沿用 `task_retrospectives`，但在接口层把它解释为 Decision Cycle 的后续观察：

```text
retrospective = {
  id,
  task_id,
  action_taken,
  outcome: {
    status,
    return_pct?,
    horizon?,
    benchmark_return_pct?,
    market_regime?,
    position_size?,
    notes?
  },
  observed_at,
  rule_snapshot_id?,
  data_snapshot_id?,
  created_at
}
```

同一个任务允许多个窗口或多个动作记录。每条记录保留自己的 `observed_at`，不能覆盖之前记录。

建议的 `outcome.status`：

```text
NOT_RECORDED
NOT_TAKEN
TAKEN
EXPIRED
INVALIDATED
OBSERVED
```

`TAKEN` 只表示用户记录了采取行动，不表示盈利；收益和基准比较必须单独存在。

### 4.3 兼容现有 Retrospective 数据

当前实现已经允许 `action_taken` 使用 `NOT_TAKEN`、`APPROVE`、`REJECT`、`NO_ACTION` 和 `OTHER`，并允许 `outcome.status` 使用 `observed`、`positive`、`negative`、`mixed` 和 `unknown`。第一版不强制重写历史行，而是在 `DecisionJournal` 投影层做归一化：

```text
APPROVE   -> TAKEN
REJECT    -> NOT_TAKEN
NOT_TAKEN -> NOT_TAKEN
NO_ACTION -> NOT_TAKEN
OTHER     -> OTHER
```

原始 `action_taken` 和 `outcome` 必须同时返回，归一化字段只用于筛选和统计。后续若需要更严格的结果窗口，再追加结构化字段和迁移，不通过改变历史 JSON 来“修正”过去的记录。

### 4.4 Derived Memory / Confirmed Memory

候选和确认后的长期记忆使用独立的 `memory_candidates` 容器，不直接写入
`semantic_memories`。这样可以让候选 review 生命周期、来源统计和未来上下文权限保持清晰。
字段如下：

```text
memory = {
  id,
  user_id,
  kind,
  title,
  content,
  source_type,
  status,
  confidence,
  sample_size,
  observation_window,
  source_task_ids[],
  source_rule_snapshot_ids[],
  as_of,
  observed_at,
  created_at,
  reviewed_at?,
  archived_at?
}
```

状态：

```text
CANDIDATE -> CONFIRMED -> STALE -> ARCHIVED
       \-> REJECTED
```

来源类型：

```text
USER_AUTHORED
SYSTEM_DERIVED
TASK_SUMMARY
RETROSPECTIVE_PATTERN
RULE_PATTERN
```

第一版已将用于过滤、排序和权限判断的字段结构化；`semantic_memories` 仍保留给用户直接维护的语义记忆。

## 5. 派生边界

系统分三步工作：

```text
事实读取
  -> 确定性聚合和统计
      -> LLM 解释候选模式
          -> 用户确认
              -> Confirmed Memory
```

确定性层负责：

- 计算样本量；
- 过滤无 `outcome` 的记录；
- 按规则版本和时间窗口分组；
- 计算采纳率、违反率、观察收益和基准差异；
- 标注数据不足、规则版本混杂和市场环境变化。

LLM 只负责：

- 把已计算的模式写成可读解释；
- 提出候选标题和需要用户确认的问题；
- 引用原始任务和统计依据。

LLM 不负责：

- 修改历史决策；
- 计算核心指标；
- 把一次结果概括为稳定规律；
- 直接把 candidate 写成 confirmed memory。

当前实现的 review 动作为：

```text
CANDIDATE -> CONFIRMED
CANDIDATE -> REJECTED
CANDIDATE -> ARCHIVED
CANDIDATE -> CONFIRMED (EDIT_AND_CONFIRM)
CONFIRMED -> ARCHIVED
```

只有 `CONFIRMED` 行会出现在 `task_context.confirmed_memories` 和 LLM 的只读输入中。
`REJECTED`、`ARCHIVED` 和未保存的统计候选不会进入未来任务上下文。

Memory 被放入任务上下文时会写入一条去重的
`TASK_CONTEXT_INJECTED` 使用记录。该记录只证明系统把 Memory 提供给了任务，
不代表模型采纳了它，也不代表它造成了某个收益。后续结果仍通过任务自己的
`Retrospective` 关联，并在 Memory 页面展示使用次数、使用后的可比较结果和
平均结果。

用户可以针对最近一次使用提交 `HELPFUL`、`NOT_HELPFUL` 或 `UNCERTAIN` 反馈。
页面提交明确的 `usage_id`，绑定当前展示的使用记录，避免提交期间新任务改变
反馈对象。API 也支持指定历史使用记录；省略 `usage_id` 时使用最近一条记录。
反馈按使用记录保存并可更新，不自动改变 Memory 状态。确定性汇总规则是：
至少两次“无帮助”且没有“有帮助”时显示归档建议；“无帮助”多于“有帮助”
时显示复查建议；“有帮助”多于“无帮助”时显示继续保留，其余情况显示复查建议。

## 6. 统计和时间窗口

每个 Pattern 必须同时显示：

```text
sample_size
eligible_outcome_size
observation_window
rule_version_scope
market_regime_scope
confidence
```

推荐窗口：

- `T+5`: 短期后续表现；
- `T+20`: 中期后续表现；
- `USER_RECORDED`: 用户明确记录的实际行动和结果。

比较规则：

1. 不同 `rule_snapshot_id` 默认分组展示，不能静默合并。
2. 不同市场环境应显示为不同分组，至少标出 `market_regime` 是否一致。
3. `NOT_TAKEN` 只用于行为统计；不能直接和 `TAKEN` 的收益混成一个胜率。
4. 缺少结果的记录只计入决策数量，不计入结果分母。
5. 样本量低于 3 时只能显示为观察，不生成候选 Memory；默认低于 5 时不显示“模式成立”措辞。
6. 结果应同时展示绝对收益和相对基准收益，避免单纯受市场整体上涨误导。

## 7. 聚合模块和接口

新增一个后端深模块 `DecisionJournal`，它隐藏跨表查询、权限、分组和派生规则，对外只暴露少量接口：

```text
list_journal(filters) -> JournalPage
get_summary(filters) -> JournalSummary
get_patterns(filters) -> PatternReport
review_memory(memory_id, action) -> Memory
```

外部 HTTP 接口建议：

```text
GET  /api/journal
GET  /api/journal/summary
GET  /api/journal/patterns
GET  /api/memory
POST /api/memory
POST /api/memory/{id}/review
```

`GET /api/journal` 参数：

```text
symbol
sector
intent
outcome_status
rule_snapshot_id
from
to
cursor
limit
```

返回结构：

```text
{
  "items": [
    {
      "decision_record": {...},
      "retrospectives": [...],
      "evidence_summary": {...},
      "replay_refs": {...}
    }
  ],
  "next_cursor": "..."
}
```

`GET /api/journal/summary` 返回研究次数、各 Intent 数量、采纳/拒绝/未采取数量、可比较结果数、规则满足/违反次数和数据不足提示。

`GET /api/journal/patterns` 返回确定性统计和候选 Memory 的依据，不直接写入 `semantic_memories`。

`POST /api/memory/{id}/review` 的 action：

```text
CONFIRM
EDIT_AND_CONFIRM
REJECT
ARCHIVE
```

所有接口都必须按当前认证用户过滤。`task_id`、`memory_id` 和来源任务列表都必须再次做 user ownership 校验，不能只信任客户端传入的 `user_id`。

## 8. UI 信息架构

建议在总览页增加 `Decision Journal` 入口，页面拆成三个 tab：

```text
+------------------------------------------------------------------+
| Decision Journal                 [Journal] [Patterns] [Memory]   |
| [Date] [Symbol] [Intent] [Rule] [Outcome]                       |
+----------------------+-------------------------------------------+
| Summary              | Decision timeline                        |
| Research      24     | 2026-11-05 600000.SH                     |
| Taken          7     | WATCH                                     |
| Not taken     11     | Rule v3 · Data 2026-11-05                |
| Violations     3     | Evidence 4 · Approval rejected           |
| Comparable     9     | Outcome: NOT_TAKEN · T+5: +2.4%          |
|                      |                                           |
| Memory candidates   | 2026-11-01 510300.SH                     |
| [Review 2]          | BUY_CANDIDATE                             |
|                      | Outcome: TAKEN · T+20: +5.1%              |
+----------------------+-------------------------------------------+
```

### Journal

展示事实时间线。每条记录能展开：

- 当时 Decision Intent；
- rationale 和 risk；
- Evidence、Rule Snapshot、Data Snapshot；
- Approval；
- 一个或多个 Retrospective；
- `Replay` 入口。

### Patterns

展示跨任务统计：

- 按 Intent 的后续观察；
- 按规则版本的满足/违反；
- 用户采纳、拒绝和未采取；
- 数据不足或不可比原因；
- Memory candidate 的来源任务。

### Memory

展示用户长期记忆：

- `CONFIRMED`、`CANDIDATE`、`STALE`、`ARCHIVED`；
- 来源任务和样本量；
- 用户确认、编辑、拒绝和归档；
- “将被带入未来研究上下文”的明确状态。

## 9. 推荐实现顺序

### Slice 1：事实时间线

- 新增 `DecisionJournal` 查询模块；
- 复用现有 `research_tasks`、`decisions`、`evidence`、`approvals`、`task_retrospectives`；
- 增加 `GET /api/journal`；
- 桌面端先做只读 Journal 页面；
- 验证用户隔离、分页、快照链接和旧任务回放。

### Slice 2：确定性 Summary / Patterns

- 增加 outcome window 解析；
- 实现规则版本分组、Intent 统计和行为统计；
- 增加 `GET /api/journal/summary`、`GET /api/journal/patterns`；
- 显示样本量、不可比原因和缺失结果。

### Slice 3：Memory candidate

- 把达到最低门槛的统计模式转换为独立的 `SYSTEM_DERIVED` candidate；
- 记录候选 key、状态、样本量、可比较结果数、平均结果、来源任务和规则快照；
- 使用 `POST /api/journal/memory-candidates` 显式保存候选，避免 GET 查询产生写入副作用；
- 候选保存在 `memory_candidates` 派生表，不进入 `semantic_memories` 或新任务上下文；
- 重复保存同一个候选 key 会刷新统计并保留候选 ID；
- 增加 `MEMORY_CANDIDATE_CREATED` / `MEMORY_CANDIDATE_REFRESHED` 审计事件。

### Slice 4：Review and confirmed memory

- 增加 `review` 接口；
- 支持确认、编辑确认、拒绝、归档；
- 新任务 context 只检索 `CONFIRMED`；
- 增加跨任务回归测试。

### Slice 5：Memory 使用记录

- 新任务加载确认后的 Memory 时记录 `TASK_CONTEXT_INJECTED`；
- 同一 Memory、任务和使用类型去重，所有读写按用户隔离；
- 增加 `GET /api/journal/memory-candidates/{candidate_id}/usage`；
- 显示使用次数、任务引用和使用任务的后续观察，不推断收益因果关系。

### Slice 6：Memory 效果反馈

- 增加 `POST /api/journal/memory-candidates/{candidate_id}/feedback`；
- `HELPFUL`、`NOT_HELPFUL`、`UNCERTAIN` 反馈绑定具体使用记录；
- 同一使用记录可更新反馈，保留创建时间并追加更新审计事件；
- 汇总显示 `NO_FEEDBACK`、`KEEP`、`REVIEW_SUGGESTED`、
  `ARCHIVE_SUGGESTED`，不自动修改确认状态；
- 页面区分最近一次使用的反馈入口与累计反馈形成的建议。

### 后续候选：Retrospective 体验

- 把当前任务底部的 `RetrospectivePanel` 连接到 Journal；
- 支持 `T+5`、`T+20` 和 `USER_RECORDED` 多个观察窗口；
- 记录实际动作、收益、基准收益、超额收益、市场环境和仓位；
- 后端将缺省窗口归一化为 `USER_RECORDED`，并拒绝非法窗口、非数值结果和未来 `observed_at`；
- 允许从 Journal 直接回到任务详情。

## 10. 验收标准

### 意图层

- 用户能回答“我过去在什么条件下做过什么判断”；
- 用户能区分当时判断、实际动作和事后结果；
- 系统不会暗示短期结果等于决策正确。

### 设计层

- Journal 不复制 `decisions` 和 `task_retrospectives` 的事实；
- Pattern 和 Memory 是派生层；
- 原始快照和审计记录保持可回放；
- Local 与 Cloud 使用同一接口语义。

### 实现层

- 跨任务查询集中在 `DecisionJournal` 深模块；
- API 不要求前端拼接多张表；
- 所有写入都校验 user ownership；
- 结构化字段用于筛选和统计，文本只用于解释。

### 行为层

- 一个任务有多个 Retrospective 时都能显示；
- 同一用户可以跨任务查询；
- 不同用户不能看到彼此记录；
- 不同规则版本不会被错误合并；
- 没有 outcome 的决策不计入成功率；
- `NOT_TAKEN` 能正确统计；
- 未来 `observed_at` 会被拒绝；
- 未确认 Memory 不会影响新任务；
- 确认后的 Memory 会被新任务读取；
- 归档 Memory 不影响原始决策和审计；
- SQLite 与 PostgreSQL 的响应结构一致。

### 系统层

- 查询有分页和合理索引；
- 大量历史任务不会阻塞任务执行；
- 聚合失败只影响 Journal/Patterns，不损坏原始研究记录；
- 任何统计结果都能追溯到来源任务、规则版本和数据快照。

## 11. 主要风险与处理

| 风险 | 处理 |
|---|---|
| 一次上涨被解释为决策正确 | 同时展示样本量、基准和多窗口；不输出正确/错误二元结论 |
| 规则版本变化造成伪规律 | 按 `rule_snapshot_id` 分组，版本混杂时标记不可比 |
| 没有结果被当成零收益 | 单独使用 `eligible_outcome_size`，缺失结果不进分母 |
| `NOT_TAKEN` 被当成失败 | 作为独立行为状态展示，只做机会观察 |
| AI 生成过度概括 | LLM 只解释确定性统计，必须列来源和置信度 |
| Memory 反过来改变历史 | Memory 只读入未来 context，不回写 Decision Record |
| Local/Cloud 数据隔离遗漏 | 所有查询和写入统一经过 authenticated user scope |

## 12. 设计决策

MVP 采用“复用现有事实实体 + 增加聚合读取模块”的方案。只有当跨任务投影的查询复杂度明显影响写模型、性能或回放能力时，才引入独立 read model 或 materialized projection；届时仍不改变原始 `research_tasks`、`decisions` 和 `task_retrospectives` 的所有权。
