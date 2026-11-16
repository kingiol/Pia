# Task Plan: Pia Full Local + Cloud Implementation

## Active UX redesign phase (2026-11-08)

### Goal

把 Pia 改造成普通股民无需培训即可完成第一次研究的现代客户端，覆盖
Tauri Desktop、Web/PWA、iOS 和 Android。首条成功路径必须是：

```text
启动 -> 看懂当前状态 -> 完成最少配置 -> 运行第一次复盘 -> 看懂结论 -> 做出人工选择
```

### Scope

- Shared React Desktop/Web: first-run checklist, guided empty state, modern visual
  system, clearer Chinese copy, responsive layout and data provenance.
- iOS SwiftUI: friendly connect/setup state, Today/Research/Alerts navigation,
  understandable task cards and approval detail.
- Android Compose: same information architecture and visual tokens as iOS.
- Preserve existing API contracts and task/risk/approval behavior.

### Acceptance

- A new user can identify the next action within five seconds of opening.
- First-run setup explains Profile, Portfolio, Data and First review in order.
- Fixture/replay data is visibly labeled as replay data.
- Runtime/auth/data failures include a next action.
- Desktop/Web build passes; iOS package tests/build and Android debug assemble pass
  where the local toolchains are available.
- Existing task approval, evidence and audit behavior remains intact.

### Phases

- [x] UX spec and current-state audit
- [x] Shared React onboarding and visual redesign
- [x] iOS native onboarding/navigation redesign
- [x] Android native onboarding/navigation redesign
- [x] Cross-platform build and runtime verification

### Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `r0/playwright` path was not present under Codex root | 1 | Used `/Users/kingiol/.codex/skills/playwright/SKILL.md` |
| `planning-with-files` path was not present under Codex root | 1 | Used `/Users/kingiol/.agents/skills/planning-with-files/SKILL.md` |

## Goal

根据本地规划文档，完整实现 Local-first MVP，并继续完成 M1-M7 中约定的 Local、Cloud、Web、iOS 和 Android 能力。所有发布门必须有代码、测试或运行证据；未验证的能力不能标记为完成。

## Current Phase

Phase 21: Full milestone implementation audit and Cloud/mobile closure

### Current subphase

- [x] Add the missing Sector Analyst contract
- [x] Align declared agent tools with runtime permission matrices
- [x] Add contract regression coverage for every agent YAML
- [x] Add Bull/Bear/Debate/Research Manager contracts
- [x] Add mobile approval action parity for iOS and Android
- [x] Persist task snapshot checkpoints across retry and audit the resume path
- [x] Re-run full local acceptance after contract changes
- [x] Add explicit MVP universe coverage quality gate and regression evidence
- [x] Add provider-backed company profile research data and provenance
- [x] Reuse persisted live market snapshots and cache repeated research calls
- [x] Add native credential-manager lookup and `pia credentials` management commands
- [x] Expose queue depth, task age, storage and worker heartbeat metrics
- [x] Add `exchange`, `listed_at`, and `active` normalization/persistence
- [x] Obtain truthful SSE/SZSE ETF `listed_at` sources and complete the active
  universe metadata quality gate
- [x] Re-run Python and generated-client checks after metadata changes
- [x] Re-run full local acceptance after metadata changes
- [x] Update MVP audit and progress with current per-requirement status
- [x] Re-run full local acceptance after Evidence provenance persistence fix
- [x] Wire Windows package, launch, sidecar, task and notification acceptance into release-gates CI
- [x] Fix Android approval actions so request-more-research and mark-as-watch
  are forwarded to the Cloud API
- [x] Add iOS and Android task takeover controls for failed/retryable tasks

Current conclusion: Local-first MVP core is implemented and locally accepted.
Strict release readiness remains incomplete because Windows packaging/host
evidence and real Tushare credentials are unavailable. DeepSeek is now
credentialed and live-accepted. AKShare
historical point-in-time aggregate snapshots are implemented and verified across
three trading dates. The documented instrument metadata contract is complete for all active AKShare stock and ETF
rows. Two inactive suspended rows have no upstream listing date and remain
explicitly reported as inactive metadata gaps without entering candidate scans.
Agent YAML contracts now include Sector Analyst and are checked against the
runtime permission matrix; no declared read or approval tool is silently denied.

