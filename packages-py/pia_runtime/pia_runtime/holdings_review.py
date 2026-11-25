from __future__ import annotations

import json
import math
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from .adapters import _canonical_symbol
from .decision_context import build_context_pack
from .models import Decision, DecisionStatus, Evidence, RuleReason, RuleResult, Task, TaskStatus, new_id, now_iso
from .provider_provenance import CapabilityUnavailable
from .result_metadata import build_result_metadata
from .rules import evaluate_holdings_limits

if TYPE_CHECKING:
    from .runtime import PiaRuntime


TRIGGER = "DailyHoldingsReview"
ACTIVE = {"QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED"}
MARKET_ZONE = ZoneInfo("Asia/Shanghai")


def _attempt(runtime: PiaRuntime, user_id: str, as_of: str) -> Any:
    return runtime.db.fetchone(
        """SELECT a.*, t.status, t.rule_snapshot_id FROM holdings_review_attempts a
           JOIN research_tasks t ON t.id=a.task_id
           WHERE a.user_id=? AND a.as_of=? ORDER BY t.created_at DESC, t.id DESC LIMIT 1""",
        (user_id, as_of),
    )


def _cutoff(runtime: PiaRuntime) -> date:
    now = datetime.now(runtime.scheduler.timezone)
    return now.date() if now.time() >= runtime.scheduler.close_time else now.date() - timedelta(days=1)


def _session(runtime: PiaRuntime, *, refresh: bool) -> str:
    if runtime.settings.data_provider == "fixture":
        return "2026-11-05"
    cutoff = _cutoff(runtime)
    start = cutoff - timedelta(days=14)
    days = runtime.analytics.verified_trading_days(start.isoformat(), cutoff.isoformat())
    latest_weekday = cutoff - timedelta(days=max(0, cutoff.weekday() - 4))
    if refresh and latest_weekday.isoformat() not in days:
        try:
            _, rows = runtime._provider_call(
                "trading_calendar", "get_trading_calendar", start.isoformat(), cutoff.isoformat(),
            )
        except CapabilityUnavailable:
            rows = []
        days.update({row["trade_date"]: row["is_open"] for row in rows if _verified_calendar(row)})
        _save_calendar(runtime, rows)
    for offset in range(15):
        day = cutoff - timedelta(days=offset)
        if days.get(day.isoformat(), day.weekday() < 5):
            return day.isoformat()
    raise ValueError("HOLDINGS_SESSION_UNAVAILABLE")


def _portfolio(runtime: PiaRuntime, user_id: str, as_of: str) -> dict[str, Any] | None:
    return runtime.db.get_latest_portfolio_snapshot(user_id, as_of=as_of, include_fixture=False)


def summary(runtime: PiaRuntime, user_id: str) -> dict[str, Any]:
    as_of = _session(runtime, refresh=False)
    record = _attempt(runtime, user_id, as_of)
    portfolio = _portfolio(runtime, user_id, as_of)
    return {
        "as_of": as_of,
        "portfolio_as_of": portfolio["as_of"] if portfolio else None,
        "portfolio_snapshot_id": portfolio["snapshot_id"] if portfolio else None,
        "rule_snapshot_id": runtime.get_rules(user_id)["rule_snapshot_id"],
        "attempt": task_review(runtime, record["task_id"], user_id) if record else None,
    }


