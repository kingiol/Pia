# Local-first MVP Implementation

P0 / P1 adaptation (2026-11-12): frozen context packs, capability provenance,
deterministic synthesis, stage budgets, execution flow, versioned screening,
request-scoped model routing and budget reservations, change-aware CI, and
persisted result metadata are implemented. See [delivery](CAPABILITY_DELIVERY.md)
and [verification status](CAPABILITY_IMPLEMENTATION_STATUS.md) for interfaces,
conservative defaults, and platform/external-service evidence boundaries.

## Delivered Slice

The repository now contains a runnable local slice for the first vertical workflow:

```text
MarketClose event
  -> fixture/provider snapshot
  -> SQLite persistence
  -> deterministic Rules v1
  -> Agent trace
  -> Evidence
  -> Decision
  -> Human approval gate
  -> append-only audit
  -> React/Vite workspace
```

The execution boundary is:

```text
Tauri 2 Desktop
  -> React + TypeScript + Vite
  -> Python Local Runtime
  -> SQLite
  -> optional live adapters (AKShare, Tushare, DeepSeek)
```

## Implementation Map

| Area | Files | Behavior |
|---|---|---|
| Contracts | `contracts/openapi.yaml`, `contracts/schemas/` | Task, decision, evidence and event shapes |
| Persistence | `migrations/001_initial.sql`, `migrations/002_events.sql` | Tasks, snapshots, trace, evidence, decisions, approvals, audit and events |
| Runtime | `packages-py/pia_runtime/pia_runtime/runtime.py` | Local task lifecycle and replayable orchestration |
| Rules | `packages-py/pia_runtime/pia_runtime/rules.py`, `runtime.py`, `db.py` | Rules v1, per-user versions, task snapshots, data, market, portfolio and concentration gates |
| Providers | `packages-py/pia_runtime/pia_runtime/adapters.py` | Fixture provider, AKShare latest and historical point-in-time adapters, and credential-gated Tushare boundary |
| LLM | `packages-py/pia_runtime/pia_runtime/llm.py`, `credentials.py` | ModelRouter、DeepSeek OpenAI-compatible structured/streaming/tool-call generation、usage、stable error mapping and native credential-manager lookup |
| Portfolio | `packages-py/pia_runtime/pia_runtime/portfolio.py` | CSV, dependency-free XLSX first-sheet and manual imports |
| Events | `packages-py/pia_runtime/pia_runtime/events.py`, `runtime.py` | Priority metadata, cooldown-bucket dedupe, automatic event derivation from market/portfolio sync and declared event dispatch |
| Retrospective | `migrations/015_retrospectives.sql`, `runtime.py`, `api.py`, `apps/desktop/src/App.tsx` | Records actual user action and observed outcome against immutable task snapshots for rule review |
| API | `packages-py/pia_runtime/pia_runtime/api.py` | Local/cloud JSON API, bearer auth, leases, finite SSE trace stream, manual takeover, task-context export and runtime metrics |
| Workspace | `apps/desktop/src/`, `apps/web/src/` | Profile, candidate scan, research, debate, evidence, trace and approval UI |
| Desktop shell | `apps/desktop/src-tauri/` | Tauri 2 window, tray status/scheduler controls, hide-to-tray lifecycle, managed Python runtime cleanup, macOS/Windows bundle targets and platform-native notification entry points |
| Verification | `tests/`, `scripts/` | Unit, contract, replay, REST/SSE E2E and build checks |

## Runtime Modes

Replay and local development use fixed fixtures and deterministic calculations. This keeps Rules, state transitions and audit behavior testable without a network dependency.

For a live LLM call, set:

```env
PIA_REQUIRE_LLM=1
DEEPSEEK_API_KEY=<local secret>
```

The API key is read only by the Python runtime. A missing key produces `CREDENTIALS_REQUIRED` and a recoverable task state; it never falls back to a fabricated model response.

Cloud runtime supports separate API, worker and scheduler roles:

```bash
PIA_POSTGRES_DSN='postgresql://...' PIA_CLOUD_AUTH_TOKEN=<token> PIA_START_SCHEDULER=1 ./scripts/cloud.sh
```

The API process handles authentication, task and sync endpoints. The worker
claims queued tasks through database leases. The scheduler uses the provider
trading calendar and the same event deduplication rules to dispatch
`MarketClose` once per registered user with user-scoped dedupe keys. Worker
processes never start a scheduler. Leaving `PIA_START_SCHEDULER` unset runs API and worker only,
which is suitable for an external scheduler or manually ingested events.

