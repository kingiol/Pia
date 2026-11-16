# Progress Log

## 2026-11-11: Cloud Runtime Naming

- Standardized runtime modes as `local` / `cloud`, including CLI, settings,
  worker defaults, webhook provider, mobile endpoints, session storage,
  operational scripts and product documentation.
- Kept legacy CLI, environment, native credential and client settings readable.
  New Cloud settings take precedence; runtime health reports `cloud`.
- Preserved migration filenames and existing data files. Cloud backup/restore
  falls back to an existing legacy analytics path when no explicit path is set.
- Passed 214 Python tests, generated client consistency, Desktop/Web builds,
  iOS tests and shell build, Android APK build, Local/Cloud API E2E, Cloud
  scheduler, isolated PostgreSQL E2E, backup/restore, recovery and chaos checks.
- Updated a stale chart contract assertion to the existing localized titles.
- Standalone TypeScript checking remains blocked by pre-existing type errors;
  diagnostics match the unchanged HEAD baseline after line normalization.
  Packaged desktop binaries and real-device delivery were not revalidated.

## 2026-11-09: Decision Journal Slice 1

- Added the read-only `DecisionJournal` projection over existing tasks,
  decisions, evidence, approvals and retrospectives.
- Added user-scoped `GET /api/journal` with symbol, intent, outcome, rule
  snapshot, date and cursor filters.
- Added a desktop/web Decision Journal view with summary counts, filters and
  links back to the original research task.
- Added journal API contract generation and focused regression coverage.
- Validation passed: `pnpm build`, Python bytecode compilation, OpenAPI YAML
  parsing and a journal projection smoke check. Full Python tests remain
  environment-blocked because this workspace lacks `pytest`, `pydantic` and
  `PyYAML`.

## 2026-11-10: Decision Journal Slice 2

- Added deterministic `GET /api/journal/summary` and
  `GET /api/journal/patterns` projections with user scoping, intent grouping,
  rule snapshot grouping, action normalization and comparable `return_pct`
  statistics.
- Added Desktop/Web Journal tabs for `Journal`, `Patterns` and `Memory`.
  Memory candidates remain read-only observations and are not written to
  `semantic_memories` or future task context.
- Added regression coverage for summary counts, missing outcomes, rule version
  separation, candidate thresholds and cross-user isolation.
- Validation passed: `pnpm build`, Python bytecode compilation,
  `tests.test_journal` (4 tests), `scripts/trust-ui-smoke.sh`, Journal
  Playwright tab smoke, and `git diff --check`.
- The full contract suite still has the pre-existing iOS wording mismatch:
  `tests.test_contracts.ContractTest.test_mobile_failure_state_exposes_task_takeover`
  expects `Take over`, while the current iOS UI uses `人工接管`.

## 2026-11-10: Decision Journal Slice 3

- Added the user-scoped `memory_candidates` derived table with stable candidate
  keys, `SYSTEM_DERIVED` source type, `CANDIDATE` status, source task IDs,
  rule snapshot IDs and deterministic outcome statistics.
- Added `POST /api/journal/memory-candidates`; the cloud recomputes the
  candidate from Journal data and rejects candidates below the minimum sample
  threshold.
- Added idempotent candidate refresh and audit events. Candidates remain
  separate from `semantic_memories`, so they cannot enter future research
  context before a later confirmation flow.
- Desktop/Web Memory tab now lets the user save an eligible candidate and shows
  its persisted state.
- Validation passed: `tests.test_journal` (6 tests), generated contract checks,
  `pnpm build`, Python bytecode compilation, `git diff --check`, and a real
  browser save-state smoke.

## 2026-11-10: Decision Journal Slice 4

- Added `memory_candidates` review lifecycle with `CONFIRM`,
  `EDIT_AND_CONFIRM`, `REJECT` and `ARCHIVE` actions, reviewer metadata,
  notes and audit events.
- Added user-scoped `POST /api/journal/memory-candidates/{candidate_id}/review`
  and synchronized OpenAPI/generated TypeScript contracts.
- Added `confirmed_memories` to task context and the read-only LLM research
  payload. Candidates remain excluded until a user confirms them.
- Desktop/Web Memory view now supports confirm, edit-and-confirm, reject and
  archive actions.
- Validation passed: `tests.test_journal` (7 tests), `pnpm build`, Python
  bytecode compilation and `git diff --check`. The full contract suite still
  has the pre-existing iOS `Take over` wording mismatch.

## 2026-11-10: Decision Journal Slice 5

- Added `memory_candidate_usages` with user-scoped, task-scoped,
  idempotent `TASK_CONTEXT_INJECTED` records.
- Confirmed memories are recorded when a research task loads its context;
  rejected and archived candidates cannot be recorded as used.
- Added deterministic usage summaries to Journal patterns and
  `GET /api/journal/memory-candidates/{candidate_id}/usage`.
- Desktop/Web Memory cards now show later task references, usage count and
  comparable outcomes after use.
- Validation passed: Journal and cloud sync regression tests and Desktop
  production build, rechecked together with Slice 6.

## 2026-11-10: Decision Journal Slice 6

- Added per-usage user feedback with `HELPFUL`, `NOT_HELPFUL` and `UNCERTAIN`
  ratings, including update-in-place behavior and audit events.
- Added deterministic feedback summaries and non-automatic recommendations:
  `KEEP`, `REVIEW_SUGGESTED` and `ARCHIVE_SUGGESTED`.
- Added `POST /api/journal/memory-candidates/{candidate_id}/feedback` and
  extended the usage response with feedback details.
- Desktop/Web Memory cards now let users rate the latest recorded use and see
  the resulting review recommendation.
- Feedback submissions include the displayed usage ID, preventing a newer
  task from silently changing the feedback target.
- Confirmed memories expose a manual archive action; archived memories leave
  future task context while retaining usage and feedback history.
- Added focused regression coverage for per-usage updates, no-usage rejection,
  user isolation and archive suggestions that preserve confirmed status.
- Validation passed: `tests.test_journal tests.test_cloud_sync` (16 tests),
  Desktop/Web production builds, generated TypeScript client check, OpenAPI
  parsing, feedback migration parity, Python bytecode compilation and
  `git diff --check`.
- Isolated browser verification passed: feedback update changes the summary,
  confirmed memory can be manually archived, two feedback records remain
  available afterward and archived memory is excluded from task context.
  Desktop and 390px screenshots were inspected; no horizontal overflow was
  found at 390px.
- Contract suite at this point: 16 passed, with the iOS wording assertion
  still pending localization alignment; it was fixed in Slice 7.
- Standalone `tsc --noEmit` remains blocked by missing React declarations,
  missing Vite `ImportMeta.env` declarations and the existing Push
  `Uint8Array`/`BufferSource` type mismatch. Vite build success does not imply
  this type check passed.

## 2026-11-10: Decision Journal Slice 7

- Added structured retrospective windows: `T+5`, `T+20` and
  `USER_RECORDED`.
- Retrospectives now normalize and validate benchmark return, excess return,
  market regime and position size fields (0–100%) while retaining arbitrary
  extension fields for compatibility.
- Journal summaries and patterns expose horizon counts, average benchmark
  return and average excess return; Memory candidate content carries the same
  deterministic evidence.
- Patterns and Memory cards display benchmark and excess return alongside
  absolute return, so broad market movement is not presented as decision
  quality.
- Desktop/Web task detail now supports multiple retrospective entries with
  localized controls for action, window, return, benchmark, position size,
  market regime and notes.
- Updated the shared retrospective schema and generated TypeScript client.
- Fixed the mobile takeover contract assertion to accept the product's Chinese
  `人工接管` label.
- Validation passed: `./scripts/test.sh` (206 tests), Desktop/Web production
  builds, OpenAPI/schema parsing, generated client check and `git diff --check`.
- Browser inspection passed for the structured retrospective form and existing
  retrospective timeline. Standalone `tsc --noEmit` remains blocked by the
  repository's pre-existing React/Vite/Push type declaration issues.

## 2026-11-09: Trust recovery and event visibility

- Stale task deep links now wait for the task list, clear missing selections and
  return to the Overview instead of polling a deleted task indefinitely.
- Runtime/API errors are mapped to actionable Chinese messages; raw JSON error
  payloads such as `task_not_found` are no longer shown to users.
- The workspace now distinguishes connecting, replay, live, degraded and
  unavailable data states in the top bar and local runtime footer.
- Overview now surfaces the latest event notifications so users can see why Pia
  is asking for attention and open the linked research task directly.
- Added `scripts/trust-ui-smoke.sh` covering stale task recovery, raw error
  suppression and mobile horizontal overflow.
- Validation passed: `pnpm run build`, `pnpm run build:web`,
  `./scripts/trust-ui-smoke.sh`, and `git diff --check`.

## 2026-11-09: Ordinary-investor UX redesign completed

- Shared Desktop/Web workspace now has a four-step first-run checklist:
  investor profile, holdings, data readiness and first review.
- Replaced the raw JSON investor profile editor with ordinary form controls for
  objective, risk tolerance, drawdown, asset types and universe.
- Added warm editorial visual system, clearer Chinese labels, live/replay
  provenance badge, better error actions and responsive mobile-web layout.
- iOS now uses native Today/Research/Notifications tabs with a first-review
  setup card and Chinese task/approval copy.
- Android now uses native Today/Research/Notifications navigation with the same
  first-review card, summary cards and readable status labels.
- Updated the pilot guide to describe the first-launch flow and replay-data
  boundary.
- Validation passed: `npm run build`, `npm run build:web`, `swift test`,
  `ANDROID_HOME=/Users/kingiol/Library/Android/sdk ./gradlew :app:assembleDebug`,
  and `git diff --check`.

## 2026-11-08: UX redesign started

- Audited current Desktop/Web, iOS and Android entry points.
- Confirmed Desktop/Web share the React workspace; mobile clients are native
  SwiftUI and Jetpack Compose.
- Started the UX redesign phase in `task_plan.md`.

## 2026-11-08: Final release verification

- Loaded `config/example.env` and ran release acceptance with
  `PIA_ACCEPTANCE_MODE=release PIA_ACCEPTANCE_AS_OF=2026-11-06`.
- Python regression passed **197 tests**; generated TypeScript client check and
  `git diff --check` passed.
- Release acceptance passed Local/Cloud/temporary PostgreSQL, scheduler and
  dedupe, backup/restore, restart recovery, worker chaos, SLA, Replay,
  Desktop UI, Web/iOS/Android, Tauri, packaged macOS lifecycle, sidecar health,
  native notification and live DeepSeek structured/tool/streaming plus
  `StockResearch`.
- Independent AKShare freshness for `2026-11-06` passed with
  `quality=verified`, `market_snapshot_quality=verified`, universe `7,593`,
  field completeness `1.0`, no failures, `daily_bars=1`,
  `fundamentals=1` and `research_sources=12`.
- Tushare was intentionally skipped. Strict preflight remains blocked by
  `windows_msi`, `windows_host` and `tushare_credentials`; external Push
  credentials remain a full-milestone blocker.
- Closed the documented `get_index_series` gap: fixture, AKShare and Tushare
  adapters now expose a date-range series contract with symbol filtering,
  provenance and regression coverage.
- Closed the mobile live-trace gap: iOS and Android now consume authenticated
  task SSE streams and refresh task detail on events. iOS tests and Android
  debug compilation passed.
- Full release acceptance was rerun after the mobile change and passed across
  Local/Cloud/PostgreSQL/recovery/chaos/SLA/Replay/Desktop/Web/iOS/Android/
  Tauri/macOS plus live DeepSeek and AKShare checks.

## 2026-11-08: Latest MVP verification and cloud control hardening

- Loaded `config/example.env` and ran release acceptance successfully.
- Python regression now passes **195 tests**.
- Real AKShare freshness for `2026-11-06` passed with verified market and
  snapshot quality, universe size `7,593`, field completeness `1.0`, and no
  failures.
- DeepSeek structured output, tool calling, streaming and live `StockResearch`
  runtime passed. Tushare was intentionally skipped.
- Persisted `pause_requested` is now authoritative for pause/resume across
  separate API and worker runtimes; a shared-database regression covers the
  cross-process control boundary.
- Fixed the deterministic freshness fixture to use a date that remains in the
  future as the calendar advances.
- Strict release blockers remain Windows MSI/host evidence and Tushare
  credentials; external push credentials remain a full-milestone blocker.

## 2026-11-08: Release recheck and lease isolation hardening

- Re-ran release acceptance with `config/example.env` loaded and
  `PIA_ACCEPTANCE_AS_OF=2026-11-06`; the full matrix passed with 191 Python
  tests.
- Real AKShare freshness passed for `2026-11-06`: market and snapshot quality
  were `verified`, universe size was 7,593, field completeness was 1.0, and
  there were no failures.
- DeepSeek structured output, tool calling, streaming and live `StockResearch`
  passed. Tushare and external push acceptance were intentionally skipped.
- Hardened Cloud lease heartbeat authorization to enforce the task owner's
  user scope, with a regression test for cross-user heartbeat rejection.
- Post-patch Python regression passed **192 tests**; Cloud E2E additionally
  verified the cross-user heartbeat request is rejected at the HTTP boundary.

## 2026-11-08: Credentialed release acceptance and fixture isolation

- Loaded `config/example.env` with the configured DeepSeek credential and ran
  `PIA_ACCEPTANCE_MODE=release` for `as_of=2026-11-06`.
