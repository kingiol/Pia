#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

mode="${PIA_ACCEPTANCE_MODE:-local}"
root_tmp="$(mktemp -d)"
trap 'rm -rf "$root_tmp"' EXIT

echo "== Pia acceptance: ${mode} =="

if [ "$mode" = "release" ]; then
  if ! "$PWD/scripts/python.sh" - <<'PY'
from pia_runtime.credentials import configured_secret, is_configured

raise SystemExit(0 if is_configured(configured_secret("DEEPSEEK_API_KEY")) else 1)
PY
  then
    echo "RELEASE ACCEPTANCE FAIL: DEEPSEEK_API_KEY is required in the environment or native credential manager" >&2
    exit 2
  fi
  if [ "${PIA_DATA_PROVIDER:-akshare}" != "akshare" ]; then
    echo "RELEASE ACCEPTANCE FAIL: PIA_DATA_PROVIDER must be akshare" >&2
    exit 2
  fi
fi

echo "-- Python, contracts and Desktop build"
./scripts/test.sh
echo "-- Temporal freshness soak"
./scripts/freshness-e2e.sh

echo "-- Scheduler, market-close dispatch and dedupe"
./scripts/scheduler-e2e.sh

echo "-- Local REST/SSE and metrics"
PIA_DB_PATH="$root_tmp/local.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/local.duckdb" \
  ./scripts/e2e.sh

echo "-- PostgreSQL backup and restore"
./scripts/cloud-backup-restore-e2e.sh

echo "-- PostgreSQL Cloud auth, isolation and leases (temporary cluster)"
./scripts/postgres-cloud-e2e.sh

echo "-- Restart recovery and retry"
PIA_DB_PATH="$root_tmp/recovery.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/recovery.duckdb" \
PIA_RECOVERY_ROOT="$root_tmp/recovery" \
PIA_PORT="${PIA_ACCEPTANCE_RECOVERY_PORT:-8876}" \
  ./scripts/recovery-e2e.sh

echo "-- Worker crash recovery"
PIA_DB_PATH="$root_tmp/chaos.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/chaos.duckdb" \
PIA_CHAOS_ROOT="$root_tmp/chaos" \
PIA_PORT="${PIA_ACCEPTANCE_CHAOS_PORT:-8875}" \
  ./scripts/chaos-e2e.sh

echo "-- Local SLA and success-rate gate"
PIA_DB_PATH="$root_tmp/sla.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/sla.duckdb" \
PIA_DATA_PROVIDER=fixture \
PIA_SLA_ROOT="$root_tmp/sla" \
  ./scripts/sla-e2e.sh

if [ -n "${PIA_POSTGRES_DSN:-}" ]; then
  echo "-- PostgreSQL Cloud auth, isolation and leases"
  PIA_PORT="${PIA_ACCEPTANCE_POSTGRES_PORT:-8879}" \
    ./scripts/cloud-e2e.sh
else
  echo "POSTGRES ACCEPTANCE SKIP (set PIA_POSTGRES_DSN to run)"
fi

echo "-- Replay and Web build"
PIA_DB_PATH="$root_tmp/replay.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/replay.duckdb" \
PIA_DATA_PROVIDER=fixture \
  ./scripts/replay.sh >/dev/null
pnpm run build:web >/dev/null
echo "-- Desktop GUI smoke"
./scripts/desktop-ui-smoke.sh

echo "-- Web, iOS and Android client acceptance"
./scripts/mobile-acceptance.sh

echo "-- Tauri compile"
cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml

if [ "$(uname -s)" = "Darwin" ] && [ -d "apps/desktop/src-tauri/target/release/bundle/macos/Pia.app" ]; then
  echo "-- Packaged Desktop lifecycle"
  ./scripts/desktop-lifecycle-smoke.sh
else
  echo "DESKTOP LIFECYCLE SKIP (macOS release bundle not available)"
fi

sidecar="$(find apps/desktop/src-tauri/binaries -maxdepth 1 -type f -perm -111 -name 'pia-runtime-*' -print -quit 2>/dev/null || true)"
if [ -n "$sidecar" ]; then
  echo "-- Packaged sidecar health"
  "$sidecar" health --json >/dev/null
  echo "SIDECAR HEALTH PASS"
