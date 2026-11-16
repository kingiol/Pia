# MVP Implementation Audit

审计日期：2026-11-08

## 最终复核结果（2026-11-08）

本次最终复核加载了 `config/example.env`，使用其中的 DeepSeek 凭据，
按用户要求没有调用 Tushare：

- `./scripts/test.sh`：**197 tests passed**；
- `./scripts/python.sh scripts/generate_ts_client.py --check`：通过；
- `git diff --check`：通过；
- `PIA_ACCEPTANCE_MODE=release PIA_ACCEPTANCE_AS_OF=2026-11-06
  ./scripts/acceptance.sh`：通过，覆盖 Local/Cloud/临时 PostgreSQL、
  scheduler/dedupe、备份恢复、重启/混沌、SLA、Replay、Desktop UI、
  Web/iOS/Android、Tauri、macOS packaged lifecycle、sidecar health、
  macOS native notification、真实 DeepSeek structured/tool/streaming 和
  `StockResearch` runtime；
- 独立 `provider-freshness-e2e.sh` 的 AKShare `2026-11-06` 检查：通过，
  `quality=verified`、`market_snapshot_quality=verified`、universe `7,593`、
  字段完整度 `1.0`、`failures=[]`，并返回 `daily_bars=1`、
  `fundamentals=1`、`research_sources=12`；
- `release-preflight.sh`：DeepSeek credentials 已通过；MVP 仍阻塞
  `windows_msi`、`windows_host` 和按当前范围跳过的 `tushare_credentials`；
  完整 M0-M7 另缺真实 Web Push/APNs/FCM credentials。
- `get_index_series` 已补齐为真正的日期范围序列工具；fixture、AKShare
  和 Tushare provider 均声明 `index_series` capability，runtime 支持
  `start_date`、`end_date` 和 `symbols`，并保留单日 `indices` 兼容字段。
- iOS 和 Android 任务详情现在会真实订阅认证 SSE；收到任务事件后刷新
  trace、decision、evidence 和状态。iOS 已有 SSE 解析回归，Android
  debug assemble 已通过。
- 本轮完整 release acceptance 在上述移动端改动后再次通过，包含
  `197` 个 Python tests、Android debug assemble、iOS tests/build 和
  authenticated mobile SSE client。

这次结果覆盖了本机可验证的 MVP 功能闭环。Windows、Tushare 和外部 Push
仍属于环境证据边界，不能从本机测试推断为已发布验证。

## 最新复核结果（2026-11-08）

本次复核在加载 `config/example.env` 后完成，未调用 Tushare：

- `./scripts/test.sh`：**197 tests passed**；
- `./scripts/acceptance.sh`（release mode）：通过，覆盖 Local/Cloud/临时
  PostgreSQL、scheduler/dedupe、备份恢复、重启/混沌、SLA、Replay、Desktop
  UI、Web/iOS/Android、Tauri、macOS packaged lifecycle、sidecar health、
  macOS native notification、真实 DeepSeek structured/tool/streaming 和
  `StockResearch` runtime；
- AKShare freshness `2026-11-06`：`quality=verified`、
  `market_snapshot_quality=verified`、universe `7,593`、字段完整度 `1.0`、
  `failures=[]`；
- 新增跨 runtime 暂停/恢复回归：API runtime 写入共享数据库控制字段后，
  独立 worker runtime 会暂停并在恢复后继续；取消仍通过数据库终态生效；
- 修复 `scripts/freshness-e2e.sh` 中过期的未来日期夹具，避免当前日期变化
  使确定性 freshness 验收误报。

`./scripts/release-preflight.sh` 仍返回 `mvp_release_ready=false`，当前
阻塞为 `windows_msi`、`windows_host` 和按用户要求跳过的
`tushare_credentials`。完整 M0-M7 发布门还缺真实
`external_push_credentials`。这些是 Windows、Tushare 和外部推送环境证据，
不代表本机 Local-first MVP 核心验收失败。

审计依据：

- `docs/PRD.md` 第 6、7、8、10 节；
- `docs/ACCEPTANCE.md` 的 AC-000 至 AC-010 和 P0 工程验收；
- `docs/MILESTONES.md` M1-M7 的完成定义；
- 当前代码、测试、构建产物、运行脚本和本次 live smoke。

## MVP 需求矩阵（2026-11-08）

| MVP 能力 | 代码/证据 | 当前状态 |
|---|---|---|
| Profile、Ruleset、Portfolio 配置与版本快照 | `pia_runtime/runtime.py`、SQLite/PostgreSQL repository、Desktop workspace；`test_rules.py`、`test_runtime.py` | **Implemented + verified** |
| 沪深主板、创业板、科创板、北交所和 ETF 股票池 | AKShare universe adapter、metadata normalization、coverage quality gate；AKShare freshness `2026-11-06` | **Implemented + live verified** |
| 日线、财务、交易日历、指数、行业、公告/新闻数据 | `data_worker.py`、AKShare provider、raw/normalized/snapshot persistence；freshness `quality=verified` | **Implemented + live verified** |
| 市场广度、指数、行业、个股基础指标与候选排序 | market tools、candidate scan、snapshot reuse；scheduler/E2E/replay tests | **Implemented + verified** |
| Market/Sector/Stock/Technical/Portfolio/Risk Agent | agent contracts、runtime dispatch、permission matrix；`test_contracts.py`、`test_security.py` | **Implemented + verified** |
| Agent Trace、Evidence、Bull/Bear Debate、Risk Review | trace/evidence stores、workspace panels、replay and UI smoke | **Implemented + verified** |
| Rules Engine 数据、市场、股票池、仓位和风险门禁 | `rules.py`、rule case matrix、approval guards；`test_rules.py`、`test_runtime.py` | **Implemented + verified** |
| Event Engine 收盘、异常、公告、持仓风险事件 | event derivation、dedupe/cooldown/priority/retry；scheduler and event tests | **Implemented + verified** |
| `BUY_CANDIDATE` / `SELL_CANDIDATE` / `HOLD` / `WATCH` / `NO_ACTION` | task/decision state machine、approval API and UI | **Implemented + verified** |
| 研究任务、证据、结论、审批和追加审计持久化 | SQLite/DuckDB schema、immutable audit、approval/replay APIs | **Implemented + verified** |
| Tauri Desktop 启动 Python Sidecar | Tauri externalBin、packaged macOS lifecycle、sidecar health smoke | **Implemented + macOS verified** |
| SQLite/DuckDB、任务回放、重启/崩溃恢复 | backup/restore、recovery/chaos、replay and SLA E2E | **Implemented + verified** |
| 本地通知、失败恢复、暂停/恢复/取消 | native notification smoke、retry/takeover、cross-process pause/resume regression | **Implemented + macOS verified** |
| 无自动下单路径 | paper/read-only broker capabilities、security tests、approval gate | **Implemented + verified** |
| API schema、质量状态、日志、密钥脱敏 | OpenAPI/generated client、quality fields、redaction tests and metrics | **Implemented + verified** |
| macOS 首发桌面打包 | `.app`、`.dmg`、sidecar、lifecycle and notification evidence | **Implemented + verified** |
| Windows 同期启动、MSI、sidecar、通知 | PowerShell scripts and CI workflow exist; no Windows runner evidence on this host | **Code path implemented; release evidence missing** |
| Tushare fallback/provenance | adapter and contract tests exist; no real token supplied | **Intentionally unverified per user scope** |

