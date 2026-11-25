from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import RuleReason, RuleResult


def load_rules(path: Path) -> dict[str, Any]:
    # The baseline file is JSON-compatible YAML so the runtime has no mandatory third-party dependency.
    return json.loads(path.read_text())


def evaluate_holdings_limits(
    positions: list[dict[str, Any]], nav: Decimal | None, rules: dict[str, Any],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Decimal]] = {"stock": {}, "etf": {}, "sector": {}}
    unknown_sector = False
    symbol_sectors: dict[str, str] = {}
    if nav is not None:
        for position in positions:
            values = groups[position["asset_type"]]
            symbol = position["symbol"]
            value = position["market_value"]
            values[symbol] = values.get(symbol, Decimal(0)) + value
            if position["asset_type"] == "stock":
                sector = str(position.get("sector") or "").strip()
                if sector.lower() in {"", "unknown", "未知", "未分类", "--"} or (
                    symbol in symbol_sectors and sector != symbol_sectors[symbol]
                ):
                    unknown_sector = True
                else:
                    symbol_sectors[symbol] = sector
                    sectors = groups["sector"]
                    sectors[sector] = sectors.get(sector, Decimal(0)) + value

    checks = []
    for name, key in (("stock", "max_position_weight"), ("etf", "max_etf_weight"), ("sector", "max_sector_weight")):
        limit = Decimal(str(rules[key]))
        available = nav is not None and (name != "sector" or not unknown_sector)
        rows = []
        if available:
            for label, market_value in groups[name].items():
                rows.append({
                    "label": label, "actual": float(market_value / nav), "breach": market_value > limit * nav,
                })
        checks.append({
            "kind": name, "limit": float(limit), "items": rows,
            "status": ("unavailable" if not available else
                       "breach" if any(row["breach"] for row in rows) else "clear"),
        })
    return checks