The latest hardening pass also scopes live research-provider requests to the
task `as_of` date and rejects future Tushare news rows even when the provider
omits a symbol code. This closes a runtime path that could otherwise bypass the
historical data quality guarantees already enforced by `DataWorker`.

Latest audit recheck (2026-11-08) passed 197 Python tests and the full release
acceptance matrix. Task-level expiration now reaches terminal `EXPIRED` with
error, event and immutable audit evidence. Research Provider fallback now treats degraded research
payloads as fallback candidates when another live Provider is available, while
preserving a last-resort partial result with explicit audit evidence. SSE now
terminates on `DONE` and `EXPIRED`. The broader goal remains active: the next
phase must verify every M0-M7 and Cloud/mobile requirement against code and
add implementation where the current evidence is only a contract or smoke test.
The documented `get_index_series` tool now has a real date-range provider
contract with symbol filtering and provenance across fixture, AKShare and
Tushare adapters; Tushare remains intentionally unverified without a token.
Mobile task detail now consumes authenticated SSE on both iOS and Android and
refreshes live trace, evidence and decision state; Android debug compilation
and iOS transport tests pass.
Cloud lease heartbeat now enforces task-owner scope, with a cross-user
regression test. Cloud pause/resume now uses persisted control state across
separate API and worker runtimes. The Cloud/mobile audit is now complete for
the code and local acceptance boundaries; Windows, Tushare and external
push-gateway evidence remain explicitly open.

### Phase 21 entry audit

- [x] Build a requirement matrix from PRD, ACCEPTANCE, MILESTONES and
  TRACEABILITY, including explicit local and cloud variants
- [x] Audit the complete documented tool catalog against runtime dispatch and
  permission contracts
- [x] Audit Cloud worker/scheduler/leases/sync/backup/notification behavior
  beyond current happy-path E2E
- [x] Audit mobile background/push/token and real client workflow boundaries
- [x] Close any implementation gaps found by the matrix with focused tests
- [x] Re-run the appropriate local and cloud acceptance suites
- [x] Update docs and persistent evidence with remaining external-only gates

## Phases

### Phase 1-8: Documentation and Local vertical slice

- [x] 完成产品、架构、数据、Rules、事件、Research Workspace、里程碑和验收文档
- [x] 完成 Python runtime、SQLite/DuckDB、Rules v1、Replay、Trace、Evidence、Decision、Approval、Audit
- [x] 完成 React/Vite Desktop/Web workspace
- [x] 完成 Tauri 2 开发模式、任务控制、事件幂等、备份恢复和基础 Cloud API
- [x] 完成 LangGraph/Pydantic、Sector Analyst、AKShare adapter、scheduler 和通知适配器
- [x] 完成当前 MVP 审计并记录发布阻塞项

### Phase 10: MVP release hardening

- [x] 完成 provider 日线、财务、公告、新闻、交易日历和股票池 raw/normalized/snapshot 管线
- [x] 完成 AKShare live provider quality gate、字段完整率和 raw/normalized/snapshot 验证
- [x] 完成 AKShare 历史 point-in-time aggregate snapshot、三日 freshness 和覆盖率验证
- [ ] 完成长期 freshness、Tushare credentials 下的主备切换和跨 Provider provenance 验证
- [x] 完成可独立运行的 Python sidecar、Tauri externalBin 和 macOS bundle 验证
- [x] 完成 Windows build/launch/package verification path（PowerShell 脚本与 CI
  已实现，真实 Windows runner acceptance 待执行）