因此，MVP 的**功能实现和本机可执行验收**已经闭合；严格发布状态仍不能标记为 ready，原因只剩平台/凭据证据：Windows MSI/host，以及按当前范围跳过的 Tushare。Web Push/APNs/FCM 外部网关属于完整 M0-M7 发布门，不属于原始 Local-first MVP 的本地闭环。

## 本次复核摘要（2026-11-08）

当前判断不是“所有文档功能都已完成发布验收”，而是：

> **Local-first MVP 核心闭环已实现并通过本地验收；完整 MVP 发布门仍未关闭。**

### 真实凭据复核（2026-11-08）

用户已在 `config/example.env` 配置 `DEEPSEEK_API_KEY`，并明确暂不验证
Tushare。本次使用该配置执行：

- `PIA_ACCEPTANCE_MODE=release PIA_ACCEPTANCE_AS_OF=2026-11-06
  PIA_FRESHNESS_DATES=2026-11-06 ./scripts/acceptance.sh`：完整通过；
- 190 个 Python tests、生成客户端检查、Desktop/Web 构建和跨端验收全部通过；
- AKShare freshness：`quality=verified`、
  `market_snapshot_quality=verified`、universe `7,593`、字段完整度 `1.0`、
  `failures=[]`；
- DeepSeek structured output、tool calling、streaming 和 live
  `StockResearch` runtime task 全部通过；
- Tushare live 检查按要求跳过，外部 push gateway 也因未配置而明确跳过。

本轮还修复了 release acceptance 在加载 `example.env` 时污染本地 fixture
验收的问题：cloud/replay/SLA/recovery/chaos 阶段现在固定使用 fixture 和
临时数据库；recovery 脚本会创建传入的临时目录。`release-preflight.sh` 当前
只阻塞 `windows_msi`、`windows_host` 和 `tushare_credentials`；完整里程碑
另外还需要真实 external push credentials。

### 最终现场复核（2026-11-08）

使用 `config/example.env` 中已配置的 DeepSeek 凭据重新执行 release acceptance：

- release acceptance 通过，包含 190 个 Python tests、Local/Cloud/临时
  PostgreSQL、恢复/混沌、SLA、Replay、Desktop/Web、iOS/Android、Tauri、
  macOS lifecycle、sidecar health 和 native notification；
- AKShare `2026-11-06` freshness 通过：`quality=verified`、
  `market_snapshot_quality=verified`、universe `7,593`、字段完整度 `1.0`、
  `failures=[]`；
- DeepSeek structured output、Tool Calling、streaming 和 live
  `StockResearch` runtime task 通过；
- Tushare 按用户要求跳过，没有调用真实 `TUSHARE_TOKEN`；
- release-preflight 的 `deepseek_credentials` 已通过，MVP blockers 仅剩
  `windows_msi`、`windows_host`、`tushare_credentials`；完整里程碑另有
  `external_push_credentials`。

### 最新现场复核（2026-11-08）

- `./scripts/acceptance.sh`：通过，覆盖 Local/Cloud/临时 PostgreSQL、
  scheduler/dedupe、备份恢复、重启/混沌、SLA、Replay、Desktop UI、
  Web/iOS/Android、Tauri compile、macOS packaged lifecycle、sidecar health
  和 macOS native notification。