- Full release acceptance passed: 190 Python tests, generated client check,
  Desktop/Web builds, Local/Cloud/temporary PostgreSQL E2E, recovery/chaos,
  SLA, Replay, Desktop UI, iOS/Android, Tauri compile, packaged macOS
  lifecycle, sidecar health and native notification.
- Real AKShare freshness passed with `quality=verified`,
  `market_snapshot_quality=verified`, universe `7,593`, field completeness
  `1.0` and no failures.
- DeepSeek structured output, tool calling, streaming and live `StockResearch`
  runtime task passed. Tushare was intentionally skipped because its token is
  still a placeholder.
- Fixed release acceptance contamination from `PIA_DATA_PROVIDER=akshare` and
  `PIA_DB_PATH=.pia/pia.sqlite3`: fixture-based cloud, replay, SLA, recovery
  and chaos stages now use fixture mode and temporary databases; recovery
  creates its supplied root directory.
- `release-preflight.sh` now reports only `windows_msi`, `windows_host` and
  `tushare_credentials` as MVP blockers; full milestone external push
  credentials remain unverified.
- The final rerun also passed the Cloud Provider health endpoint and the
  user-scoped sync cursor regression; Tushare remained intentionally skipped.

## 2026-11-08: MVP audit recheck and provider/SSE hardening

- Re-ran `./scripts/acceptance.sh`: local acceptance passed end to end.
- Python suite now passes **189 tests**, including regressions for task-level
  expiration and the change that makes
  research Provider fallback quality-aware.
- Task-level `expires_at` now transitions running tasks to terminal `EXPIRED`,
  records `TASK_EXPIRED`, emits the terminal status event and preserves the
  immutable audit trail.
- Research calls now try the next live Provider when a primary
  `fundamentals`, `news`, `filings` or `company_profile` result is
  `partial`/`unavailable`; when no better Provider exists, the degraded result
  remains visible and is audited instead of being promoted to `verified`.
- SSE task streams now close on `DONE` and `EXPIRED` as well as the existing
  terminal statuses.
- TypeScript client was regenerated from the task contract; generated client
  check and `git diff --check` passed.
- Real AKShare freshness for `2026-11-06` passed with
  `quality=verified`, `market_snapshot_quality=verified`, universe `7,593`,
  field completeness `1.0` and no failures.
- `./scripts/release-preflight.sh` still reports
  `mvp_release_ready=false`. Remaining release evidence blockers are
  `windows_msi`, `windows_host`, `deepseek_credentials` and
  `tushare_credentials`; full milestone external push credentials are also
  unavailable.
- `PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh` passed again with terminal
  success rate `1.0` and P95 `0.065s`; this is local fixture evidence and does
  not replace long-run external-provider evidence.
- Release-preflight/push acceptance shell syntax and focused regression checks
  passed (`4/4` tests).
- Release acceptance now validates the required DeepSeek credential and
  `akshare` provider before starting the expensive local matrix, so missing
  release inputs fail fast with an explicit message.

## 2026-11-08: Live snapshot and research reuse

- Live candidate scans and research tasks now reuse the newest persisted
  `verified`/`partial` market snapshot for the requested `as_of` when no
  explicit fixture or snapshot id is supplied.
- Live research results are cached per provider, symbol and `as_of` for the
  lifetime of a runtime, so repeated tasks do not re-fetch fundamentals, news,
  filings and company profile unnecessarily.
- Added regression coverage proving persisted snapshot reuse does not call the
  live market provider and repeated research preserves per-capability
  provenance without another provider round trip.
- Validation: focused tests passed and the full Python suite passed with
  **184 tests**.

## 2026-11-08: Provider-backed company profile research

- Added a `company_profile` capability to the AKShare and Tushare adapters.
- AKShare uses the CNINFO company profile endpoint with an Eastmoney metadata
  fallback; Tushare uses `stock_basic` metadata.
- Live StockResearch now records the profile provider in provenance and no
  longer synthesizes `industry=unknown` when provider metadata is available.
- Provider unavailability remains explicit through a partial profile and an
  audit event, so fundamentals/news/filings research can still be recovered.
- Added adapter and runtime regressions.
- Validation: focused adapter/runtime tests passed (71 tests), and a live
  AKShare profile lookup for `600000.SH` returned verified company metadata.

## 2026-11-08: Research point-in-time runtime hardening

- Live `StockResearch` now passes the task `as_of` date to
  `get_fundamentals()` and `search_news()` through the provider router.
  Historical research can no longer silently query latest-only fundamentals or
  news results.
- Fixed Tushare news filtering so the requested date is enforced even when
  upstream rows omit `ts_code`; the previous boolean precedence could allow a
  future row through in that case.
- Added regressions covering provider request scoping and future Tushare news
  rejection.
- Focused runtime and adapter tests passed; `git diff --check` passed.

## 2026-11-08: ETF historical bars parity

- AKShare `get_daily_bars()` now routes ETF symbols to
  `fund_etf_hist_em`; Tushare routes ETF symbols to `fund_daily`.
- Both paths normalize the requested symbol and preserve provider metadata and
  quality state.
- Added contract tests for both providers.
- Validation: full suite passed with **179 tests**, generated client check and
  Desktop Vite build passed.

## 2026-11-08: Historical AKShare point-in-time snapshots

- Added an AKShare historical aggregate snapshot path for dates before the
  current trading date. It uses date-scoped stock/ETF daily bars, historical
  index data and historical industry data instead of latest-only spot data.
- Added bounded parallel fetching and provider-process caches for historical
  bars, indices, sectors and universe metadata. Coverage below 98% remains
  `partial`/`unavailable`; no latest values are used to fill missing history.
- Added an adapter contract test proving an older `as_of` uses historical bars
  and returns `point_in_time_scope=historical`.
- Live validation:
  `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-04,2026-11-05,2026-11-06
  PIA_AKSHARE_HISTORICAL_WORKERS=16 ./scripts/provider-freshness-e2e.sh`
  passed all three dates with `quality=verified`,
  `market_snapshot_quality=verified`, universe `7,593`, field completeness
  `1.0`, and no failures.
- Validation: full suite passed with **177 tests**, generated client check and
  Desktop Vite build passed.

## 2026-11-08: Credential-manager release path alignment

- Fixed release-mode acceptance to resolve `DEEPSEEK_API_KEY` through the same
  environment-first/native credential-manager path used by the runtime.
- Fixed Tushare provider freshness and release fallback checks to resolve
  `TUSHARE_TOKEN` through the native credential manager as well.
- Added regression coverage for native-manager Tushare resolution.
- Validation: focused credential/provider/preflight tests passed; the full suite
  passed with **173 tests**, generated client check passed, Desktop Vite build
  passed, and `git diff --check` passed.

## 2026-11-08: Current MVP completion audit

- Re-ran `./scripts/test.sh`: **176 tests passed**.
- Re-ran `./scripts/acceptance.sh`: local mode passed, including Local/Cloud/
  temporary PostgreSQL, recovery/chaos, SLA, replay, Desktop UI, Web/iOS/
  Android builds, Tauri compile, packaged macOS lifecycle, sidecar health and
  macOS native notification.
- Re-ran `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`: live AKShare freshness passed with
  `quality=verified`, `market_snapshot_quality=verified`, universe `7,593`,
  field completeness `1.0`, and no failures.
- Added point-in-time guards so latest-only market snapshots cannot satisfy older
  dates; fundamentals and news are filtered to the requested date. Historical
  AKShare aggregate snapshots are now available and verified across three dates.
- `git diff --check` passed.
- `./scripts/release-preflight.sh` still reports
  `mvp_release_ready=false`; strict release blockers remain Windows MSI/host
  evidence and real DeepSeek/Tushare credentials. Real external push
  credentials remain a full-milestone blocker.

## 2026-11-08: Mobile task takeover parity

- Added `Take over` controls for `RETRYABLE`, `FAILED` and `TIMEOUT` task
  details in the iOS SwiftUI and Android Compose clients.
- The controls call the existing authenticated takeover API and refresh the
  task context after the action.
- Added a cross-client contract regression for the takeover UI and forwarding.
- Validation: mobile acceptance passed, including iOS tests/build, Android
  debug build and Web Push service-worker syntax; the full Python suite passed
  (**172 tests**).

## 2026-11-08: Android approval action forwarding

- Fixed the Android Research Workspace action handler so `REQUEST_MORE_RESEARCH`
  and `MARK_AS_WATCH` call the authenticated Cloud approval endpoint instead of
  being silently ignored after the buttons were rendered.
- Unknown Android task actions now fail visibly instead of returning a fake
  successful empty response.
- Added a contract regression test that checks both actions are forwarded by the
  Android client.
- Validation: focused contract tests passed, the full Python suite passed
  (**170 tests**), and `./scripts/mobile-acceptance.sh` passed, including iOS
  tests, Swift build, Android debug build and Web Push service worker syntax.

## 2026-11-08: Desktop shell controls and responsive workspace hardening

- Added documented tray controls for runtime status, pausing/resuming scheduled
  tasks and quitting Pia; tray actions reuse the existing Scheduler API through
  the frontend event bridge.
- Closing the main window now hides it to the tray; only the tray Quit action
  exits the app and performs full Sidecar cleanup.
- Added a Topbar task/symbol search plus `Command/Ctrl+K` focus, and
  `Command/Ctrl+P` / `Command/Ctrl+Enter` shortcuts for Portfolio and New
  review actions.
- New reviews now return the workspace to Overview so the created task and trace
  are immediately visible.
- Fixed narrow viewport intrinsic-width overflow in detail panels and the
  mobile navigation strip.
- Validation: desktop contract tests, browser UI smoke (including shortcuts and
  390x844 overflow), Vite production build and Tauri `cargo check` passed.

## 2026-11-08: Web route persistence

- Added path-based Web workspace routing for `/overview`, `/market`,
  `/watchlist`, `/portfolio`, `/research`, `/research/:taskId`, `/profile`,
  `/rules`, `/data-health`, `/audit` and `/alerts`.
- Direct Web loads restore the selected view/task; navigation updates browser
  history without changing Tauri's static-resource query-link behavior.
- Browser UI smoke now verifies `/market` and `/research/:taskId` routes.
- Validation: Web/Desktop Vite builds and `desktop-ui-smoke.sh` passed.

## 2026-11-08: Topbar search and shortcut behavior

- Added a real task/symbol search field to the shared Desktop/Web Topbar.
  Searches match task id, trigger type, status, date and serialized target
  symbols, while preserving the full task counters.
- `Command/Ctrl+K` focuses the search field; `Command/Ctrl+P` changes to
  Portfolio; `Command/Ctrl+Enter` creates a review even while search is
  focused, while other form fields remain protected from accidental submits.
- Validation: contract tests, Vite builds and browser UI smoke passed.

## 2026-11-08: Windows release-gate workflow closure

- Added a dedicated `windows-release` job to
  `.github/workflows/release-gates.yml`.
- The job installs the Python/Node/Rust toolchains, builds the PyInstaller
  sidecar and Tauri MSI, verifies sidecar health, runs packaged Windows task
  and device lifecycle acceptance, runs the native notification smoke, and
  uploads the MSI, sidecar and release manifest.
- The workflow YAML parsed successfully on the local host. PowerShell syntax
  was not executable locally because `pwsh` is unavailable; the Windows runner
  remains the authoritative verification environment.

## 2026-11-08: MVP document audit and evidence provenance fix

- Re-ran the current MVP verification after reading `docs/PRD.md`,
  `docs/ACCEPTANCE.md`, `docs/MILESTONES.md` and `docs/MVP_AUDIT.md`.
- Found and fixed a real persistence gap: `Evidence.provider_id` was present in
  the model and API but was not stored in SQLite/PostgreSQL evidence rows.
- Added the `016_evidence_provider.sql` migration for both databases and updated
  `save_evidence()` so live market/news/filing evidence preserves its provider.
- `./scripts/test.sh`: **169 tests passed**.
- `./scripts/acceptance.sh`: local mode passed, including Local/Cloud/
  temporary PostgreSQL E2E, recovery/chaos, SLA, Desktop UI, mobile builds,
  Tauri compile, packaged macOS lifecycle, sidecar health and native
  notification smoke.