def evaluate_close_review(
    market: dict[str, Any],
    portfolio: dict[str, Any],
    rules: dict[str, Any],
    rule_snapshot_id: str,
    evidence_count: int = 0,
    profile: dict[str, Any] | None = None,
    target_symbol: str | None = None,
) -> RuleResult:
    reasons: list[RuleReason] = []
    warnings: list[RuleReason] = []
    profile = profile or {}
    allowed_asset_types = {
        str(value).strip().lower()
        for value in profile.get("allowed_asset_types", [])
        if str(value).strip()
    }
    allowed_universe = {
        str(value).strip().lower()
        for value in profile.get("universe", [])
        if str(value).strip()
    }

    def in_profile(instrument: dict[str, Any]) -> bool:
        asset_type = str(instrument.get("asset_type", "")).strip().lower()
        board = str(instrument.get("board", "")).strip().lower()
        return (
            (not allowed_asset_types or asset_type in allowed_asset_types)
            and (not allowed_universe or board in allowed_universe)
        )

    quality = market.get("quality")
    if quality == "stale" or market.get("stale") is True:
        reasons.append(RuleReason(
            "data.quality", "STALE_DATA", "error", quality, "verified",
            "Market snapshot is stale and cannot support a new decision.",
        ))
    elif quality != "verified":
        reasons.append(RuleReason(
            "data.quality", "DATA_UNAVAILABLE", "error", market.get("quality"), "verified",
            "Market snapshot is not verified.",
        ))

    breadth = float(market.get("breadth", 0))
    if breadth < rules["market_gate"]["breadth_min"]:
        warnings.append(RuleReason(
            "market.breadth", "MARKET_CONDITION_FAILED", "warning", breadth,
            f">= {rules['market_gate']['breadth_min']}",
            "Market breadth is below the configured gate.",
        ))
    if rules["market_gate"].get("index_trend_required") and market.get("index_trend") not in {"up", "flat"}:
        warnings.append(RuleReason(
            "market.index_trend", "MARKET_CONDITION_FAILED", "warning", market.get("index_trend"), "up or flat",
            "Index trend does not satisfy the configured market gate.",
        ))
    volatility = market.get("volatility")
    if volatility is not None and float(volatility) > rules["market_gate"].get("volatility_max", 1):
        warnings.append(RuleReason(
            "market.volatility", "MARKET_VOLATILITY_FAILED", "warning", market.get("volatility"),
            f"<= {rules['market_gate']['volatility_max']}",
            "Market volatility is above the configured gate.",
        ))

    drawdown = float(portfolio.get("drawdown", 0))
    if drawdown >= rules["critical_drawdown"]:
        reasons.append(RuleReason(
            "portfolio.drawdown.critical", "RISK_REVIEW_FAILED", "error", drawdown,
            f"< {rules['critical_drawdown']}",
            "Portfolio drawdown is at the critical threshold.",
        ))
    elif drawdown >= rules["drawdown_limit"]:
        reasons.append(RuleReason(
            "portfolio.drawdown.limit", "DRAWDOWN_LIMIT", "error", drawdown,
            f"< {rules['drawdown_limit']}",
            "Portfolio drawdown blocks new buying activity.",
        ))
    elif drawdown >= rules["drawdown_warning"]:
        warnings.append(RuleReason(
            "portfolio.drawdown.warning", "DRAWDOWN_WARNING", "warning", drawdown,
            f"< {rules['drawdown_warning']}",
            "Portfolio drawdown is elevated.",
        ))

    for position in portfolio.get("positions", []):
        weight = float(position.get("weight", 0))
        symbol = position.get("symbol", "unknown")
        limit = rules["max_etf_weight"] if position.get("asset_type") == "etf" else rules["max_position_weight"]
        code = "ETF_POSITION_LIMIT" if position.get("asset_type") == "etf" else "POSITION_LIMIT_EXCEEDED"
        if weight > limit:
            reasons.append(RuleReason(
                f"portfolio.position.{symbol}", code, "error", weight, f"<= {limit}",
                f"{symbol} weight exceeds the configured position limit.",
            ))

    instruments = list(market.get("instruments", []))
    if target_symbol:
        target = next(
            (instrument for instrument in instruments if str(instrument.get("symbol")) == target_symbol),
            None,
        )
        if target is None or not in_profile(target):
            reasons.append(RuleReason(
                f"universe.{target_symbol}",
                "UNIVERSE_REJECTED",
                "error",
                target_symbol,
                "eligible for the user's Profile",
                f"{target_symbol} is outside the user's allowed asset types or universe.",
            ))

    for instrument in instruments:
        if not in_profile(instrument):
            continue
        symbol = instrument.get("symbol", "unknown")
        if instrument.get("is_st") or instrument.get("suspended") or instrument.get("is_delisting"):
            reasons.append(RuleReason(
                f"universe.{symbol}", "UNIVERSE_REJECTED", "error", symbol, "eligible",
                f"{symbol} is excluded by the configured stock universe.",
            ))
        if int(instrument.get("listed_days") or 0) < rules["new_listing_observation_days"]:
            reasons.append(RuleReason(
                f"universe.{symbol}", "NEW_LISTING", "error", instrument.get("listed_days"),
                f">= {rules['new_listing_observation_days']}",
                f"{symbol} has not completed the minimum listing observation period.",
            ))
        if float(instrument.get("average_turnover", rules.get("min_average_turnover", 0))) < rules["min_average_turnover"]:
            reasons.append(RuleReason(
                f"liquidity.{symbol}", "LOW_LIQUIDITY", "error", instrument.get("average_turnover"),
                f">= {rules['min_average_turnover']}",
                f"{symbol} does not meet the minimum average turnover.",
            ))

    sector_weights: dict[str, float] = {}
    for position in portfolio.get("positions", []):
        sector = position.get("sector", "unknown")
        sector_weights[sector] = sector_weights.get(sector, 0) + float(position.get("weight", 0))
    for sector, weight in sector_weights.items():
        if weight > rules["max_sector_weight"]:
            reasons.append(RuleReason(
                f"portfolio.sector.{sector}", "SECTOR_CONCENTRATION", "error", weight,
                f"<= {rules['max_sector_weight']}",
                f"Sector exposure for {sector} exceeds the configured limit.",
            ))

    if evidence_count < 3:
        warnings.append(RuleReason(
            "evidence.minimum", "EVIDENCE_INSUFFICIENT", "warning", evidence_count, ">= 3",
            "The decision does not yet have the minimum evidence set.",
        ))

    if reasons:
        decision = "BLOCKED"
    elif any(reason.code in {"MARKET_CONDITION_FAILED", "MARKET_VOLATILITY_FAILED"} for reason in warnings):
        decision = "NO_ACTION"
    elif warnings:
        decision = "WATCH"
    else:
        decision = "WATCH"
    return RuleResult(decision, reasons, warnings, rule_snapshot_id)
