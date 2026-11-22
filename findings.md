# Findings & Decisions

## Desktop data isolation (2026-11-22)

- Debug scripts put live and fixture runs in the same repo-local database. A packaged Release launch can default to the sidecar's temporary resource directory.
- Desktop readiness previously checked only the runtime mode on a fixed URL. The launcher will own the local process and verify its instance on the port that it bound.
- Keep the Release bundle identifier and credential service for compatibility. Select distinct Debug identities, including separate Debug storage for fixtures and live data. Existing data migration remains an explicit backup and restore.

## Candidate discovery and watchlists (2026-11-22)

- The global refresh fetched default candidates independently of explicit scans in Market. Both successful and failed empty responses reached Watchlist as an empty array.
- Market previously hid scanning controls when no snapshot had been persisted. Fixture mode can scan its known demo data even in a fresh workspace.
- Watchlist persistence replaces the full list identified by the user's list name. Adding symbols must merge with saved symbols, while editing can explicitly replace the list.

## Portfolio management and import (2026-11-22)

- The previous bulk-import entry was a fragment link to an always-visible form. The new entry opens the form directly.
- Fixture snapshots have no user position actions. The management table should show saved holdings only and keep the existing runtime fixture behavior for research.
- A row's index and symbol identify it within an immutable snapshot revision, including legacy imports that contain the same symbol on more than one row.

## Single-position entry (2026-11-22)

- Bulk import persists a complete snapshot. The single-position write must merge against the latest user snapshot on the server and keep the historical revision available.
- Desktop and Web share `PortfolioView`. The existing native dialog styling and risk-event pipeline cover the new flow.
- Fixture snapshots should remain available for display and replay, while the form uses only the user's own positions for writes.

## 2026-11-09 Decision Journal Slice 1

- The first Journal slice can reuse the current write model; a separate
  `decision_records` table would duplicate historical facts.
- Cross-task complexity is isolated in `DecisionJournal`, so the UI consumes
  one projection instead of joining task details itself.
- Pagination cursors are only valid with the same filter set; the client keeps
  the first slice read-only and does not expose derived Memory actions yet.
- Existing retrospective action and outcome values are preserved; the Journal
  adds normalized fields for filtering without rewriting history.

## 2026-11-09 Product validation phase

- The first product priority is trust recovery, not additional Agent roles.
- A stale task id persisted in the browser could produce repeated 404 requests
  after the local runtime database changed. The UI now treats this as a
  recoverable navigation state and returns to Overview.
- The first user-visible event-driven loop now exists on Overview: recent
  notifications explain why Pia is asking for attention and link to the
  related task.
- The next validation gate is behavioral: recruit experienced individual
  investors and measure first-review completion, useful-alert rate, weekly
  return and willingness to pay.

## 2026-11-08 UX redesign specification

- The current shared React workspace is feature-complete for a pilot but has no
  first-run onboarding or setup checklist.
- Desktop and Web share `apps/desktop/src/App.tsx` and `styles.css`; changes there
  cover both surfaces.
- The current Profile editor is raw JSON and therefore unsuitable for ordinary
  investors without training.
- The first-run state needs four visible steps: investor profile, holdings,
  data/credentials and first review.
- The main visual direction is calm editorial finance: warm paper background,
  ink typography, emerald action color, amber risk states, strong hierarchy and
  large readable task cards.
- The product must make replay/fixture provenance visible so synthetic data cannot
  be mistaken for live market data.
- Mobile clients are thin native shells with no shared UI layer; they need the
  same information architecture and copy, implemented natively.

## 2026-11-09 UX redesign implementation

- Desktop/Web now present a first-launch checklist above the task queue and
  expose `回放数据` versus `实时数据` in the top bar.
- Desktop/Web responsive CSS needed a final `max-width: 700px` override because
  the original desktop sidebar styles were declared after the old mobile media
  query.
- iOS `TaskStatus` display text is shared between the home and detail views;
  the native build caught and fixed the initial scope mistake.
- Android debug build succeeds when `ANDROID_HOME` and `ANDROID_SDK_ROOT` point
  to the installed SDK.
- The shared Profile view no longer requires JSON editing; it now writes the
  same versioned payload from ordinary controls for objective, risk, drawdown,
  asset types and universe.

## 2026-11-08 Final release verification

