# Pia Pilot User Guide

## 1. First launch

Pia opens with a five-step checklist:

```text
投资方式 -> 持仓 -> 规则 -> 数据 -> 第一次收盘复盘
```

Use 「体验演示复盘」 to inspect a sample result before importing holdings. The
preview uses sample data and does not create research or journal records. For a
personal review, follow the highlighted setup steps.

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

For the desktop holdings pilot, open **收盘持仓复核** on the overview. It
uses the latest compatible imported holdings, verified closing prices, and
your personal position limits. Fill in account cash, including an explicit
zero if applicable. If the holdings snapshot is older than the trading
session, confirm that quantities and cash were unchanged or update the
holdings first. See [the holdings review specification](DAILY_HOLDINGS_REVIEW.md)
for coverage and retry behavior.

The manual review shows the proposed close date. The runtime uses its configured
close time and the cached trading calendar. The UI flags estimates when the
calendar is missing. Fixture mode uses the demo date. The scheduler can also
dispatch a MarketClose event. Open a stored task to replay its original inputs.

```text
event -> data snapshot -> agents -> debate -> risk review -> decision
```

Every conclusion must show its source, `as_of`, `observed_at`, quality and
expiry state. A stale or unavailable snapshot blocks a new action.

## 5. Review and record the outcome

Compare the market date and portfolio date in the research result, then open
the applicable rule and evidence. A result awaiting review can be marked for
watch, sent for further research, or dismissed. Use 「记录不行动」 beside a
completed result to save why you took no action. Use the retrospective form to
record other actions or subsequent outcomes. 「查看本次决策日志」 opens the
entry for that research.

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