- `npm run build:web`: passed.
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`: passed with `verified`, universe
  `7,593`, field completeness `1.0`, and no failures.
- `./scripts/release-preflight.sh`: `mvp_release_ready=false`; Windows MSI/
  host evidence and real DeepSeek/Tushare credentials remain unavailable.

## 2026-11-08: MVP visualization coverage

- Added shared accessible chart primitives for Market breadth, Index trend,
  Portfolio exposure, Drawdown and Agent timeline.
- Charts are linked to the current snapshot/task date and source, show exact
  values beside bars, support keyboard focus and expose explicit empty states.
- Browser smoke now checks chart rendering on Market, Portfolio and Research
  routes.
- Validation: Web/Desktop builds, contract tests and browser UI smoke passed.

## 2026-11-08: Release gate dependency correction

- Release acceptance now requires `DEEPSEEK_API_KEY` and keeps the configured
  `TUSHARE_TOKEN` fallback checks optional, matching the documented release
  workflow.
- External Web Push/APNs/FCM acceptance runs when at least one gateway URL is
  configured; with no gateway configured it reports an explicit skip instead
  of blocking the MVP DeepSeek/data acceptance. Partial gateway configuration
  still fails through `push-acceptance.sh`.
- Updated `.github/workflows/release-gates.yml` to report optional Tushare and
  external push coverage instead of failing before the live acceptance starts.
- Validation: `bash -n scripts/acceptance.sh scripts/cloud-e2e.sh scripts/e2e.sh`
  and `git diff --check` passed.

## 2026-11-08: Metrics contract and credential portability hardening

- Added Local and Cloud HTTP E2E assertions for queue depth, active task count,
  oldest active task age, storage bytes and SQLite/PostgreSQL backend metrics.
- Declared the runtime system metrics fields in `contracts/openapi.yaml` and
  generated a typed `MetricsResponse` contract for the shared TypeScript client.
- Added OpenAPI contract coverage for the metrics system fields.
- Hardened Windows Credential Vault creation to pass the secret through stdin
  and an explicit PowerShell `-ArgumentList`; added Windows and Linux mutation
  contract tests.
- Validation:
  - `./scripts/test.sh`: **165 tests passed**.
  - `./scripts/e2e.sh`: Local metrics contract passed.
  - `./scripts/cloud-e2e.sh`: Cloud metrics contract passed.
  - `./scripts/postgres-cloud-e2e.sh`: PostgreSQL metrics contract passed.
  - `./scripts/acceptance.sh`: local mode passed.
  - `npm run build:web` and generated-client check passed.

## 2026-11-08: Runtime operations metrics

- Added worker heartbeat tracking to the shared observability snapshot.
- Added `/api/metrics` system fields for queue depth, active task count,
  oldest active task age, database backend and SQLite/DuckDB storage bytes.
- Added regression coverage for heartbeat and system metrics.
- Focused runtime/observability tests: **51 passed**.
- `git diff --check` and Python compilation passed.

## 2026-11-08: Native credential-manager support

- Added `pia_runtime.credentials.CredentialStore` with environment-variable
  precedence and native lookup/write/delete support for macOS Keychain, Linux
  Secret Service and Windows Credential Vault.
- Connected DeepSeek, Tushare, cloud auth, SMTP, webhook and push gateway
  secrets to the credential store without persisting values in task payloads,
  audit records or logs.
- Added `pia credentials set/status/delete`; `status` only reports a boolean.
- Added four regression tests covering precedence, placeholder fallback,
  argument-array access and placeholder rejection.
- `./scripts/test.sh`: **161 tests passed**.
- `./scripts/acceptance.sh`: local mode passed, including temporary
  PostgreSQL, recovery/chaos, Desktop UI, mobile builds, Tauri lifecycle,
  sidecar health and macOS native notification delivery.

## 2026-11-08: Active universe metadata gate closed

- Added official SSE ETF fund-list and SZSE ETF workbook listing-date sources.
- Added Eastmoney batch listing-date fallback for suspended/delisted stock rows,
  while retaining exchange-provided values as authoritative when available.
- Added robust `YYYYMMDD` parsing and metadata caching; inactive rows remain
  auditable without blocking eligible candidate scans.
- Real AKShare universe result: 7,593 rows across
  `main=3488`, `chinext=1453`, `star=622`, `bse=364`, `etf=1666`;
  all active rows have `exchange` and `listed_at`. Two inactive suspended rows
  (`920309.BJ`, `688827.SH`) have no upstream listing date and are reported
  separately.
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`: verified, field completeness `1.0`,
  7,593 universe rows, no failures.
- Added regression coverage for exchange-source merging and inactive metadata
  handling.

## 2026-11-08: MVP implementation audit recheck

- `./scripts/test.sh`: **155 tests passed**.
- `./scripts/acceptance.sh`: local mode passed, including Local/Cloud/
  temporary PostgreSQL E2E, replay, backup/restore, restart/chaos recovery,
  Desktop UI smoke, Web/iOS/Android builds, Tauri compile, packaged macOS
  lifecycle, sidecar health and macOS native notification delivery.
- `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
  ./scripts/provider-freshness-e2e.sh`: real Provider freshness passed with
  `market_snapshot_quality=verified`, 7,593 universe rows, completeness
  `1.0`, and no failures.
- `./scripts/release-preflight.sh`: `mvp_release_ready=false`; remaining MVP
  release evidence blockers are Windows MSI/host execution and real
  DeepSeek/Tushare credentials. External push credentials remain a
  full-milestone blocker.

## 2026-11-08: Agent contract alignment

- Added the missing `Sector Analyst` contract at `agents/sector.yaml`.
- Aligned `Technical Analyst`, `Risk / Rules Agent` and `Decision Agent`
  permissions with their declared tools; `submit_order` remains disabled.
- Added a contract test that every `agents/*.yaml` tool is present in the
  runtime permission matrix.
- `./scripts/test.sh`: **155 tests passed**.
- `./scripts/acceptance.sh`: local mode passed after the contract changes.

## 2026-11-08: Mobile approval action parity

- Added `REQUEST_MORE_RESEARCH` and `MARK_AS_WATCH` actions to the iOS and
  Android task approval views.
- Android approval controls now use a stacked layout to stay usable on narrow
  screens.
- Added a cross-client contract test for the five cloud approval actions.
- `./scripts/mobile-acceptance.sh`: iOS tests, Swift build, Android debug
  build and Web Push service-worker syntax all passed.

## 2026-11-08: Retry checkpoint persistence

- Retryable tasks now persist `_market_snapshot_id`,
  `_portfolio_snapshot_id` and `_checkpoint_stage` in `target_json`.
- Retried tasks inherit completed snapshot checkpoints and record a
  `TASK_RETRY_CREATED` audit event.
- Fixed the shared SQLite/PostgreSQL task update path so target changes are
  persisted instead of remaining in memory only.
- Added a regression covering an LLM credential failure after snapshot
  preparation; full suite now reports **157 tests passed**.

## 2026-11-08: Final local MVP verification

- `./scripts/test.sh`: **152 tests passed**.
- `./scripts/acceptance.sh`: local mode passed, including data freshness,
  scheduler/dedupe, Local/Cloud/PostgreSQL E2E, backup/restore, restart/chaos
  recovery, SLA, replay, Desktop UI, Web/iOS/Android builds, Tauri compile,
  packaged macOS lifecycle, sidecar health and macOS native notification smoke.
- `./scripts/python.sh scripts/generate_ts_client.py --check`: passed.
- `git diff --check`: passed.
- `./scripts/release-preflight.sh`: `mvp_release_ready=false`; blockers remain
  `windows_msi`, `windows_host`, `deepseek_credentials` and
  `tushare_credentials`.
- Inactive metadata gaps remain explicit and non-eligible; active stock and ETF
  metadata now pass the live quality gate.

## 2026-11-08: MVP audit result after universe coverage gate

- Added `validate_universe_coverage()` and integrated it into market sync.
  Missing `main`, `chinext`, `star`, `bse`, or `etf` categories now produces
  `UNIVERSE_COVERAGE_MISSING` and prevents a verified market snapshot.
- Added deterministic regression tests for complete and incomplete universe
  coverage.
- Validation:
  - `./scripts/test.sh`: **152 tests passed**.
  - `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=5
    ./scripts/provider-freshness-e2e.sh`: 2026-11-02 through 2026-11-06,
    all verified, 7,593 universe rows per day, completeness 1.0, no failures.
  - `./scripts/acceptance.sh`: local mode passed.
  - `./scripts/release-preflight.sh`: still reports
    `mvp_release_ready=false` for Windows MSI/host and real
    DeepSeek/Tushare credentials.
- Audit finding: the documented instrument metadata contract is implemented for
  stocks and Tushare-backed funds. Live AKShare ETF `listed_at` remains
  unavailable and is reported as a quality failure rather than fabricated.

## 2026-11-08: Instrument metadata normalization

- Added `exchange`, `listed_at`, and `active` to the market adapter DTO,
  DataWorker merge path, and DuckDB `normalized_universe` schema.
- AKShare stock listing dates now come from official SSE/SZSE/BSE listing
  endpoints; Tushare stock/fund listing dates are mapped from provider fields.
- Corrected BSE `920xxx` symbol normalization from `.SZ` to `.BJ`.
- Added metadata completeness reporting and adapter/rules regression coverage.
- Live AKShare inspection: 7,593 instruments, board counts
  `main=3846`, `chinext=1453`, `star=622`, `bse=6`, `etf=1666`;
  ETF rows remain without `listed_at` because the current ETF feed does not
  expose listing dates. The system reports this instead of fabricating dates.

## 2026-11-08: MVP audit continuation

- Re-read the PRD, acceptance criteria, traceability matrix, data/rules
  contract, and current MVP audit.
- Confirmed the local-first core is implemented and locally accepted, while
  strict release readiness remains blocked by Windows/credentialed external
  evidence.
- Found one implementation-level audit gap: the market quality gate did not
  explicitly require all five documented universe categories
  (`main`, `chinext`, `star`, `bse`, `etf`) to be present.
- Next action is to add that quality gate and verify its failure behavior with
  deterministic fixtures before rerunning the acceptance matrix.

## 2026-11-08: Research Workspace approval actions

- **Status:** Local and Cloud approval workflows now match the documented
  Research Workspace actions.
- Added `REQUEST_MORE_RESEARCH` and `MARK_AS_WATCH` to the API validation,
  OpenAPI contract, generated TypeScript client and Desktop approval panel.
- `REQUEST_MORE_RESEARCH` records an audited follow-up request and creates a
  parent-linked `FollowUp` task. `MARK_AS_WATCH` records the action and updates
  the user-scoped `Research watchlist`.
- Added runtime tests plus Local and Cloud HTTP E2E assertions for both
  actions.
- Validation:
  - `./scripts/test.sh`: **147 tests passed**.
  - `./scripts/e2e.sh`: `MARK AS WATCH PASS`.
  - `./scripts/cloud-e2e.sh`: `MARK AS WATCH PASS`.
  - `./scripts/acceptance.sh`: local mode passed, including macOS native
    notification smoke.

## 2026-11-08: Live provider fallback hardening

- **Status:** Local/Cloud implementation remains green; external release gates
  remain open.
- Fixed a correctness gap where live provider failures could fall back to the
  fixture provider. Live mode now routes only across configured real providers;
  fixture data remains available only for explicit fixture mode and Replay.
- Added regression coverage proving an unavailable live provider returns
  `CAPABILITY_UNAVAILABLE` instead of silently producing fixture data.
- Validation:
  - `./scripts/test.sh`: **145 tests passed**.
  - `./scripts/acceptance.sh`: local mode passed, including Local/Cloud REST,
    temporary PostgreSQL, recovery/chaos, Desktop UI, mobile builds, Tauri
    compile, packaged macOS lifecycle and sidecar health.
- Extended `scripts/acceptance.sh` release mode with a real no-fixture
  `StockResearch` task assertion. When credentials are injected, it now verifies
  the full live data/Agent/LLM Research Manager path and rejects failed or
  fixture-backed completion.

## 2026-11-08: MVP feature audit recheck

- **Status:** Local-first MVP core implemented and locally accepted; release
  acceptance remains open.
- Re-ran `./scripts/test.sh`: **144 tests passed**.
- Re-ran `./scripts/acceptance.sh`: local mode passed, including REST/SSE,
  scheduler/dedupe, Local/Cloud and temporary PostgreSQL E2E, backup/restore,
  restart/chaos recovery, SLA, replay, Desktop UI smoke, Web/iOS/Android
  acceptance, Tauri compile, packaged macOS lifecycle and sidecar health.
- Re-ran `./scripts/desktop-ui-smoke.sh`: passed task grouping, task deep link,
  Raw data, Replay, Watchlist, Rules gate and 390×844 overflow checks.
- `scripts/generate_ts_client.py --check` and `git diff --check` passed.
- Fixed a Playwright strict locator in `scripts/desktop-ui-smoke.sh` by targeting
  the unique `Watchlists` heading.
- `./scripts/release-preflight.sh` remains non-passing because this Darwin host
  has no Windows MSI/runner evidence and no real DeepSeek/Tushare credentials;
  external push credentials are also absent for the full milestone.
- Added explicit Evidence `Used by` data derived from persisted Agent trace
  evidence references, evidence-level task/hash links, and keyboard navigation
  for the task list plus focusable evidence cards.
- Re-ran the focused replay regression, `npm run build`, generated-client check,
  `git diff --check`, and `./scripts/desktop-ui-smoke.sh`: all passed.
- Extended iOS and Android task detail views to show risk/confidence, rules gate,
  Agent names and Evidence `Used by` metadata; `./scripts/mobile-acceptance.sh`
  passed with Swift tests/build, Android debug build and Web Push syntax check.

## 2026-11-08: Rule retrospective closure

- **Status:** Local/Cloud rule review path implemented and verified; external
  release gates remain open.
- Added `task_retrospectives` SQLite/PostgreSQL migrations and immutable
  user-scoped persistence for actual action, outcome, notes, observed time,
  `rule_snapshot_id` and `data_snapshot_id`.
- Added `POST`/`GET /api/tasks/{task_id}/retrospectives`, OpenAPI schema,
  generated TypeScript client methods, task detail/context inclusion and
  append-only `RETROSPECTIVE_RECORDED` audit/event records.
- Added the Desktop Research Workspace form and retrospective history panel.
- Validation:
  - `./scripts/test.sh`: 143 tests passed.
  - `./scripts/e2e.sh`: retrospective write/read passed.
  - `./scripts/cloud-e2e.sh`: user-b write/read and default-user isolation passed.
  - `./scripts/postgres-cloud-e2e.sh`: PostgreSQL migration parity and
    retrospective user isolation passed.
  - `npm run build`: passed.

## 2026-11-08: Ten-day live provider freshness recheck

- **Status:** Local-first MVP core remains verified; complete release gate remains open
- `./scripts/test.sh`: 141 tests passed; `./scripts/acceptance.sh` local mode
  passed, including the full local/cloud, desktop, web and mobile acceptance
  stages.