- Loaded `config/example.env`; DeepSeek structured output, tool calling,
  streaming and live `StockResearch` all passed in release acceptance.
- The final Python regression passed **197 tests**; generated client check and
  `git diff --check` passed.
- Independent AKShare freshness for `2026-11-06` passed with
  `quality=verified`, `market_snapshot_quality=verified`, universe `7,593`,
  field completeness `1.0`, `failures=[]`, one daily bar, one fundamentals
  result and 12 research sources.
- Local/Cloud/temporary PostgreSQL, recovery/chaos, SLA, Replay, Desktop,
  Web/iOS/Android, Tauri, packaged macOS lifecycle, sidecar health and native
  notification acceptance all passed.
- Tushare was intentionally not invoked. Strict preflight remains blocked by
  Windows MSI/host evidence and the omitted Tushare token; external push
  credentials remain a full-milestone gate.
- `get_index_series` previously returned a single snapshot's `indices`; it now
  returns a date-range `series` with symbol filtering and provider provenance
  across fixture, AKShare and Tushare adapters. The old `indices` field remains
  for single-day compatibility.
- Mobile task detail previously exposed only an SSE URL; iOS and Android now
  parse authenticated SSE frames and refresh live task detail, closing the M5
  real-time trace gap.
- Full release acceptance was rerun after this change and passed with 197
  Python tests, Android debug assemble, iOS tests/build, live AKShare and live
  DeepSeek.

## 2026-11-08 Latest MVP verification

- Release acceptance passed with **193 Python tests**, Local/Cloud/temporary
  PostgreSQL E2E, recovery/chaos, SLA, replay, Desktop/Web/mobile builds,
  Tauri/macOS lifecycle, sidecar health, native notification and live DeepSeek.
- AKShare `2026-11-06` freshness passed with `verified` quality, universe
  `7,593`, field completeness `1.0` and no failures.
- Cloud pause/resume control now persists `pause_requested`; independent API
  and worker runtimes coordinate through the database instead of relying on
  in-memory events. The behavior is covered by a two-runtime regression.
- `freshness-e2e.sh` used a stale hard-coded future date and could fail after
  the calendar advanced. Its deterministic future fixtures now use `2099-01-02`.
- Strict preflight remains blocked by Windows MSI/host evidence and the
  intentionally omitted Tushare token. Full-milestone external push credentials
  are still unavailable.

## 2026-11-08 Full milestone audit continuation

- The active objective is broader than the already completed MVP release
  acceptance: all documented M0-M7 capabilities must be implemented for both
  Local and Cloud execution where the docs require them.
- Current release acceptance proves many happy paths, but it does not by itself
  prove every documented tool, Cloud failure boundary, mobile background/push
  behavior or platform packaging path.
- `runtime.py` has an explicit fallback
  `ToolPermissionDenied("Tool ... is not implemented")`; the documented tool
  catalog must be enumerated against this dispatch before marking M4/M5
  complete.
- Current docs explicitly leave Tushare credentialed fallback, Windows runner
  packaging/notification, external push delivery and long-run external
  freshness/SLA as environment-gated evidence. These remain separate from
  code gaps and must not be silently reclassified as implemented.
- The documented tool catalog is implemented in `PiaRuntime.invoke_tool`; the
  explicit not-implemented fallback is only reached for unknown or unauthorized
  names. Agent YAML declarations are checked against the same permission matrix.
- Cloud sync had a real pagination bug: `sync_changes()` paged the global audit
  stream before filtering by user, so another user's audit traffic could skip
  changes. The query now scopes by `user_id` and computes `has_more` from the
  next scoped row; a regression test covers the interleaved-user case.

## 2026-11-08 Final verification

- With `config/example.env` loaded, release acceptance passed with 190 Python
  tests, live AKShare freshness, and real DeepSeek structured, tool-call,
  streaming, and `StockResearch` runtime checks.
- AKShare `2026-11-06` returned verified market and snapshot quality, 7,593
  instruments, 1.0 field completeness, and no failures.
- Tushare was intentionally not invoked. `release-preflight.sh` therefore
  keeps only `windows_msi`, `windows_host`, and `tushare_credentials` as MVP
  blockers; full milestone push credentials remain external-only.