def start(
    runtime: PiaRuntime, user_id: str, *, cash: float | None = None,
    as_of: str | None = None, automatic: bool = False,
    expected_session: str | None = None, expected_snapshot_id: str | None = None,
) -> Task | None:
    cash_provided = cash is not None
    if cash_provided and (isinstance(cash, bool) or not 0 <= cash <= sys.float_info.max):
        raise ValueError("HOLDINGS_CASH_INVALID")
    as_of = as_of or _session(runtime, refresh=True)
    with runtime._user_write(user_id):
        portfolio = _portfolio(runtime, user_id, as_of)
        if automatic and portfolio is None:
            return None
        snapshot_id = portfolio["snapshot_id"] if portfolio else None
        if cash is not None and (not snapshot_id or as_of != expected_session or snapshot_id != expected_snapshot_id):
            raise ValueError("HOLDINGS_SNAPSHOT_CHANGED")
        latest = _attempt(runtime, user_id, as_of)
        if cash is None and snapshot_id:
            prior = runtime.db.fetchone(
                """SELECT a.cash FROM holdings_review_attempts a
                   JOIN research_tasks t ON t.id=a.task_id
                   WHERE a.user_id=? AND a.portfolio_snapshot_id=? AND a.as_of<=? AND a.cash IS NOT NULL
                   ORDER BY a.as_of DESC, t.created_at DESC LIMIT 1""",
                (user_id, snapshot_id, as_of),
            )
            if prior:
                cash = prior["cash"]
        if latest:
            existing = runtime.db.get_task(latest["task_id"])
            unchanged = (
                latest["portfolio_snapshot_id"] == snapshot_id and latest["cash"] == cash
                and latest["rule_snapshot_id"] == runtime.get_rules(user_id)["rule_snapshot_id"]
            )
            if latest["status"] in ACTIVE:
                if cash_provided and not unchanged:
                    raise ValueError("HOLDINGS_REVIEW_IN_PROGRESS")
                return existing
            if unchanged and (automatic or latest["confirmed_at"]):
                return existing
            if unchanged and latest["status"] in {"NO_ACTION", "BLOCKED"}:
                review = task_review(runtime, latest["task_id"], user_id)
                if review and review["result"] and review["result"]["calculation"] in {"clear", "breach", "empty"}:
                    return existing
        task = runtime.create_task(TRIGGER, {"as_of": as_of}, user_id=user_id, autostart=False)
        runtime.db.execute(
            """INSERT INTO holdings_review_attempts(task_id, user_id, as_of, portfolio_snapshot_id, cash)
               VALUES (?, ?, ?, ?, ?)""",
            (task.id, user_id, as_of, snapshot_id, cash),
        )
    if runtime.settings.autostart_tasks and runtime.settings.mode != "cloud":
        runtime.run_task(task.id)
    return task


def task_review(runtime: PiaRuntime, task_id: str, user_id: str) -> dict[str, Any] | None:
    task = runtime.db.get_task(task_id)
    if not task or task.user_id != user_id or task.trigger_type != TRIGGER:
        return None
    row = runtime.db.fetchone(
        "SELECT confirmed_at FROM holdings_review_attempts WHERE task_id=? AND user_id=?",
        (task_id, user_id),
    )
    decision = runtime.db.fetchone("SELECT rationale_json FROM decisions WHERE task_id=?", (task_id,))
    result = json.loads(decision["rationale_json"])["synthesis"]["holdings_review"] if decision else None
    return {
        "task_id": task_id, "as_of": task.target["as_of"], "task_status": task.status.value,
        "confirmed_at": row["confirmed_at"] if row else None, "result": result,
        "replay": bool(task.target.get("_replay_of")), "error": (task.error or {}).get("code"),
    }


def confirm(runtime: PiaRuntime, task_id: str, user_id: str, *, unchanged: bool) -> dict[str, Any]:
    with runtime._user_write(user_id):
        review = task_review(runtime, task_id, user_id)
        if not review:
            raise KeyError(task_id)
        if review["confirmed_at"]:
            return review
        latest = _attempt(runtime, user_id, review["as_of"])
        result = review["result"]
        if (not latest or latest["task_id"] != task_id or review["task_status"] not in {"NO_ACTION", "BLOCKED"}
                or not result or result["calculation"] not in {"clear", "breach"}):
            raise ValueError("HOLDINGS_REVIEW_NOT_READY")
        portfolio = _portfolio(runtime, user_id, review["as_of"])
        if not portfolio or portfolio["snapshot_id"] != latest["portfolio_snapshot_id"]:
            raise ValueError("HOLDINGS_SNAPSHOT_CHANGED")
        if latest["rule_snapshot_id"] != runtime.get_rules(user_id)["rule_snapshot_id"]:
            raise ValueError("HOLDINGS_RULES_CHANGED")
        if result["needs_confirmation"] and not unchanged:
            raise ValueError("HOLDINGS_INPUT_CONFIRMATION_REQUIRED")
        stamp = now_iso()
        runtime.db.execute(
            "UPDATE holdings_review_attempts SET confirmed_at=? WHERE task_id=? AND user_id=?",
            (stamp, task_id, user_id),
        )
        payload = {"as_of": review["as_of"], "portfolio_snapshot_id": latest["portfolio_snapshot_id"],
                   "unchanged": unchanged, "confirmed_at": stamp}
        runtime.db.append_event(task_id, "HOLDINGS_REVIEW_CONFIRMED", payload)
        runtime.db.audit(task_id, "HOLDINGS_REVIEW_CONFIRMED", payload, user_id=user_id)
        return {**review, "confirmed_at": stamp}


