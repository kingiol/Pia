# MVP Readiness Assessment

> 本文档最初记录 2026-11-05 的实现前 readiness review。实现锁定包已经
> 落地；当前发布状态以 `docs/MVP_AUDIT.md` 和 `docs/ACCEPTANCE.md` 为准。

## 1. 结论

当前文档包已经达到：

```text
产品方向明确
架构方向明确
风险边界明确
验收意图明确
```

历史评估曾认为还没有达到：

```text
另一个 Agent 无需重新决策即可
从空仓库实现、启动、测试并验收完整 MVP
```

当前状态是：

> **Implementation-ready；Local-first MVP core implemented，release acceptance
> incomplete。**

当前仓库已经完成：

- Monorepo 和跨端目录；
- Tauri 2 Sidecar 和本地运行时；
- 收盘复盘与个股研究垂直切片；
- Provider、Rules、Agent contract 和数据质量层；
- Desktop/Web 工作台与移动端客户端。

完整 MVP 仍不能标记为发布完成，剩余问题是外部凭据、Windows runner、
真实设备和长期运行证据，而不是缺少实现入口。

## 2. 已经足够明确的部分

| 领域 | 状态 | 依据 |
|---|---|---|
| 产品定位 | Ready | `PRD.md` |
| MVP 不做自动下单 | Ready | `PRD.md`、`ADR.md` |
| Rules-First | Ready | `ADR.md`、`DATA_RULES_EVENTS.md` |
| Web/Tauri/iOS/Android 分层 | Ready | `ARCHITECTURE.md`、`MONOREPO.md` |
| Local-first Runtime 方向 | Ready | `ARCHITECTURE.md`、`ADR.md` |
| Adapter 分层原则 | Ready | `ADAPTERS.md`、`ADR.md` |
| Research Workspace 信息架构 | Ready | `RESEARCH_WORKSPACE.md` |
| 里程碑和周计划 | Ready | `MILESTONES.md`、`EXECUTION_PLAN.md` |
| 风险和发布门 | Ready | `RISK_REGISTER.md`、`ACCEPTANCE.md` |

## 3. 阻塞完整 MVP 的 P0 缺口

### P0-1：MVP 发布组合已解决

当前已锁定：

```text
MVP：Tauri Desktop + Local Python Agent + SQLite/DuckDB
后续：Cloud Agent + Web/PWA + iOS/Android
```

因此，首发平台和 Agent 执行位置不再是阻塞决策。Cloud Agent 只需保留契约和扩展边界，不进入 MVP 发布门。

### P0-2：Provider 主备已确定，授权和字段仍待确认

Provider 组合已经锁定为：

- 主 Provider：`akshare`；
- 备用 Provider：`tushare`。

仍需确认：

- 具体接口和字段；
- 授权范围；
- API 配额；
- 失败和切换策略；
- 费用预算；
- 研究用途和商业用途限制。

这些信息缺失时，代码可以运行 fixture 和 AKShare 主 Provider，但无法完成
Tushare 授权范围、配额和商业用途的真实发布验收。

### P0-3：API Contract 已落地

OpenAPI 和 JSON Schema 已经存在并由生成检查验证：

```text
contracts/openapi.yaml
contracts/events/*.json
contracts/tasks/*.json
contracts/decisions/*.json
```

Desktop/Web 使用生成的 TypeScript client；iOS/Android 按同一 `/api` 契约实现。

### P0-4：数据库 Schema 已落地

SQLite/PostgreSQL migration、唯一约束、审计不可变触发器和 JSON Schema
已经落地。当前仍需持续验证不同数据库版本的运行兼容性。

- SQL migration；
- 主键和外键；
- 唯一约束；
- 索引；
- 枚举；
- JSON 字段 Schema；
- 审计记录不可变约束；
- SQLite/PostgreSQL 差异策略。

数据回放、幂等和审计要求已有单测与 E2E 证据。

### P0-5：规则基线已锁定并实现

`rules/baseline.yaml`、`rules/rule_cases.yaml` 和规则测试矩阵已经落地。

后续修改必须创建新的 Ruleset version。旧任务固定引用原来的 `rule_snapshot_id`，不能被新规则改写。

### P0-6：Agent Contract 已落地

需要为每个 P0 Agent 定义：

- 输入 Schema；
- 输出 Schema；
- 可调用 Tools；
- 禁止调用的 Tools；
- Prompt 版本；
- 失败和重试；
- 超时；
- 证据最低要求；
- 何时返回 `NO_ACTION`；
- 模型和成本上限。

