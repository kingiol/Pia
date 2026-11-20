# Pia Pilot User Guide

## 1. First launch

Pia opens with a five-step checklist:

```text
投资方式 -> 持仓 -> 规则 -> 数据 -> 第一次收盘复盘
```

Finish the highlighted next step before starting a review. The workspace shows
whether the current snapshot is live data or replay data; replay data is for
checking the workflow and must not be treated as live market readiness.

## 2. Start the local workspace

```bash
./scripts/desktop.sh
```

The desktop shell starts the local Python sidecar, SQLite and DuckDB. A Cloud
runtime is optional for the local MVP flow.

## 3. Configure a Profile

Open Profile and confirm:

- allowed asset types and universe;
- risk preference and drawdown limits;
- enabled Ruleset version;
- current portfolio and cash.

Import portfolio data with CSV, XLSX or manual rows. Set the business date the
holdings describe. A new review uses the latest imported snapshot on or before
its research date. The fixture walkthrough uses the demo date shown in the
import form. In Rules, enter a single-stock position limit as a percentage to
save a new version. Existing research keeps its original inputs and rules.

## 4. Run research

Start today's close review after the close or let the scheduler dispatch a
MarketClose event. The manual review uses the current Shanghai date in live
mode and the demo date in fixture mode. Open a stored task to replay the inputs
from an earlier session. Follow the task timeline:

```text
event -> data snapshot -> agents -> debate -> risk review -> decision
```

Every conclusion must show its source, `as_of`, `observed_at`, quality and
expiry state. A stale or unavailable snapshot blocks a new action.

## 5. Review and record the outcome

Compare the market date and portfolio date in the research result, then open
the applicable rule and evidence. A result awaiting review can be marked for
watch, sent for further research, or dismissed. Use the retrospective form to
record what you did, including why you took no action. Open the Decision
Journal to find the record and replay the original research inputs.

## 6. Recover a failed task

For a failed task:

1. inspect the failure and last completed Agent in Trace;
2. retry when the failure is transient;
3. pause/resume when input or credentials need correction;
4. take over manually and export context when investigation is needed;
5. cancel only when the task should not continue.

Do not delete the task to hide a failure. Audit records are append-only.

## 7. Before a pilot session

Run the local checks:

```bash
./scripts/test.sh
./scripts/replay.sh
./scripts/release-preflight.sh
```

The preflight command may return non-zero when external credentials or a
platform runner are unavailable. Treat that output as a release checklist, not
as a task failure.

## 8. Pilot safety boundaries

- Use daily or close data only unless a separately approved data source is
  configured.
- Never treat a fixture replay as proof of live provider readiness.
- Do not bypass a Rules or Risk Review block.
- Verify evidence freshness before relying on a conclusion.
- Keep API keys and provider tokens in the local environment or credential
  manager only.