def _verified_calendar(row: dict[str, Any]) -> bool:
    return (bool(row.get("trade_date")) and row.get("quality", "verified") == "verified"
            and isinstance(row.get("is_open"), bool)
            and row.get("provenance", {}).get("source_type") != "last_good_snapshot")


def _save_calendar(runtime: PiaRuntime, rows: list[dict[str, Any]]) -> None:
    snapshot_id = new_id("holdings_calendar")
    observed_at = now_iso()
    runtime.analytics.save_trading_calendar(
        {**row, "snapshot_id": snapshot_id, "quality": "verified", "as_of": row["trade_date"],
         "observed_at": row.get("observed_at") or observed_at}
        for row in rows if row.get("provider_id") and _verified_calendar(row)
    )


def _close_bar(rows: Any, symbol: str, as_of: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    matching = []
    for row in rows:
        if not isinstance(row, dict) or _canonical_symbol(str(row.get("symbol") or "")) != symbol:
            continue
        try:
            arrived = datetime.fromisoformat(str(row.get("observed_at") or ""))
        except ValueError:
            continue
        if arrived.tzinfo is None or arrived < datetime.fromisoformat(f"{as_of}T15:00:00+08:00"):
            continue
        price = row.get("close")
        if (row.get("trade_date") == as_of and row.get("as_of", as_of) == as_of
                and row.get("quality") in {"verified", "partial"}
                and row.get("provenance", {}).get("source_type") != "last_good_snapshot"
                and row.get("adjustment") in {None, "", "none", "raw", "unadjusted"}
                and not row.get("suspended") and row.get("volume") != 0
                and isinstance(price, (int, float)) and not isinstance(price, bool)
                and math.isfinite(price) and price > 0):
            matching.append(row)
    return matching[0] if len(matching) == 1 else None


def session_inputs(
    runtime: PiaRuntime, as_of: str, symbols: list[str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    def matching_calendar(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return next((row for row in rows if row.get("trade_date") == as_of and _verified_calendar(row)), {})

    try:
        _, rows = runtime._provider_call(
            "trading_calendar", "get_trading_calendar", as_of, as_of,
            accept_result=lambda rows: (bool(matching_calendar(rows)), "HOLDINGS_CALENDAR_UNAVAILABLE"),
        )
        calendar = matching_calendar(rows)
        _save_calendar(runtime, rows)
    except CapabilityUnavailable:
        calendar = {}
    bars = {}
    if calendar.get("is_open") is True:
        for symbol in symbols:
            try:
                _, rows = runtime._provider_call(
                    "daily_bars", "get_daily_bars", symbol, as_of, as_of,
                    accept_result=lambda rows: (bool(_close_bar(rows, symbol, as_of)), "HOLDINGS_CLOSE_UNAVAILABLE"),
                )
            except CapabilityUnavailable:
                continue
            bar = _close_bar(rows, symbol, as_of)
            if bar:
                bars[symbol] = bar
    return calendar, bars


def build_pack(runtime: PiaRuntime, task: Task, binding: dict[str, Any]) -> dict[str, Any]:
    as_of = task.target["as_of"]
    attempt = runtime.db.fetchone(
        "SELECT * FROM holdings_review_attempts WHERE task_id=? AND user_id=?", (task.id, task.user_id),
    )
    if not attempt:
        raise ValueError("HOLDINGS_REVIEW_INPUT_UNAVAILABLE")
    portfolio = runtime._load_snapshot_by_id("portfolio_snapshots", attempt["portfolio_snapshot_id"], task.user_id)
    holdings = []
    for position in (portfolio or {}).get("positions", []):
        quantity = position.get("quantity")
        holdings.append({
            "symbol": _canonical_symbol(str(position.get("symbol") or "")),
            "quantity": quantity if type(quantity) in {int, float} and 0 < quantity <= sys.float_info.max else None,
            "asset_type": str(position.get("asset_type") or "").strip().lower(),
            "sector": str(position.get("sector") or "").strip() or None,
        })
    symbols = list(dict.fromkeys(
        item["symbol"] for item in holdings if re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", item["symbol"])
    ))
    calendar, bars = session_inputs(runtime, as_of, symbols) if symbols else ({}, {})
    observed = now_iso()
    market_id = new_id("holdings_prices")
    market = {
        "snapshot_id": market_id, "as_of": as_of, "observed_at": observed,
        "source": "holdings_closes", "quality": "verified" if calendar.get("is_open") and len(bars) == len(symbols) else "partial",
        "calendar": calendar, "daily_bars": bars,
        "provenance": {"fallback_used": any(
            row.get("provenance", {}).get("fallback_used") for row in [calendar, *bars.values()]
        )},
        "provider_attempts": [
            json.loads(row["payload_json"]) for row in runtime.db.fetchall(
                "SELECT payload_json FROM provider_attempts WHERE task_id=? ORDER BY call_id, ordinal", (task.id,),
            )
        ],
    }
    replay_portfolio = {
        key: portfolio.get(key) for key in ("snapshot_id", "source", "as_of", "observed_at")
    } if portfolio else {}
    portfolio_quality = "unavailable" if not portfolio else "partial" if holdings and attempt["cash"] is None else "verified"
    replay_portfolio.update(positions=holdings, review_cash=attempt["cash"], quality=portfolio_quality)
    evidence = []
    for symbol, bar in bars.items():
        evidence.append(Evidence(
            source=bar.get("provider_id", bar.get("source", "unknown")), title=f"{symbol} closing price",
            observed_at=bar["observed_at"], as_of=as_of, expires_at=f"{as_of}T23:59:59+08:00",
            quality="verified", excerpt=f"Unadjusted close: {bar['close']}", snapshot_id=market_id,
            source_type="daily_bar", provider_id=bar.get("provider_id"), provenance=bar.get("provenance", {}),
        ))
    if portfolio:
        evidence.append(Evidence(
            source=portfolio["source"], title="Imported holdings snapshot",
            observed_at=portfolio.get("observed_at") or observed, as_of=portfolio["as_of"],
            expires_at=f"{as_of}T23:59:59+08:00", quality="verified",
            excerpt=f"{len(holdings)} position rows; review cash: {attempt['cash']}",
            snapshot_id=portfolio["snapshot_id"], source_type="portfolio",
        ))
    pack = build_context_pack(
        task=task, binding=binding, market=market, portfolio=replay_portfolio, research={},
        evidence=[item.to_dict() for item in evidence],
        data_mode="fixture" if runtime.settings.data_provider == "fixture" else "live",
    )
    with runtime.db.transaction():
        for item in pack["evidence"]:
            runtime._save_evidence(task, Evidence(**item))
        runtime.db.save_context_pack(task, pack)
    runtime.analytics.save_snapshot(
        snapshot_id=market_id, kind="holdings_closes", as_of=as_of, observed_at=observed,
        source=market["source"], quality=market["quality"], payload=pack["blocks"]["market"]["data"],
    )
    return pack


def _result(pack: dict[str, Any]) -> dict[str, Any]:
    as_of = pack["analysis_as_of"]
    market = pack["blocks"]["market"]["data"]
    portfolio = pack["blocks"]["portfolio"]["data"]
    holdings = portfolio["positions"]
    bars = market["daily_bars"]
    calendar = market["calendar"]
    cash = portfolio["review_cash"]
    issues = []
    if holdings and not calendar.get("is_open"):
        issues.append("SESSION_CLOSED" if calendar else "CALENDAR_UNAVAILABLE")
    if not portfolio.get("snapshot_id"):
        issues.append("PORTFOLIO_UNAVAILABLE")
    if holdings and cash is None:
        issues.append("CASH_REQUIRED")
    positions = []
    for position in holdings:
        symbol = position["symbol"]
        quantity = position.get("quantity")
        asset_type = position.get("asset_type")
        bar = bars.get(symbol)
        valid_holding = quantity is not None and asset_type in {"stock", "etf"}
        if not valid_holding and "HOLDINGS_INVALID" not in issues:
            issues.append("HOLDINGS_INVALID")
        value = Decimal(str(quantity)) * Decimal(str(bar["close"])) if bar and valid_holding else None
        if value is not None and not math.isfinite(float(value)):
            value = None
        positions.append({
            "symbol": symbol, "asset_type": asset_type, "sector": position.get("sector"),
            "quantity": quantity, "close": bar["close"] if bar else None, "market_value": value,
            "provider_id": bar.get("provider_id") if bar else None,
            "observed_at": bar.get("observed_at") if bar else None,
            "failed_attempts": [
                {"provider_id": attempt["provider_id"], "reason": attempt.get("reason_code")}
                for attempt in market.get("provider_attempts", [])
                if attempt.get("subject") == symbol and attempt.get("outcome") != "success"
            ],
        })
    if any(item["close"] is None for item in positions):
        issues.append("CLOSES_UNAVAILABLE")
    if "HOLDINGS_INVALID" not in issues and any(
        item["close"] is not None and item["market_value"] is None for item in positions
    ):
        issues.append("HOLDINGS_INVALID")
    nav = None
    if positions and not issues:
        nav = sum((item["market_value"] for item in positions), Decimal(str(cash)))
        if nav <= 0 or not math.isfinite(float(nav)):
            issues.append("HOLDINGS_INVALID")
            nav = None
    checks = evaluate_holdings_limits(positions, nav, pack["rule_snapshot"]["rules"])
    if nav is not None and checks[-1]["status"] == "unavailable":
        issues.append("SECTOR_UNAVAILABLE")
    empty = bool(portfolio.get("snapshot_id")) and not holdings
    calculation = ("empty" if empty else "incomplete" if issues else
                   "breach" if any(check["status"] == "breach" for check in checks) else "clear")
    for position in positions:
        if position["market_value"] is not None:
            position["market_value"] = float(position["market_value"])
    portfolio_as_of = portfolio.get("as_of")
    return {
        "calculation": calculation, "issues": issues, "portfolio_as_of": portfolio_as_of,
        "portfolio_snapshot_id": portfolio.get("snapshot_id"),
        "needs_confirmation": bool(portfolio_as_of and portfolio_as_of < as_of),
        "cash": cash, "nav": float(nav) if nav is not None else None,
        "covered": len(bars), "total": len({item["symbol"] for item in positions}),
        "positions": positions, "checks": checks, "rule_snapshot_id": pack["rule_snapshot"]["id"],
        "data_mode": pack["data_mode"],
    }


def execute(runtime: PiaRuntime, task: Task, pack: dict[str, Any]) -> None:
    result = _result(pack)
    task.data_snapshot_id = pack["blocks"]["market"]["data"]["snapshot_id"]
    status = DecisionStatus.NO_ACTION if result["calculation"] in {"clear", "empty"} else DecisionStatus.BLOCKED
    runtime._transition(task, TaskStatus.REVIEWING)
    budget = runtime._provider_context.budget
    budget.start("rules")
    budget.check()
    budget.finish()
    decision = Decision(
        status, "high" if result["calculation"] in {"clear", "breach"} else "low", "unknown",
        [], "Review the position limits and their evidence.", [],
        _rule_result(result, status),
        synthesis={"holdings_review": result, "evidence_ids": [item["id"] for item in pack["evidence"]]},
    )
    metadata = build_result_metadata(
        pack, [dict(row) for row in runtime.db.fetchall("SELECT * FROM task_stage_runs WHERE task_id=?", (task.id,))],
        runtime.db.task_events(task.id), has_result=True,
    )
    if result["calculation"] == "incomplete" and metadata["completion"] == "complete":
        metadata.update(completion="partial", degraded=True, quality_summary="partial")
    with runtime.db.transaction():
        runtime._check_cancelled(task)
        runtime.db.save_result_metadata(task.id, task.user_id, metadata)
        runtime.db.save_decision(task.id, decision)
        runtime._transition(task, TaskStatus(status.value))


def _rule_result(result: dict[str, Any], status: DecisionStatus) -> RuleResult:
    codes = {"stock": "POSITION_LIMIT_EXCEEDED", "etf": "ETF_POSITION_LIMIT", "sector": "SECTOR_CONCENTRATION"}
    reasons = [
        RuleReason(
            f"holdings.{check['kind']}.{item['label']}", codes[check["kind"]], "error",
            item["actual"], check["limit"], f"{item['label']} exceeds the configured limit.",
        )
        for check in result["checks"] for item in check["items"] if item["breach"]
    ]
    warnings = [
        RuleReason("holdings.inputs", issue, "warning", None, "available", issue)
        for issue in result["issues"]
    ]
    return RuleResult(status.value, reasons, warnings, result["rule_snapshot_id"])