- `./scripts/test.sh`：**190 tests passed**（串行运行）。
- `./scripts/python.sh scripts/generate_ts_client.py --check`：通过。
- `git diff --check`：通过。
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`：通过；`quality=verified`、
  `market_snapshot_quality=verified`、universe `7,593`、字段完整率 `1.0`、
  `failures=[]`。
- 研究 Provider fallback 已增加质量感知：有备用 Provider 时，
  `partial/unavailable/stale` 结果会触发回退；没有备用时保留降级结果并
  明确审计，不伪造为 `verified`。
- SSE 终态已补齐 `DONE` 和 `EXPIRED`，避免已结束任务继续等待 idle timeout。
- 任务级 `expires_at` 已接入运行时状态机：过期任务进入 `EXPIRED`，
  写入 `TASK_EXPIRED` 错误、终态事件和不可变审计记录；对应回归测试已通过。
- 任务状态契约同步生成到 TypeScript client，`models.ts` 生成检查通过。
- `PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh`：终态成功率 `1.0`、
  P95 `0.065s`；该结果是本地 fixture soak，不替代真实外部服务长期证据。
- `PIA_ACCEPTANCE_MODE=release ./scripts/acceptance.sh` 现在会在运行本地
  矩阵前校验必需的 DeepSeek 凭据和 `akshare` Provider；缺失时快速失败并
  明确指出配置项。

当前严格发布门仍由 `./scripts/release-preflight.sh` 判定为
`mvp_release_ready=false`，具体阻塞为：

1. `windows_msi`：当前工作区没有真实 Windows MSI 制品；
2. `windows_host`：本次运行主机是 Darwin，未产生 Windows sidecar/启动/
   health/通知运行证据；
3. `tushare_credentials`：没有真实 `TUSHARE_TOKEN`，未执行真实主备回退和
   跨 Provider provenance。

完整里程碑还缺 `external_push_credentials`，即真实 Web Push/APNs/FCM
gateway 和设备 token 的投递证据；这不是当前 Local-first 核心代码验收的
失败项，但阻塞完整跨端发布。

### 补丁后复核（2026-11-08）

- 使用 `config/example.env` 中的 DeepSeek 配置重新执行
  `PIA_ACCEPTANCE_MODE=release PIA_ACCEPTANCE_AS_OF=2026-11-06
  PIA_FRESHNESS_DATES=2026-11-06 ./scripts/acceptance.sh`：通过。
- release acceptance 覆盖 191 个 Python tests、Local/Cloud/临时
  PostgreSQL、恢复/混沌、SLA、Replay、Desktop/Web、iOS/Android、Tauri、
  macOS lifecycle、sidecar health 和 macOS native notification。
- AKShare freshness 对 `2026-11-06` 返回 `quality=verified`、
  `market_snapshot_quality=verified`、universe `7,593`、字段完整率 `1.0`
  和 `failures=[]`；DeepSeek structured output、Tool Calling、streaming
  和 live `StockResearch` 也通过。
- Tushare live 检查和 external push 因用户明确暂不提供对应凭据而跳过。
- Cloud lease heartbeat 现在和 release 一样校验任务所属用户；新增跨用户
  heartbeat 回归测试，避免其他用户延长别人的 lease。
- 补丁后的完整 Python 回归为 **192 tests passed**，更新后的 Cloud E2E
  也验证了跨用户 heartbeat 在 HTTP 层返回 `404`。

当前结论仍是：MVP 核心功能已经实现并通过本机可执行验收，但严格发布门仍
未关闭，阻塞项为 `windows_msi`、`windows_host` 和按当前范围跳过的
`tushare_credentials`。

### 当前工作区现场复核（2026-11-08）

本次重新执行：

- `./scripts/test.sh`：**189 tests passed**；
- `./scripts/acceptance.sh`：**local mode 通过**，包含 Local/Cloud/临时
  PostgreSQL、恢复/混沌、SLA、Replay、Desktop UI、iOS/Android、Tauri
  compile、macOS packaged lifecycle、sidecar health 和 macOS native
  notification；
- `./scripts/release-preflight.sh`：`mvp_release_ready=false`，当前阻塞项仍为
  `windows_msi`、`windows_host`、`deepseek_credentials` 和
  `tushare_credentials`；完整里程碑还缺 `external_push_credentials`。

本轮还将 DataWorker 的 market snapshot、交易日历、universe、daily bars、
fundamentals、news 和 filings 调用接入 `GET /api/metrics` 的
`observability.provider_calls`，并保留主备 Provider 各自的耗时和错误记录。

本次重新执行
`PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
./scripts/provider-freshness-e2e.sh` 已完成并通过：
`quality=verified`、`market_snapshot_quality=verified`、universe `7,593`、
字段完整率 `1.0`，无 failures。该结果证明最近开市日的真实 AKShare
质量门通过；它仍不替代长期外部 Provider 运行证据。

本次现场复核重新执行了以下命令：

- `./scripts/test.sh`：**181 tests passed**；
- `./scripts/acceptance.sh`：**local mode 通过**，包含 freshness、
  scheduler/dedupe、Local/Cloud/临时 PostgreSQL、备份恢复、重启/混沌恢复、
  SLA、Replay、Desktop UI、Web/iOS/Android、Tauri compile、macOS packaged
  lifecycle、sidecar health 和 macOS native notification；
- `./scripts/python.sh scripts/generate_ts_client.py --check`：
  **GENERATED CLIENT CHECK PASS**；
- `git diff --check`：通过；
- `./scripts/release-preflight.sh`：`mvp_release_ready=false`，阻塞项为
  `windows_msi`、`windows_host`、`deepseek_credentials` 和
  `tushare_credentials`；完整里程碑还缺 `external_push_credentials`。

本轮继续修复了一个历史数据边界：实时 `StockResearch` 现在把任务的
`as_of` 传递给 fundamentals/news Provider，Tushare 新闻即使缺少
`ts_code` 也会按发布日期过滤。相关回归测试已通过，避免研究运行时绕过
`DataWorker` 已有的 point-in-time 质量门。

本轮还补齐了 live company profile 资料链路：AKShare 使用 CNINFO 公司概况
并回退到 Eastmoney 个股信息，Tushare 使用 `stock_basic`；StockResearch
现在保存 profile 的 provider provenance。现场查询 `600000.SH` 返回
`浦发银行`、`货币金融服务`、上市日期 `1999-11-10`，质量为 `verified`。
profile endpoint 不可用时会显式记录 `COMPANY_PROFILE_UNAVAILABLE` 并降级为
`partial`，不会伪造真实行业资料。

当前工作树复核补充结果：

- `./scripts/test.sh`：**177 tests passed**；
- `./scripts/acceptance.sh`：local mode 通过，覆盖 Local/Cloud/
  temporary PostgreSQL、恢复/混沌、SLA、Replay、Desktop UI、Web/iOS/
  Android、Tauri compile、macOS packaged lifecycle、sidecar health 和
  macOS native notification；
- iOS/Android failure-state task takeover controls now call the authenticated
  takeover endpoint and are covered by the cross-client contract test；
- `git diff --check`：通过；
- release acceptance 和 provider freshness 已统一支持环境变量与 native
  credential manager；缺少真实凭据时仍 fail closed；
- `./scripts/release-preflight.sh`：`mvp_release_ready=false`，阻塞项仍为
  `windows_msi`、`windows_host`、`deepseek_credentials` 和
  `tushare_credentials`；完整里程碑的真实外部推送凭据仍未完成。

本次重新执行的证据：

- `./scripts/test.sh`：**172 tests passed**；
- `./scripts/acceptance.sh`：local mode 通过，包含 freshness、scheduler/dedupe、
  Local/Cloud/PostgreSQL E2E、备份恢复、重启/混沌恢复、SLA、Replay、
  Desktop UI、Web/iOS/Android 构建、Tauri compile、macOS packaged lifecycle
  、sidecar health 和 macOS native notification smoke；
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`：现场复核通过，
  `market_snapshot_quality=verified`、universe `7,593`、字段完整率 `1.0`，
  无 failures；
- `./scripts/desktop-ui-smoke.sh`：通过任务创建、状态分组、任务深链接、
  Raw data、Replay、Watchlist、Rules gate 和 390×844 响应式检查；
- `./scripts/python.sh scripts/generate_ts_client.py --check` 和
  `git diff --check`：通过；
- 本次复核修复了 Evidence provenance 的数据库持久化缺口：`provider_id`
  现在在 SQLite/PostgreSQL migration、写入和任务详情读取链路中保持一致；
  live provider 回归测试已通过；
