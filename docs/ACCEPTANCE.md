# Acceptance Criteria

## 1. 发布等级

- **P0**：不满足则不能进入试点。
- **P1**：可以带已知限制发布，但必须有后续计划。
- **P2**：优化项，不阻塞 MVP。

## 2. P0 产品验收

| ID | 验收项 | 方法 | 通过标准 |
|---|---|---|---|
| AC-000 | 无 Cloud Agent 启动 MVP | E2E | Tauri 可启动 Python Sidecar，并在本地完成任务创建、Trace 和结果持久化 |
| AC-001 | 创建研究任务 | E2E | 任务进入状态机并显示触发原因 |
| AC-002 | 收盘事件触发 | Integration | 数据完成后创建唯一任务 |
| AC-003 | 证据可追溯 | UI + Replay | 结论可定位到来源和快照 |
| AC-004 | Rules 阻断 | Unit + E2E | 任一硬规则失败即阻断建议 |
| AC-005 | 人工审批 | E2E | 审批产生用户、时间、版本和快照 |
| AC-006 | 无自动下单 | Security review | MVP 没有 LLM 到订单写入路径 |
| AC-007 | 失败恢复 | Chaos/Integration | Worker 失败后任务可重试或明确失败 |
| AC-008 | 过期数据标记 | UI | 过期证据不能显示为最新 |
| AC-009 | 多空辩论 | E2E | 双方观点、证据和未解决问题可见 |
| AC-010 | 风险优先级 | Integration | 持仓重大风险优先于普通扫描 |

## 3. P0 工程验收

- 所有 API 输入输出有 Schema；
- 所有 P0 数据字段有质量状态；
- 所有任务状态转移有日志；
- 关键审计记录追加写入；
- 密钥不写入日志；
- 数据库备份和恢复演练成功；
- 本地 SQLite/DuckDB 在应用重启后可恢复任务和审计；
- 日终任务达到目标成功率；
- 研究任务超过 SLA 后不会无限运行。

## 4. 规则测试矩阵

| 场景 | 预期 |
|---|---|
| 数据缺失 | `BLOCKED / DATA_UNAVAILABLE` |
| 数据过期 | `BLOCKED / STALE_DATA` |
| 市场门禁不满足 | `NO_ACTION` 或 `BLOCKED` |
| 股票属于禁止股票池 | `BLOCKED / UNIVERSE_REJECTED` |
| 超过最大仓位 | `BLOCKED / POSITION_LIMIT_EXCEEDED` |
| 风险等级 critical | `BLOCKED / RISK_REVIEW_FAILED` |
| 规则通过但证据不足 | `WATCH` 或 `NO_ACTION` |
| 规则通过且用户未审批 | `WAITING_APPROVAL` |
| 用户拒绝 | `REJECTED`，不得自动重提同一动作 |

## 5. 数据回放验收

给定：

- `data_snapshot_id`
- `rule_snapshot_id`
- `task_input`

系统应能重建：

- Tool 输入；
- Rules Engine 结果；
- Decision 状态；
- 审批前后的状态变化。

LLM 生成的自然语言可以略有差异，但结构化字段和硬门禁必须稳定。

## 6. 安全验收

- 外部新闻中包含恶意指令时，Agent 不改变系统规则；
- Tool 返回的文本不能注入订单能力；
- 非授权 Agent 调用受限 Tool 时被拒绝并记录；
- 用户只能查看自己账户和持仓；
- 删除研究任务不会删除审计记录；
- 前端无法直接访问数据库或长期密钥。
- Tauri UI 在 Cloud Agent 不可用时仍可完成本地 MVP 流程。

## 7. 试点退出条件

发生以下任一情况，暂停试点并回滚相关功能：

- 出现未审批的交易写入；
- 数据时间点错误导致研究使用未来数据；
- 规则结果无法回放；
- 审计记录缺失；
- 关键持仓数据泄露；
- Worker 失败后任务静默消失。
