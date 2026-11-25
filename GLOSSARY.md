# Personal Investment Decision Context

这个上下文定义个人投资研究中“决策、结果和长期记忆”的共同语言。它用于保证跨任务复盘不会把历史事实、事后观察和推导出的经验混为一谈。

## Decision Journal

跨任务查看和分析用户投资研究记录的产品视图。它组织已有的研究任务、决策、证据、规则快照、审批和后续观察，不创建第二套事实来源。
_Avoid_: Trading diary, Notes

## Decision Record

某个研究任务在特定时间点形成的结构化判断，包含决策状态、理由、风险、证据、规则快照和数据快照。Decision Record 是历史事实，只能追加关联信息，不能被后来结果覆盖。
_Avoid_: Prediction, Trade result

## Decision Intent

Decision Record 表达的用户或系统建议行动，例如 `BUY_CANDIDATE`、`WATCH`、`NO_ACTION`。它表示当时的意图，不表示订单已提交、成交或最终正确。
_Avoid_: Position, Execution

## Decision Snapshot

构成 Decision Record 的不可变上下文，包括 `rule_snapshot_id`、`data_snapshot_id`、证据的 `as_of` 和有效期，以及当时的用户配置。它用于回放和判断跨任务记录是否可比较。
_Avoid_: Current state

## Observed Outcome

在 Decision Record 之后观察到的市场变化或用户行为，例如实际是否采取行动、指定窗口内的收益、风险事件和结果备注。Observed Outcome 不会改写原始 Decision Record。
_Avoid_: Correctness, P&L truth

## Retrospective

用户对某个 Decision Record 后续实际动作和观察结果的追加记录。一个任务可以有多个 Retrospective；缺少结果记录不等于零收益或决策错误。
_Avoid_: Post-mortem, Trade log

## Derived Memory

从多个 Decision Record、Retrospective、规则和结果统计中推导出的候选经验。Derived Memory 必须带来源任务、样本量、时间窗口和推导状态，默认不能影响新任务。
_Avoid_: AI insight, Learned truth

## Confirmed Memory

用户审阅并确认后可供未来研究任务检索的 Personal Investment Memory。Confirmed Memory 仍然是可修订的用户知识，不得覆盖其来源的历史事实。
_Avoid_: Permanent rule, Auto strategy

## Rule Pattern

按规则版本和市场环境分组后，对规则满足、违反、采纳和后续结果进行的统计模式。Rule Pattern 需要足够样本量才可展示为候选记忆。
_Avoid_: Alpha, Proven edge

## Decision Cycle

从 Decision Record 到一个或多个 Retrospective，再到可选 Derived Memory 的完整生命周期。Decision Cycle 的阶段和时间点必须可回放。
_Avoid_: Trade lifecycle