- Local/Cloud/temporary PostgreSQL E2E now assert the runtime system metrics
  contract, including queue depth, active task age, storage bytes and the
  SQLite/PostgreSQL backend;
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`：真实 Provider freshness 通过，
  `market_snapshot_quality=verified`、universe `7,593`、字段完整率 `1.0`，
  无 failures；
- `./scripts/native-notification-smoke.sh`：`DELIVERED`；
- `./scripts/python.sh -m pia_runtime.cli credentials status
  DEEPSEEK_API_KEY`：只返回配置状态，不回显凭据；
- `./scripts/release-preflight.sh`：`mvp_release_ready=false`，当前阻塞项为
  `windows_msi`、`windows_host`、`deepseek_credentials`、
  `tushare_credentials`；完整里程碑还需要真实
  `external_push_credentials`。
- Windows build/launch/notification 的可执行验收路径已接入
  `.github/workflows/release-gates.yml` 的 `windows-release` job；当前 Darwin
  主机没有该 job 的实际 runner 结果，因此不能把它标记为已验收。
- 新增 point-in-time 质量门：标记为 `latest` 的 Provider 快照不能用于较早
  的请求日期；财务报告和新闻发布日期也不能晚于请求日期。AKShare 已增加
  基于历史日线、历史指数和历史行业接口的 `historical` aggregate snapshot
  路径；`2026-11-04`、`2026-11-05`、`2026-11-06` 三个交易日均返回
  `quality=verified`、`market_snapshot_quality=verified`、universe `7,593`、
  字段完整率 `1.0` 且无 failures。没有历史接口的 provider 仍会明确返回
  `POINT_IN_TIME_UNAVAILABLE`，不会把 latest 快照冒充历史数据。

因此，按文档的严格发布定义，答案是**核心功能已实现，但还没有全部完成发布验收**。
已完成的是 Local-first 代码和本地可复现证据；未完成的是 Windows 真实发布链路、
真实 DeepSeek/Tushare 外部验收，以及外部推送和长期运行证据。

本次继续实现并验证了此前设计文档中的桌面交互缺口：Tauri 托盘现在提供运行状态、
暂停/恢复收盘调度和退出入口；关闭主窗口会隐藏到托盘，退出时会清理 Sidecar；
Workspace 支持 Command/Ctrl+K、Command/Ctrl+P、Command/Ctrl+Enter；移动窄屏
详情面板不再因证据或 Trace 的内容宽度产生横向溢出。相关契约测试和
`desktop-ui-smoke.sh` 已通过。

同时补齐了设计文档要求的 Web 路径定位、Topbar 任务搜索和 MVP 图表：
`/market`、`/portfolio`、`/research/:taskId` 可导航并保留任务上下文；
搜索条件写入 Web URL；Market breadth、Index trend、Portfolio exposure、
Drawdown 和 Agent timeline 均显示日期、来源、单位和精确值，并由浏览器
smoke 验证。

本轮还补齐了 M7 文档要求的试点凭据管理：环境变量优先，缺失或占位符
时从 macOS Keychain、Linux Secret Service 或 Windows Credential Vault
读取；`pia credentials set/status/delete` 提供显式管理入口。真实凭据的
外部验收仍然需要由部署环境注入，不以本机缺失凭据伪造通过。

## 2026-11-08 追加复核

本次补充了 MVP 股票池覆盖质量门。`DataWorker` 现在会对归一化 universe
明确统计并要求 `main`、`chinext`、`star`、`bse`、`etf` 五类全部存在；
缺少任一类别会写入 `UNIVERSE_COVERAGE_MISSING`，并阻止 market snapshot
进入 `verified`。新增缺类 fixture 和完整覆盖 fixture 回归测试均已通过。

本次验证结果：

- `./scripts/test.sh`：**154 tests passed**；
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=5
  ./scripts/provider-freshness-e2e.sh`：`2026-11-02` 至 `2026-11-06`
  五个开市日全部 `verified`，每日 universe 为 7,593，字段完整率为
  `1.0`，无 failures；
- `./scripts/acceptance.sh`：local mode 通过；
- `./scripts/release-preflight.sh`：仍为
  `mvp_release_ready=false`，阻塞项仍为
  `windows_msi`、`windows_host`、`deepseek_credentials`、
  `tushare_credentials`。

后续实现已把 `exchange`、`listed_at`、`active` 接入 AKShare/Tushare
adapter、DataWorker merge 和 DuckDB `normalized_universe` schema；股票上市
日期来自交易所列表和批量市场元数据，ETF 上市日期来自 SSE 基金列表与 SZSE
官方 ETF workbook，Tushare 来自 `stock_basic/fund_basic`。
真实 AKShare universe 检查显示：7,593 行中
`main=3488`、`chinext=1453`、`star=622`、`bse=364`、`etf=1666`；
所有 active 行的 `exchange`/`listed_at` 均完整。仅有
`920309.BJ`、`688827.SH` 两个 inactive suspended 行没有上游上市日期，
系统将其作为 inactive metadata gap 记录，不伪造日期，也不进入候选扫描。
`PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
./scripts/provider-freshness-e2e.sh` 已返回 `verified`、字段完整率 `1.0`
且无 failures。

## Research Workspace 验证边界

`docs/RESEARCH_WORKSPACE.md` 的核心区域和主要交互已经落地，并由 Desktop
browser smoke 覆盖。桌面端 Evidence `Used by`、Evidence 稳定 hash 链接和
任务列表键盘导航已经实现；移动端详情页也显示风险、规则门禁、Agent 名称和
Evidence `Used by`。剩余的是移动真机/模拟器的完整交互证据，不是已知的桌面
MVP 功能缺失。

## 结论

当前可以判定为：**MVP 核心功能已实现并通过 local acceptance，但完整 MVP
发布门尚未关闭**。

仓库已经形成可运行的 Local-first 研究闭环：本地 Python runtime、SQLite/DuckDB、Rules v1、任务状态机、事件去重、LangGraph/Pydantic、Trace、Evidence、Bull/Bear Debate、Risk Review、人工审批、审计、备份恢复、React/Tauri 工作台和基础 Cloud API 都有实现。

仍未关闭的发布门主要是：

1. 真实 `DEEPSEEK_API_KEY` 下的 runtime、streaming 和 Tool Calling acceptance 尚未执行；
2. Tushare credentials 下的 fundamentals/news/filings fallback 和跨 Provider provenance 尚未验收；
3. Windows sidecar、Tauri 启动、MSI 打包和 Windows 通知没有证据；
4. macOS 原生通知已有真实 smoke，但 Windows 和跨会话投递仍未验收；
5. 日终成功率和 P95 目前只有本地 fixture 证据（本次 200 个任务），没有长期或真实外部服务证据。

当前版本应标记为：

> **Local-first MVP core implemented / release acceptance incomplete**

## 本次验证

本次复核日期为 2026-11-08。当前本地验证结果如下：

已通过：

- `./scripts/test.sh`：143 tests passed；
- 最新增补 Cloud scheduler 多用户派发、角色隔离、租约审计隔离和事件
  dedupe 回归后，`./scripts/test.sh`：140 tests passed；
  `./scripts/cloud-e2e.sh` 和
  `./scripts/cloud-scheduler-e2e.sh` scheduler health/lifecycle smoke 均通过；