Cloud requires PostgreSQL for both business records and analytical storage.
`PostgresAnalyticsStore` reuses the analytical repository methods and shares the
business repository's connection and transactions. Cloud does not open SQLite
or DuckDB files; `PIA_DB_PATH` and `PIA_DUCKDB_PATH` apply to Local storage.
Pre-release Cloud deployments initialize a fresh PostgreSQL database without
legacy DuckDB imports. See [Cloud Storage](CLOUD_STORAGE.md) for deployment and
backup/restore.

Market-derived quality, breadth, price-volume and filing events also carry
user-scoped dedupe keys in Cloud mode, so one user's event cannot suppress
another user's event.

## Remaining Expansion Boundaries

The following remain explicit release or expansion boundaries and are not hidden as completed MVP behavior:

- longer-run AKShare freshness, field coverage and upstream contract monitoring;
  historical aggregate snapshots now use date-scoped stock/ETF bars, indices and
  sectors, with bounded parallel fetching, provider caches and a 98% coverage
  gate. Latest-only providers still fail closed for older requested dates;
- Tushare credential/quota activation, fallback acceptance and cross-provider provenance;
- Windows sidecar, MSI packaging, launch and health verification;
- Windows/cross-session notification delivery and long-run external-service SLA evidence;
  Windows now attempts WinRT Toast and falls back to the session `msg` command;
  real Windows runner and cross-session evidence remain open;
- platform push credentials and delivery acceptance for APNs/FCM/Web Push;
- device lifecycle, incremental sync, secure mobile token storage, Web Push
  subscription, APNs token upload and Android push-token storage/background
  refresh scheduling are implemented in the mobile clients, but require
  device/emulator runtime acceptance;
- cloud notification gateway delivery through
  `PIA_NOTIFICATION_WEBHOOK_URL` / `PIA_NOTIFICATION_WEBHOOK_TOKEN` and
  platform-specific Web Push/APNs/FCM routes has local HTTP gateway acceptance;
  notification delivery receipts are persisted and exposed through the
  authenticated notification deliveries endpoint;
  external provider credentials and real device delivery remain open;
- signed installer/update metadata and real broker write access remain open;
  PostgreSQL-backed cloud execution, multi-device sync and device lifecycle
  contracts are implemented and covered by local/temporary-PostgreSQL E2E.

Credential handling is implemented through `pia credentials set/status/delete`
and Desktop's Local settings. Saved DeepSeek credentials take precedence over
`DEEPSEEK_API_KEY`; clearing them restores the environment fallback. Other
credentials retain environment-first precedence. Secrets are not persisted in
SQLite, DuckDB, task payloads or logs.

The metrics response now includes queue depth, active task age, storage bytes,
database backend and worker heartbeat age in addition to task success rate,
P95 duration, request latency and LLM usage.

The Desktop workspace also implements the documented platform interaction
boundary: Command/Ctrl+K focuses the Topbar search, Command/Ctrl+P navigates
to Portfolio, Command/Ctrl+Enter creates a New review, and a successful review
creation returns to Overview. The Topbar search filters tasks by id, status,
trigger and target payload. Narrow detail panels explicitly opt into
shrinkable grid sizing so long evidence and trace content cannot create
horizontal overflow on mobile-width Web/Tauri windows.

The shared workspace includes accessible lightweight charts for Market breadth,
Index trend, Portfolio exposure, Drawdown and Agent timeline. Each chart
exposes its title, unit, as-of date, source and exact values in text, including
an explicit empty state when its input series is unavailable.

Local DuckDB and Cloud PostgreSQL analytical storage preserve raw provider
payloads, normalized daily bars and analytical snapshots. Local backup packages
include SQLite and DuckDB; Cloud backups contain one PostgreSQL dump for both
business and analytical tables. The authenticated Cloud runtime, task leases
and shared Web build retain the same Rules, evidence and approval boundaries.

Rule retrospectives are available in both Local and Cloud modes through
`POST /api/tasks/{task_id}/retrospectives` and
`GET /api/tasks/{task_id}/retrospectives`. Each record keeps the task's rule
and data snapshot identifiers, observed time, actual action, outcome and notes,
and is included in task detail/context and incremental audit sync.