- Ran `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=10
  ./scripts/provider-freshness-e2e.sh`.
- Provider calendar resolved `2026-10-26` through `2026-11-06` (10 open dates).
  Every date returned `quality=verified` and
  `market_snapshot_quality=verified`, field completeness `1.0`, and no failures.
- This closes the previously pending short freshness window. Long-run
  production-window evidence, Tushare fallback/provenance, real DeepSeek
  runtime, Windows package/launch evidence, and external push delivery remain
  open.

## 2026-11-08: Responsive research workspace

- **Status:** M5 workspace mobile layout implemented and locally verified
- Added responsive rules for the shared Desktop/Web workspace: horizontal
  navigation on narrow screens, single-column task/detail and control grids,
  wrapped approval/notification actions, and compact audit/trace/data rows.
- Extended `scripts/desktop-ui-smoke.sh` with a 390×844 viewport assertion that
  the rendered page does not overflow horizontally.
- Validation: `npm run build` and `./scripts/desktop-ui-smoke.sh` passed.

## 2026-11-07: MVP audit recheck and lease isolation hardening

- **Status:** Local-first MVP core verified; complete release gate remains open
- Fixed Cloud lease release authorization and audit partitioning:
  `TASK_LEASE_RELEASED` now records the owning task/user, cross-user release
  attempts are rejected, and cursor sync filters by the audit row's `user_id`.
- Validation:
  - `./scripts/test.sh`: 140 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including Cloud scheduler,
    temporary PostgreSQL, lease/user isolation, Desktop GUI, mobile clients,
    Tauri compile, macOS packaged lifecycle and sidecar health.
  - `git diff --check`: passed.
  - `./scripts/release-preflight.sh`: `mvp_release_ready=false`; blockers are
    Windows MSI/host evidence and real DeepSeek/Tushare credentials. Full
    milestone push credentials remain unverified.

## 2026-11-07: Cloud scheduler execution boundary

- **Status:** Local/Cloud scheduler implementation verified; external release gates remain open
- Added `cloud --scheduler` and `PIA_START_SCHEDULER=1` support so the Cloud
  API, worker and market-close scheduler can run as separate operational roles.
- Added `scripts/cloud-scheduler-e2e.sh` to verify authenticated scheduler
  health plus stop/start lifecycle; it is part of `scripts/acceptance.sh`.
- Cloud scheduler now enumerates registered users, dispatches one
  user-scoped `MarketClose` event per user, and prevents worker-side duplicate
  scheduler startup.
- Market-derived data-quality, breadth, anomaly and filing events now use
  user-scoped dedupe keys for Cloud multi-user isolation.
- Hardened `.github/workflows/release-gates.yml`: missing DeepSeek/Tushare
  secrets now fail the manual release gate instead of silently skipping it.
- Validation:
  - `./scripts/test.sh`: 138 tests passed.
  - `./scripts/cloud-e2e.sh`: authentication, leases, cancellation, approval,
    user isolation, notification delivery, events and idempotency passed.
  - `./scripts/cloud-scheduler-e2e.sh`: scheduler health and lifecycle passed.
  - `./scripts/acceptance.sh`: local mode passed with the scheduler stage.
  - `git diff --check` and `bash -n scripts/cloud.sh`: passed.

## 2026-11-07: Current MVP function audit

- **Status:** Local-first MVP core implemented; complete release gate remains open
- Validation:
  - `./scripts/test.sh`: 138 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including Local/Cloud REST/SSE,
    temporary PostgreSQL, backup/restore, restart/chaos recovery, SLA, replay,
    Desktop GUI, Web/iOS/Android client checks, Tauri compile, macOS packaged
    lifecycle and sidecar health.
  - `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_LOOKBACK_DAYS=5
    ./scripts/provider-freshness-e2e.sh`: provider calendar resolved
    2026-11-02 through 2026-11-06; all dates were verified with completeness
    1.0 and no failures.
  - `./scripts/native-notification-smoke.sh`: macOS local-native delivery
    returned `DELIVERED`.
  - `./scripts/scheduler-e2e.sh`: real local Runtime market-close dispatch,
    task execution and dedupe passed.
  - `./scripts/release-preflight.sh`: `mvp_release_ready=false`; blockers are
    Windows MSI/host evidence, real `DEEPSEEK_API_KEY`, and real
    `TUSHARE_TOKEN`.

## 2026-11-07: MVP release-gate recheck after provider resilience changes

- **Status:** Local-first MVP core verified; release gates remain open
- Validation:
  - `./scripts/test.sh`: 132 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including Local/Cloud REST/SSE,
    temporary PostgreSQL, backup/restore, restart/chaos recovery, SLA, Replay,
    Desktop GUI, Web/iOS/Android, Tauri compile, macOS lifecycle and sidecar
    health.
  - `npm run build:web` and Desktop Vite production build passed.
  - `./scripts/release-preflight.sh`: `mvp_release_ready=false`; blockers are
    Windows MSI/host evidence, real `DEEPSEEK_API_KEY`, and real `TUSHARE_TOKEN`.

## 2026-11-07: Current MVP evidence recheck

- **Status:** Local-first MVP core verified; release gates remain open
- Validation:
  - `./scripts/test.sh`: 132 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including Local/Cloud
    REST/SSE, temporary PostgreSQL, backup/restore, restart/chaos recovery,
    Desktop GUI, Web/iOS/Android, Tauri compile, macOS lifecycle and sidecar
    health.
  - `PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh`: terminal success rate
    `1.0`, P95 `0.063s`.
  - `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-04,2026-11-05,2026-11-06
    ./scripts/provider-freshness-e2e.sh`: all three dates `verified`, market
    snapshot `verified`, field completeness `1.0`, no failures.
  - `./scripts/release-preflight.sh`: `mvp_release_ready=false`; blockers
    remain Windows MSI/host evidence and real DeepSeek/Tushare credentials.

## 2026-11-07: External release-gate automation

- **Status:** implementation complete; real credentialed run pending
- Added `.github/workflows/release-gates.yml` with a macOS runner and manual
  trading-date inputs.
- The workflow requires `DEEPSEEK_API_KEY` and `TUSHARE_TOKEN`, then runs
  release-mode DeepSeek structured/stream/tool-call checks, AKShare freshness,
  Tushare fallback/provenance, the full acceptance runner and release preflight.
- Missing secrets fail the manual gate; the task plan keeps the corresponding
  capability unchecked until a real run produces evidence.

## 2026-11-07: Windows native notification path

- **Status:** implementation complete; Windows runner evidence pending
- Added a WinRT Toast path to `LocalNotificationProvider` on Windows, with
  `msg` session delivery as a compatibility fallback when Toast activation is
  unavailable.
- Added regression coverage for Toast command construction and fallback
  delivery; the full Python suite now passes with 132 tests.
- Windows packaged acceptance and real cross-session delivery still require the
  Windows CI runner.

## 2026-11-07: Provider-calendar freshness automation

- **Status:** implementation complete; long-run scheduled evidence pending
- Extended `scripts/provider_freshness.py` to resolve the latest N open dates
  from the selected Provider trading calendar when explicit dates are absent.
- Added `PIA_FRESHNESS_LOOKBACK_DAYS` support to the acceptance wrapper and a
  weekday `.github/workflows/provider-freshness.yml`.
- Validation: the real AKShare calendar path selected
  `2026-11-02` through `2026-11-06`; all five dates were `verified`, field
  completeness was `1.0`, and there were no failures.

## 2026-11-07: Model routing and provider-neutral LLM errors

- **Status:** implemented and locally verified
- Added `ModelRouter` and `ModelRoute` so Agent runtime selects models by
  capability, preferred provider and priority.
- Added stable LLM error mapping for credentials, rate limits, provider
  unavailability, authentication, content safety and invalid structured output.
- Retryable provider errors now preserve `RETRYABLE` task recovery semantics;
  non-retryable provider errors become explicit `FAILED` results with provider
  metadata.
- Validation: 131 Python tests and full local acceptance passed.

## 2026-11-07: Provider resilience and LLM cost observability

- **Status:** implemented and locally verified
- Added configurable Provider retry attempts, exponential backoff, circuit
  breaker thresholds/cooldowns and runtime health state.
- Provider retries and circuit-open decisions are recorded in append-only audit
  events; fallback routing skips open circuits.
- Added SQLite/PostgreSQL `llm_usage` persistence for prompt tokens,
  completion tokens, request count and estimated USD cost.
- Added LLM usage to task detail, `/api/metrics`, agent trace token usage and
  the Desktop Trace panel.
- Validation: 128 Python tests, generated client check, Desktop build and full
  local acceptance passed.

## 2026-11-07: Latest MVP implementation audit recheck

- **Status:** Local-first MVP core verified; release gates remain open
- Re-ran `./scripts/acceptance.sh` after the Paper Broker and SMTP Email provider
  additions; local mode passed with 122 Python tests.
- Acceptance covered Paper Broker preview/paper submit, notification delivery
  receipts, Local/Cloud REST/SSE, temporary PostgreSQL, backup/restore,
  restart/chaos recovery, SLA, Replay, Desktop GUI, Web/iOS/Android builds,
  Tauri compile, macOS lifecycle and sidecar health.
- `./scripts/release-preflight.sh` still reports `mvp_release_ready=false`:
  Windows MSI/host evidence and real DeepSeek/Tushare credentials are
  unavailable on this Darwin host.

## 2026-11-07: Documented Tool Layer and Semantic Memory

- **Status:** complete for Local and Cloud repository/API behavior
- Implemented every tool named in `docs/DATA_RULES_EVENTS.md`, including
  research-provider reads, index/technical features, portfolio exposure and
  simulation, evidence saving, approval requests and follow-up task creation.
- Added user-scoped watchlists and structured semantic memories with SQLite and
  PostgreSQL migrations, runtime methods, authenticated API endpoints, OpenAPI
  schemas and generated TypeScript client methods.
- Added local E2E assertions for watchlist save and memory save/search, plus
  user-isolation and permission regression tests.
- Validation: 122 Python tests passed, generated client check passed, Desktop
  Vite build passed, and the new focused E2E flow passed.

## 2026-11-07: MVP implementation audit recheck

- **Status:** Local-first MVP core verified; release gates remain open
- **Actions taken:**
  - Fixed historical provider quality promotion to compare the latest open
    trading day at or before `as_of`.
  - Added a regression test for a calendar response containing later dates.
  - Ran the real AKShare freshness gate for `2026-11-04`, `2026-11-05` and
    `2026-11-06`.
- **Validation:**
  - `./scripts/test.sh`: 122 tests passed.
  - AKShare three-date freshness: all dates `verified`, completeness `1.0`,
    no failures.
  - `./scripts/acceptance.sh`: local mode passed after removing a stale local
    runtime that had occupied port `8765`.
- **Remaining release boundary:**
  - Windows package/launch/notification evidence, real DeepSeek/Tushare
    credentials, external push delivery and long-run external-provider SLA.

## 2026-11-07: MVP UI and live-path closure
- **Status:** complete for local/browser-verifiable behavior
- **Actions taken:**
  - Fixed the generated TypeScript client to bind browser `fetch` to
    `globalThis`, eliminating the real-page `Illegal invocation` failure.
  - Changed Desktop task creation and candidate scans to use the current
    market snapshot and provider date; fixture mode remains explicit replay.
  - Changed the Rules page to show the selected task's evaluated gate result
    instead of a fabricated empty `WATCH` result.
  - Made Tauri launch the local runtime with `PIA_DATA_PROVIDER=akshare` by
    default while preserving an explicit `PIA_DATA_PROVIDER=fixture` override.
  - Added `scripts/desktop-ui-smoke.sh` to acceptance and verified the browser
    path through task creation, evidence, trace and Rules rendering.
  - Updated iOS and Android new-review actions to use the Asia/Shanghai date.
- **Validation:**
  - `./scripts/test.sh`: 114 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including the new Desktop GUI
    smoke.
  - Desktop Vite build, Tauri `cargo check`, iOS tests/build and Android
    `assembleDebug` passed.
- **Remaining boundary:**
  - Real DeepSeek/Tushare credentials, Windows runner/package evidence and
    external push/long-run freshness evidence remain open.

## 2026-11-07: Temporal quality gate and release preflight
- **Status:** complete for locally verifiable behavior
- **Actions taken:**
  - Added ISO temporal metadata validation for `as_of`, `observed_at`,
    `expires_at` and source publication timestamps.
  - Added future-date, ordering and expiry regression tests.
  - Updated `DataWorker` to stop future-date requests, downgrade invalid rows,
    preserve quality errors and emit `TEMPORAL_METADATA_INVALID` failures.
  - Added `scripts/release-preflight.sh` and `scripts/release_preflight.py`
    to report artifact, platform, credential, PostgreSQL and external push
    readiness without exposing secret values.
  - Documented the preflight command in `README.md` and `docs/OPERATIONS.md`.
- **Validation:**
  - Focused DataWorker/Rules tests: 16 passed.
  - Full suite: 104 tests passed.
  - Release preflight correctly returned non-zero with explicit missing
    Windows, DeepSeek, Tushare and external push evidence.
- **Remaining boundary:**
  - External credentials and Windows/real-device environments are still
    required for their respective acceptance gates.

