from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable


FIELD_ALIASES = {
    "symbol": ("symbol", "ts_code", "代码", "股票代码", "证券代码"),
    "trade_date": ("trade_date", "日期", "交易日期", "date"),
    "open": ("open", "开盘", "开盘价"),
    "high": ("high", "最高", "最高价"),
    "low": ("low", "最低", "最低价"),
    "close": ("close", "收盘", "收盘价"),
    "volume": ("volume", "vol", "成交量"),
    "amount": ("amount", "成交额"),
}


def normalize_daily_bars(
    rows: Iterable[dict[str, Any]],
    *,
    provider_id: str,
    provider_version: str = "unknown",
    adapter_version: str = "0.1.0",
    observed_at: str | None = None,
) -> list[dict[str, Any]]:
    normalized = []
    observed = observed_at or datetime.now(timezone.utc).isoformat()
    for row in rows:
        normalized.append(normalize_daily_bar(
            row,
            provider_id=provider_id,
            provider_version=provider_version,
            adapter_version=adapter_version,
            observed_at=observed,
        ))
    return normalized


def normalize_daily_bar(
    row: dict[str, Any],
    *,
    provider_id: str,
    provider_version: str = "unknown",
    adapter_version: str = "0.1.0",
    observed_at: str | None = None,
) -> dict[str, Any]:
    values = {
        field: _first(row, aliases)
        for field, aliases in FIELD_ALIASES.items()
    }
    missing = [
        field for field in ("symbol", "trade_date", "close")
        if values[field] in (None, "")
    ]
    quality = "unavailable" if missing else "partial" if any(
        values[field] in (None, "") for field in ("open", "high", "low", "volume", "amount")
    ) else "verified"
    as_of = _date_string(values["trade_date"])
    canonical = {
        "symbol": str(values["symbol"]).strip() if values["symbol"] is not None else None,
        "trade_date": as_of,
        "open": _number(values["open"]),
        "high": _number(values["high"]),
        "low": _number(values["low"]),
        "close": _number(values["close"]),
        "volume": _number(values["volume"]),
        "amount": _number(values["amount"]),
        "source": provider_id,
        "provider_id": provider_id,
        "provider_version": provider_version,
        "adapter_version": adapter_version,
        "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "quality": quality,
        "normalization_warnings": missing,
    }
    fingerprint = repr(sorted(canonical.items())).encode()
    canonical["snapshot_id"] = f"snap_{hashlib.sha256(fingerprint).hexdigest()[:16]}"
    return canonical


def _first(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _date_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    return text[:10].replace("/", "-")