- The follow-up release recheck passed with 191 Python tests and the same live
  AKShare/DeepSeek evidence. Cloud lease heartbeat now enforces the owning
  task's user scope, matching lease release behavior; cross-user heartbeat
  rejection is covered by repository and HTTP-level regression tests. The
  post-patch Python suite passed 192 tests.

## Requirements
- 用户希望依据一段关于 A 股 AI Agent 的讨论记录，在本地生成完整的 PRD、里程碑、执行计划及配套文档。
- 讨论最终聚焦于一个 A 股 Personal Investment Agent，而非简单的股票问答机器人。
- 产品应持续观察市场、持仓和事件，主动触发研究，并把个人交易纪律固化为程序规则。
- 产品应支持多 Agent 投研、证据引用、看多看空辩论、风险审核和人工审批。
- 技术讨论覆盖 Agent 列表、MCP Tools、数据源、Memory、定时任务、Rules Engine、Event Engine、Research Workspace、项目目录、数据库 Schema、Agent State、Web/移动端/桌面端部署和桌面宿主选型。

## Research Findings
- 讨论给出的产品定位：Personal Investment Agent 是一个理解个人交易体系、持续观察 A 股市场、主动发现机会、严格执行交易纪律的 AI 投资助理。
- 核心原则：Agent 负责理解和推理，程序负责计算和约束，用户负责最终授权。
- 推荐系统形态：Event-Driven、Multi-Agent、Rules-First。
- 推荐早期架构：模块化单体 + 独立数据采集 Worker + Agent Worker。
- 推荐 Agent 角色：Investment Chief、Market Analyst、Sector Analyst、Stock Researcher、Technical Analyst、Portfolio Analyst、News Analyst、Risk/Rules Agent、Decision Agent。
- 讨论明确指出，不应让所有 Agent 都使用 LLM；上涨家数、技术指标、仓位、风险暴露等应由数据服务和确定性工具计算。
- MVP 建议采用日线 + 收盘后研究；盘中分钟级信号需要授权实时数据和更高可靠性。
- 每条证据至少保留 `source`、`observed_at`、`as_of`、`expires_at`、`quality` 等时效和质量字段。
- 决策输出应包含 `BUY_CANDIDATE`、`SELL_CANDIDATE`、`HOLD`、`WATCH`、`NO_ACTION` 等状态，而不是只返回 BUY/SELL/HOLD。
- 事件引擎需要事件去重、冷却窗口、优先级和失败重试，持仓重大风险优先于普通候选股扫描。
- Tools 必须按 Agent 权限分组；新闻 Agent 不应具备提交订单权限。
- 对外可提供 MCP Server；内部高频调用优先普通 Python Service/RPC。
- 讨论给出的桌面验证内容：启动 Python Agent、SSE 实时输出 Agent Trace、系统托盘常驻、退出清理进程、macOS/Windows 打包，并测量安装包、冷启动、空闲内存和研究任务峰值资源。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Python 作为 Agent Runtime | LangGraph、Pydantic、数据生态和量化工具集成便利 |
| React + TypeScript + Vite 作为 Workspace UI | Tauri 加载静态资源即可，适合复杂研究工作台、图表、Markdown 和实时 Trace |
| PostgreSQL 作为云端主库，SQLite 作为本地单用户模式 | 云端支持并发和审计，本地模式降低部署门槛 |
| DuckDB 作为分析/回测存储 | 适合本地列式分析和历史数据扫描 |
| Redis 只在需要队列、缓存或事件分发时引入 | 避免 MVP 早期增加不必要基础设施 |
| LLM 输出必须使用结构化 Schema | 降低解析不稳定，便于审计和回放 |
| Broker/Order Adapter 默认只读或模拟 | 先验证研究与纪律闭环，后续再评估半自动交易 |
| 先做 Web/PWA + Tauri 2 桌面宿主 | 云端 Agent 便于多端访问；Tauri 2 负责本地桌面壳层和 Python Sidecar |
| Tauri UI 不使用 Next.js | Next.js 的 SSR/API 能力在 Tauri 静态包中不可直接使用，引入 Node Cloud 会重复 Python Agent/API 运行时 |

