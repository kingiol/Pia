# Local-first MVP Implementation Inputs

## 1. 当前结论

Local-first MVP 的实现边界已经确定：

```text
Tauri 2 Desktop
  -> React + TypeScript + Vite
  -> Python Local Agent Sidecar
  -> SQLite + DuckDB
  -> 日线数据 + 收盘后研究
  -> Rules + Evidence + Audit + Human Approval
```

以下内容不属于 MVP 发布门：

- Cloud Agent；
- Web/PWA；
- iOS SwiftUI；
- Android Kotlin + Jetpack Compose；
- 远程数据库和多设备同步；
- 盘中实时行情；
- 真实订单提交。

这意味着现在可以开始做 Monorepo、Tauri Sidecar、Local API、数据快照、Rules Engine 和第一条收盘复盘垂直切片。

## 2. 会直接阻塞实现的输入

这些信息如果没有确定，Agent 可以搭骨架，但无法可靠完成完整可验证 MVP。

| ID | 需要确定的输入 | 最小答案 | 为什么阻塞 |
|---|---|---|---|
| I-001 | 首发操作系统 | macOS 首发，Windows 必须实现 | 决定 Tauri 打包、Sidecar 分发和通知实现 |
| I-002 | 股票池范围 | 沪深主板、创业板、科创板、北交所和 ETF | 决定 Universe、交易日历和数据字段 |
| I-003 | 股票过滤规则 | ST、停牌、新股、退市整理、流动性下限 | 决定数据清洗和 Rules 结果 |
| I-004 | 主数据 Provider | `akshare` Python package，默认不要求 API key；凭据暂不需要提供 | 决定 Adapter、字段映射和回放输入 |
| I-005 | 备用数据 Provider | `tushare`；Token、积分/配额先使用占位符 | 决定故障切换和质量门禁 |
| I-006 | LLM Provider | `deepseek`，model=`deepseek-flash`；真实 API key 只允许由本地运行时或 CI 注入，当前仓库不携带凭据 | 决定 Agent Runtime、密钥和成本控制 |
| I-007 | 规则基线 | 先采用建议初始值作为 Ruleset `v1`，后续版本化修改 | 决定 Rules Engine 的正确答案 |
| I-008 | 持仓输入方式 | MVP 支持 CSV、Excel 和手工录入；只读接口后续接入 | 决定 Portfolio Adapter 和测试夹具 |
| I-009 | 数据与密钥策略 | 已确认允许外部 API 和远程 LLM；密钥仍只保存在本机 | 决定隐私边界和日志脱敏 |
| I-010 | Replay 基线 | 先用合成 fixture；真实数据阶段再选历史交易日 | 决定 replay fixtures 和验收基线 |

## 3. 可以先用默认值推进的输入

如果你暂时不想逐项决定，可以先采用以下默认值；实现时仍会把它们写入配置和 ADR，后续可版本化修改。

| 领域 | 默认值 |
|---|---|
| 用户模型 | 单用户、单本机、无登录 |
| 首发平台 | macOS 首发，Windows 同期实现并至少完成启动、任务、通知和打包验证 |
| 数据粒度 | 日线，收盘后运行 |
| 研究对象 | 沪深主板、创业板、科创板、北交所和 ETF；暂不包含可转债和衍生品 |
| 股票过滤 | 排除 ST、停牌、新股、退市整理和无完整历史数据标的 |
| Provider 路由 | `akshare` 主、`tushare` 备；主源失败时执行 Contract-compatible fallback |
| Provider 失败 | 两个 Provider 都不可用时阻断任务，不使用未经授权的替代源 |
| LLM | `deepseek` Adapter，model=`deepseek-flash`；默认调用 `POST /chat/completions`，保留 Provider Port |
| LLM 失败 | 任务保留结构化中间结果并进入 `RETRYABLE`，不伪造结论 |
| 持仓导入 | CSV、Excel、手工录入；只读券商接口作为后续 Adapter |
| 订单能力 | `submit_order` 不存在或显式 Disabled |
| 本地存储 | SQLite 保存事务、任务和审计；DuckDB 保存分析快照 |
| 备份 | 用户可导出本地备份包；开发阶段提供脚本备份 |
| 通知 | 系统通知 + 工作台内通知 |
| 测试数据 | 先用合成数据，后补脱敏历史快照；不把真实账户数据提交到仓库 |
| 运行模式 | `local` 固定；`cloud` 和 `auto` 只保留接口 |

## 4.1 凭据占位策略

当前仓库不保存 Tushare Token 或 DeepSeek API key；两者只允许在本地运行时或 CI 中注入。实现阶段使用以下配置入口：