`agents/*.yaml`、`agent_contracts.py` 和结构化运行时已经提供 Agent State、
工具权限和回放测试。

### P0-7：确定性测试夹具已落地

验收要求的 fixtures 已落地：

```text
tests/fixtures/
  market_snapshot/
  portfolio_snapshot/
  news/
  provider_responses/
  rule_cases/
  replay_tasks/
```

固定输入现在可以证明：

- 数据归一化稳定；
- Rules 结果稳定；
- Event 去重稳定；
- 任务回放稳定；
- Agent 结构化输出符合契约。

### P0-8：开发和验证命令已落地

`config/`、`scripts/`、CI 和各端 README 已明确：

- Node/Python/Rust 版本；
- 包管理器；
- 本地数据库启动方式；
- 环境变量模板；
- Provider Key 配置；
- Migration 命令；
- 单元测试命令；
- Contract Test 命令；
- Replay 命令；
- E2E 命令；
- Tauri 启动和打包命令；
- CI 检查命令。

## 4. 非阻塞但必须排期的缺口

- Cloud 扩展阶段的任务租约和结果同步；
- Local/Cloud 的 Ruleset 和 Audit 权威关系；
- iOS/Android Push 和后台刷新；
- Provider 账单和配额监控；
- LLM 成本上限和模型降级；
- 真实新闻授权和内容存储策略；
- 多用户认证和账户隔离；
- Tauri 安装包自动更新；
- 生产环境备份恢复演练。

## 5. MVP Implementation Lock Pack

Implementation Lock Pack 已补齐，清单中的文件均已存在。剩余工作属于
外部服务、平台和长期运行验收：

```text
contracts/
  openapi.yaml
  events/
  schemas/

migrations/
  001_initial.sql

config/
  example.env
  providers.example.yaml

rules/
  baseline.yaml
  rule_cases.yaml

agents/
  market.yaml
  research.yaml
  technical.yaml
  portfolio.yaml
  risk.yaml

tests/fixtures/
  market/
  portfolio/
  providers/
  replay/

scripts/
  dev.sh
  test.sh
  replay.sh
  e2e.sh
```

## 6. 最小锁定决策

推荐直接锁定：

| 决策 | MVP 推荐 |
|---|---|
| 发布组合 | Tauri Desktop + Local Python Agent |
| 主行情 Provider | `akshare`，默认无需 API key；先用 package Adapter 和 fixtures |
| 备用行情 Provider | `tushare`，Token 先使用占位符，凭据补齐后启用 |
| 数据粒度 | 日线 + 收盘后 |
| Agent 执行 | `local` 默认，`cloud` 后续扩展 |
| 数据库 | SQLite + DuckDB；PostgreSQL 后续扩展 |
| LLM | `deepseek` Adapter，model=`deepseek-flash`，真实 API key 由本地运行时读取 |
| Broker | CSV、Excel、手工录入；只读真实账户接口后续接入 |
| 移动端 | iOS SwiftUI、Android Jetpack Compose，非 MVP 阻塞 |
| 订单 | 禁止真实提交 |

## 7. 可执行完成定义

当以下条件完成后，才可以说“文档足以实现完整可验证 MVP”：

- `contracts/` 存在可生成客户端的 Schema；
- `migrations/` 可以初始化数据库；
- Provider 主备、DeepSeek model 和占位凭据策略已确定；真实凭据可以后补；
- `rules/baseline.yaml` 和规则测试矩阵已确定；
- 每个 P0 Agent 有输入、输出、Tool 权限和 Prompt 版本；
- 固定 fixtures 可以完成收盘复盘和个股研究回放；
- `scripts/test.sh` 能一次运行 Unit、Integration、Contract、Replay；
- `scripts/e2e.sh` 能验证创建任务、查看 Trace、证据、阻断和审批；
- Tauri Sidecar 启停和失败恢复有自动化验证；
- `ACCEPTANCE.md` 中所有 P0 项都有对应测试或人工检查；
- 发布组合和未完成项得到 Product Owner 签字确认。

## 8. 最终判断

文档和实现已经足以支持持续开发、自动验证和跨端集成。Local-first MVP
核心已完成；完整发布仍受真实 DeepSeek/Tushare 凭据、Windows runner、
真实通知投递、真机后台运行和长期外部服务 SLA 证据约束。详细逐项状态以
`docs/MVP_AUDIT.md` 为准。
