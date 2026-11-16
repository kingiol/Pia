# Pia Requirement Matrix

2026-11-12 P0/P1 adaptation: implementation and verification for CAP-P0-01..05
and CAP-P1-01..04 are tracked in [Capability Implementation Status](CAPABILITY_IMPLEMENTATION_STATUS.md).
The matrix below retains earlier MVP evidence; it is not a claim that new
external-service or platform release checks have run.

审计日期：2026-11-08

This matrix separates implementation from deployment evidence. A contract or
unit test is not treated as proof of a real external gateway or platform
runtime.

| Requirement | Local evidence | Cloud evidence | Mobile/Web evidence | Status |
|---|---|---|---|---|
| FR-001 Profile | SQLite profile versions, Desktop editor, runtime tests | PostgreSQL repository and user-scoped API in `cloud-e2e.sh` | Profile context is included in task APIs | Implemented and verified |
| FR-002 Versioned Rules | Rule snapshots, gate tests and replay | PostgreSQL migration parity and authenticated rules API | Rules gate is rendered in clients | Implemented and verified |
| FR-003 Portfolio | Manual/CSV/XLSX import, exposure and risk tests | User-scoped portfolio import/read in Cloud E2E | Task context exposes portfolio-derived risk | Implemented and verified |
| FR-010 Market Observation | AKShare sync, raw/normalized/snapshot layers, freshness gate | Cloud data sync endpoint and provider health | Data Health view and typed transport | Implemented and verified |
| FR-011 Candidate Scan | Ranked scan and replay tests | Authenticated candidate endpoint with user profile scope | Desktop/Web workspace path | Implemented and verified |
| FR-012 Event Deduplication | Scheduler and event unit/E2E tests | User-scoped dedupe and event isolation in Cloud E2E | Sync consumes scoped audit changes | Implemented and verified |
| FR-020 Research Task | Local task state machine, trace and SSE | Authenticated task API, independent worker and scheduler | iOS/Android/Web task transport with authenticated SSE detail refresh | Implemented and verified |
| FR-021 Structured Agent State | LangGraph/Pydantic contracts and agent trace | Worker executes the same runtime against shared database | Client task detail decodes structured payloads | Implemented and verified |
| FR-022 Evidence Citation | Evidence persistence, expiry gates and replay | Authenticated task data/context and evidence provenance | Desktop/iOS evidence panels | Implemented and verified |
| FR-023 Bull/Bear Debate | Graph nodes, debate outputs and UI smoke | Cloud worker produces the same trace and decision | Desktop/iOS task detail renders trace/evidence | Implemented and verified |
| FR-024 Retry/Takeover | Retry, timeout, crash recovery and takeover tests | Worker lease/retry/recovery E2E | iOS/Android takeover and retry controls | Implemented and verified |
| FR-024a Context Export | Local context export and replay | Authenticated `/context` endpoint and isolation checks | Generated client and mobile transport methods | Implemented and verified |
| FR-030 Rules Gate | Deterministic P0 rule matrix | Cloud approval guard and PostgreSQL parity | Approval actions are status-gated | Implemented and verified |
| FR-031 Risk Review | Risk agent, priority preemption and portfolio gates | User-scoped risk events and cloud task execution | Risk section in task detail | Implemented and verified |
| FR-032 Human Approval | Approval records, no-auto-order guard and audit | Authenticated approval with user isolation | Desktop/iOS/Android approval actions | Implemented and verified |
| FR-033 Audit Record | Append-only audit and replay | Scoped audit API, sync cursor and PostgreSQL migrations | Mobile sync persists cursor | Implemented and verified |
| FR-034 Rule Retrospective | Immutable retrospective storage and UI | PostgreSQL parity and user-scoped Cloud E2E | Client contract exposes task context | Implemented and verified |
| M1 Local Sidecar | Tauri sidecar, packaged macOS lifecycle and health smoke | Cloud role boundary is explicit | Web/mobile do not depend on local sidecar | Local verified; Windows evidence pending |
| M2 Provider quality | AKShare point-in-time freshness, 7,593 instruments, completeness 1.0 | Provider health/metrics and fallback contracts | Data health fields are transportable | AKShare verified; Tushare live evidence pending |
| M6 Notification routing | Local native notification and delivery receipt | Webhook/platform gateway routing, persisted receipts and retryable event delivery | Web service worker, iOS APNs token upload, Android token storage | Code verified; external gateway/device delivery pending |
| M7 Backup/recovery/operations | SQLite/DuckDB backup, restore, chaos and SLA | PostgreSQL `pg_dump`/`pg_restore` drill and metrics | Client background refresh boundaries build | Implemented; production platform evidence pending |

## Evidence status

- `./scripts/test.sh`: 197 tests passed.
- `PIA_ACCEPTANCE_MODE=release ... ./scripts/acceptance.sh`: Local/Cloud,
  temporary PostgreSQL, recovery, chaos, SLA, Replay, Desktop, Tauri,
  macOS lifecycle, mobile builds, live DeepSeek and AKShare freshness passed.
- `./scripts/cloud-e2e.sh` and `./scripts/postgres-cloud-e2e.sh`: authenticated
  task execution, leases, pause/resume, isolation, sync, devices, notifications
  and idempotency passed.
- `./scripts/mobile-acceptance.sh`: iOS transport/tests, Android debug build,
  WorkManager boundary, authenticated mobile SSE clients and Web
  service-worker syntax passed.
- `./scripts/release-preflight.sh`: Windows MSI/host and Tushare are not
  verified; external Web Push/APNs/FCM credentials are not configured.

The latest release acceptance rerun also passed after mobile SSE completion;
it covered authenticated iOS/Android task streams, Local/Cloud execution,
temporary PostgreSQL, recovery/chaos/SLA, Tauri/macOS packaging and live
DeepSeek/AKShare checks.

The remaining rows are deployment or credential gates. They must remain
explicitly unverified until a Windows runner, real Tushare token, or external
push gateway/device is available.