## Latest Local-first Decision
- MVP 正式入口改为 Tauri 2 Desktop。
- Python Local Agent Sidecar、SQLite 和 DuckDB 是首发执行与存储组合。
- Cloud Agent、Web/PWA、iOS 和 Android 作为后续扩展，不进入 MVP 发布门。
- MVP 的 Ruleset、Approval 和 Audit 以本地 SQLite 为权威。
- `AgentGateway`、OpenAPI/JSON Schema、Agent Contract 和 Adapter Port 仍作为跨执行面共享边界。
- 主要新增阻碍集中在 Provider/授权、股票池、规则阈值、LLM、持仓输入、首发 OS 和 replay 日期；详见 `docs/IMPLEMENTATION_INPUTS.md`。

## User-confirmed Inputs
- macOS 首发，Windows 必须实现。
- 股票池包含沪深主板、创业板、科创板、北交所和 ETF。
- 排除 ST、停牌、新股、退市整理等标的。
- 主数据 Provider 为 `akshare`，备用 Provider 为 `tushare`。
- LLM 先使用 `deepseek`，通过抽象的 LLM Provider Port 保留后续扩展能力。
- 允许外部 API 和远程 LLM。
- 持仓输入需要覆盖 CSV、Excel、手工录入；只读接口继续通过 Adapter 扩展。
- 规则阈值尚未给定，文档已提供一组待确认的初始值。
- Replay 日期的含义已补充说明；第一阶段可先使用合成 fixture，暂不阻塞 Sidecar Spike。
- AKShare 作为 Python package 接入，Provider Adapter 默认不要求 API key；仍需处理网络可用性、上游接口变化和数据质量。
- DeepSeek MVP 使用 OpenAI-compatible API：`https://api.deepseek.com` + `POST /chat/completions` + `deepseek-flash`。

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 浏览器打开分享页要求登录 | 调用公开分享数据接口获取完整 conversation payload |
| 原始对话包含 UI DSL、搜索痕迹和重复消息 | 只提取产品事实、决策和可执行约束，重写为稳定文档 |
| 当前没有代码仓库 | 将交付物设计成独立 Markdown 文档包，后续可直接迁移到代码仓库 |

## Resources
- 用户提供的讨论记录：https://chatgpt.com/share/6aec911f-91e8-83ec-9356-f2be5de19249
- 讨论中引用的 TradingAgents：https://github.com/TauricResearch/TradingAgents
- 讨论中引用的 OpenBB：https://openbb.co/
- 讨论中引用的 TradingAgents-CN 相关合集：https://github.com/LLMQuant/awesome-trading-agents
- 讨论中引用的 AKShare：https://github.com/akfamily/akshare
- 讨论中引用的 Tushare：https://tushare.pro/
- 讨论中引用的 Tauri：https://v2.tauri.app/

## Visual/Browser Findings
- 分享页面的浏览器渲染会跳转到登录页，但公开分享接口返回了完整对话内容。
- 对话标题为“股票AI工具开源对比”。
- 对话包含多轮追问：产品全景、完整架构、Research Workspace、可落地技术设计、部署形态和桌面宿主比较；当前已选定 Tauri 2。

## 2026-11-08 Implementation Findings

- Live research execution previously called fundamentals and news providers
  without the task `as_of`, even though the DataWorker pipeline enforced
  point-in-time quality. The runtime now forwards that date through the same
  provider router used for fallback and audit.
- Tushare `search_news()` used a precedence-sensitive filter that skipped the
  date check for rows without `ts_code`. The filter now requires both symbol
  compatibility and publication date validity.

## 2026-11-07 Implementation Findings

- The generated TypeScript client is now used by the shared Desktop/Web transport for task, profile, portfolio, market, candidate, approval, scheduler and data-sync flows.
- Web cloud mode now has a token entry flow backed by session storage; local mode still works without a token.
- Cloud CORS preflight explicitly permits `Authorization`, `Idempotency-Key` and `X-Worker-Id`.
- Cloud mode emits redacted JSON request logs and exposes request count, error count and request P95 through health diagnostics.
- Windows packaging now has PowerShell sidecar/package scripts and a CI matrix, but a Windows runner result is still required before claiming platform verification.
- Cloud notifications now route through local native delivery or a configured webhook gateway; unconfigured providers return explicit `DISABLED` receipts.

## 2026-11-07 Temporal and Release Findings

- Provider responses previously carried point-in-time fields but did not
  consistently reject future dates or impossible timestamp ordering.
