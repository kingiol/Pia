#!/usr/bin/env python3
"""Run a credentialed multi-date provider freshness gate."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pia_runtime.adapters import AkshareMarketProvider, TushareMarketProvider
from pia_runtime.analytics import AnalyticsStore
from pia_runtime.config import Settings
from pia_runtime.credentials import configured_secret
from pia_runtime.data_worker import DataWorker


def run_freshness(
    provider: Any,
    dates: list[str],
    symbols: list[str],
    database_path: Path,
) -> dict[str, Any]:
    if not dates:
        raise ValueError("at least one trading date is required")
    if not symbols:
        raise ValueError("at least one symbol is required")

    store = AnalyticsStore(database_path)
    results: list[dict[str, Any]] = []
    try:
        worker = DataWorker(provider, store)
        for as_of in dates:
            result = worker.sync_market_data(as_of, symbols)
            failures = result.get("failures", [])
            results.append({
                "as_of": as_of,
                "provider_id": result.get("provider_id"),
                "quality": result.get("quality"),
                "market_snapshot_quality": result.get("market_snapshot_quality"),
                "field_completeness": result.get("market_quality", {}).get(
                    "field_completeness"
                ),
                "counts": result.get("counts", {}),
                "failures": failures,
            })
            if any(failure.get("code") == "Push2RateLimitError" for failure in failures):
                break
    finally:
        store.close()

    failures = [
        item
        for item in results
        if item["quality"] != "verified"
        or item["market_snapshot_quality"] != "verified"
        or item["failures"]
    ]
    return {
        "provider_id": provider.provider_id,
        "dates": dates,
        "symbols": symbols,
        "results": results,
        "passed": not failures,
        "failed_dates": [item["as_of"] for item in failures],
        "unchecked_dates": dates[len(results):],
    }


def resolve_freshness_dates(
    provider: Any,
    requested_dates: list[str],
    lookback_days: int = 0,
    *,
    now: datetime | None = None,
) -> tuple[list[str], str]:
    """Resolve explicit dates or the latest completed trading sessions."""
    if requested_dates:
        return requested_dates, "explicit"
    if lookback_days <= 0:
        return [], "missing"

    market_timezone = ZoneInfo("Asia/Shanghai")
    local_now = now.astimezone(market_timezone) if now else datetime.now(market_timezone)
    close_time = time.fromisoformat(os.getenv("PIA_MARKET_CLOSE_TIME", Settings().market_close_time))
    last_completed_day = local_now.date()
    if local_now.time() < close_time:
        last_completed_day -= timedelta(days=1)
    calendar_start = last_completed_day - timedelta(days=max(lookback_days * 3, lookback_days + 10))
    rows = provider.get_trading_calendar(
        calendar_start.isoformat(),
        last_completed_day.isoformat(),
    )
    open_dates = sorted({
        str(row.get("trade_date", ""))[:10]
        for row in rows
        if row.get("is_open") and str(row.get("trade_date", ""))[:10] <= last_completed_day.isoformat()
    })
    dates = open_dates[-lookback_days:]
    if len(dates) < lookback_days:
        raise ValueError(
            f"provider calendar returned only {len(dates)} open dates; "
            f"{lookback_days} required"
        )
    return dates, "provider_calendar"


def _provider(name: str) -> Any:
    if name == "akshare":
        return AkshareMarketProvider()
    if name == "tushare":
        token = configured_secret("TUSHARE_TOKEN")
        if not token:
            raise SystemExit(
                "TUSHARE_TOKEN is required in the environment or native credential manager"
            )
        return TushareMarketProvider(token)
    raise SystemExit(f"unsupported provider: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default=os.environ.get("PIA_DATA_PROVIDER", "akshare"),
        choices=("akshare", "tushare"),
    )
    parser.add_argument(
        "--dates",
        default=os.environ.get("PIA_FRESHNESS_DATES", ""),
        help="comma-separated trading dates in YYYY-MM-DD form",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=int(os.environ.get("PIA_FRESHNESS_LOOKBACK_DAYS", "0") or "0"),
        help="resolve the latest N completed trading dates from the provider calendar",
    )
    parser.add_argument(
        "--symbols",
        default=os.environ.get("PIA_ACCEPTANCE_SYMBOLS", "600000.SH"),
        help="comma-separated symbols",
    )
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args()

    requested_dates = [value.strip() for value in args.dates.split(",") if value.strip()]
    symbols = [value.strip() for value in args.symbols.split(",") if value.strip()]
    provider = _provider(args.provider)
    try:
        dates, date_source = resolve_freshness_dates(
            provider,
            requested_dates,
            args.lookback_days,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not dates:
        raise SystemExit(
            "set PIA_FRESHNESS_DATES or PIA_FRESHNESS_LOOKBACK_DAYS "
            "to run provider freshness"
        )
    temporary_database: tempfile.TemporaryDirectory[str] | None = None
    database_path = args.database
    if database_path is None:
        temporary_database = tempfile.TemporaryDirectory(prefix="pia-provider-freshness-")
        database_path = Path(temporary_database.name) / "freshness.duckdb"
    try:
        report = run_freshness(provider, dates, symbols, database_path)
        report["date_source"] = date_source
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 2
    finally:
        if temporary_database is not None:
            temporary_database.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