- [x] 完成 scheduler 交易日历、数据同步、失败告警和通知 contract 验收
- [ ] 完成 macOS/Windows 原生通知真实投递验收
- [x] 完成 Desktop Excel import UI
- [x] 完成 Prompt Injection、Tool permission、secret redaction、chaos、SLA/P95 和 local P0 acceptance runner
- [x] 让 release acceptance 和 provider freshness 同时支持环境变量与 native credential manager
- [x] 完成真实 DeepSeek integration contract test（仅使用本机注入凭据）
- [x] 完成 Cloud structured JSON logs、request metrics、health diagnostics 和 CORS auth headers
- [x] 完成 generated TypeScript client 接入 Desktop/Web transport 和 Web Bearer login
- [x] 增加 Windows PowerShell sidecar/package scripts 和 macOS/Windows CI matrix

### Phase 11: Cloud execution plane

- [x] Implement PostgreSQL repository and migration parity
- [x] Implement cloud scheduler/worker separation, leases, retries and observability baseline
- [x] Implement generated clients and typed Desktop/Web transport
- [x] Implement configurable cloud notification gateway provider and delivery routing
- [x] Add native Web Push/APNs/FCM provider credential wiring and real delivery
  acceptance entrypoint (`scripts/push-acceptance.sh`); execute it once external
  gateway credentials and device tokens are supplied
- [x] Implement device registration
- [x] Implement multi-device sync with cursor/idempotency/conflict policy
- [x] Add cloud integration and recovery acceptance tests

### Phase 12: Web, iOS and Android clients

- [x] Complete Web/PWA login, task list, trace, evidence, approval and notification flows
- [x] Add iOS SwiftUI client using generated contract and cloud transport
- [x] Add Android Kotlin/Jetpack Compose client using generated contract and cloud transport
- [x] Add platform-specific push/background refresh boundaries and tests

### Phase 13: Operations and release

- [x] Add metrics, structured logs, health checks and release diagnostics
- [x] Add backup/restore runbooks for local and cloud deployments
- [x] Add release artifact manifest and optional signature path
- [x] Run the local acceptance matrix and update all documentation
- [ ] Run strict release acceptance with external credentials and Windows runner

### Phase 14: MVP UI/live path closure

- [x] Fix generated browser client fetch binding and verify the real workspace in a browser
- [x] Make Desktop task creation and candidate scans use the current market snapshot/provider date
- [x] Make Desktop Rules view render the selected task's evaluated gate result
- [x] Default the Tauri runtime path to AKShare while preserving explicit fixture replay
- [x] Add Desktop GUI smoke to the acceptance runner
- [x] Make iOS and Android new-review actions use the Asia/Shanghai trading date
- [ ] Execute real DeepSeek/Tushare release checks with injected credentials
- [ ] Execute Windows build, MSI, launch and native notification acceptance
- [ ] Execute external Web Push/APNs/FCM delivery and long-run freshness/P95 gates

真实 Provider/LLM release gate 的 CI 入口已补齐：
`.github/workflows/release-gates.yml` 会在手动注入仓库 Secret 后运行；
上述条目仍保持未完成，直到 workflow 产生真实运行证据。

### Phase 20: Point-in-time research hardening

- [x] Pass task `as_of` into live fundamentals and news provider calls
- [x] Fix Tushare news date filtering when rows omit `ts_code`
- [x] Add runtime and adapter regressions for historical research boundaries
- [x] Expose provider capability call latency, error rate and P95 in runtime metrics
- [ ] Execute credentialed DeepSeek/Tushare and Windows release gates
- [ ] Collect long-run external-provider and native-notification evidence

### Phase 15: Complete documented Tool Layer and semantic memory

- [x] Implement every tool named in `docs/DATA_RULES_EVENTS.md`
- [x] Persist user-scoped watchlists and structured semantic memories
- [x] Expose watchlist/memory APIs with OpenAPI and generated client coverage
- [x] Add Local and PostgreSQL repository parity migrations and user-scope tests

### Phase 16: Provider resilience and LLM cost observability

- [x] Add configurable provider retry and exponential backoff
- [x] Add provider circuit breaker with cooldown and health diagnostics
- [x] Audit provider retry scheduling and fallback routing
- [x] Persist LLM usage, request count and estimated cost for SQLite/PostgreSQL
- [x] Expose LLM usage in task detail, `/api/metrics` and Desktop Trace
- [x] Add SQLite/PostgreSQL migration parity and regression coverage