- `DataWorker` now treats those records as `unavailable` (or `stale` when an
  expiry has elapsed), records the exact error code, and prevents the market
  snapshot promotion path from restoring `verified`.
- Fundamentals are allowed to use an older report-period `as_of`; daily bars,
  market snapshots and source records must match the requested research date.
- `scripts/release-preflight.sh` is intentionally a non-passing gate on this
  machine: it reports the missing Windows runner/package, DeepSeek/Tushare
  credentials and external push credentials instead of claiming release
  readiness.
- A real packaged macOS launch exposed that killing only the PyInstaller
  parent left its extracted child process alive. Tauri now owns a process group
  and terminates the full group on exit; the lifecycle smoke confirms no
  sidecar remains.
- The local freshness soak intentionally reports only deterministic quality
  behavior; it cannot prove external-provider freshness over a real trading
  calendar.

## 2026-11-07 Provider Coverage Findings

- AKShare market snapshots previously truncated instruments to 2,000 and did
  not include ETF spot rows. After removing the cap and adding ETF mapping, a
  live `2026-11-06` snapshot returned 7,593 instruments: 5,927 stocks and
  1,666 ETFs.
- Provider fallback must treat `partial` and `unavailable` quality as failure
  conditions even when no exception is raised. Runtime now records the failed
  quality attempt and continues to a healthy fallback provider.
- Spot endpoints can omit listing age and exclusion metadata. DataWorker now
  merges the same provider's universe metadata into the persisted market
  snapshot before Rules and replay consume it.
- Live AKShare DataWorker synchronization after these changes returned
  aggregate and market-snapshot quality `verified`, field completeness `1.0`,
  no failures, 7,593 universe rows and 12 research sources.

## 2026-11-07 MVP Audit Recheck

- The current workspace passes `./scripts/test.sh` with 120 tests and passes
  `./scripts/acceptance.sh` in local mode.
- The local acceptance path covers REST/SSE, approval, replay, temporary
  PostgreSQL, backup/restore, restart recovery, worker chaos, local SLA,
  mobile builds, Tauri compilation, packaged macOS lifecycle and sidecar
  health.
- The MVP core is implemented and locally verifiable, but the PRD release gate
  is still open: Windows package/startup evidence, real DeepSeek runtime,
  credentialed Tushare fallback/provenance, and long-run/external delivery
  evidence are not present.
- The PRD explicitly lists Windows same-time startup/package validation as an
  MVP requirement, so the missing Windows runner evidence is an MVP blocker.
  External Web Push/APNs/FCM delivery remains a later full-milestone blocker;
  local gateway routing is already verified.
- `scripts/release_preflight.py` now requires an actual `*.msi` file, and
  `scripts/desktop-build.ps1` fails when either the Windows sidecar or MSI is
  missing. Execution of that path still requires a Windows runner.

## 2026-11-07 Latest MVP Verification

- Re-ran `./scripts/acceptance.sh` after the Paper Broker and SMTP Email
  provider changes; local mode passed with 120 Python tests.
- Acceptance also passed Paper Broker preview/paper submit, notification
  delivery receipts, temporary PostgreSQL, recovery/chaos, SLA, Desktop GUI
  smoke, mobile builds, Tauri compile, macOS lifecycle and sidecar health.
- `./scripts/release-preflight.sh` still reports `mvp_release_ready=false`
  because this Darwin host has no Windows runner/MSI, `DEEPSEEK_API_KEY`, or
  `TUSHARE_TOKEN`. These are release evidence blockers.

## 2026-11-07 Documented Tool and Memory Completion

- Implemented the full tool catalog named in `docs/DATA_RULES_EVENTS.md`:
  index series, price/volume features, fundamentals, company profile, news,
  filings, earnings summary, instrument comparison, exposure calculation,
  position simulation, evidence persistence, approval requests, follow-up task
  scheduling and child research task creation.
- Added user-scoped `watchlists` and `semantic_memories` tables to both SQLite
  and PostgreSQL migrations, with runtime methods, authenticated API routes,
  OpenAPI declarations and generated TypeScript client methods.
- Added regression coverage for tool permissions, tool behavior, memory
  isolation and the local E2E API flow. Fixture fundamentals remain `partial`
  when no real fundamentals source exists.

## 2026-11-07 MVP UI and live-path closure