else
  echo "SIDECAR HEALTH SKIP (build with scripts/build-sidecar.sh)"
fi

if [ "$(uname -s)" = "Darwin" ]; then
  echo "-- macOS native notification smoke"
  ./scripts/native-notification-smoke.sh
elif [ "$(uname -s)" = "Windows_NT" ] && command -v pwsh >/dev/null 2>&1; then
  echo "-- Windows native notification smoke"
  pwsh -NoProfile -File ./scripts/native-notification-smoke.ps1
else
  echo "NATIVE NOTIFICATION SMOKE SKIP (requires macOS or PowerShell on Windows)"
fi

if [ "$mode" = "release" ]; then
  push_gateway_configured=0
  for push_gateway_var in PIA_WEB_PUSH_GATEWAY_URL PIA_APNS_GATEWAY_URL PIA_FCM_GATEWAY_URL; do
    if [ -n "${!push_gateway_var:-}" ]; then
      push_gateway_configured=1
      break
    fi
  done
  if [ "$push_gateway_configured" = "1" ]; then
    echo "-- External push delivery"
    ./scripts/push-acceptance.sh
  else
    echo "EXTERNAL PUSH ACCEPTANCE SKIP (configure a gateway URL and token to run)"
  fi
  echo "-- Live provider and DeepSeek checks"
  PIA_DB_PATH="$root_tmp/live.sqlite3" \
  PIA_DUCKDB_PATH="$root_tmp/live.duckdb" \
  PIA_DATA_PROVIDER=akshare \
  PIA_REQUIRE_LLM=1 \
  PIA_ACCEPTANCE_AS_OF="${PIA_ACCEPTANCE_AS_OF:-2026-11-06}" \
    "$PWD/scripts/python.sh" - <<'PY'
import os
from pathlib import Path
from pia_runtime.adapters import AkshareMarketProvider
from pia_runtime.analytics import AnalyticsStore
from pia_runtime.config import Settings
from pia_runtime.credentials import configured_secret
from pia_runtime.data_worker import DataWorker
from pia_runtime.llm import DeepSeekClient
from pia_runtime.runtime import PiaRuntime

provider = AkshareMarketProvider()
as_of = os.environ["PIA_ACCEPTANCE_AS_OF"]
symbols = [
    item.strip()
    for item in os.environ.get("PIA_ACCEPTANCE_SYMBOLS", "600000.SH").split(",")
    if item.strip()
]
store = AnalyticsStore(Path(os.environ["PIA_DUCKDB_PATH"]))
try:
    sync = DataWorker(provider, store).sync_market_data(as_of, symbols)
finally:
    store.close()
if sync["market_snapshot_quality"] != "verified":
    raise SystemExit(
        f"live market snapshot quality gate failed: {sync['market_snapshot_quality']}"
    )
if sync["quality"] != "verified" or sync["failures"]:
    raise SystemExit(f"live data quality gate failed: {sync}")
required_counts = ("market_snapshot", "trading_calendar", "universe", "daily_bars", "fundamentals")
if any(sync["counts"].get(key, 0) <= 0 for key in required_counts):
    raise SystemExit(f"live data completeness gate failed: {sync['counts']}")
client = DeepSeekClient(
    Settings.from_env().deepseek_api_key,
    Settings.from_env().deepseek_base_url,
    Settings.from_env().deepseek_model,
)
result = client.generate_json(
    "Return a JSON object with a single boolean field named ok.",
    {"ok": True},
)
if result.get("ok") is not True:
    raise SystemExit("DeepSeek structured output contract failed")
tool_calls = [{
    "type": "function",
    "function": {
        "name": "read_fixture",
        "description": "Read the supplied fixture marker before returning the result.",
        "parameters": {
            "type": "object",
            "properties": {"marker": {"type": "string"}},
            "required": ["marker"],
            "additionalProperties": False,
        },
    },
}]
tool_invocations = []
tool_result = client.generate_with_tools(
    "Use the read_fixture tool with marker 'live' and then return JSON with ok=true.",
    {"ok": True},
    tool_calls,
    lambda name, arguments: tool_invocations.append((name, arguments)) or {"marker": "live"},
)
if tool_result.get("ok") is not True or not tool_invocations:
    raise SystemExit("DeepSeek tool-calling contract failed")