## 2026-11-07: Complete universe and ETF market coverage
- **Status:** complete for local/provider contract behavior
- **Actions taken:**
  - Removed the AKShare market snapshot's hard 2,000-instrument truncation.
  - Added ETF instruments to AKShare market snapshots so Profile-scoped
    candidate scans can include the configured ETF universe.
  - Added delisting metadata to AKShare stock instruments.
  - Added optional ETF daily snapshot mapping for Tushare and filtered it to
    ETF board symbols.
  - Added adapter regressions for ETF inclusion and a 2,001-instrument
    snapshot to prevent reintroducing truncation.
- **Validation:**
  - Adapter contract tests: 10 passed.
  - Full Python/Web test runner: 111 tests passed.
  - Full local acceptance: passed, including Local/Cloud E2E, temporary
    PostgreSQL, recovery/chaos, mobile acceptance, Tauri compile, macOS
    packaged lifecycle and sidecar health.
  - Live AKShare snapshot: 7,593 instruments (5,927 stocks and 1,666 ETFs),
    20 indices and 20 sectors.
  - Live DataWorker sync for `2026-11-06` and `600000.SH`: aggregate and
    market snapshot quality `verified`, completeness `1.0`, no failures,
    universe `7,593`, research sources `12`.
- **Remaining boundary:**
  - Real provider trading-day coverage and Windows release evidence still
    require their external environments.

## 2026-11-07: Quality-aware provider fallback
- **Status:** complete for Local/Cloud runtime behavior
- **Actions taken:**
  - Changed market synchronization fallback to accept a provider only when
    both aggregate and market-snapshot quality are `verified` with no failures.
  - Degraded `partial`/`unavailable` responses now emit a provider-failed audit
    and continue to the next healthy provider when fallback is enabled.
  - Added a regression where the primary provider returns degraded data without
    raising an exception and the secondary provider is selected.
- **Validation:**
  - Focused fallback tests: 2 passed.
  - Full Python/Web runner: 111 tests passed.
- **Remaining boundary:**
  - Credentialed Tushare fallback still needs a real token and live quota/error
    exercise.

## 2026-11-07: Credentialed provider freshness gate
- **Status:** implementation complete; live evidence pending credentials
- **Actions taken:**
  - Added `scripts/provider_freshness.py` and
    `scripts/provider-freshness-e2e.sh` for explicit multi-date Provider
    freshness checks.
  - The gate validates aggregate quality, market-snapshot quality, field
    completeness, row counts and failure lists for every requested date.
  - Release acceptance invokes the gate when `PIA_FRESHNESS_DATES` is set;
    otherwise it reports an explicit skip.
  - Added pass/degraded-date unit coverage.
- **Validation:**
  - Freshness gate unit tests: 2 passed.
  - Script syntax check passed.
  - The new gate is ready for explicit multi-date execution; no multi-date
    external run was claimed in this environment.
- **Remaining boundary:**
  - Run the gate across real trading dates with AKShare and Tushare credentials.

## 2026-11-07: Provider-consistent universe metadata
- **Status:** complete for local/provider contract behavior
- **Actions taken:**
  - Enriched Tushare market snapshot instruments from the same provider's
    universe metadata, including name, board, ST, delisting and listing age.
  - Merged fetched universe metadata into DataWorker snapshots before the
    snapshot is persisted, so Rules sees consistent listing and exclusion
    fields after a live sync.
  - Added regression coverage for listing-age enrichment.
- **Validation:**
  - Full Python/Web runner: 111 tests passed.
  - Full `./scripts/acceptance.sh` after the metadata merge passed, including
    temporary PostgreSQL, recovery/chaos, mobile acceptance, Tauri compile and
    packaged macOS lifecycle/sidecar health.
  - Live AKShare DataWorker sync remained verified with completeness `1.0`,
    no failures, 7,593 universe rows and 1,666 ETFs in the market snapshot.
- **Remaining boundary:**
  - Tushare metadata enrichment still needs a credentialed live run.

## 2026-11-07: Packaged Desktop lifecycle hardening
- **Status:** complete for macOS evidence
- **Actions taken:**
  - Fixed Tauri cleanup on `ExitRequested` as well as `Exit`.
  - Spawned the runtime in its own process group and terminate the complete
    group on Unix; Windows uses `taskkill /T`.
  - Added `scripts/desktop-lifecycle-smoke.sh` and wired it into local
    acceptance; extended Windows acceptance with desktop startup/exit checks.
- **Validation:**
  - `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml`: passed.
  - `cargo tauri build` from `apps/desktop/src-tauri`: macOS app and DMG built.
  - Packaged lifecycle smoke: `DESKTOP LIFECYCLE PASS`; no sidecar remained
    after quitting the app.
- **Remaining boundary:**
  - Windows lifecycle still requires a Windows runner.

## 2026-11-07: Full acceptance after quality and lifecycle changes
- **Status:** complete for local and temporary-cloud evidence
- **Validation:**
  - `./scripts/test.sh`: 107 tests passed.
  - `./scripts/acceptance.sh`: local acceptance passed, including REST/SSE,
    positive approval, temporary PostgreSQL, backup/restore, recovery, chaos,
    SLA (`1.0`, P95 `0.060s`), Web/iOS/Android acceptance, Desktop lifecycle,
    Tauri compile and packaged sidecar health.
  - Release mode remains intentionally unrun because this shell has no
    `DEEPSEEK_API_KEY` or `TUSHARE_TOKEN`.

## 2026-11-07: Freshness quality soak
- **Status:** complete for local quality behavior
- **Actions taken:**
  - Added `scripts/freshness-e2e.sh` with 1,000 deterministic temporal cases.
  - Covered valid metadata, future `as_of`, observed-before-as-of,
    expired evidence and future publication timestamps.
  - Added the soak to `scripts/acceptance.sh` and documented its scope.
- **Validation:** `FRESHNESS E2E PASS cases=1000`.
- **Remaining boundary:** external-provider long-run freshness still requires
  real credentials and scheduled production-like runs.

## 2026-11-07: MVP acceptance recheck

- **Status:** complete
- **Actions taken:**
  - Re-ran `./scripts/acceptance.sh` after the deterministic `Research Manager`
    node was added to the agent graph.
  - Re-ran native notification smoke and fixture replay.
  - Updated the current evidence count from 97/96 to 99 tests.
- **Validation:**
  - `./scripts/test.sh`: 99 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including REST/SSE, positive
    approval, recovery, chaos, SLA, replay, Web, iOS, Android, Tauri compile,
    and packaged macOS sidecar health.
  - `./scripts/native-notification-smoke.sh`: `DELIVERED`.
  - `./scripts/replay.sh`: replay trace includes `Research Manager`.
- **Remaining release gates:**
  - Real DeepSeek and Tushare credentials are not configured.
  - No Windows runner is available for package/launch/notification evidence.
  - Long-run external-provider freshness and real push delivery remain unverified.

## 2026-11-07: Cloud backup and user-scoped approval hardening

- **Status:** complete
- **Actions taken:**
  - Added `scripts/cloud-backup-restore-e2e.sh` with an isolated temporary
    PostgreSQL cluster and DuckDB snapshot.
  - Added user-b positive approval and approval-audit assertions to
    `scripts/cloud-e2e.sh`.
  - Added the backup/restore drill to `scripts/acceptance.sh`.
- **Validation:**
  - `./scripts/cloud-backup-restore-e2e.sh`: `POSTGRES BACKUP RESTORE E2E PASS`.
  - `./scripts/cloud-e2e.sh`: `USER B APPROVAL PASS`.
  - `./scripts/acceptance.sh`: local mode passed with 99 tests and all existing
    recovery, mobile, Tauri, and sidecar checks.

## 2026-11-07: PostgreSQL Cloud acceptance

- **Status:** complete
- **Actions taken:**
  - Added `scripts/postgres-cloud-e2e.sh` to create an isolated UTF-8
    PostgreSQL cluster and run the complete Cloud E2E against `PostgresDatabase`.
  - Added the temporary PostgreSQL Cloud path to `scripts/acceptance.sh`.
- **Validation:**
  - `./scripts/postgres-cloud-e2e.sh`: `POSTGRES CLOUD E2E PASS`.
  - Coverage includes authentication, task cancellation, positive approval for
    two users, audit/portfolio/event isolation, leases, device lifecycle and
    idempotency.

## 2026-11-07: Platform notification gateway acceptance

- **Status:** complete for local gateway behavior
- **Actions taken:**
  - Added a real local HTTP gateway test for Web Push, APNs and FCM routing.
  - Verified per-platform Bearer tokens, user scoping and device payloads.
- **Validation:**
  - `tests.test_notifications`: 6 tests passed, including
    `test_platform_gateway_delivers_to_real_local_gateway`.
- **Remaining boundary:** external provider credentials, device/browser delivery,
  lock-screen delivery and cross-session notification behavior remain unverified.

## 2026-11-07: Release provider gate hardening

- **Status:** complete for credentialed path definition
- **Actions taken:**
  - Extended release-mode Tushare checks beyond market snapshot to trading
    calendar, universe, daily bars, fundamentals, news and filings.
  - Added provenance and quality assertions for every returned capability.
- **Validation:**
  - Release gate Python source parses successfully.
  - Credentialed execution remains pending until `TUSHARE_TOKEN` is injected.

## Session: 2026-11-05

### Phase 1: Requirements & Discovery
- **Status:** complete
- **Started:** 2026-11-05
- Actions taken:
  - 阅读 `planning-with-files` skill。
  - 检查 `/Users/kingiol/Desktop/Pia`，确认目录为空且不是 Git 仓库。
  - 访问用户提供的 ChatGPT 分享链接。
  - 使用公开分享数据接口提取完整对话内容。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: Planning & Structure
- **Status:** complete
- Actions taken:
  - 将讨论整理为产品愿景、MVP 边界、架构、数据、规则、事件、Tauri 2 桌面验证、里程碑和验收范围。
  - 决定生成入口 README 与 10 份主题文档。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`

### Phase 3: Implementation
- **Status:** complete
- Actions taken:
  - 生成 PRD、架构、Research Workspace、数据与规则、里程碑、执行计划、验收、风险、运营和 ADR 文档。
  - 为每个里程碑定义目标、交付物、完成定义和依赖。
- Files created/modified:
  - `README.md`
  - `docs/PRD.md`
  - `docs/ARCHITECTURE.md`
  - `docs/RESEARCH_WORKSPACE.md`
  - `docs/DATA_RULES_EVENTS.md`
  - `docs/MILESTONES.md`
  - `docs/EXECUTION_PLAN.md`
  - `docs/ACCEPTANCE.md`
  - `docs/RISK_REGISTER.md`
  - `docs/OPERATIONS.md`
  - `docs/ADR.md`
  - `docs/TRACEABILITY.md`

### Phase 4: Testing & Verification
- **Status:** complete
- Actions taken:
  - 检查所有 Markdown 文件是否存在。
  - 检查核心术语、MVP 范围、人工审批边界和时间线是否一致。
  - 检查交付物之间是否存在断链。
- Files created/modified:
  - `progress.md`

### Phase 5: Delivery
- **Status:** complete
- Actions taken:
  - 形成可从 README 开始阅读的文档包。
  - 记录当前剩余决策：数据供应商、合规边界、平台优先级、Tauri 2 Sidecar 和跨平台验证结果。
- Files created/modified:
  - `README.md`

### 2026-11-06: Native Mobile UI Decision
- **Status:** complete
- Actions taken:
  - 将移动端方案从跨平台 UI 调整为 iOS SwiftUI 和 Android Kotlin + Jetpack Compose。
  - 新增跨平台 Monorepo 目录、代码复用边界、Transport 抽象和单一契约来源。
  - 新增 ADR-009，明确不使用 React Native，移动端默认连接云端 Agent。
- Files created/modified:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ADR.md`
  - `docs/MONOREPO.md`
  - `docs/PRD.md`
  - `progress.md`

### 2026-11-06: Adapter Architecture
- **Status:** complete
- Actions taken:
  - 检查现有文档对数据源、Broker、LLM、通知、存储和平台 Adapter 的覆盖范围。
  - 确认原文档只有概念性描述，缺少统一 Port、Provider Registry、Normalizer、故障切换和 Contract Tests。
  - 新增 Provider/Platform Adapter 规范，并加入 ADR-010。
- Files created/modified:
  - `README.md`
  - `docs/ADAPTERS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/DATA_RULES_EVENTS.md`
  - `docs/MONOREPO.md`
  - `docs/ADR.md`
  - `docs/MILESTONES.md`
  - `progress.md`

### 2026-11-06: Hybrid Agent Runtime
- **Status:** complete
- Actions taken:
  - 将 Agent 运行模式正式定义为云端默认、Tauri 本地 Sidecar 可选的 Hybrid Runtime。
  - 区分控制面、云端执行面和本地执行面。
  - 明确 MVP 不包含完整离线同步和双向冲突解决。