- The generated browser client stored `fetch` without its browser receiver,
  causing the real Desktop/Web workspace to fail with `Illegal invocation`.
  The generated client now uses `globalThis.fetch.bind(globalThis)`.
- Desktop task creation previously sent a fixed replay date and fixture even
  after live data synchronization. It now binds new tasks and candidate scans
  to the latest market snapshot, or to the current provider date when no
  snapshot exists.
- The Rules configuration page previously displayed a hardcoded empty `WATCH`
  result. It now displays the evaluated Rules result from the selected task.
- Tauri starts with AKShare by default; fixture replay is still available by
  explicitly setting `PIA_DATA_PROVIDER=fixture`.
- Browser-level smoke now covers workspace loading, task creation, evidence,
  trace and selected-task Rules rendering.

## 2026-11-07 MVP audit recheck

- Historical provider quality promotion now compares the latest open trading
  day at or before `as_of`; a later calendar row can no longer downgrade a
  valid historical snapshot.
- The regression suite is now 115 tests.
- Real AKShare freshness passed for `2026-11-04`, `2026-11-05` and
  `2026-11-06`, with verified aggregate and market-snapshot quality,
  completeness `1.0`, and no failures.
- Local acceptance passed after clearing a stale runtime on port `8765`.
- Windows packaging/launch/notification evidence and real DeepSeek/Tushare
  credentials remain release blockers.

## 2026-11-08 MVP Audit Recheck

### Current audit continuation

- `docs/PRD.md` requires the MVP universe to cover `main`, `chinext`, `star`,
  `bse`, and `etf`, and `docs/DATA_RULES_EVENTS.md` requires per-instrument
  `asset_type`, `board`, `exchange`, `listed_at`, and trading-state metadata.
- `data_quality.validate_snapshot()` currently checks only generic market
  snapshot fields; it does not independently validate universe category
  coverage.
- Provider adapters already emit board/asset metadata and the runtime profile
  defaults to the five documented categories, so the missing piece is a
  quality gate and evidence, not a new provider adapter.
- The remaining release blockers documented in `docs/MVP_AUDIT.md` are still
  environment/evidence blockers: Windows MSI/host execution, real DeepSeek
  credentials, real Tushare credentials, and external push credentials for
  the full milestone.

- The current local regression suite is **144 tests passed**.
- `./scripts/acceptance.sh` passes in local mode and covers the implemented
  Local-first MVP path, Cloud/PostgreSQL compatibility, recovery, replay,
  Desktop UI, mobile builds and packaged macOS sidecar lifecycle.
- The Desktop smoke now proves task status grouping, stable task deep-link
  restoration, raw snapshot inspection, replay, watchlist save/research
  shortcuts, selected-task Rules evaluation and narrow viewport overflow safety.
- The previous audit text claiming that task grouping, Raw data/replay and
  Watchlist UI were missing was stale and has been corrected.
- Evidence `Used by` metadata is now derived from persisted trace evidence
  references; Evidence cards expose task/hash stable links and the task list
  supports arrow/Home/End keyboard navigation with focus-visible affordances.
- The remaining Research Workspace gap is real mobile-device or simulator
  interaction evidence, which cannot be inferred from a browser viewport smoke.
- `release-preflight.sh` correctly reports MVP release blockers:
  Windows MSI/host evidence, real DeepSeek credentials and real Tushare
  credentials. Full milestone readiness additionally requires external push
  credentials. These are verification/environment blockers, not failed local
  implementation tests.

## 2026-11-08 Provider Observability Finding

- `GET /api/metrics` already exposed HTTP, task, LLM and worker metrics but did
  not distinguish provider capability latency or fallback failures.
- `PiaRuntime._provider_call()` is the common live-provider routing boundary;
  instrumenting it records one metric per provider route attempt without
  changing decision or fallback semantics.
- The new `observability.provider_calls` payload is keyed by
  `provider_id:capability:method` and includes call count, error count, error
  rate, P95 milliseconds, latest status and latest error.
- `DataWorker.sync_market_data()` now emits the same metrics for market
  snapshot, trading calendar, universe, daily bars, fundamentals, news and
  filings.
- Full local regression now passes with **186 tests** and local acceptance
  passes through Cloud/PostgreSQL, recovery, mobile and packaged Desktop
  checks.
