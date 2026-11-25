"""Collect and verify same-session observations through the holdings review route."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.holdings_review import MARKET_ZONE, _verified_calendar, session_inputs
from pia_runtime.provider_provenance import CapabilityUnavailable
from pia_runtime.runtime import PiaRuntime


SYMBOLS = ("600000.SH", "000001.SZ", "510300.SH", "159915.SZ")
DEADLINE = time(18)


def probe(runtime: PiaRuntime, report_dir: Path) -> bool:
    started = datetime.now(MARKET_ZONE)
    session = started.date()
    as_of = session.isoformat()
    if started.time() < runtime.scheduler.close_time:
        raise ValueError("Run the probe after the configured Shanghai close time.")

    calendar, bars = session_inputs(runtime, as_of, list(SYMBOLS))
    deadline = datetime.combine(session, DEADLINE, MARKET_ZONE)
    coverage = {}
    for symbol in SYMBOLS:
        bar = bars.get(symbol)
        if bar:
            coverage[symbol] = {
                "as_of": bar["trade_date"], "observed_at": bar["observed_at"],
                "provider_id": bar.get("provider_id"),
                "close": bar["close"],
                "on_time": datetime.fromisoformat(bar["observed_at"]) <= deadline,
            }
        else:
            coverage[symbol] = {"failure": "CLOSE_UNAVAILABLE"}
    status = (
        "closed" if calendar.get("is_open") is False else
        "passed" if calendar.get("is_open") and all(item.get("on_time") for item in coverage.values())
        and started <= deadline else "failed"
    )
    result = {
        "as_of": as_of, "status": status, "started_at": started.isoformat(),
        "finished_at": datetime.now(MARKET_ZONE).isoformat(),
        "calendar": calendar, "coverage": coverage,
        "attempts": [json.loads(row["payload_json"]) for row in runtime.db.fetchall(
            "SELECT payload_json FROM provider_attempts ORDER BY call_id, ordinal",
        )],
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    file = report_dir / f"{as_of}-{started:%H%M%S%f}.json"
    temporary = file.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(file)
    print(json.dumps({"session": as_of, "status": status, "report": str(file)}, ensure_ascii=False))
    return status in {"closed", "passed"}


def verify(runtime: PiaRuntime, report_dir: Path, through: date) -> bool:
    start = through - timedelta(days=30)
    try:
        _, rows = runtime._provider_call(
            "trading_calendar", "get_trading_calendar", start.isoformat(), through.isoformat(),
        )
    except CapabilityUnavailable:
        rows = []
    days = {row["trade_date"]: row["is_open"] for row in rows if _verified_calendar(row)}
    recent = sorted(day for day, opened in days.items() if opened)[-5:]
    if len(recent) != 5:
        print(json.dumps({"passed": False, "error": "FIVE_CONFIRMED_SESSIONS_REQUIRED"}))
        return False
    day = date.fromisoformat(recent[0])
    while day <= through:
        if day.weekday() < 5 and day.isoformat() not in days:
            print(json.dumps({"passed": False, "error": "CALENDAR_UNAVAILABLE", "date": day.isoformat()}))
            return False
        day += timedelta(days=1)

    by_session = {day: False for day in recent}
    for day in recent:
        for report in report_dir.glob(f"{day}-*.json"):
            values = json.loads(report.read_text(encoding="utf-8"))
            coverage = values.get("coverage", {})
            if (values.get("as_of") == day and values.get("status") == "passed"
                    and set(coverage) == set(SYMBOLS)
                    and all(_observed_on_time(item, day) for item in coverage.values())):
                by_session[day] = True
                break
    passed = all(by_session.values())
    print(json.dumps({"passed": passed, "sessions": by_session}))
    return passed


def _observed_on_time(item: dict, as_of: str) -> bool:
    close = item.get("close")
    if (item.get("as_of") != as_of or item.get("provider_id") in {None, "fixture"}
            or type(close) not in {int, float} or not 0 < close < math.inf):
        return False
    try:
        observed = datetime.fromisoformat(item.get("observed_at") or "")
    except (TypeError, ValueError):
        return False
    session = date.fromisoformat(as_of)
    return bool(observed.tzinfo and
                datetime.combine(session, time(15), MARKET_ZONE) <= observed <= datetime.combine(session, DEADLINE, MARKET_ZONE))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("probe", "verify"))
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--through", type=date.fromisoformat, help="Final calendar date for verification")
    args = parser.parse_args()
    settings = Settings.from_env()
    if settings.mode != "local" or settings.data_provider == "fixture":
        parser.error("Choose a live provider and Local mode.")
    if args.command == "probe" and args.through is not None:
        parser.error("--through applies only to verify.")
    with tempfile.TemporaryDirectory() as work:
        runtime = PiaRuntime(replace(
            settings, db_path=Path(work) / "pia.sqlite3", analytics_db_path=Path(work) / "pia.duckdb",
            scheduler_enabled=False, autostart_tasks=False,
        ))
        try:
            if args.command == "probe":
                return 0 if probe(runtime, args.report_dir) else 1
            now = datetime.now(MARKET_ZONE)
            through = args.through or (now.date() if now.time() >= DEADLINE else now.date() - timedelta(days=1))
            return 0 if verify(runtime, args.report_dir, through) else 1
        finally:
            runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