- Files created/modified:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ADR.md`
  - `docs/MONOREPO.md`
  - `docs/MILESTONES.md`
  - `progress.md`

### 2026-11-06: MVP Readiness Audit
- **Status:** complete
- Actions taken:
  - 按“另一个 Agent 能否无需重新决策完成并验证 MVP”的标准审查全部文档。
  - 确认当前文档达到 Architecture-ready，但尚未达到 Implementation-ready。
  - 识别 8 个 P0 缺口：发布组合、Provider 主备、API Contract、数据库 migration、规则基线、Agent Contract、测试夹具、执行命令。
  - 新增 MVP Readiness Assessment 和 Implementation Lock Pack 清单。
- Files created/modified:
  - `README.md`
  - `docs/MVP_READINESS.md`
  - `progress.md`

### 2026-11-06: Local-first MVP Rebaseline
- **Status:** in_progress
- Actions taken:
  - 将 MVP 发布组合锁定为 Tauri Desktop + Python Local Agent + SQLite/DuckDB。
  - 将 Cloud Agent、Web/PWA、iOS、Android、远程同步和实时行情移出 MVP 发布门。
  - 更新 PRD、ARCHITECTURE、MONOREPO、ADR、MILESTONES、EXECUTION_PLAN、ACCEPTANCE、OPERATIONS 和 README。
  - 新增 `docs/IMPLEMENTATION_INPUTS.md`，分类记录实现阻碍、默认值和需要用户提供的信息。
  - 将本地 SQLite 设为 MVP 的 Ruleset、Approval 和 Audit 权威存储。
- Files created/modified:
  - `README.md`
  - `docs/PRD.md`
  - `docs/ARCHITECTURE.md`
  - `docs/MONOREPO.md`
  - `docs/ADR.md`
  - `docs/MILESTONES.md`
  - `docs/EXECUTION_PLAN.md`
  - `docs/ACCEPTANCE.md`
  - `docs/OPERATIONS.md`
  - `docs/MVP_READINESS.md`
  - `docs/DATA_RULES_EVENTS.md`
  - `docs/IMPLEMENTATION_INPUTS.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### 2026-11-06: Local-first Documentation Verification
- **Status:** complete
- Actions taken:
  - 搜索旧的 Cloud-default、Hybrid Runtime 和 Web/Mobile MVP 发布表述。
  - 确认 README、PRD、ARCHITECTURE、MONOREPO、ADR、MILESTONES、EXECUTION_PLAN、ACCEPTANCE、OPERATIONS 和 MVP_READINESS 已统一为 Local-first。
  - 检查 Markdown 相对链接和新增长文档引用。
  - 运行 `git diff --check`。
- Test Results:
  - 旧的 Cloud-default 表述：未发现；
  - 相对链接缺失：0；
  - Markdown 文件数量：19；
  - Git whitespace errors：0。

### 2026-11-06: User Input Applied
- **Status:** in_progress
- Actions taken:
  - 记录 macOS 首发、Windows 必须实现。
  - 将股票池扩展为沪深主板、创业板、科创板、北交所和 ETF。
  - 将 Provider 锁定为 `akshare` 主、`tushare` 备。
  - 将 LLM 锁定为 `deepseek` Adapter，具体 model 通过配置注入。
  - 将持仓输入锁定为 CSV、Excel、手工录入，保留只读接口扩展。
  - 将外部 API 和远程 LLM 标记为允许。
  - 在 `docs/IMPLEMENTATION_INPUTS.md` 固化 Ruleset `v1`、Replay 顺序和 Replay 日期解释。
- Remaining decisions:
  - 真实数据阶段的历史 Replay 日期。

### 2026-11-06: Ruleset and Replay Decision Locked
- **Status:** complete
- Actions taken:
  - 固化 DeepSeek model=`deepseek-flash`。
  - 将规则初始值接受为 Ruleset `v1`，并记录后续通过新版本修改的机制。
  - 将合成 fixture 优先、真实历史日期后置的 Replay 顺序写入文档。
  - 新增 ADR-013，明确历史任务继续引用原 Ruleset snapshot。
- Validation:
  - Markdown 相对链接：0 缺失；
  - `git diff --check`：通过。

### 2026-11-06: DeepSeek Endpoint Locked
- **Status:** complete
- Actions taken:
  - 采用 DeepSeek OpenAI-compatible API。
  - 固化 `base_url=https://api.deepseek.com`、`POST /chat/completions` 和 `model=deepseek-flash`。
  - 保留 `Responses API` 和其他 LLM Provider 作为后续 Adapter 扩展。
  - 明确 AKShare 在本地以 Python package 方式接入，Provider Adapter 不要求 API key；网络可用性和数据质量仍需检查。
- Validation:
  - Markdown 相对链接：0 缺失；
  - `git diff --check`：通过。

### 2026-11-06: Credential Placeholder Policy
- **Status:** complete
- Actions taken:
  - 明确 API key、Tushare Token 暂不要求用户提供。
  - 增加 `__PROVIDE_LATER__` 占位策略和 `CREDENTIALS_REQUIRED` / `CAPABILITY_DISABLED` 行为。
  - 允许在无真实凭据时继续实现 Mock Adapter、合成 fixtures、Rules、Replay、Audit 和本地 UI。
  - 明确真实凭据只通过本机环境变量或系统 Credential Manager 注入。

### 2026-11-06: Real DeepSeek Runtime Decision
- **Status:** complete
- Actions taken:
  - 根据用户要求，MVP Agent、集成测试和 E2E 使用真实 DeepSeek API。
  - 移除 Mock LLM 作为缺少凭据时的替代路径。
  - 缺少 DeepSeek key 时任务返回 `CREDENTIALS_REQUIRED` 并阻止运行。
  - 真实 key 只作为本机运行时秘密使用，不写入文档、Git 或日志。

### 2026-11-06: UI/UX Design System
- **Status:** complete
- Actions taken:
  - 新增 `docs/DESIGN_SYSTEM.md`。
  - 定义 Desktop、Web、iOS、Android 的信息架构、布局、Design Tokens、核心组件、图表、文案、状态、无障碍、动效和设计验收。
  - 明确共享语义和 Tokens，平台保留原生导航和系统能力。
  - 更新 README 和 Monorepo 文档入口。

### 2026-11-06: Local-first MVP Implementation Started
- **Status:** in_progress
- **Actions taken:**
  - Confirmed the repository contains the planning/documentation baseline but no implementation code.
  - Locked the first implementation slice to a local, replayable close review flow.
  - Started the Implementation Lock Pack and executable runtime work.
- **Next:**
  - Add contracts, migrations, config, rules, agent contracts and fixtures.
  - Implement Python local runtime, React workspace and Tauri shell.

### 2026-11-06: Local-first MVP Implementation Complete
- **Status:** complete
- **Actions taken:**
  - Added OpenAPI/JSON Schema contracts, SQLite migrations, Ruleset `v1`, Agent contracts and deterministic replay fixtures.
  - Implemented Python local runtime with task state machine, SQLite persistence, append-only audit, evidence, decisions, approvals and finite SSE trace streaming.
  - Implemented market close orchestration with Market, Portfolio, Technical and Risk/Rules agent runs.
  - Added event ingestion with priority metadata, deduplication and `MarketClose` dispatch.
  - Added CSV, dependency-free first-sheet XLSX and manual portfolio imports.
  - Added optional AKShare and credential-gated Tushare adapter boundaries plus real DeepSeek OpenAI-compatible JSON client.
  - Added React/Vite Research Workspace and Tauri 2 desktop shell configuration with macOS/Windows bundle targets.
  - Added runnable `scripts/test.sh`, `scripts/replay.sh`, `scripts/e2e.sh` and `scripts/dev.sh`.
- **Validation:**
  - Python unit/contract/replay tests: 8 passed.
  - Vite production build: passed.
  - REST + SSE E2E: passed.
  - Tauri `cargo check`: passed.
  - `git diff --check`: passed.
- **Known expansion boundaries:**
  - Production AKShare field monitoring, Tushare activation, DuckDB analytics, signed packaged Python sidecars, cloud execution and broker writes remain behind explicit ports.

### 2026-11-06: Functional Surface Completion
- **Status:** complete
- **Actions taken:**
  - Added event ingestion API and dedupe-backed `MarketClose` dispatch.
  - Added Market, Portfolio, Rules, Data Health and Audit workspace views.
  - Added local portfolio import flow for CSV and manual JSON, with normalized weights and audit records.
  - Added optional first-sheet XLSX parsing without a mandatory third-party dependency.
  - Added API endpoints for latest market snapshot, audit records and event history.
- **Validation:**
  - Replay result: `BLOCKED` decision with 3 evidence items and 5 agent runs.
  - REST + finite SSE E2E: passed.
  - Unit/contract/replay tests: 8 passed.
  - Vite build and Tauri `cargo check`: passed.

### 2026-11-07: Local MVP Hardening Started
- **Status:** in_progress
- **Actions taken:**
  - 按 `docs/PRD.md`、`docs/ACCEPTANCE.md`、`docs/MILESTONES.md` 和当前代码执行完整 MVP 审计。
  - 修复 `wait_for_task()` 在任务进入终态但后台线程仍未结束时提前返回的问题，增加显式 completion event。
  - 验证 32 个 Python 测试、Local/Cloud E2E、SSE、Desktop/Web build、Tauri `cargo check` 和 macOS debug app bundle。
  - 新增 `docs/MVP_AUDIT.md`，记录逐项实现状态和发布阻塞项。
- **Validation:**
  - `./scripts/test.sh`: 32 tests passed；
  - `./scripts/e2e.sh`: passed；
  - `./scripts/cloud-e2e.sh`: passed；
  - `npm run build`: passed；
  - `npm run build:web`: passed；
  - `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml`: passed；
  - `cargo tauri build --debug --bundles app`: macOS app bundle passed。
- **Conclusion:**
  - 当前为可运行的 Local-first vertical slice，尚未满足完整 MVP 发布门。
  - 主要缺口：真实数据管线、自动调度、原生通知、LangGraph/Pydantic runtime、可独立运行的打包 Sidecar、Windows 验证、安全/chaos/SLA 验收。
- **Status:** in_progress
- **Actions taken:**
  - Audited the delivered slice against `docs/ACCEPTANCE.md`, `docs/PRD.md` and `docs/MILESTONES.md`.
  - Confirmed the current code passes the narrow MarketClose replay path but does not yet satisfy the complete P0 release gate.
  - Started implementation of Sidecar lifecycle, event dispatch, complete rules gates, stale evidence handling, approval safety and retry provenance.
- **Current risks:**
  - Packaged signed Python binaries, live provider production coverage, Cloud Agent and mobile clients remain later work after the Local MVP gate.

### 2026-11-07: Local MVP Hardening and Cloud Runtime
- **Status:** in_progress
- **Actions taken:**
  - Tauri now owns Python runtime startup and shutdown in the desktop process.
  - Added Profile versions, structured Bull/Bear/Debate traces and workspace rendering.
  - Added stale/universe/liquidity/market volatility/evidence gates and approval safety for `NO_ACTION`.
  - Added restart recovery, retry parent/fixture provenance, SQLite backup/restore and executable scripts.
  - Added Cloud runtime mode with bearer authentication and task lease/heartbeat/release endpoints.
- **Validation:**
  - Python tests: 14 passed.
  - REST + SSE E2E: passed.
  - Vite build: passed.
  - Tauri `cargo check`: passed.
  - Cloud auth smoke test: health is public, task list requires bearer token.

### 2026-11-07: MVP Recheck and REST Regression
- **Status:** in_progress
- **Actions taken:**
  - Re-ran `./scripts/test.sh`: 74 tests passed, generated client check passed, Desktop Vite build passed.
  - Fixed `scripts/e2e.sh` to use temporary SQLite/DuckDB paths by default, making direct repeated runs deterministic.
  - Added an API regression to verify `/api/data/sync` updates the snapshot returned by `/api/market`.
  - Re-ran `./scripts/e2e.sh` twice and `./scripts/acceptance.sh`: all local acceptance stages passed.
  - Updated `docs/MVP_AUDIT.md` to distinguish event ingestion from automatic anomaly/event generation.
- **Validation:**
  - `DATA SYNC MARKET PASS snap_20261105_close_fixture`
  - `./scripts/e2e.sh` repeated twice: passed.
  - `./scripts/acceptance.sh`: passed in local mode.
- **Remaining MVP release gaps:**
  - Real DeepSeek and Tushare credentialed acceptance;
  - automatic price/volume, breadth, filing and portfolio-risk event generation;
  - Windows build/package/launch/notification evidence;
  - real native push and long-run operational evidence.

### 2026-11-07: Automatic Event Derivation
- **Status:** complete for local runtime behavior
- **Actions taken:**
  - Added configurable automatic event generation thresholds and feature flag.
  - Added market-sync derivation for `DataQualityDegraded`, `MarketBreadthChanged`,
    `PriceVolumeAnomaly` and `FilingPublished`.
  - Added portfolio-import derivation for `PortfolioRiskChanged` when risk crosses
    a configured limit or changes materially.
  - Bound derived event tasks to persisted market/portfolio snapshot IDs so the
    task cannot silently re-read a different point-in-time dataset.
  - Updated scheduler data-quality handling to dispatch a blocking event instead
    of only writing a notification.
- **Validation:**
  - Added `tests/test_event_derivation.py`.
  - Full suite: 77 tests passed.
  - Local REST E2E: passed.
  - Local acceptance: passed.
- **Remaining boundary:**
  - Real provider freshness and long-running event windows still require
    credentialed/live operational acceptance.

### 2026-11-07: Cloud Event Isolation and Snapshot Consistency
- **Status:** complete for local/cloud contract behavior
- **Actions taken:**
  - Added event `user_id` migration for SQLite and PostgreSQL.
  - Scoped event dedupe, event listing, retry ownership and API reads by user.
  - Added Cloud E2E coverage proving two users can reuse the same logical
    dedupe key without seeing each other's events.
  - Added CORS `DELETE` support for device unregister and verified the preflight.
  - Scheduler `MarketClose` events now carry the just-synced market snapshot ID.
- **Validation:**
  - Full suite: 78 tests passed.
  - `./scripts/cloud-e2e.sh`: event isolation and CORS preflight passed.
  - `./scripts/e2e.sh`: passed with data-sync snapshot regression.