stream_events = list(client.stream_with_tools(
    "Return a JSON object with a single boolean field named ok.",
    {"ok": True},
    [],
    lambda name, arguments: {},
))
stream_result = next(
    (event.result for event in reversed(stream_events) if event.kind == "completed"),
    None,
)
if not isinstance(stream_result, dict) or stream_result.get("ok") is not True:
    raise SystemExit("DeepSeek streaming contract failed")

runtime = PiaRuntime(Settings.from_env())
try:
    live_task = runtime.create_task(
        "StockResearch",
        {"as_of": as_of, "symbol": symbols[0]},
    )
    live_detail = runtime.wait_for_task(
        live_task.id,
        timeout=runtime.settings.task_timeout_seconds + 30,
    )
    if not live_detail:
        raise SystemExit("Live runtime task returned no detail")
    live_status = live_detail["task"]["status"]
    if live_status in {"FAILED", "RETRYABLE", "TIMEOUT"}:
        raise SystemExit(
            f"Live runtime task failed: {live_status} "
            f"{live_detail['task'].get('error')}"
        )
    if not live_detail.get("trace"):
        raise SystemExit("Live runtime task produced no agent trace")
    if not any(
        row.get("agent_name") == "LLM Research Manager"
        for row in live_detail.get("trace", [])
    ):
        raise SystemExit("Live runtime task did not execute LLM Research Manager")
    print("LIVE RUNTIME TASK PASS", live_task.id, live_status)
finally:
    runtime.close()

tushare_token = configured_secret("TUSHARE_TOKEN")
if tushare_token:
    from pia_runtime.adapters import TushareMarketProvider

    tushare = TushareMarketProvider(tushare_token)
    health = tushare.health()
    if health.status != "healthy":
        raise SystemExit(f"Tushare provider is not healthy: {health.to_dict()}")
    tushare_snapshot = tushare.get_market_snapshot(as_of)
    if tushare_snapshot.get("source") != "tushare":
        raise SystemExit("Tushare snapshot provenance is missing")
    calendar = tushare.get_trading_calendar(as_of, as_of)
    if not calendar:
        raise SystemExit("Tushare trading calendar returned no rows")
    universe = tushare.get_universe()
    if not universe:
        raise SystemExit("Tushare universe returned no rows")
    symbol = symbols[0]
    daily_bars = tushare.get_daily_bars(symbol, as_of, as_of)
    if not daily_bars:
        raise SystemExit(f"Tushare daily bars returned no rows for {symbol}")
    if any(row.get("provider_id") != "tushare" for row in daily_bars):
        raise SystemExit("Tushare daily-bar provenance is missing")
    fundamentals = tushare.get_fundamentals(symbol)
    if fundamentals.get("source") != "tushare":
        raise SystemExit("Tushare fundamentals provenance is missing")
    news = tushare.search_news(symbol)
    filings = tushare.search_filings(symbol, as_of)
    for source_name, rows in (("news", news), ("filings", filings)):
        for row in rows:
            if row.get("symbol") != symbol or row.get("quality") not in {"verified", "partial"}:
                raise SystemExit(f"Tushare {source_name} provenance or quality is invalid")
    print(
        "TUSHARE LIVE PASS",
        tushare_snapshot.get("snapshot_id"),
        {
            "calendar": len(calendar),
            "universe": len(universe),
            "daily_bars": len(daily_bars),
            "news": len(news),
            "filings": len(filings),
        },
    )
else:
    print("TUSHARE LIVE SKIP (set TUSHARE_TOKEN to validate fallback and provenance)")
print("LIVE PROVIDER + DEEPSEEK STREAM/TOOLS PASS")
PY
  if [ -n "${PIA_FRESHNESS_DATES:-}" ] || [ -n "${PIA_FRESHNESS_LOOKBACK_DAYS:-}" ]; then
    echo "-- Credentialed provider freshness"
    ./scripts/provider-freshness-e2e.sh
  else
    echo "PROVIDER FRESHNESS SKIP (set PIA_FRESHNESS_DATES or PIA_FRESHNESS_LOOKBACK_DAYS)"
  fi
else
  echo "LIVE ACCEPTANCE SKIP (set PIA_ACCEPTANCE_MODE=release with local credentials)"
fi

echo "Pia acceptance checks passed for mode=${mode}"
