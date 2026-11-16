# Data, Rules Engine, Event Engine and Tools

## 1. 数据分层

```text
Raw Source
  -> Raw Landing
  -> Normalized Tables
  -> Quality Layer
  -> Point-in-Time Snapshot
  -> Agent Tools
  -> Research Evidence
```

### 推荐早期数据范围

- 交易日历；
- 指数日线；
- 股票日线 OHLCV；
- 市场涨跌家数、停牌和涨跌停统计；
- 行业和概念分类；
- 基础财务指标；
- 公告和新闻摘要；
- 用户持仓和现金。

MVP 股票池覆盖沪深主板、创业板、科创板、北交所和 ETF。所有可进入候选扫描的 active 标的必须带有 `asset_type`、`board`、`exchange`、`listed_at` 和交易状态字段，Rules Engine 按资产类型分别处理股票和 ETF 的仓位、流动性及数据有效期。停牌或退市历史标的仍保留在 raw/normalized 层供审计；若上游没有历史上市日期，必须记录为 inactive metadata 缺失，不能伪造，也不能进入候选扫描。

默认排除 ST、停牌、新股观察期内、退市整理和历史数据不完整的标的。排除结果必须保存为结构化 Rule Result，不能只在 UI 中隐藏。

MVP 以日线和收盘后任务为主。实时行情、分钟级异动和盘中通知必须在确认授权和数据质量后单独立项。

Provider Adapter、归一化、能力声明和故障切换规范见 [ADAPTERS.md](ADAPTERS.md)。

## 2. 数据契约

所有可被 Agent 使用的数据都应带以下元数据：

```json
{
  "symbol": "600000.SH",
  "metric": "close",
  "value": 10.24,
  "source": "provider_name",
  "observed_at": "2026-11-05T16:10:00+08:00",
  "as_of": "2026-11-05",
  "expires_at": "2026-11-06T09:30:00+08:00",
  "quality": "verified",
  "snapshot_id": "snap_20261105_close_001"
}
```

质量枚举：

- `verified`：通过完整性、时效性和来源校验；
- `partial`：部分字段缺失，但可用于受限研究；
- `stale`：超过有效期，只可用于历史上下文；
- `unavailable`：不可用于决策。

## 3. 数据库 Schema

以下是 MVP 最小实体集合，实际实现以 SQLite 为主；Cloud 扩展时再适配 PostgreSQL 方言。

### 用户和配置

```text
users
  id, created_at

investor_profiles
  id, user_id, version, risk_level, goals_json,
  allowed_markets_json, created_at, active

rulesets
  id, user_id, version, name, definition_json,
  created_at, active

rule_snapshots
  id, ruleset_id, version, definition_hash, definition_json,
  created_at

watchlists
  id, user_id, name, symbols_json, created_at
```

### 市场和持仓

```text
instruments
  symbol, exchange, name, board, is_st, listed_at, active

market_snapshots
  id, as_of, observed_at, source, quality, payload_uri

market_metrics
  snapshot_id, metric_name, value, scope, metadata_json

portfolio_snapshots
  id, user_id, as_of, cash, total_value, source, payload_json

positions
  snapshot_id, symbol, quantity, avg_cost, market_value,
  weight, unrealized_pnl, metadata_json
```

### 任务和审计

```text
research_tasks
  id, user_id, trigger_type, target_json, status,
  created_at, started_at, finished_at, parent_task_id,
  data_snapshot_id, rule_snapshot_id

agent_runs
  id, task_id, agent_name, status, input_json,
  output_json, error_json, started_at, finished_at,
  model, token_usage

tool_calls
  id, task_id, agent_run_id, tool_name, input_json,
  output_json, status, latency_ms, created_at

evidence
  id, task_id, source_type, source_uri, title,
  observed_at, as_of, expires_at, quality,
  excerpt, content_hash, snapshot_id

decisions
  id, task_id, status, confidence, rationale_json,
  invalidation_json, risk_level, created_at

approvals
  id, task_id, user_id, action, created_at,
  rule_snapshot_id, data_snapshot_id, notes
```

### 事件

```text
events
  id, event_type, dedupe_key, priority, payload_json,
  occurred_at, expires_at, status

event_deliveries
  id, event_id, task_id, attempt, status,
  next_retry_at, last_error
```

## 4. Rules Engine

### 4.1 规则层级

1. **Data Gate**：数据存在、时效和质量满足要求。
2. **Market Gate**：市场环境满足用户配置。
3. **Universe Gate**：股票属于允许股票池，排除 ST、停牌或用户禁止范围。
4. **Portfolio Gate**：仓位、集中度、现金和风险暴露满足要求。
5. **Instrument Gate**：个股流动性、波动、公告和技术条件满足要求。
6. **Approval Gate**：用户已经明确批准该建议。