### Phase 17: Rule retrospective closure

- [x] Add immutable task retrospective storage with SQLite/PostgreSQL parity
- [x] Expose user-scoped retrospective read/write API and OpenAPI contract
- [x] Add Desktop retrospective form and task detail display
- [x] Add Local, Cloud and temporary PostgreSQL E2E coverage

### Phase 12 continuation: Mobile and multi-device completion

- [x] Add device unregister lifecycle to the Cloud API and generated clients
- [x] Add iOS device registration, incremental sync and Keychain token persistence
- [x] Add Android device registration, incremental sync and Keystore-backed token persistence
- [x] Add iOS background refresh scheduling boundary
- [x] Add Android WorkManager refresh boundary
- [x] Add Web PWA manifest and service worker shell
- [x] Verify Python, Swift, Android and Web builds after the slice

## Current evidence

- 最新修正：live provider fallback 只允许在 AKShare/Tushare 等真实
  provider 之间切换；fixture 仅在显式 `PIA_DATA_PROVIDER=fixture` 或
  Replay 中使用。真实 provider 失败不会再伪造 fixture 成功。
- Research Workspace approval actions now include `REQUEST_MORE_RESEARCH`
  and `MARK_AS_WATCH` across Local/Cloud API, OpenAPI, generated clients and
  Desktop UI; follow-up tasks and user-scoped watchlists are persisted and
  audited.
- Mobile failure-state task takeover now calls the authenticated Cloud API on
  iOS and Android and refreshes task context after completion.
- Mobile task detail now consumes authenticated SSE on iOS and Android and
  refreshes live trace, decision, evidence and status.
