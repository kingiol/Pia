# Cloud Storage

## Scope and Acceptance

Cloud uses PostgreSQL for transactional records and analytical data. Local mode
continues to use SQLite and DuckDB. Cloud startup requires `PIA_POSTGRES_DSN`;
there is no implicit file-backed fallback.

The analytical repository keeps its existing methods and result shapes. Cloud
stores raw provider payloads, normalized bars, instruments, fundamentals,
research sources, calendars and analytical snapshots in PostgreSQL. It shares
the transactional repository's connection and transaction boundary.

Acceptance:

- Cloud API and worker can read each other's analytical writes without any
  SQLite or DuckDB files.
- Local storage and frozen-context replay continue to work.
- All seven analytical tables support inserts, updates and batch rollback.
- Cloud backup and restore use a single PostgreSQL dump containing both stores.
- A fresh PostgreSQL database is initialized automatically at Cloud startup.

## Deployment and Transaction Boundaries

Cloud has not launched. Deploy against a fresh PostgreSQL database; existing
development databases can be recreated. Legacy Cloud DuckDB imports and
two-store backup compatibility are outside scope. Stop API, worker and scheduler
processes before replacing a development database.

```bash
export PIA_POSTGRES_DSN='postgresql://...'
PIA_CLOUD_AUTH_TOKEN='<token>' ./scripts/cloud.sh
```

Cloud startup applies PostgreSQL schema migrations, including analytical tables.
API and worker startup serialize schema initialization with an advisory lock.
No DuckDB or SQLite file is read or created.

The unified database removes the cross-engine commit boundary, but does not
make an entire research task one transaction. Existing task stages and
checkpoints remain independently persisted.

## Operations

```bash
PIA_CLOUD_AUTH_TOKEN='<token>' ./scripts/cloud.sh
./scripts/cloud-backup.sh /absolute/path/backup
./scripts/cloud-restore.sh /absolute/path/backup
```

New backups use `pia-cloud-backup-v2`, contain `postgres.dump` and an integrity
manifest, and require no `PIA_DUCKDB_PATH`. Restore requires stopped Cloud
processes and replaces the destination's backed-up database objects.

## Validation

Run `./scripts/test.sh`, `./scripts/postgres-cloud-e2e.sh` and
`./scripts/cloud-backup-restore-e2e.sh`. PostgreSQL integration coverage includes
analytical upserts, shared rollback, independent connections, concurrent startup,
task data access, frozen replay and dump/restore.

Cloud storage sizes report the entire PostgreSQL database under `database`,
and its analytical tables and indexes under `analytics_database`. These values
overlap and must not be added.

### Verification on 2026-11-16

- `./scripts/test.sh`: passed; 273 Python tests, with 7 PostgreSQL integration
  tests skipped in the offline suite; contract generation, documentation links,
  Desktop tests, TypeScript checking and Desktop build passed.
- `./scripts/postgres-cloud-e2e.sh`: passed against a disposable PostgreSQL
  cluster. The 7 PostgreSQL tests skipped above passed here, alongside the
  multi-process API/worker, scheduler and push-gateway scenarios.
- `./scripts/cloud-backup-restore-e2e.sh`: passed for unified PostgreSQL backups,
  including restored analytical data and offline replay.
- Shell syntax and `git diff --check`: passed.

Fixtures and a local HTTP push gateway were used. No existing Cloud database was
recreated, no deployment was performed, and remote GitHub Actions were not run.