- Provider retry/backoff/circuit breaker、LLM usage persistence 和 cost metrics
  已在本轮新增并通过回归测试；
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-04,2026-11-05,2026-11-06 ./scripts/provider-freshness-e2e.sh`：三日均 `verified`，字段完整率均为 `1.0`，无失败；
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=5 ./scripts/provider-freshness-e2e.sh`：Provider calendar 自动选取 `2026-11-02` 至 `2026-11-06`，五日均 `verified`，字段完整率均为 `1.0`，无失败；
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=10 ./scripts/provider-freshness-e2e.sh`：Provider calendar 自动选取 `2026-10-26` 至 `2026-11-06`，十日均 `verified`，市场快照均为 `verified`，字段完整率均为 `1.0`，无失败；
- 本次最终复核的 `./scripts/acceptance.sh` local mode 通过，包含 143 个
  Python tests、Local/Cloud REST/SSE、临时 PostgreSQL、备份恢复、恢复/混沌、
  SLA、Replay、Desktop GUI、Web/iOS/Android、Tauri compile、macOS packaged
  lifecycle 和 sidecar health；release mode 因缺少真实凭据而跳过。
- `tests/test_event_derivation.py`：自动事件派生和 snapshot 绑定回归通过；
- Desktop Vite production build；
- `./scripts/e2e.sh`：Local REST/SSE、通知已读、设备生命周期、数据同步后市场快照读取、metrics；
- `./scripts/acceptance.sh` local mode；本次复核重新执行并通过；
- Local REST/SSE、metrics、Cloud auth/isolation/leases；
- device registration/unregister lifecycle；
- 独立 `./scripts/cloud-e2e.sh`；
- 临时 PostgreSQL cluster 上的 `cloud-e2e.sh`；
- `./scripts/recovery-e2e.sh`；
- `./scripts/chaos-e2e.sh`；
- `./scripts/sla-e2e.sh`：20 个本地 fixture 任务，terminal success rate `1.0`，本轮 P95 `0.058s`；
- `PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh`：200 个本地 fixture 任务，
  terminal success rate `1.0`，本次 P95 `0.063s`；
- fixture replay；
- Web build；
- Tauri `cargo check`；
- `cargo tauri --version`：`tauri-cli 2.12.4`；
- 已存在的 macOS sidecar `pia-runtime-aarch64-apple-darwin health --json`。
- 本次现场复核（2026-11-07）再次确认：`./scripts/test.sh` 为 122 tests
  passed，`./scripts/acceptance.sh` local mode 通过，
  `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-04,2026-11-05,2026-11-06
  ./scripts/provider-freshness-e2e.sh` 三个日期均为 `verified`，
  `./scripts/native-notification-smoke.sh` 返回 `DELIVERED`。
- 本轮复核重新执行 `./scripts/acceptance.sh`：Local acceptance 通过，包含
  规则版本、通知投递回执、正向审批、临时 PostgreSQL、恢复/混沌、移动端、
  Tauri 编译、macOS Desktop 生命周期和 sidecar health。
- `./scripts/python.sh scripts/generate_ts_client.py --check` 和
  `git diff --check` 通过；`./scripts/release-preflight.sh` 明确报告
  Windows MSI/主机、DeepSeek credentials 和 Tushare credentials 尚未满足。
- 最新 `./scripts/acceptance.sh` local mode 通过，包含 Paper Broker
  preview/paper submit、SMTP Email contract tests、通知投递回执、临时
  PostgreSQL、恢复/混沌、SLA、Replay、Desktop GUI、Web/iOS/Android、
  Tauri compile、macOS packaged lifecycle 和 sidecar health。
- 2026-11-07 最新复核：`./scripts/test.sh` 为 128 tests passed，
  `npm run build:web` 和 Desktop Vite production build 均通过；
  `./scripts/acceptance.sh` local mode 通过。`./scripts/release-preflight.sh`
  仍报告 `mvp_release_ready=false`，阻塞项为 Windows MSI/主机、
  `DEEPSEEK_API_KEY` 和 `TUSHARE_TOKEN`。
- 本轮新增 `ModelRouter` 和 provider-neutral LLM error mapping；随后加入
  Windows Toast 通知路径和回退测试，最新完整回归为 132 tests passed，
  `./scripts/acceptance.sh` local mode 仍通过。
- `PaperBrokerAdapter` 已实现只读、订单预览和 paper submit；live
  `submit_order` 永久返回 `CAPABILITY_DISABLED`。SMTP Email provider 已接入
  Settings、NotificationRouter 和 delivery receipt。

本次复核还修复了历史交易日质量升级逻辑：同步日历包含目标日之后的交易日
时，系统现在只比较 `as_of` 之前的最后开市日；新增回归测试覆盖该场景。

## 本轮复核新增发现

本轮已关闭此前发现的三个本地代码/证据缺口：

1. Desktop 任务创建和候选扫描现在绑定当前市场快照或当前 Provider 日期；
   fixture 仅在显式 replay 模式下使用。
2. Desktop Rules 页面现在展示选中任务的真实门禁结果，不再显示固定的空
   `WATCH` 结果。
3. 新增 `scripts/desktop-ui-smoke.sh` 并接入 acceptance，覆盖工作台加载、
   创建任务、Evidence/Trace 和 Rules 展示；AC-000 的本地 GUI 证据已补齐。
- 本轮 `./scripts/acceptance.sh` 通过，包含 packaged sidecar health；
- OpenAPI 路径覆盖回归和真实本地 webhook gateway delivery 测试通过；
- `./scripts/e2e.sh` 连续运行两次：均通过，默认使用临时 SQLite/DuckDB，避免历史 dedupe 数据污染。
- `./scripts/cloud-e2e.sh`：事件用户隔离和 `DELETE` CORS 预检通过。
- 本轮补齐了租约释放的用户授权和审计归属：`TASK_LEASE_RELEASED`
  现在写入租约所属用户，跨用户释放会被拒绝，增量同步按审计行
  `user_id` 做最终过滤；SQLite 回归测试已覆盖。
- `./scripts/cloud-e2e.sh`：组合快照按用户隔离读取通过。
- `./scripts/desktop-lifecycle-smoke.sh`：打包 macOS 应用启动、sidecar
  启动、退出和进程组清理通过。
- 2026-11-07 临时 PostgreSQL 17 集群上的 `cloud-e2e.sh` 通过，覆盖
  `PostgresDatabase` migration parity、任务取消、lease、用户隔离、设备生命周期
  和事件隔离。
- 本次最终复核（2026-11-07）：重新执行 `./scripts/test.sh`，114 tests
  passed；重新执行 `./scripts/acceptance.sh`，Local acceptance 通过；
  `git diff --check` 通过。
- 2026-11-07 追加复核：`./scripts/test.sh` 为 115 tests passed；
  修复历史交易日质量升级后，AKShare `2026-11-04`、`2026-11-05`、
  `2026-11-06` 三日 provider freshness 全部通过；`./scripts/acceptance.sh`
  在清理残留本地 runtime 后完整通过。
- 本轮修复了 AKShare 市场快照的 2,000 标的截断、ETF 快照缺失，以及
  `partial/unavailable` Provider 结果未触发 fallback 的问题；对应 adapter、
  runtime 回归测试和完整 acceptance 均已通过。
- 最新 `./scripts/acceptance.sh` 的 SLA 结果为 20 个本地 fixture 任务、
  terminal success rate `1.0`、P95 `0.070s`；恢复、混沌、REST/SSE、Cloud
  isolation、Tauri compile、packaged Desktop lifecycle 和 sidecar health 均通过。
- 在 universe metadata merge 和质量感知 fallback 修复后，最新
  `./scripts/acceptance.sh` 仍通过，Python/Web runner 为 114 tests。
- Local 和 Cloud E2E 现在都覆盖正向人工审批路径：
  `WAITING_APPROVAL -> APPROVED`，并验证 `approval_id`；同时修复了显式
  portfolio fixture 被最新持仓快照覆盖的问题，新增回归测试已通过。
- 本次重新打包的 macOS sidecar `health --json` 返回 `status=ok`，冷启动
  用时约 10.86 秒；`./scripts/native-notification-smoke.sh` 返回
  `{"status":"DELIVERED","provider_id":"local-native"}`。
- 新增 `./scripts/mobile-acceptance.sh`：本次 iOS 6 项 transport/push-token
  tests、SwiftUI build、Android `:app:assembleDebug` 和 Web Push Service Worker
  syntax check 均通过；脚本自动探测了
  `/Users/kingiol/Library/Android/sdk`。上述结果只证明客户端边界可构建，
  不等于真实 APNs/FCM/Web Push 投递已完成。
- 本次复核额外确认：`./scripts/native-notification-smoke.sh` 返回
  `{"status":"DELIVERED","provider_id":"local-native"}`；`git diff --check`、
  `npm run build:web`、Desktop Vite build 和 Tauri `cargo check` 均通过。
- iOS `swift test --package-path apps/ios/PiaMobileClient`：5 tests passed；
  `swift build --package-path apps/ios/PiaMobileClient --product PiaApp` 通过；
  已覆盖 task context、evidence、trace、approval、pause/resume、cancel 和 retry
  对应的 transport/model。
- Android `:app:assembleDebug` 通过；已覆盖 task detail、evidence、trace、
  approval、pause/resume、cancel 和 retry 控件。
- 新增 `POST /api/tasks/{task_id}/cancel`、`TASK_CANCELLED` audit/event、
  OpenAPI schema 和 generated TypeScript client 已通过本地及 Cloud E2E；
  `TASK CANCEL PASS` 已出现。
- 候选扫描现在按当前用户 Profile 的 `allowed_asset_types` 和 `universe`
  过滤；取消任务等待、事件优先级抢占和设备 response 字段也有回归测试。
- 最新 packaged sidecar health probe 返回 `status=ok`，同时报告 fixture、
  AKShare 和 Tushare 的 capability 状态；本轮冷启动约 10.6 秒，尚未形成独立
  启动性能门。
- Windows 发布路径已补充 `scripts/windows-acceptance.ps1`，并接入 Windows
  CI；它会验证 packaged sidecar health、HTTP 任务/evidence 和设备生命周期，
 但本机没有 Windows runner，因此本轮仍无真实 Windows 结果。
- 本次 acceptance recheck 在新增 deterministic `Research Manager` 节点后仍通过；
  fixture replay trace 已包含 `Research Manager`，未发现主链路回归。
- 2026-11-07 Cloud hardening：`cloud-e2e.sh` 新增 user-b 正向审批和
  `APPROVAL_RECORDED` 用户隔离断言；`cloud-backup-restore-e2e.sh` 在临时
  PostgreSQL 集群上完成 `pg_dump`/`pg_restore` 和 DuckDB snapshot 恢复。
- `postgres-cloud-e2e.sh` 现在会在隔离 UTF-8 PostgreSQL 集群上运行完整
  Cloud E2E；认证、审批、租约、设备、用户隔离、事件和幂等性均已通过。
- 当前质量门新增 `as_of`、`observed_at`、`expires_at`、发布时刻和字段完整率
  检查；未来时间和顺序错误会降级为 `unavailable`/`stale` 并产生明确失败原因。
- `./scripts/release-preflight.sh` 会区分本地制品、真实凭据、Windows 平台和
  外部推送状态；当前因本机缺少 Windows runner、DeepSeek/Tushare 凭据而返回
  非零，这是预期的阻塞结果。
- 2026-11-07 最新复核：`./scripts/test.sh` 为 140 tests passed；
  `./scripts/acceptance.sh` local mode 通过，包含临时 PostgreSQL、
  Cloud scheduler、租约/用户隔离、桌面 GUI、移动端构建、Tauri 编译、
  macOS packaged lifecycle 和 sidecar health；`git diff --check` 通过。
- 最新 `./scripts/release-preflight.sh` 仍为
  `mvp_release_ready=false`，阻塞项为 `windows_msi`、`windows_host`、
  `deepseek_credentials` 和 `tushare_credentials`；完整里程碑还缺
  `external_push_credentials`。
- 已补齐 `scripts/push-acceptance.sh`：配置真实 Web Push/APNs/FCM
  gateway 和一次性测试设备 token 后，会注册设备、触发验收事件并检查
  `DELIVERED` receipt；当前仍缺真实凭据，因此未把它标记为已验证。

live smoke：

- AKShare `1.20.35` 可调用；
- 修复后的 `get_market_snapshot("2026-11-06")` live smoke 返回 20 个指数、20 个行业
  和 7,593 个 instrument，其中 5,927 个 stock、1,666 个 ETF；breadth
  `0.127889`、volatility `0.270912`。
- 修复后的完整 `DataWorker.sync_market_data("2026-11-06", ["600000.SH"])` 返回
  `quality=verified`、`market_snapshot_quality=verified`、字段完整率 `1.0` 且无
  请求失败；保存了 market snapshot、calendar、universe、daily bars、fundamentals
  和 research sources（universe 7593、research sources 12）。
- `./scripts/provider-freshness-e2e.sh` 现在已用 AKShare 对
  `2026-11-04`、`2026-11-05`、`2026-11-06` 完成三日真实检查；长期窗口和
  Tushare fallback 仍未验收。
- 本机未配置 `DEEPSEEK_API_KEY` 或 `TUSHARE_TOKEN`，因此 release acceptance 没有执行真实 DeepSeek 和完整主备切换；PostgreSQL cloud E2E 已在临时 PostgreSQL 17 集群通过。
- 最新 `./scripts/release-preflight.sh` 仍报告 `mvp_release_ready=false`：
  当前 Darwin 主机没有 Windows runner/MSI、`DEEPSEEK_API_KEY` 或
  `TUSHARE_TOKEN`；这表示发布证据缺失，不是本地 acceptance 失败。
- 2026-11-07 当前复核补充：200 个 fixture 任务 soak 通过，terminal
  success rate `1.0`、P95 `0.063s`；AKShare 对
  `2026-11-04`、`2026-11-05`、`2026-11-06` 的 freshness gate 均为
  `verified`，字段完整率均为 `1.0`，无 failures。长期外部服务 SLA、
  Tushare fallback/provenance、Windows 和真实 DeepSeek 证据仍未完成。
- Release-mode Tushare gate 现在覆盖交易日历、universe、daily bars、
  fundamentals、news 和 filings 的 provider/source/quality 检查；本机仍无
  `TUSHARE_TOKEN`，因此实际远端调用未执行。
- Tushare adapter 已补齐可选指数和申万行业映射；无 Token 时保持
  `capability_disabled`，因此本轮仍没有真实 fallback、配额和 provenance 证据。

`./scripts/acceptance.sh` 的 local mode 已通过；release mode 仍因缺少 `DEEPSEEK_API_KEY` 未执行。当前 live smoke 证明了 AKShare 主 Provider 的一次完整同步质量，但不等于长期稳定性或备用 Provider 已验收。

## MVP 必须项逐项结论

| PRD MVP 必须项 | 判定 | 当前证据和缺口 |
|---|---|---|
| Profile、股票池、持仓、风险偏好和规则配置 | 通过 | Profile 和 Ruleset 都支持按用户版本化；CSV/XLSX/manual 持仓导入、规则编辑 API、Desktop 规则编辑器、任务固定 rule snapshot、按用户 Profile 过滤候选和 UI/单测均已覆盖 |
| 沪深主板、创业板、科创板、北交所和 ETF 股票池 | 通过 active universe 质量门 | AKShare 全量返回 7,593 行，五类覆盖通过；SSE/SZSE ETF 上市日期来源、股票批量 listing fallback、`exchange/listed_at/active` 已落库；仅两个 inactive suspended 行保留 metadata gap |
| 日线行情和基础财务数据 | 通过三日 live freshness gate | AKShare 历史 aggregate snapshot 已覆盖 `2026-11-04`、`2026-11-05`、`2026-11-06`，每日 `quality=verified`、`market_snapshot_quality=verified`、universe `7,593`、字段完整率 `1.0`、无 failures；更长运行窗口仍需持续采集 |
| 市场广度、指数、行业和个股指标 | 通过 | live snapshot 返回指数、行业、广度、波动率和个股日线；StockResearch 现在也使用 provider-backed company profile；fixture/replay 也可重建 |
| 公告/新闻结构化引用 | 部分通过 | Evidence provenance、source/as-of/quality 和 AKShare 新闻绑定已验证；Tushare 公告/新闻和 freshness 尚未验收 |
| Market/Sector/Stock/Technical/Portfolio/Risk Agent | 通过本地闭环 | 结构化节点、Trace、Pydantic contracts、replay 和 workspace 已验证 |
| Rules Engine 数据、市场、股票池、仓位和风险门禁 | 通过 | Rules matrix、用户规则版本、任务快照固定、硬阻断、审批不可绕过和 replay 均通过 |
| 收盘、公告、价格/成交量、持仓风险事件 | 本地实现 | 同步和持仓导入会自动派生质量、广度、价格/成交量、公告和组合风险事件；真实 Provider 长期窗口仍未验收 |
| 建议状态、任务、证据、结论、审批和追加审计 | 通过本地闭环 | REST/SSE E2E、replay、审批边界、audit immutability 和 UI build 通过 |
| Tauri Desktop 启动本地 Python Sidecar | macOS 本地通过 | Tauri compile、macOS bundle、packaged sidecar health、实际启动/退出和进程清理，以及浏览器级任务/Trace/Evidence/Rules smoke 均通过；Windows 仍待 runner |
| SQLite/DuckDB、回放和备份恢复 | 通过 | migration、Local backup/restore、临时 PostgreSQL `pg_dump`/`pg_restore`、DuckDB snapshot 和 restart recovery 均有测试 |
| 本地研究工作台、Trace、Evidence、Risk Review、人工审批 | 通过本地构建、接口和 GUI smoke | React/Vite build、API E2E、replay 和 `desktop-ui-smoke.sh` 通过；390×844 移动视口无水平溢出，任务/详情/审批布局会折叠 |
| 本地通知和失败恢复 | 部分通过 | 失败恢复和 chaos 已通过；macOS `local-native` smoke 和本地 Web Push/APNs/FCM gateway HTTP 验收已通过，Windows、跨会话和真实外部投递仍未验证 |
| macOS 首发、Windows 同期启动和打包 | 未完成 | macOS 有 bundle/sidecar 证据；Windows 没有 build、MSI、启动、health 或通知证据 |

## 已实现并有证据

| 功能 | 状态 | 证据 |
|---|---|---|
| Profile、Ruleset、持仓导入 | 已实现 | `runtime.py`、`rules.py`、CSV/XLSX/manual parser、相关单测 |
| Rules v1 数据/市场/股票池/仓位/风险门禁 | 已实现 | `rules.py`、`tests/test_rules.py`、replay |
| `MarketClose`、`FilingPublished`、`PortfolioRiskChanged` 等事件接入 | 已实现自动派生和 API 触发 | `events.py`、`runtime.py`、`tests/test_event_derivation.py` |
| 事件去重、冷却、优先级、重试和 lease | 已实现 | `events.py`、runtime tests |
| 任务状态机、暂停/恢复、重试、超时、重启恢复 | 已实现单测 | `runtime.py`、`migrations/006_task_control.sql` |
| Market、Sector、Stock、Technical、Portfolio、News、Bull/Bear、Debate agents | 已实现结构化节点 | `agent_graph.py`、`runtime.py` |
| LangGraph 编排和 Pydantic contracts | 已实现 | `agent_graph.py`、`agent_contracts.py` |
| SQLite + DuckDB raw/normalized/snapshot 存储 | 已实现 | `analytics.py`、backup/restore tests |
| 备份、恢复和完整性 manifest | 已实现 | `backup.py`、runtime tests |
| Local/Cloud REST、SSE、Bearer auth、用户隔离 | 已实现并有 SQLite/PostgreSQL E2E | `api.py`、`migrations/010_event_user_scope.sql`、`scripts/e2e.sh`、`scripts/cloud-e2e.sh`、`scripts/postgres-cloud-e2e.sh` |
| Research Workspace、Evidence、Trace、Risk Review、审批 UI | 已实现本地工作流 | `apps/desktop/src/App.tsx`、Desktop build |
| 无自动下单边界 | 已实现 | `submit_order` 永久拒绝、security tests |
| Prompt injection 标记、tool permission、secret redaction | 已实现单测 | `security.py`、`tests/test_security.py` |
| metrics 采集 | 已实现基础指标 | `runtime.py`、`GET /api/metrics`、E2E |
| macOS sidecar 和 Tauri 本地开发链路 | 已实现并验证 | `scripts/build-sidecar.sh`、Tauri compile、sidecar health |

## 未满足或只有部分满足

| 功能 | 判定 | 原因 |
|---|---|---|
| 真实 AKShare 日线、财务、新闻、公告质量门 | 已通过 live gate | `DataWorker.sync_market_data("2026-11-06", ["600000.SH"])` 返回 `verified`、无 failures，并保存 raw/normalized/snapshot 层 |
| 指数、行业、市场广度 live snapshot | 已通过 live gate | snapshot 返回指数、行业、广度、波动率，DataWorker 将最新交易日 snapshot 提升为 `verified` |
| 全市场股票池过滤 | 通过 | AKShare 快照已移除历史的 2,000 标的截断并纳入 ETF；实时全量 7,593 行且五类覆盖门通过，候选扫描过滤停牌、ST、退市、新股、低成交额和用户 Profile 范围；active universe 的 `exchange/listed_at/active` 已完整落库 |
| Provider 主备故障切换 | 代码与本地回归通过，live 验收待补 | fallback 现在会对异常和 `partial/unavailable` 质量都切换，并记录尝试链；Tushare 的真实凭据、配额和 fundamentals/news/filings 全能力没有验收 |
| 真实 Evidence provenance | 部分实现 | AKShare live sources 已通过 provider/source/quality 传播和标的绑定；跨 provider freshness、Tushare provenance 仍未验收 |
| DeepSeek 真实 Agent runtime | 已通过 release live gate | 使用 `config/example.env` 的凭据完成 structured output、Tool Calling、streaming 和真实 `StockResearch` runtime task |
| DeepSeek 流式输出和 Tool Calling | 已通过 release live gate | `stream_with_tools()` 和 runtime `LLM_DELTA` 路径均已用真实 DeepSeek 验收 |
| 自动收盘触发 | 本地闭环通过，生产窗口待验收 | scheduler、交易日历、live sync、质量降级通知和唯一任务去重已实现；`scripts/scheduler-e2e.sh` 已验证真实 Runtime 的收盘任务创建、执行和去重；默认关闭，仍缺真实生产调度窗口验收 |
| 自动价格/成交量异常、市场广度变化、公告和持仓风险事件 | 本地已实现 | `DataWorker` 同步结果和 `import_portfolio()` 会自动派生事件；真实 Provider 的字段质量、freshness 和长期窗口仍需验收 |
| 本地原生通知 | 部分实现 | macOS `osascript` smoke 已真实投递；Windows 已增加 WinRT Toast 路径并保留 `msg` 回退，contract tests 已有；默认关闭，Windows/跨会话演练仍缺 |
| Web Push / 移动推送边界 | 本地 gateway 已通过 | Web Push subscription、Service Worker notification click、iOS APNs token upload、Android push-token storage、背景刷新和平台路由的本地 HTTP gateway 验收已通过；真实 gateway/APNs/FCM 凭据和设备投递仍未验收 |
| Windows 同期启动、打包和运行 | 未完成 | Tauri 配置声明 `msi` target，但仓库只有 macOS sidecar；没有 Windows build、installer、launch、health 或通知证据 |
| 进程级故障恢复 | 已通过本地 chaos gate | recovery E2E 和 worker crash E2E 已验证 `RUNNING -> RETRYABLE -> retry -> BLOCKED` |
| SLA、P95、日终成功率 | 部分实现 | 20-task 本地 SLA runner 已通过，success rate `1.0`、P95 `0.058s`；本次 200-task 本地 soak 也通过（success rate `1.0`、P95 `0.063s`），真实外部服务场景和长期日终统计仍未完成 |
| API response contracts / generated client | 通过 | 20 个 API path 的 response 有 schema，TypeScript generated client 已生成并通过编译；取消任务 endpoint 及 task context 已覆盖；移动端客户端按 ADR-012 不属于 MVP 发布门 |
| 审批动作：Request more research / Mark as watch | 已实现 | Local/Cloud API、OpenAPI、生成客户端、Desktop 按钮和 E2E 均覆盖；前者创建父任务关联的 FollowUp，后者写入用户隔离的 Research watchlist |

## Acceptance 对照

| AC | 判定 | 说明 |
|---|---|---|
| AC-000 | 部分通过 | macOS sidecar 和本地 runtime 通过；Windows 启动和打包无证据 |
| AC-001 | 通过 | 创建任务、状态机和 Trace 已由 E2E 验证 |
| AC-002 | 本地闭环通过，生产窗口待验收 | `scripts/scheduler-e2e.sh` 已验证真实 Runtime 的收盘任务创建、执行和去重；真实交易日历、live 数据同步和失败告警窗口仍需外部运行验收 |
| AC-003 | 部分通过 | fixture replay 和 provenance 单测通过；live 新闻/公告来源和 freshness 仍无发布级证据 |
| AC-004 | 通过 | Rules 矩阵、硬阻断和 replay 已验证 |
| AC-005 | 本地/Cloud 通过 | Local 和 Cloud E2E 均覆盖 `WAITING_APPROVAL -> APPROVED`、`approval_id`、用户作用域和审计；真实外部部署仍需凭据和平台验收 |
| AC-006 | 通过 | 没有 broker write path，`submit_order` 被显式拒绝 |
| AC-007 | 本地通过 | retry/timeout/restart recovery 和 worker crash chaos 已通过；真实外部服务失败场景仍需补充 |
| AC-008 | 本地 + 多交易日 live 通过 | Evidence UI 会依据 `expires_at` 标记 `stale`，Rules 会阻断 stale/unavailable；AKShare `2026-11-04` 至 `2026-11-06` 历史 freshness 全部通过 |
| AC-009 | 通过 | Bull/Bear、Evidence 和 Debate Chair 在 replay 中可见 |
| AC-010 | 通过 | 风险事件优先级和组合风险门禁已有测试 |

## P0 工程验收

- 任务状态迁移、append-only audit、SQLite/DuckDB 备份恢复和应用重启恢复：已有实现和测试；
- API 输入校验、response schemas 和 TypeScript generated client：已有；移动端 generated clients 不属于 MVP 发布门；
- P0 数据字段质量状态：fixture pipeline 和 AKShare 三日历史 live pipeline
  均有；AKShare 历史 aggregate snapshot 具备 point-in-time 路径并已现场验证，
  因此仍待补的是更长运行窗口和 Tushare fallback，而不是历史快照实现；
- 密钥不进入前端日志的设计和基础 redaction：已有单测，但没有完整运行时泄露演练；
- 任务 timeout 和基础 metrics：已有；
- 长期日终成功率、真实外部服务 P95、Windows 发布链路和真实通知投递：未完成；本地 20-task SLA、200-task soak 与进程崩溃恢复已通过 E2E。

## MVP 发布前阻塞项

1. 完成真实 DeepSeek runtime task、缺 key 的 `CREDENTIALS_REQUIRED` acceptance，以及 streaming/tool-call runtime 闭环验收；
2. 完成真实 Tushare credentials 下的 fundamentals/news/filings contract test、fallback 和 provenance 演练；
3. 在 AKShare 历史路径基础上持续采集更长 freshness 窗口和真实外部服务 P95；
4. 补齐 Windows sidecar/Tauri build、MSI、启动、health、任务和通知证据；
5. 完成 Windows 原生通知真实投递和 macOS/Windows 跨会话失败状态演练；
6. 增加长期日终统计和真实外部服务 P95 证据，再重新运行完整 P0 acceptance matrix。