```env
AKSHARE_API_KEY=
TUSHARE_TOKEN=__PROVIDE_LATER__
DEEPSEEK_API_KEY=__PROVIDE_LOCALLY__
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

占位符状态下：

- `akshare` 可以运行 Python package Adapter 和合成/本地快照测试；
- `tushare` Adapter 返回 `CAPABILITY_DISABLED`，不能伪装成真实备用数据；
- DeepSeek Adapter 必须读取本地真实 API key；缺失时返回 `CREDENTIALS_REQUIRED` 并阻止 Agent 任务，不切换到 Mock LLM；
- 本地 Rules、Event、Audit、Replay 和 UI 流程仍可完整运行；
- 真实 Provider 接入只需要替换环境变量，不修改 Domain、Agent Contract 或 UI。

## 5. 不应阻塞首个 MVP 的问题

以下问题需要设计，但可以在 Local-first MVP 之后处理：

- Cloud Agent 的任务租约和远程调度；
- PostgreSQL 迁移和多用户隔离；
- Web/PWA 的登录、部署和 SEO；
- iOS/Android 的 Push、后台刷新和原生图表；
- Local/Cloud 双向同步和冲突解决；
- 多 Provider 自动计费和配额中心；
- 实时行情和盘中事件；
- 半自动交易或真实订单提交；
- 向量数据库和复杂长期记忆。

## 6. 规则阈值的建议初始值

以下是用于实现和测试的第一版配置，作为 Ruleset `v1` 使用，不代表投资建议。后续可以创建 `v2`、`v3` 修改阈值；已经完成的任务继续引用原来的 Ruleset snapshot。

| Rule | 建议初始值 | 触发动作 |
|---|---:|---|
| 日线数据最大允许延迟 | 2 个交易日 | 超过则 `BLOCKED / STALE_DATA` |
| 新股观察期 | 上市不足 60 个交易日 | `BLOCKED / NEW_LISTING` |
| 单标的最大仓位 | 10% NAV | 超过则 `BLOCKED / POSITION_LIMIT_EXCEEDED` |
| 单行业最大仓位 | 30% NAV | 超过则 `BLOCKED / SECTOR_CONCENTRATION` |
| 单 ETF 最大仓位 | 25% NAV | 超过则 `BLOCKED / ETF_POSITION_LIMIT` |
| 组合回撤预警 | 8% | `WATCH / DRAWDOWN_WARNING` |
| 禁止新增买入回撤 | 12% | `BLOCKED / DRAWDOWN_LIMIT` |
| 组合严重风险 | 20% | `BLOCKED / RISK_CRITICAL` |
| 日均成交额下限 | 1000 万人民币 | `WATCH` 或 `BLOCKED`，按标的类型配置 |
| 市场风险门禁 | 规则配置，不由 LLM 判断 | `NO_ACTION` 或 `BLOCKED` |

其中市场风险门禁的具体计算方式先保留为可配置项。实现先支持 `breadth`、指数趋势和波动率三个输入，再把阈值写入 YAML。

## 7. Replay 日期是什么

Replay 日期是“把系统带回某个已经结束的交易日，用当时可见的数据重新运行任务”的基准。例如选择一个历史交易日，系统只能读取该日及之前的数据，不能使用之后发布的财报、新闻或价格。

它用于验证：

- 是否误用了未来数据；
- Provider 归一化是否稳定；
- Rules 结果是否可重复；
- 同一任务是否可以在没有网络时重放。

第一阶段不需要你立刻提供真实日期。先使用固定的合成 fixture 完成 Local Agent Spike；进入数据回放阶段时，再从你指定的历史交易日生成脱敏快照。

## 8. 实现阶段仍有的工程风险

这些不是产品决策阻塞，但会影响首个 Spike 的顺序：

1. Python Sidecar 的分发方式：系统 Python、嵌入式 Python，还是打包后的独立运行时。
2. Tauri 与 Sidecar 的通信方式：本地 HTTP/SSE 还是 Tauri IPC；建议先用本地 HTTP/SSE，便于复用 API Contract。
3. 外部 API 密钥的存储：开发阶段使用环境变量，试点阶段使用系统 Keychain/Credential Manager。
4. 任务恢复语义：应用退出时保留 `RUNNING` 任务并在重启后转为 `RETRYABLE`，不自动重复提交任何外部写操作。
5. 本地备份格式：SQLite、DuckDB、配置和审计快照需要一起导出，并包含版本和校验信息。
6. LLM 非确定性：回放只要求结构化字段、Rules 和状态稳定，自然语言允许存在差异。

## 9. 已确认的最小回复

以上三项已确认：

```text
DeepSeek model = deepseek-flash
DeepSeek base_url = https://api.deepseek.com
DeepSeek endpoint = POST /chat/completions
Ruleset = v1，接受第 5 节的初始值
Replay = 先合成 fixture，后选择真实交易日
```

如果你暂时没有偏好，也可以直接回复：

```text
按默认值推进，先做 macOS 首发、Windows 同期支持的 Local-first MVP；使用真实 `deepseek-flash` API；规则按 Ruleset `v1` 初始值。
```

之后实现 Agent 仍会在每个 P0 决策点留下配置、测试夹具和 ADR，方便你在看到可运行结果后调整。

## 10. 实现前的完成定义

当以下条件满足时，可以开始让 Agent 连续实现 MVP，而不需要反复重新定义产品：

- 第 2 节的 I-001 至 I-010 已填写，或明确采用第 3 节默认值；
- `contracts/`、`migrations/`、`rules/`、`agents/` 和 `tests/fixtures/` 已创建；
- Tauri Sidecar Spike 已证明启动、心跳、Trace、退出清理和重启恢复；
- 至少一条收盘复盘任务可以用固定数据完成 replay；
- `scripts/test.sh`、`scripts/replay.sh` 和 `scripts/e2e.sh` 有明确入口；
- `ACCEPTANCE.md` 的 AC-000 至 AC-010 都能映射到自动测试或人工检查。