### 2026-11-07: Portfolio API Isolation
- **Status:** complete for cloud contract behavior
- **Actions taken:**
  - Scoped `/api/portfolio` to the authenticated user.
  - Added Cloud E2E assertions proving default and user B receive only their
    own portfolio snapshot.
  - Added migration contract coverage for SQLite/PostgreSQL event user scope.
- **Validation:**
  - `./scripts/cloud-e2e.sh`: portfolio isolation, event isolation and CORS
    preflight passed.

### 2026-11-07: Full implementation continuation
- **Status:** in_progress
- **Actions taken:**
  - Re-audited the repository against the full Local + Cloud objective and the MVP/M1-M7 documents.
  - Confirmed the current baseline is a tested local vertical slice, not the final release.
  - Fixed the scheduler test-double regression caused by assuming `runtime.settings` exists.
  - Updated `docs/MVP_AUDIT.md` with the current evidence and release blockers.
  - Replaced the stale plan with a full implementation plan covering MVP hardening, Cloud execution, Web/iOS/Android and operations.
- **Validation:**
  - `./scripts/test.sh`: 35 tests passed；
  - `./scripts/e2e.sh`: passed；
  - `./scripts/cloud-e2e.sh`: passed；
  - `./scripts/replay.sh`: passed；
  - `npm run build` / `npm run build:web`: passed；
  - `cargo check`: passed；
  - macOS debug `.app` bundle: passed, but contains no Python sidecar.
- **Next:**
  - Implement the live provider data contract and quality pipeline with mock contract tests first.

### 2026-11-07: Live data contract and packaged sidecar
- **Status:** in_progress
- **Actions taken:**
  - Added DuckDB normalized tables for universe, fundamentals, research sources and trading calendar.
  - Added `DataWorker.sync_market_data()` for raw payloads plus normalized market data collections and aggregate quality.
  - Added fixture, AKShare and Tushare calendar/universe/fundamental/source adapters with deterministic provider routing.
  - Added provider calendar checks to the local scheduler.
  - Added PyInstaller sidecar entry/spec, embedded migrations/rules/fixtures and Tauri `externalBin` packaging.
  - Added packaged sidecar lookup and verified the macOS bundled app starts the bundled runtime.
- **Validation:**
  - Data worker/provider/scheduler contract tests passed.
  - Full Python suite: 37 tests passed.
  - PyInstaller sidecar built for `aarch64-apple-darwin`.
  - Standalone sidecar `health --json`: passed.
  - Tauri macOS debug bundle: passed and contains `Contents/MacOS/pia-runtime`.
  - Packaged app health probe on port 8899: passed.
- **Known limitation:**
  - Windows sidecar still needs a Windows build/launch proof; live AKShare quality and upstream contract checks still need real provider runs.

### 2026-11-07: MVP Control, Scheduling, Data and Isolation Hardening
- **Status:** in_progress
- **Actions taken:**
  - Added persisted `PAUSED` task state with pause/resume API, audit events and runtime checkpoints.
  - Added lightweight runtime validation for API payloads from the checked-in JSON Schema contracts.
  - Added executable rule-case coverage for data unavailable, stale data, market gates, universe rejection, position limits and critical drawdown.
  - Added event-time cooldown keys, expired-event blocking, priority queue ordering and expired lease reclamation.
  - Added event delivery retry/backoff, retry exhaustion notifications and worker-driven due-event redelivery.
  - Added canonical daily-bar normalization with provider/adapter provenance, quality and stable snapshot IDs.
  - Added Cloud Bearer token to user-id mapping and user-scoped task/profile/portfolio/approval/notification access.
  - Added `DataQualityDegraded` handling that forces an unavailable-quality decision and deterministic block.
- **Validation:**
  - Python unit/contract/adapter/runtime tests: 30 passed.
  - Desktop Vite build: passed.
  - Local REST/SSE E2E: passed.
  - Cloud auth/lease/user-isolation/schema E2E: passed.
  - Tauri `cargo check`: passed.
  - `git diff --check`: passed.
- **Remaining high-priority work:**
  - DuckDB analytics repository and complete backup package;
  - PostgreSQL repository implementation;
  - real provider field coverage, normalizers and contract monitoring beyond daily bars;
  - packaged signed Python Sidecar installers on macOS/Windows;
  - Web Push/APNs/FCM adapters, multi-device sync and security/prompt-injection suite;
  - full P0 acceptance runner and manual desktop launch/installer verification.

### 2026-11-07: MVP implementation audit refresh
- **Status:** complete
- **Actions taken:**
  - Re-ran the full Python suite after the AKShare contract additions: 45 tests passed.
  - Re-ran Local E2E with isolated temporary SQLite/DuckDB paths: REST + finite SSE passed.
  - Re-ran Cloud E2E, fixture replay, Desktop/Web production builds and Tauri `cargo check`: passed.
  - Verified the macOS packaged `.app` starts its bundled `pia-runtime` sidecar and responds to `/api/health`.
  - Ran a real AKShare smoke check for snapshot, trading calendar, daily bars, fundamentals, news, filings and universe.
- **Findings:**
  - macOS packaged sidecar is now verified.
  - Live AKShare remains partial: snapshot has no indices, volatility is `0.0`, universe fetch timed out, fundamentals ordering and news-symbol matching need a quality gate.
  - Windows build/launch/package evidence, real DeepSeek integration, native notification delivery, chaos/SLA/P95 and a full P0 acceptance runner remain missing.
- **Files updated:**
  - `docs/MVP_AUDIT.md`
  - `progress.md`

### 2026-11-07: Current MVP release-gate recheck
- **Status:** complete
- **Actions taken:**
  - Re-ran `./scripts/test.sh`: 49 tests passed.
  - Re-ran `./scripts/acceptance.sh` in local mode: REST/SSE, metrics, Cloud auth/isolation/leases, replay, Web build, Tauri compile and sidecar health passed.
  - Ran live AKShare snapshot smoke with version `1.20.35`: 20 indices, 20 sectors and 2000 instruments returned; quality remained `partial` for historical `as_of=2026-11-06`.
  - Confirmed `DEEPSEEK_API_KEY` and `TUSHARE_TOKEN` are not present in the local shell, so release-mode credential checks were not run.
  - Inspected current runtime and found request-level provider fallback and live Evidence provenance/quality propagation are still incomplete.
- **Conclusion:**
  - Local-first vertical slice is runnable, but complete MVP release gates remain open for live data quality, provenance, DeepSeek runtime integration, Windows packaging, native notifications, chaos/SLA evidence and full response contracts.
- **Files updated:**
  - `docs/MVP_AUDIT.md`
  - `progress.md`

### 2026-11-07: Cloud observability and typed client integration
- **Status:** in_progress
- **Actions taken:**
  - Added generated TypeScript client methods for scheduler, data sync, task controls, notification acknowledgement and cloud transport.
  - Switched Desktop/Web API calls to the generated client for task, profile, portfolio, market, candidate, approval and scheduler flows.
  - Added Web Bearer-token login with session-scoped token storage and unauthorized recovery.
  - Added CORS preflight support for Authorization, Idempotency-Key and X-Worker-Id headers.
  - Added dependency-free structured JSON request logs, request P95/error counters and health diagnostics.
  - Added PowerShell sidecar/package scripts and a macOS/Windows Tauri CI matrix.
  - Added cloud notification routing with a configurable webhook gateway and explicit disabled/failed delivery receipts.
- **Validation:**
  - 38 focused Python tests passed, including observability and runtime regressions.
  - `npm run build` and `npm run build:web` passed.
  - Cloud smoke passed: CORS preflight, unauthorized response, authenticated health and structured request logs.
  - Notification provider contract tests passed for webhook delivery and disabled routing.
  - `git diff --check` passed.
- **Remaining:**
  - Native Web Push/APNs/FCM credentials, real DeepSeek/Tushare acceptance, Windows runner evidence and long-run external-service SLA remain open.

### 2026-11-07: Client and release hardening continuation
- **Status:** in_progress
- **Actions taken:**
  - Added Desktop/Web notification inbox with read acknowledgement and task navigation.
  - Added explicit Retry action for `RETRYABLE`, `FAILED` and `TIMEOUT` tasks.
  - Added notification read verification to Local REST E2E.
  - Added device-token notification gateway routing for Web Push/APNs/FCM gateway integrations.
  - Added Kotlin/Jetpack Compose Android client and CI build job.
  - Expanded iOS Codable JSON handling, retry transport and SwiftUI app shell.
  - Added macOS/Windows native notification smoke scripts and cloud PostgreSQL/DuckDB backup/restore scripts.
  - Added Tauri release artifact uploads and packaged sidecar health checks to CI.
- **Validation:**
  - `./scripts/test.sh`: 72 tests passed.
  - `./scripts/acceptance.sh`: local acceptance passed, including notification read E2E.
  - macOS `cargo tauri build`: `.app` and `.dmg` produced; bundled sidecar health passed.
  - `./scripts/native-notification-smoke.sh`: `DELIVERED`.
  - Android `:app:assembleDebug`: passed with API 36 SDK.
  - iOS Swift client tests: 3 passed; SwiftUI product build passed.
  - PostgreSQL + DuckDB cloud backup/restore rehearsal: passed.
- **Remaining:**
  - Windows runner evidence, real DeepSeek/Tushare credentials, Windows/cross-session notification delivery, long-run external-service SLA, push provider credentials and platform background refresh remain open.

### 2026-11-07: Mobile and multi-device completion slice
- **Status:** complete for code and local build evidence
- **Actions taken:**
  - Added authenticated `DELETE /api/devices/{device_id}` with inactive-row retention and immutable audit event.
  - Added device lifecycle coverage to Local REST E2E and Cloud unit tests.
  - Extended iOS transport/models with device registration, unregister, incremental sync and mixed JSON sync records.
  - Added iOS Keychain token storage and an iOS `BGTaskScheduler` background refresh coordinator.
  - Extended Android transport with device registration, unregister, sync and task-control methods.
  - Added Android Keystore-backed token storage and a network-constrained WorkManager refresh worker.
  - Added Web PWA manifest and service-worker shell.
  - Updated mobile implementation notes and generated TypeScript client.
- **Validation:**
  - Python suite: 73 tests passed.
  - Local REST E2E: passed, including device registration/unregister lifecycle.
  - TypeScript generated-client check and `git diff --check`: passed.
  - iOS client tests: 4 tests passed.
  - iOS `PiaApp` product build: passed.
  - Android `:app:assembleDebug`: passed.
  - Web production build: passed.
- **Remaining boundary:**
  - APNs/FCM/Web Push delivery still requires real platform credentials and device/emulator acceptance; this slice deliberately reports no delivery without a gateway receipt.

### 2026-11-07: Release artifact diagnostics
- **Status:** complete for local/CI tooling
- **Actions taken:**
  - Added `scripts/release_manifest.py` to enumerate release artifacts with size and SHA-256.
  - Added `scripts/release-manifest.sh` for local macOS/Linux packaging and optional OpenSSL signature generation.
  - Added CI manifest generation and artifact upload for macOS and Windows jobs.
  - Added a deterministic manifest unit test and documented the release procedure.
- **Validation:**
  - Python suite: 74 tests passed.
  - `./scripts/release-manifest.sh`: generated `.pia/release/manifest.json` with 9 artifacts.
  - Manifest JSON validation: passed.
  - Android debug build: passed.
- **Remaining boundary:**
  - A real signing key and Windows runner are still required to produce signed Windows evidence.

### 2026-11-07: Post-slice full acceptance
- **Status:** passed locally
- **Validation:**
  - `./scripts/acceptance.sh`: passed in local mode after the mobile, device lifecycle,
    PWA and release-manifest changes.
  - Python suite inside acceptance: 74 tests passed.
  - Local REST/SSE, notification read, device lifecycle, recovery, chaos, SLA,
    replay, Web build, Tauri compile and packaged sidecar health: passed.
  - PostgreSQL acceptance and live release acceptance remain explicitly skipped
    because `PIA_POSTGRES_DSN`, `DEEPSEEK_API_KEY` and `TUSHARE_TOKEN` are absent.

### 2026-11-07: MVP implementation audit recheck
- **Status:** complete for local evidence; release gate remains open
- **Actions taken:**
  - Re-ran `./scripts/test.sh`: 80 tests passed, generated TypeScript client check passed,
    Desktop Vite build passed.
  - Re-ran `./scripts/cloud-e2e.sh`: portfolio, audit and event isolation plus cloud
    task/auth/lease flow passed.
  - Re-ran `./scripts/e2e.sh`: data sync, REST/SSE, notification read, device lifecycle
    and metrics passed.
  - Re-ran `./scripts/acceptance.sh` twice in local mode: recovery, chaos, SLA, replay,
    Web build, Tauri compile and packaged macOS sidecar health passed.
  - Re-ran live AKShare sync for `2026-11-06` and `600000.SH`: `quality=verified`,
    `market_snapshot_quality=verified`, no failures, universe count 7593 and research
    source count 12.
  - Confirmed `cargo tauri --version` reports `tauri-cli 2.12.4`.
- **Conclusion:**
  - PRD MVP core behavior is implemented and locally verifiable.
  - The complete release gate is still open for real DeepSeek runtime/streaming/tool
    calling, Tushare fallback/provenance, Windows build and MSI/startup/notification
    evidence, cross-session native delivery, and long-run external-service SLA.