### 4.2 规则伪代码

```python
def evaluate_buy_gates(context: DecisionContext) -> GateResult:
    if not context.data.is_usable:
        return block("DATA_UNAVAILABLE")
    if not context.market.matches(context.rules.market_conditions):
        return block("MARKET_CONDITION_FAILED")
    if not context.instrument.is_allowed:
        return block("UNIVERSE_REJECTED")
    if context.portfolio.projected_weight > context.rules.max_position_weight:
        return block("POSITION_LIMIT_EXCEEDED")
    if context.risk.level == "critical":
        return block("RISK_REVIEW_FAILED")
    return pass_with_warnings(context.warnings)
```

### 4.3 规则结果

```json
{
  "decision": "BLOCKED",
  "reasons": [
    {
      "rule_id": "portfolio.max_position_weight",
      "actual": 0.18,
      "expected": "<= 0.10",
      "severity": "error"
    }
  ],
  "warnings": [],
  "rule_snapshot_id": "rules_v12"
}
```

LLM 可以解释规则结果，但不能修改规则结果。

## 5. Event Engine

### 5.1 事件类型

| 事件 | 触发 | 默认动作 |
|---|---|---|
| `MarketClose` | 交易日收盘数据完成 | 市场复盘 |
| `MarketBreadthChanged` | 市场广度跨过阈值 | 市场与板块研究 |
| `PriceVolumeAnomaly` | 量价异常 | 个股研究 |
| `FilingPublished` | 新公告或财报 | 事件影响分析 |
| `PortfolioRiskChanged` | 回撤、集中度或规则变化 | 风险复核 |
| `DataQualityDegraded` | 数据质量下降 | 阻断相关任务并告警 |

### 5.2 事件处理要求

- **去重**：使用 `dedupe_key`，避免同一事件重复启动工作流。
- **冷却**：同类事件在窗口内只保留最高优先级。
- **优先级**：持仓重大风险 > 数据质量 > 公告 > 普通扫描。
- **幂等**：重复投递不能产生重复审批或重复决策。
- **过期**：事件超过有效期后不再启动新的买入研究。
- **重试**：外部依赖失败采用指数退避，规则阻断不自动重试。

### 5.3 事件到任务

```text
Event
  -> Validate payload
  -> Dedupe / Cooldown
  -> Check data gate
  -> Create research_task
  -> Run Chief Agent
  -> Run specialist agents
  -> Rules / Risk Review
  -> Notify / Wait approval
```

## 6. Tools

### Market Tools

- `get_market_snapshot`
- `get_market_breadth`
- `get_index_series`
- `get_sector_strength`
- `get_price_volume_features`

### Research Tools

- `get_financial_statements`
- `get_company_profile`
- `search_filings`
- `search_news`
- `get_earnings_summary`
- `compare_instruments`

### Portfolio Tools

- `get_portfolio_snapshot`
- `calculate_exposure`
- `simulate_position_change`
- `check_rule_violations`

### System Tools

- `create_research_task`
- `get_task_trace`
- `save_evidence`
- `request_human_approval`
- `schedule_follow_up`

### 权限矩阵

| Tool | Market | Research | Portfolio | Risk | Decision |
|---|---:|---:|---:|---:|---:|
| `get_market_snapshot` | R | R | R | R | R |
| `search_news` | - | R | R | R | R |
| `get_portfolio_snapshot` | - | - | R | R | R |
| `check_rule_violations` | - | - | R | R | R |
| `request_human_approval` | - | - | - | R | R |
| `submit_order` | - | - | - | - | Disabled in MVP |

## 7. Memory

### Profile Memory

保存风险偏好、投资目标、交易规则和授权边界。必须版本化，不能由 Agent 自行修改。

### Episodic Memory

保存研究任务、结论、审批、复盘和规则违背。

### Semantic Memory

保存行业、公司、指标和用户定义的研究标签。MVP 可以使用结构化表和全文检索，暂不强制向量数据库。

### Memory 写入规则

- 每条 Memory 都要带来源和时间点；
- 研究结论和用户确认的事实分开存储；
- 低置信度内容不得覆盖高置信度 Profile；
- 用户规则只能通过显式配置流程修改。

## 8. 可观测性

至少记录：

- 任务成功率、失败率、重试率；
- 各 Agent 延迟和 token 成本；
- Tool 调用失败率；
- 数据新鲜度和字段完整率；
- `BLOCKED`、`NO_ACTION` 和人工拒绝比例；
- 规则触发频率和异常变化。