- `./scripts/test.sh`: **197 tests passed**
- `./scripts/acceptance.sh`: local mode passed after the point-in-time
  freshness hardening.
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`: latest open date passed with
  `quality=verified`, `market_snapshot_quality=verified`, universe `7,593`,
  field completeness `1.0`, and no failures.
- Point-in-time hardening rejects latest-only market snapshots for older dates
  and filters fundamentals/news to the requested date. AKShare now assembles
  historical aggregate snapshots from date-scoped bars, indices and sectors;
  the three-date live freshness gate passed. Longer operational windows and
  Tushare fallback evidence remain open.

- Earlier baseline: `./scripts/test.sh`: 143 tests passed
- `./scripts/e2e.sh`, `./scripts/cloud-e2e.sh` and
  `./scripts/postgres-cloud-e2e.sh`: retrospective write/read, audit and
  user-scope checks passed
- Cloud scheduler CLI flag and `PIA_START_SCHEDULER=1` process boundary added;
  regression suite now passes with 140 tests and `cloud-e2e.sh` remains green.
- 当前最新回归：通知 delivery receipt、DeepSeek 本地 HTTP transport、
  ModelRouter/error mapping 和 Windows artifact gate 改动后，
  `./scripts/test.sh`：141 tests passed；
  `./scripts/acceptance.sh`：local mode passed（含完整 Local/Cloud、临时
  PostgreSQL、恢复/混沌、移动端、Tauri 和 macOS packaged lifecycle/sidecar
  health）。AKShare 的 7,593 标的覆盖修复仍保留在历史验证记录中。
- `./scripts/acceptance.sh`: local mode passed (REST/SSE, positive approval,
  metrics, cloud auth/isolation/leases, replay, Web build, iOS/Android/Web
  acceptance, Tauri compile and macOS sidecar health)
- `./scripts/desktop-ui-smoke.sh`: browser-level workspace load, task creation,
  evidence/trace rendering, selected-task Rules gate and 390×844 responsive
  layout assertion passed
- `./scripts/scheduler-e2e.sh`: real local Runtime market-close dispatch,
  task execution and dedupe passed
- `./scripts/cloud-scheduler-e2e.sh`: authenticated Cloud scheduler health,
  stop/start lifecycle and process boundary passed; included in acceptance
- Lease release now enforces the authenticated user scope and records
  `TASK_LEASE_RELEASED` under the owning user; regression tests cover
  cross-user rejection and sync isolation.
- `./scripts/desktop-lifecycle-smoke.sh`: packaged macOS app startup, sidecar
  startup, exit and process-group cleanup passed
- `./scripts/freshness-e2e.sh`: deterministic 1000-case temporal quality soak passed
- `./scripts/provider-freshness-e2e.sh`: AKShare freshness passed for the
  latest 10 provider-calendar open dates, `2026-10-26` through `2026-11-06`;
  all dates were `verified`, market snapshots were `verified`, field
  completeness was `1.0`, and there were no failures. Long-run and Tushare
  fallback evidence remain open.
- 2026-11-07 当前复核：`PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh`
  通过，terminal success rate `1.0`，P95 `0.063s`；同日真实 AKShare
  freshness gate 对 `2026-11-04`、`2026-11-05`、`2026-11-06` 均为
  `quality=verified`、`market_snapshot_quality=verified`、字段完整率
  `1.0`，无 failures。
- Provider freshness 现在支持从交易日历自动解析最近 N 个开市日；
  `PIA_FRESHNESS_LOOKBACK_DAYS=5` 的真实 AKShare gate 已覆盖
  `2026-11-02` 至 `2026-11-06`，全部 verified。
- `./scripts/e2e.sh`: isolated temporary DB paths; REST + finite SSE passed
- `./scripts/cloud-e2e.sh`: authentication, user isolation and leases passed
- `./scripts/cloud-backup-restore-e2e.sh`: temporary PostgreSQL `pg_dump` /
  `pg_restore` and DuckDB snapshot recovery passed
- `./scripts/postgres-cloud-e2e.sh`: temporary PostgreSQL Cloud API
  authentication, approval, leases, isolation, events and sync passed
- temporary PostgreSQL cluster `cloud-e2e.sh`: migration parity, auth/isolation, leases, device sync and idempotency passed
- 2026-11-07 temporary PostgreSQL 17 cluster: `cloud-e2e.sh` passed with
  `PostgresDatabase`, including task cancellation, portfolio/audit/event isolation,
  leases and device lifecycle
- `./scripts/recovery-e2e.sh`: restart recovery, retry and independent worker passed
- `./scripts/chaos-e2e.sh`: worker crash, recovery and retry passed
- `./scripts/sla-e2e.sh`: 20-task local success-rate/P95 gate passed (`1.0`, `0.060s`)
- 最新 acceptance run 的本地 SLA P95 为 `0.070s`；本次结果在
  `timeout_seconds=300` 内，长期统计仍未建立
- `PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh`: 200-task local soak passed
  with terminal success rate `1.0` and P95 `0.058s`; external-provider soak is
  still pending
- `python3 scripts/generate_ts_client.py --check`: passed after Desktop/Web integration
- `npm run build` and `npm run build:web`: passed with generated transport and Web login
- Cloud smoke: CORS preflight, 401 isolation, authenticated health and structured request logs passed
- `./scripts/replay.sh`: fixture replay passed
- `npm run build` and `npm run build:web`: passed
- `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml`: passed
- `swift test --package-path apps/ios/PiaMobileClient`: 5 tests passed
- `swift build --package-path apps/ios/PiaMobileClient --product PiaApp`: passed
- `ANDROID_HOME=/Users/kingiol/Library/Android/sdk ./apps/android/gradlew --no-daemon --project-dir apps/android :app:assembleDebug`: passed
- `./scripts/mobile-acceptance.sh`: iOS transport/push-token tests, SwiftUI build,
  Android `:app:assembleDebug` (auto-detected
  `/Users/kingiol/Library/Android/sdk`) and Web Push service-worker syntax check
  passed
- Cloud notifications now support platform-specific Web Push/APNs/FCM gateway
  routing with per-channel credentials, token filtering and delivery receipts;
  real provider credentials and external delivery acceptance remain open
- Tushare adapter now maps optional index and Shenwan sector snapshots, so a
  credentialed fallback can satisfy the same market snapshot completeness gate;
  real quota/auth/provenance acceptance still requires `TUSHARE_TOKEN`
- `./scripts/native-notification-smoke.sh`: macOS `DELIVERED` from `local-native`
- `POST /api/tasks/{task_id}/cancel`: local/cloud E2E passed with `TASK CANCEL PASS`;
  append-only `TASK_CANCELLED` audit/event and generated TypeScript client are covered
- packaged sidecar `health --json`: `status=ok`; latest probe completed in about 10.6s
- Candidate scan is now filtered by the authenticated user's allowed asset types and
  universe; priority preemption and cancellation wait behavior are user-scoped and
  covered by regression tests
- Device response contracts now use the repository's `last_seen_at` field and the
  generated TypeScript model is synchronized
- `./scripts/release-manifest.sh`: generated SHA-256 artifact manifest
- macOS debug `.app` built from `apps/desktop/src-tauri`
- packaged `.app` contains `Contents/MacOS/pia-runtime` and passed a health probe
- live AKShare snapshot smoke: version `1.20.35`, 20 indices, 20 sectors and
  7,593 instruments returned (5,927 stocks and 1,666 ETFs)
- live DataWorker sync: `as_of=2026-11-06` returned `quality=verified`, `market_snapshot_quality=verified`, no request failures, 7593 universe rows and 12 research sources
- release-mode acceptance was not run because `DEEPSEEK_API_KEY` is absent from the local shell; `TUSHARE_TOKEN` is also absent for fallback acceptance
- Latest recheck: `./scripts/test.sh` passed 140 tests and
  `./scripts/acceptance.sh` passed in local mode after the lease audit
  isolation fix. `./scripts/release-preflight.sh` still blocks on Windows
  MSI/host evidence and real DeepSeek/Tushare credentials; external push
  credentials remain outside the local acceptance gate.
- `scripts/push-acceptance.sh` now provides the real external push acceptance
  path for configured Web Push/APNs/FCM gateways; it is wired into release
  acceptance and the release-gates workflow, but cannot run without gateway
  credentials and a disposable test device token.
- Latest local acceptance after Paper Broker and SMTP Email changes passed; release
  blockers remain Windows host/MSI evidence and real DeepSeek/Tushare credentials.
- Phase 15 tool/memory slice: 122 tests passed; `e2e.sh` now covers
  watchlist save and semantic memory save/search with user scoping.
- remaining release blockers include real DeepSeek runtime evidence, Windows packaging, native notification delivery, long-run SLA evidence and Tushare fallback/provenance verification
- Windows PowerShell scripts and CI matrix are present but require a Windows runner to provide build/package evidence
- `scripts/windows-acceptance.ps1` now exercises packaged sidecar health, HTTP task
  execution, evidence persistence and device lifecycle on a Windows runner; CI invokes
  it after the Windows Tauri build
- OpenAPI now declares every runtime API operation, including rules, market, portfolio, audit,
  scheduler, data sync and device lifecycle endpoints; a real local webhook gateway delivery
  test verifies JSON payloads, bearer authentication and `DELIVERED` receipts
- iOS cloud endpoint is configurable through `pia.cloud_base_url` / `PIA_CLOUD_URL`;
  Android endpoint is injected with `-PpiaCloudUrl`, and both native clients build successfully
- 2026-11-07 历史复核记录曾为 99/112/113 tests；当前最新复核为 114 tests。
  `./scripts/acceptance.sh`、`./scripts/cloud-e2e.sh`、
  `./scripts/native-notification-smoke.sh` 和 `git diff --check` 均通过；
  重新打包的 macOS sidecar health 返回 `status=ok`（冷启动约 10.86 秒）。
  DeepSeek、Tushare、Windows runner 仍未配置；PostgreSQL cloud E2E 已在
  临时 PostgreSQL 17 集群通过。
- 2026-11-07 移动端推送边界：Web Push subscription、iOS APNs token upload、
  Android push-token storage 和 mobile acceptance runner 已实现并通过构建/契约
  测试；真实 APNs/FCM/Web Push gateway 投递仍需部署凭据和真机/浏览器证据。
- 2026-11-07 当前复核：`DEEPSEEK_API_KEY`、`TUSHARE_TOKEN`、Windows runner
  和 `PIA_POSTGRES_DSN` 均未设置；因此 release acceptance、Windows
  package/launch 和真实 provider acceptance 仍未执行。Android SDK 由
  `scripts/mobile-acceptance.sh` 自动探测并完成 debug build。
- 2026-11-07 runtime input precedence fix：显式 task portfolio fixture 现在
  优先于用户最新持仓快照；无显式 fixture 时仍使用用户最新导入持仓。新增回归
  测试和 Local/Cloud positive approval E2E 均通过。
- 2026-11-07 mobile sync completion：iOS foreground/background refresh 和
  Android foreground/WorkManager refresh 现在实际消费 `/sync` 并持久化 cursor；
  Swift tests/build 和 Android debug build 均通过。
- 2026-11-07 acceptance recheck：`./scripts/acceptance.sh` local mode passed
  after adding the deterministic `Research Manager` graph node; replay traces
  include `Research Manager`, and the run completed with 98 Python tests,
  positive approval E2E, recovery/chaos/SLA, mobile acceptance, Tauri compile,
  and packaged macOS sidecar health.
- 2026-11-07 cloud hardening：Cloud E2E now covers user-b positive approval
  and user-scoped `APPROVAL_RECORDED`; acceptance also runs the temporary
  PostgreSQL backup/restore drill.
- 2026-11-07 PostgreSQL Cloud acceptance：`postgres-cloud-e2e.sh` now starts
  an isolated UTF-8 PostgreSQL cluster and runs the full Cloud E2E against
  `PostgresDatabase`; acceptance invokes this path automatically.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Scheduler test double had no `settings` attribute | 1 | Use `getattr(runtime, "settings", None)` and rerun all tests |
| `cargo tauri build` from repository root resolved `beforeBuildCommand` against the wrong working directory | 1 | Use the documented `scripts/desktop.sh` / run from `apps/desktop/src-tauri`; packaging command itself passes there |
| Direct system `python3` lacked project `duckdb` dependency | 1 | Use the repository entry point `./scripts/python.sh` for focused and full tests |

## Decisions

- Keep Rules and order boundaries deterministic and outside LLM control.
- Keep real credentials in local runtime environment only.
- Treat fixtures as replay data, never as proof of live provider readiness.
- Do not mark a phase complete from code presence alone; require scoped verification.

## 2026-11-07 Continuation: Temporal Quality and Release Preflight

- [x] Validate `as_of`, `observed_at`, `expires_at` and publication timestamps
- [x] Downgrade invalid provider rows to `unavailable`/`stale`
- [x] Emit explicit temporal quality failures from `DataWorker`
- [x] Add future-date, ordering and expiry regression tests
- [x] Add release preflight for artifacts, credentials, platform and push readiness
- [ ] Obtain real DeepSeek/Tushare credentials and execute release mode
- [ ] Run Windows package/launch/notification acceptance
- [ ] Run real external push and long-run provider freshness acceptance

## 2026-11-08: Ten-day live freshness recheck

- [x] Run AKShare freshness over the latest 10 provider-calendar open dates
- [ ] Obtain real DeepSeek/Tushare credentials and execute release mode
- [ ] Run Windows package/launch/notification acceptance
- [ ] Run real external push and longer production-window freshness acceptance

## Phase 18: Research Workspace completion

- [x] Add task status grouping in Desktop/Web workspace
- [x] Add stable task deep links and copy-link actions
- [x] Add authenticated task data/raw snapshot inspection endpoint
- [x] Add replay endpoint that preserves task input and parent linkage
- [x] Add Desktop watchlist view and candidate-to-watchlist action
- [x] Add UI smoke and API regression coverage for the new workspace paths
- [x] Add explicit Evidence `Used by` display and evidence-level stable links
- [x] Add dedicated keyboard navigation/focus affordances
- [x] Verify mobile layout order and horizontal overflow at 390×844