### 2026-11-07: Cloud contract and notification gateway hardening
- **Status:** complete for locally verifiable contract behavior
- **Actions taken:**
  - Completed `contracts/openapi.yaml` coverage for every runtime API operation,
    including rules, market, portfolio, audit, scheduler, data sync and device lifecycle.
  - Removed the duplicate device-path `responses` key and added explicit scheduler,
    data-sync, rules and device response schemas.
  - Added a YAML contract regression that detects missing runtime operations.
  - Added a real local HTTP webhook gateway test covering JSON payloads, Bearer token
    propagation and `DELIVERED` receipts.
- **Validation:**
  - Contract and notification focused tests passed.
  - Full suite: 83 tests passed.
  - Generated TypeScript client check, Desktop build and `git diff --check` passed.
- **Remaining boundary:**
  - External Web Push/APNs/FCM credentials and real platform delivery still require
    provider credentials and device/emulator acceptance.

### 2026-11-07: Mobile cloud endpoint hardening
- **Status:** complete for local build evidence
- **Actions taken:**
  - Replaced the iOS hardcoded localhost endpoint with `pia.cloud_base_url` UserDefaults,
    `PIA_CLOUD_URL`, and a simulator-safe local default.
  - Replaced the Android hardcoded emulator endpoint with Gradle `piaCloudUrl` injection,
    keeping `10.0.2.2` as the emulator default.
  - Documented physical-device and remote-cloud configuration for both clients.
- **Validation:**
  - `swift test --package-path apps/ios/PiaMobileClient`: 4 tests passed.
  - `swift build --package-path apps/ios/PiaMobileClient --product PiaApp`: passed.
  - Android `:app:assembleDebug`: passed.
- **Remaining boundary:**
  - Real device/emulator task flow, APNs/FCM/Web Push delivery and background execution
    still require platform runtime evidence.

### 2026-11-07: Task takeover and context export
- **Status:** complete for local/cloud contract behavior
- **Actions taken:**
  - Added user-scoped `POST /api/tasks/{task_id}/takeover` with immutable audit and task
    event records.
  - Added `GET /api/tasks/{task_id}/context` export containing task detail, profile,
    rules and rule snapshot metadata.
  - Added generated TypeScript client methods and Desktop actions for takeover and JSON
    context export.
  - Fixed new cloud users to receive an independent default Profile version and made
    task execution prefer the user's latest portfolio snapshot.
- **Validation:**
  - Runtime takeover/context and user profile/portfolio isolation tests passed.
  - Local REST E2E passed, including context export.
  - OpenAPI coverage, generated client check, Desktop build and `git diff --check` passed.

### 2026-11-07: Push boundaries, provider fallback and local soak
- **Status:** complete for locally verifiable implementation
- **Actions taken:**
  - Added Web Push browser subscription, device registration and Service Worker
    notification click handling.
  - Added iOS APNs token persistence/upload boundary and Android push-token storage
    boundary.
  - Added platform-specific Web Push/APNs/FCM gateway routing with per-channel
    credentials and token filtering.
  - Extended Tushare snapshots with optional index and Shenwan sector mappings and
    symbol-scoped news requests.
  - Added mobile acceptance runner and configurable 200-task local SLA soak runner.
- **Validation:**
  - `./scripts/test.sh`: 96 tests passed.
  - `./scripts/acceptance.sh`: local mode passed, including mobile acceptance,
    Tauri compile and packaged sidecar health.
  - `PIA_SLA_TASK_COUNT=200 ./scripts/soak-e2e.sh`: terminal success rate `1.0`,
    P95 `0.058s`.
  - iOS transport/push-token tests and SwiftUI build passed; Android debug build
    and Web Push Service Worker syntax check passed.
- **Remaining boundary:**
  - Real DeepSeek/Tushare credentials, Windows runner/package evidence, and real
    APNs/FCM/Web Push delivery still require external credentials and platforms.

### 2026-11-07: MVP audit re-run
- **Status:** complete
- **Actions taken:**
  - Re-read `docs/PRD.md`, `docs/ACCEPTANCE.md`, `docs/MILESTONES.md`,
    `docs/TRACEABILITY.md` and `docs/MVP_AUDIT.md`.
  - Re-ran `./scripts/test.sh`: 96 tests passed.
  - Re-ran `./scripts/acceptance.sh`: Local acceptance passed, including REST/SSE,
    recovery, chaos, local SLA, iOS transport tests, Web Push syntax, Tauri compile
    and packaged sidecar health.
  - Confirmed the current shell has no `DEEPSEEK_API_KEY`, `TUSHARE_TOKEN`,
    `ANDROID_HOME`, Windows runner, or PostgreSQL DSN.
- **Findings:**
  - Local-first MVP core remains implemented and locally verifiable.
  - Full MVP release acceptance remains incomplete because Windows evidence,
    real DeepSeek/Tushare evidence, real notification delivery, long-run external
    service SLA evidence, and the current Android build cannot be verified here.

### 2026-11-07: Approval E2E and fixture precedence
- **Status:** complete
- **Actions taken:**
  - Added positive Local and Cloud acceptance flows for
    `WAITING_APPROVAL -> APPROVED`.
  - Fixed runtime input precedence so an explicit task portfolio fixture is used
    before the latest user portfolio snapshot; latest user snapshot remains the
    default when no fixture is supplied.
  - Added a regression test covering explicit fixture precedence.
  - Updated mobile acceptance to auto-detect common Android SDK locations.
- **Validation:**
  - `./scripts/test.sh`: 97 tests passed.
  - `./scripts/acceptance.sh`: passed, including positive approval E2E and Android
    debug build.
  - `git diff --check`: passed.

### 2026-11-07: Mobile incremental sync completion
- **Status:** complete for local build evidence
- **Actions taken:**
  - Added iOS UserDefaults cursor persistence and `/sync` consumption in
    foreground and `BGTaskScheduler` refresh.
  - Added Android SharedPreferences cursor persistence and `/sync` consumption
    in foreground refresh and `WorkManager`.
  - Added PWA icon asset and manifest/service-worker icon references.
- **Validation:**
  - iOS tests and SwiftUI build passed.
  - Android `:app:assembleDebug` passed.
  - `npm run build:web` and `node --check apps/web/public/sw.js` passed.

### 2026-11-07: Current MVP implementation audit
- **Status:** core implementation verified; full release acceptance still incomplete
- **Actions taken:**
  - Re-read the MVP requirements and acceptance gates in `docs/PRD.md`,
    `docs/ACCEPTANCE.md`, `docs/MILESTONES.md`, `docs/TRACEABILITY.md` and
    `docs/MVP_AUDIT.md`.
  - Re-ran `./scripts/test.sh`: 114 tests passed and generated client check passed.
  - Re-ran `./scripts/acceptance.sh`: local acceptance passed, including Local
    REST/SSE, Cloud isolation and leases, temporary PostgreSQL, backup/restore,
    recovery, chaos, SLA, replay, mobile build checks, Tauri compile, packaged
    macOS lifecycle and sidecar health.
  - Ran `./scripts/release-preflight.sh`; it correctly returned non-zero and
    reported missing Windows MSI/host evidence and missing DeepSeek/Tushare
    credentials. External push credentials remain unverified.
  - Ran `git diff --check`: passed.
- **Current conclusion:**
  - The documented Local-first MVP core is implemented and locally verifiable.
  - The MVP cannot yet be called release-ready because PRD publishing requires
    Windows same-time packaging/startup evidence, and the release audit still
    lacks real DeepSeek and Tushare acceptance plus long-run/external delivery
    evidence.

### 2026-11-07: Notification delivery receipt lifecycle
- **Status:** complete for Local, Cloud and temporary PostgreSQL evidence
- **Actions taken:**
  - Added SQLite and PostgreSQL `notification_deliveries` migrations.
  - Persisted every notification provider receipt, including `DELIVERED`,
    `DISABLED` and `FAILED` outcomes.
  - Added authenticated, user-scoped
    `GET /api/notifications/{notification_id}/deliveries`.
  - Updated OpenAPI, generated TypeScript client, Desktop transport and
    operations/adapter documentation.
  - Added Local and Cloud E2E coverage, including cross-user isolation.
- **Validation:**
  - Local `e2e.sh`: `NOTIFICATION DELIVERY PASS`.
  - Cloud `cloud-e2e.sh`: delivery receipt and user isolation passed.
  - Temporary PostgreSQL Cloud E2E: passed with the new migration.
  - Generated client check and `git diff --check`: passed.

### 2026-11-07: DeepSeek transport contract and Windows artifact gate
- **Status:** implementation and local contract verification complete
- **Actions taken:**
  - Added a real local HTTP compatibility-cloud test for the DeepSeek client,
    covering Bearer authentication, `/chat/completions`, model selection and
    structured JSON decoding.
  - Tightened `scripts/desktop-build.ps1` to fail unless a Windows sidecar
    executable and an actual `*.msi` file are produced.
  - Tightened release preflight to inspect actual MSI files instead of only
    checking whether the output directory exists.
- **Validation:**
  - `./scripts/test.sh`: 114 tests passed.
  - `git diff --check`: passed.
  - Windows script execution remains pending a Windows runner.

### 2026-11-07: User-scoped versioned Rules
- **Status:** complete for Local, Cloud and Desktop contract evidence
- **Actions taken:**
  - Added user-scoped active rulesets and immutable rule snapshots.
  - New tasks capture the current user's rule snapshot; existing tasks continue
    to evaluate with their original version after later rule updates.
  - Added authenticated `GET/POST /api/rules`, generated client support and
    Desktop JSON editor with explicit version save.
  - Added validation for the required Rules v1 fields and audit records for
    new ruleset versions.
- **Validation:**
  - Runtime regression proves default/user-b isolation and snapshot immutability.
  - Local and Cloud E2E both report `RULESET VERSION PASS`.
  - OpenAPI/generated client checks and `git diff --check` pass.

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| 文档清单 | `rg --files` | 所有计划文件存在 | 文件均存在 | PASS |
| 术语一致性 | 搜索 `MVP`、`人工审批`、`Rules-First`、`NO_ACTION` | 核心边界在相关文档一致 | 一致 | PASS |
| 里程碑完整性 | 阅读 `docs/MILESTONES.md` 和 `docs/EXECUTION_PLAN.md` | 每个阶段有目标、交付物、依赖、DoD | 已覆盖 | PASS |
| 验收可验证性 | 阅读 `docs/ACCEPTANCE.md` | 每项验收可通过测试或人工检查证明 | 已覆盖 | PASS |

### 2026-11-08: Provider observability hardening

- **Status:** complete for Local and Cloud runtime code paths
- **Actions taken:**
  - Added capability-level provider call metrics to `RuntimeObservability`.
  - Recorded provider id, capability, method, call count, error count, error rate,
    P95 latency, latest status and latest error for each route.
  - Instrumented fixture replay and live provider fallback paths, so primary
    failures and secondary successes remain distinguishable.
  - Wired `DataWorker.sync_market_data()` into the same metrics callback for
    market snapshot, trading calendar, universe, daily bars, fundamentals,
    news and filings.
  - Added regression coverage for provider latency/error snapshots.
- **Validation:**
  - `./scripts/test.sh`: **186 tests passed**.
  - `./scripts/acceptance.sh`: **local mode passed**, including Cloud and
    temporary PostgreSQL acceptance, recovery/chaos, Desktop UI, mobile builds,
    Tauri lifecycle, sidecar health and macOS notification.
  - Generated TypeScript client check: passed.
  - Desktop Vite production build: passed.
  - `git diff --check`: passed.
- **Remaining boundary:**
  - Metrics expose provider duration and failures, but real DeepSeek/Tushare
    credentials and Windows runner evidence are still external release gates.

### 2026-11-08: Final MVP verification recheck

- **Status:** Local-first MVP core verified; strict release gate remains open
- **Validation:**
  - `./scripts/test.sh`: **186 tests passed**.
  - `./scripts/acceptance.sh`: **local mode passed**, including Local/Cloud/
    temporary PostgreSQL, backup/restore, restart recovery, worker chaos, SLA,
    replay, Desktop UI, Web/iOS/Android builds, Tauri compile, packaged macOS
    lifecycle, sidecar health and macOS native notification.
  - `PIA_DATA_PROVIDER=akshare PIA_FRESHNESS_DATES=2026-11-06
    ./scripts/provider-freshness-e2e.sh`: passed with
    `quality=verified`, `market_snapshot_quality=verified`, universe `7,593`,
    field completeness `1.0`, and no failures.
  - `./scripts/release-preflight.sh`: `mvp_release_ready=false`.
- **Open release gates:**
  - Windows host/MSI/package and native notification evidence;
  - real `DEEPSEEK_API_KEY` structured/streaming/tool acceptance;
  - real `TUSHARE_TOKEN` fallback and cross-provider provenance acceptance.
  - External push credentials remain a full-milestone gate.

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-11-05 | 分享页跳转登录 | 1 | 使用公开分享后端接口 |
| 2026-11-05 | 当前目录无 Git 仓库 | 1 | 生成独立文档包 |
| 2026-11-06 | Shell 搜索命令中的反引号被解释 | 1 | 改用单引号重新执行搜索，结果通过 |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 10 release hardening，Phase 11 cloud baseline 已落地 |
| Where am I going? | 补齐 Cloud notification providers、真实凭据验收、Windows runner 和移动端扩展 |
| What's the goal? | 完整实现文档中的 Local-first MVP 及后续 Local/Cloud/Web/iOS/Android milestones |
| What have I learned? | 代码和 fixture 已形成稳定本地闭环；真实 provider、平台和凭据仍必须单独验收 |
| What have I done? | 已实现 runtime、Rules、Events、Workspace、Cloud sync、typed transport、observability 和 macOS sidecar |
