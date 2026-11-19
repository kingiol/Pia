from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import math
import os
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from statistics import pstdev
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .normalization import normalize_daily_bars
from .models import new_id, now_iso


@dataclass(slots=True)
class ProviderHealth:
    provider_id: str
    status: str
    capabilities: list[str]
    supports_replay: bool
    requires_credentials: bool
    provider_version: str = "unknown"
    adapter_version: str = "0.1.0"
    markets: list[str] | None = None
    data_granularity: list[str] | None = None
    supports_point_in_time: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "capabilities": self.capabilities,
            "supports_replay": self.supports_replay,
            "requires_credentials": self.requires_credentials,
            "provider_version": self.provider_version,
            "adapter_version": self.adapter_version,
            "markets": self.markets or ["CN_STOCK"],
            "data_granularity": self.data_granularity or ["daily"],
            "supports_point_in_time": self.supports_point_in_time,
        }


class ProviderCircuitOpen(RuntimeError):
    code = "PROVIDER_CIRCUIT_OPEN"


class ProviderResultDegraded(RuntimeError):
    code = "PROVIDER_RESULT_DEGRADED"

    def __init__(self, result: Any, reason: str | None) -> None:
        super().__init__(reason or self.code)
        self.result = result


def _safe_fixture_path(root: Path, name: str, label: str) -> Path:
    """Resolve a JSON fixture without allowing paths outside its fixture root."""
    fixture_root = root.resolve()
    candidate = (fixture_root / name).resolve()
    try:
        candidate.relative_to(fixture_root)
    except ValueError as error:
        raise ValueError(f"{label} fixture path escapes fixture directory") from error
    if candidate.suffix.lower() != ".json":
        raise ValueError(f"{label} fixture must be a JSON file")
    return candidate


@dataclass(slots=True)
class ProviderRuntimeState:
    consecutive_failures: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    retry_count: int = 0
    opened_until: float = 0.0
    last_error: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    latency_ms: float | None = None
    probe_in_flight: bool = False

    def is_open(self, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return self.opened_until > current

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_until = 0.0
        self.last_error = None
        self.last_success_at = now_iso()
        self.probe_in_flight = False

    def record_failure(
        self,
        error: BaseException,
        *,
        failure_threshold: int,
        reset_seconds: float,
    ) -> None:
        self.consecutive_failures += 1
        self.failed_calls += 1
        self.last_error = getattr(error, "code", type(error).__name__)
        self.last_failure_at = now_iso()
        self.probe_in_flight = False
        if self.consecutive_failures >= max(1, failure_threshold):
            self.opened_until = time.monotonic() + max(0.0, reset_seconds)

    def to_dict(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "circuit_state": "open" if self.is_open(now) else "half_open" if self.opened_until else "closed",
            "consecutive_failures": self.consecutive_failures,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "cooldown_seconds": round(max(0.0, self.opened_until - now), 3),
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "latency_ms": self.latency_ms,
        }


class ProviderRegistry:
    def __init__(
        self,
        providers: list[Any],
        *,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 0.25,
        retry_max_backoff_seconds: float = 2.0,
        circuit_failure_threshold: int = 3,
        circuit_reset_seconds: float = 30.0,
        sleep: Any = time.sleep,
    ) -> None:
        self.providers = providers
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.retry_max_backoff_seconds = max(
            self.retry_backoff_seconds,
            float(retry_max_backoff_seconds),
        )
        self.circuit_failure_threshold = max(1, int(circuit_failure_threshold))
        self.circuit_reset_seconds = max(0.0, float(circuit_reset_seconds))
        self._sleep = sleep
        self._runtime_state: dict[tuple[str, str, str], ProviderRuntimeState] = {}
        self._lock = threading.RLock()

    def health(self) -> list[dict[str, Any]]:
        result = []
        for provider in self.providers:
            payload = provider.health().to_dict()
            capabilities = {
                capability: self._state(provider, capability).to_dict()
                for capability in payload["capabilities"]
            }
            states = [self._state(provider, capability) for capability in payload["capabilities"]]
            payload["runtime"] = {
                **(states[0].to_dict() if states else ProviderRuntimeState().to_dict()),
                "total_calls": sum(state.total_calls for state in states),
                "failed_calls": sum(state.failed_calls for state in states),
                "retry_count": sum(state.retry_count for state in states),
            }
            payload["capability_health"] = capabilities
            if payload["status"] == "healthy" and states and all(state.is_open() for state in states):
                payload["status"] = "circuit_open"
            result.append(payload)
        return result

    def select(self, capability: str, require_credentials: bool = False) -> Any:
        for provider in self.providers:
            status = provider.health()
            if (
                status.status != "healthy"
                or capability not in status.capabilities
                or self._state(provider, capability).is_open()
            ):
                continue
            if require_credentials and not status.requires_credentials:
                continue
            return provider
        raise RuntimeError(f"CAPABILITY_UNAVAILABLE: {capability}")

    def select_chain(
        self,
        capability: str,
        *,
        preferred_provider_id: str | None = None,
        require_credentials: bool = False,
    ) -> list[Any]:
        """Return healthy providers in deterministic preference order."""
        preferred = [
            provider
            for provider in self.providers
            if preferred_provider_id and provider.provider_id == preferred_provider_id
        ]
        remaining = [
            provider
            for provider in self.providers
            if provider not in preferred
        ]
        remaining.sort(key=lambda provider: provider.provider_id == "fixture")
        result = []
        for provider in [*preferred, *remaining]:
            status = provider.health()
            if (
                status.status != "healthy"
                or capability not in status.capabilities
                or self._state(provider, capability).is_open()
            ):
                continue
            if require_credentials and not status.requires_credentials:
                continue
            result.append(provider)
        return result

    def call(
        self,
        provider: Any,
        method_name: str,
        *args: Any,
        on_retry: Any = None,
        capability: str | None = None,
        credential_scope: str = "default",
        call_id: str | None = None,
        on_attempt: Any = None,
        quality_check: Any = None,
        invoke: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke a provider method with bounded retries and circuit protection."""
        capability = capability or {
            "search_news": "news", "search_filings": "filings",
        }.get(method_name, method_name.removeprefix("get_"))
        state = self._state(provider, capability, credential_scope)
        with self._lock:
            if state.is_open() or (state.opened_until and state.probe_in_flight):
                raise ProviderCircuitOpen(f"provider circuit is open: {provider.provider_id}")
            if state.opened_until:
                state.probe_in_flight = True
        method = getattr(provider, method_name, None)
        if method is None:
            raise AttributeError(f"{provider.provider_id}.{method_name} is unavailable")

        call_id = call_id or new_id("provider_call")
        for attempt in range(self.retry_attempts):
            started = time.monotonic()
            record = {
                "attempt_id": new_id("provider_attempt"), "call_id": call_id,
                "provider_id": provider.provider_id, "capability": capability,
                "attempt": attempt + 1, "started_at": now_iso(),
                "outcome": "failed", "quality": None, "reason_code": None,
            }
            with self._lock:
                state.total_calls += 1
            try:
                result = invoke(provider, method_name, args, kwargs) if invoke else method(*args, **kwargs)
                if quality_check:
                    accepted, reason = quality_check(capability, result)
                    if not accepted:
                        raise ProviderResultDegraded(result, reason)
            except Exception as error:
                record["reason_code"] = getattr(error, "code", type(error).__name__)
                if isinstance(error, ProviderResultDegraded):
                    record["outcome"] = "degraded"
                    record["quality"] = error.result.get("quality") if isinstance(error.result, dict) else "partial"
                record["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
                if on_attempt:
                    on_attempt(record)
                retryable = _is_retryable_provider_error(error)
                if retryable and attempt + 1 < self.retry_attempts:
                    state.retry_count += 1
                    delay = min(
                        self.retry_max_backoff_seconds,
                        self.retry_backoff_seconds * (2**attempt),
                    )
                    if on_retry is not None:
                        on_retry(
                            provider=provider.provider_id,
                            method=method_name,
                            attempt=attempt + 1,
                            delay_seconds=delay,
                            error=error,
                        )
                    self._sleep(delay)
                    continue
                if retryable or isinstance(error, ProviderResultDegraded):
                    state.record_failure(
                        error,
                        failure_threshold=self.circuit_failure_threshold,
                        reset_seconds=self.circuit_reset_seconds,
                    )
                state.probe_in_flight = False
                raise
            state.record_success()
            state.latency_ms = round((time.monotonic() - started) * 1000, 3)
            record.update(outcome="success", duration_ms=state.latency_ms,
                          quality=result.get("quality") if isinstance(result, dict) else "verified")
            if on_attempt:
                on_attempt(record)
            return result
        raise RuntimeError("provider call exhausted without a result")

    def _state(
        self, provider: Any, capability: str, credential_scope: str = "default",
    ) -> ProviderRuntimeState:
        with self._lock:
            return self._runtime_state.setdefault(
                (provider.provider_id, capability, credential_scope), ProviderRuntimeState(),
            )


class FixtureMarketProvider:
    provider_id = "fixture"

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            status="healthy",
            capabilities=[
                "market_snapshot",
                "daily_bars",
                "market_breadth",
                "index_series",
                "trading_calendar",
            ],
            supports_replay=True,
            requires_credentials=False,
        )

    def get_market_snapshot(self, as_of: str, fixture_name: str | None = None) -> dict[str, Any]:
        name = fixture_name or f"close-{as_of}.json"
        path = _safe_fixture_path(self.fixture_dir / "market", name, "market")
        if not path.exists():
            raise FileNotFoundError(f"market fixture not found: {path}")
        return json.loads(path.read_text())

    def get_market_breadth(
        self,
        as_of: str,
        fixture_name: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.get_market_snapshot(as_of, fixture_name)
        return {
            "as_of": snapshot.get("as_of", as_of),
            "snapshot_id": snapshot.get("snapshot_id"),
            "source": snapshot.get("source", self.provider_id),
            "breadth": snapshot.get("breadth"),
            "index_trend": snapshot.get("index_trend"),
        }

    def get_index_series(
        self,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        _validate_date_range(start_date, end_date)
        requested = {
            _canonical_index_symbol(str(symbol))
            for symbol in (symbols or [])
            if str(symbol).strip()
        }
        grouped: dict[str, dict[str, Any]] = {}
        for path in sorted((self.fixture_dir / "market").glob("*.json")):
            payload = json.loads(path.read_text())
            trade_date = str(payload.get("as_of") or "")[:10]
            if not (start_date <= trade_date <= end_date):
                continue
            for index in payload.get("indices", []):
                symbol = _canonical_index_symbol(str(index.get("symbol") or ""))
                if not symbol or (requested and symbol not in requested):
                    continue
                entry = grouped.setdefault(
                    symbol,
                    {
                        "symbol": symbol,
                        "name": str(index.get("name") or symbol),
                        "points": [],
                    },
                )
                entry["points"].append({
                    "trade_date": trade_date,
                    "close": _float(index.get("close")),
                    "change_pct": _float(index.get("change_pct")),
                    "source": str(payload.get("source") or self.provider_id),
                    "snapshot_id": payload.get("snapshot_id"),
                })
        series = []
        for entry in grouped.values():
            entry["points"].sort(key=lambda point: point["trade_date"])
            series.append(entry)
        series.sort(key=lambda item: item["symbol"])
        end_points = [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "close": item["points"][-1]["close"],
                "change_pct": item["points"][-1]["change_pct"],
                "as_of": item["points"][-1]["trade_date"],
                "source": self.provider_id,
                "snapshot_id": item["points"][-1].get("snapshot_id"),
            }
            for item in series
            if item["points"][-1]["trade_date"] == end_date
        ]
        return {
            "provider": self.provider_id,
            "source": self.provider_id,
            "quality": "verified" if series else "unavailable",
            "start_date": start_date,
            "end_date": end_date,
            "as_of": end_date,
            "series": series,
            # Compatibility for callers that consumed the old single-day shape.
            "indices": end_points,
        }

    def get_portfolio_snapshot(self, fixture_name: str = "default.json") -> dict[str, Any]:
        path = _safe_fixture_path(self.fixture_dir / "portfolio", fixture_name, "portfolio")
        if not path.exists():
            raise FileNotFoundError(f"portfolio fixture not found: {path}")
        return json.loads(path.read_text())

    def get_trading_calendar(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        rows = []
        current = start
        while current <= end:
            rows.append({
                "trade_date": current.date().isoformat(),
                "is_open": current.weekday() < 5,
            })
            current += timedelta(days=1)
        return rows

    def get_universe(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted((self.fixture_dir / "market").glob("*.json")):
            payload = json.loads(path.read_text())
            rows.extend(payload.get("instruments", []))
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("symbol"):
                normalized = dict(row)
                symbol = str(normalized["symbol"]).strip().upper()
                normalized["symbol"] = symbol
                normalized.setdefault("exchange", _exchange_for_symbol(symbol))
                normalized.setdefault(
                    "listed_at",
                    _listed_at_from_value(
                        normalized.get("listed_at")
                        or normalized.get("list_date")
                        or normalized.get("上市日期")
                    ),
                )
                normalized.setdefault(
                    "active",
                    not bool(
                        normalized.get("suspended")
                        or normalized.get("is_delisting")
                    ),
                )
                deduped[symbol] = normalized
        return list(deduped.values())

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        for path in sorted((self.fixture_dir / "market").glob("*.json")):
            payload = json.loads(path.read_text())
            if not (start_date <= str(payload.get("as_of", "")) <= end_date):
                continue
            for instrument in payload.get("instruments", []):
                if instrument.get("symbol") != symbol:
                    continue
                close = instrument.get("close")
                return [{
                    "symbol": symbol,
                    "trade_date": payload["as_of"],
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": None,
                    "amount": instrument.get("average_turnover"),
                    "quality": "partial",
                    "provider_id": self.provider_id,
                    "provider_version": "fixture",
                    "adapter_version": "0.1.0",
                    "observed_at": payload.get("observed_at"),
                    "as_of": payload["as_of"],
                }]
        return []


class AkshareMarketProvider:
    """Optional live adapter. Importing pia_runtime never requires akshare to be installed."""

    provider_id = "akshare"

    def __init__(self) -> None:
        self.sdk = None
        self._sdk_available = importlib.util.find_spec("akshare") is not None
        self._listing_metadata: dict[str, dict[str, str | None]] | None = None
        self._etf_listing_metadata: dict[str, dict[str, str | None]] | None = None
        self._universe_cache: list[dict[str, Any]] | None = None
        self._historical_bars_cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._historical_index_cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._historical_sector_cache: dict[str, dict[str, dict[str, Any]]] = {}

    def _require_sdk(self) -> Any:
        if self.sdk is None:
            try:
                import akshare as sdk  # type: ignore
            except ImportError as error:
                raise RuntimeError(
                    "CAPABILITY_DISABLED: install akshare to enable the live adapter"
                ) from error
            self.sdk = sdk
        return self.sdk

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            status="healthy" if self.sdk or self._sdk_available else "capability_disabled",
            capabilities=[
                "market_snapshot",
                "daily_bars",
                "market_breadth",
                "index_series",
                "trading_calendar",
                "fundamentals",
                "company_profile",
                "news",
                "filings",
                "universe",
            ] if self.sdk or self._sdk_available else [],
            supports_replay=True,
            requires_credentials=False,
            provider_version=getattr(self.sdk, "__version__", "unknown") if self.sdk else "unknown",
        )

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        self._require_sdk()
        code = symbol.split(".")[0]
        if _board_for_symbol(symbol) == "etf":
            method = getattr(self.sdk, "fund_etf_hist_em", None)
        else:
            method = self._stock_history_endpoint()
        if method is None:
            raise RuntimeError(f"CAPABILITY_DISABLED: AKShare historical endpoint unavailable for {symbol}")
        frame = method(
            symbol=code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="",
        )
        rows = _records(frame)
        for row in rows:
            row.setdefault("symbol", symbol)
        return normalize_daily_bars(
            rows,
            provider_id=self.provider_id,
            provider_version=getattr(self.sdk, "__version__", "unknown"),
        )

    def get_trading_calendar(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        self._require_sdk()
        try:
            frame = self.sdk.tool_trade_date_hist_sina()
            dates = {
                str(value)[:10].replace("/", "-")
                for row in _records(frame)
                for value in row.values()
                if value
            }
        except AttributeError:
            dates = set()
        start = start_date[:10]
        end = end_date[:10]
        current = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        verified_calendar = bool(dates)
        if not dates:
            dates = {
                (current + timedelta(days=offset)).date().isoformat()
                for offset in range((end_dt.date() - current.date()).days + 1)
                if (current + timedelta(days=offset)).weekday() < 5
            }
        rows = []
        while current <= end_dt:
            rows.append({
                "trade_date": current.date().isoformat(),
                "is_open": current.date().isoformat() in dates,
                "quality": "verified" if verified_calendar else "partial",
                "source_method": "exchange_calendar" if verified_calendar else "weekday_estimate",
            })
            current += timedelta(days=1)
        return rows

    def get_market_snapshot(self, as_of: str) -> dict[str, Any]:
        self._require_sdk()
        if (
            as_of != datetime.now(timezone.utc).date().isoformat()
            and self._stock_history_endpoint() is not None
            and not self._is_latest_open_date(as_of)
        ):
            return self._get_historical_market_snapshot(as_of)
        observed_at = datetime.now(timezone.utc).isoformat()
        spot = self.sdk.stock_zh_a_spot_em()
        records = _records(spot)
        listing_metadata = self._get_listing_metadata()
        etf_listing_metadata = self._get_etf_listing_metadata()
        instruments = []
        advances = declines = unchanged = 0
        for row in records:
            symbol = str(row.get("代码") or row.get("证券代码") or "").strip()
            name = str(row.get("名称") or row.get("股票简称") or symbol)
            change = _float(row.get("涨跌幅"))
            if change is None:
                unchanged += 1
            elif change > 0:
                advances += 1
            elif change < 0:
                declines += 1
            else:
                unchanged += 1
            if not symbol:
                continue
            instruments.append({
                "symbol": _canonical_symbol(symbol),
                "name": name,
                "asset_type": "stock",
                "board": _board_for_symbol(symbol),
                "exchange": _exchange_for_symbol(symbol),
                "listed_at": (
                    _listed_at_from_row(row, "上市日期", "list_date")
                    or listing_metadata.get(symbol.split(".")[0], {}).get("listed_at")
                ),
                "is_st": "ST" in name.upper() or "＊" in name,
                "is_delisting": _is_delisting_name(name),
                "suspended": _float(row.get("最新价")) is None,
                "active": _float(row.get("最新价")) is not None
                and not _is_delisting_name(name),
                "listed_days": 9999,
                "close": _float(row.get("最新价")),
                "change_pct": change or 0.0,
                "average_turnover": (_float(row.get("成交额")) or 0.0),
            })
        # ETFs are part of the configured MVP universe. Keep them in the
        # snapshot so candidate scans do not silently omit them. They are
        # intentionally excluded from stock market breadth calculations.
        etf_spot = getattr(self.sdk, "fund_etf_spot_em", None)
        if etf_spot:
            try:
                for row in _records(etf_spot()):
                    symbol = str(row.get("代码") or row.get("证券代码") or "").strip()
                    if not symbol:
                        continue
                    name = str(row.get("名称") or row.get("证券简称") or symbol)
                    close = _float(row.get("最新价") or row.get("收盘价"))
                    change = _float(row.get("涨跌幅"))
                    instruments.append({
                        "symbol": _canonical_symbol(symbol),
                        "name": name,
                        "asset_type": "etf",
                        "board": "etf",
                        "exchange": _exchange_for_symbol(symbol),
                    "listed_at": (
                        _listed_at_from_row(row, "上市日期", "list_date")
                        or etf_listing_metadata.get(
                            symbol.split(".")[0], {}
                        ).get("listed_at")
                    ),
                        "is_st": False,
                        "is_delisting": _is_delisting_name(name),
                        "suspended": close is None,
                        "active": close is not None
                        and not _is_delisting_name(name),
                        "listed_days": _listed_days(
                            _listed_at_from_row(row, "上市日期", "list_date") or ""
                        ) or 9999,
                        "close": close,
                        "change_pct": change or 0.0,
                        "average_turnover": (
                            _float(row.get("成交额"))
                            or _float(row.get("成交额(元)"))
                            or 0.0
                        ),
                    })
            except Exception:
                # Stock data remains usable when the optional ETF endpoint is
                # unavailable; the provider health/quality path records the
                # capability boundary separately.
                pass
        total = max(1, advances + declines + unchanged)
        sectors = self._get_sectors()
        indices = self._get_indices()
        volatility = _volatility([_float(row.get("涨跌幅")) for row in records])
        current_date = datetime.now().date().isoformat()
        quality = (
            "verified"
            if instruments and indices and volatility is not None and as_of == current_date
            else "partial"
        )
        return {
            "snapshot_id": f"live_{self.provider_id}_{as_of}",
            "as_of": as_of,
            "observed_at": observed_at,
            "source": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "adapter_version": "0.2.0",
            "quality": quality if instruments else "unavailable",
            "point_in_time_scope": "latest",
            "breadth": advances / total,
            "index_trend": "up" if advances >= declines else "down",
            "volatility": volatility,
            "indices": indices,
            "sectors": sectors,
            "instruments": instruments,
            "daily_bars": [],
        }

    def _is_latest_open_date(self, as_of: str) -> bool:
        """Use the latest spot snapshot only when the requested date is current."""
        if not getattr(self.sdk, "tool_trade_date_hist_sina", None):
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        if as_of > today:
            return False
        try:
            rows = self.get_trading_calendar(as_of, today)
        except Exception:
            return False
        latest_open = max(
            (
                str(row.get("trade_date", ""))[:10]
                for row in rows
                if row.get("is_open")
            ),
            default=None,
        )
        return latest_open == as_of

    def _get_historical_market_snapshot(self, as_of: str) -> dict[str, Any]:
        """Build a date-scoped snapshot from historical provider endpoints."""

        observed_at = datetime.now(timezone.utc).isoformat()
        universe = [
            dict(row)
            for row in self.get_universe()
            if _listed_on_or_before(row.get("listed_at"), as_of)
        ]
        workers = max(
            1,
            min(16, int(os.environ.get("PIA_AKSHARE_HISTORICAL_WORKERS", "8"))),
        )
        bars: dict[str, dict[str, Any]] = {}
        rate_limited = threading.Event()

        def fetch(row: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or rate_limited.is_set():
                return "", None
            try:
                return symbol, self._historical_bar(symbol, as_of)
            except Exception as error:
                if type(error).__name__ == "Push2RateLimitError":
                    rate_limited.set()
                    raise
                return symbol, None

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(fetch, row) for row in universe]
            for future in as_completed(futures):
                symbol, row = future.result()
                if symbol and row:
                    bars[symbol] = row

        instruments: list[dict[str, Any]] = []
        changes: list[float | None] = []
        advances = declines = unchanged = 0
        for metadata in universe:
            symbol = str(metadata.get("symbol") or "").strip().upper()
            bar = bars.get(symbol)
            if not bar:
                continue
            change = _float(bar.get("change_pct"))
            changes.append(change)
            if change is None:
                unchanged += 1
            elif change > 0:
                advances += 1
            elif change < 0:
                declines += 1
            else:
                unchanged += 1
            instruments.append({
                **metadata,
                "symbol": symbol,
                "close": _float(bar.get("close")),
                "change_pct": change or 0.0,
                "average_turnover": _float(bar.get("amount")) or 0.0,
                "suspended": False,
                "active": True,
            })

        total = max(1, advances + declines + unchanged)
        indices = self._get_historical_indices(as_of)
        sectors = self._get_historical_sectors(as_of)
        coverage = len(instruments) / max(1, len(universe))
        volatility = _volatility(changes)
        quality = (
            "verified"
            if (
                instruments
                and coverage >= 0.98
                and indices
                and sectors
                and volatility is not None
            )
            else "partial"
            if instruments
            else "unavailable"
        )
        return {
            "snapshot_id": f"live_{self.provider_id}_{as_of}",
            "as_of": as_of,
            "observed_at": observed_at,
            "source": self.provider_id,
            "provider_id": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "adapter_version": "0.3.0",
            "quality": quality,
            "point_in_time_scope": "historical",
            "historical_coverage": {
                "eligible_instruments": len(universe),
                "observed_instruments": len(instruments),
                "ratio": round(coverage, 6),
                "target": 0.98,
            },
            "breadth": advances / total,
            "index_trend": "up" if advances >= declines else "down",
            "volatility": volatility,
            "indices": indices,
            "sectors": sectors,
            "instruments": instruments,
            "daily_bars": list(bars.values()),
        }

    def _stock_history_endpoint(self) -> Any:
        return getattr(self.sdk, "stock_zh_a_hist_em", None) or getattr(self.sdk, "stock_zh_a_hist", None)

    def _historical_bar(
        self,
        symbol: str,
        as_of: str,
    ) -> dict[str, Any] | None:
        cached = self._historical_bars_cache.setdefault(symbol, {})
        if as_of in cached:
            return cached[as_of]

        code = symbol.split(".")[0]
        start_date = (
            date.fromisoformat(as_of) - timedelta(days=45)
        ).strftime("%Y%m%d")
        end_date = datetime.now(timezone.utc).date().strftime("%Y%m%d")
        if _board_for_symbol(symbol) == "etf":
            method = getattr(self.sdk, "fund_etf_hist_em", None)
        else:
            method = self._stock_history_endpoint()
        if method is None:
            return None
        frame = method(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="",
        )
        rows = _records(frame)
        normalized = normalize_daily_bars(
            rows,
            provider_id=self.provider_id,
            provider_version=getattr(self.sdk, "__version__", "unknown"),
            adapter_version="0.3.0",
        )
        for raw, row in zip(rows, normalized):
            trade_date = str(row.get("trade_date") or "")[:10]
            if not trade_date:
                continue
            row["symbol"] = symbol
            row["change_pct"] = _float(
                raw.get("涨跌幅")
                or raw.get("pct_chg")
                or raw.get("change_pct")
            )
            cached[trade_date] = row
        return cached.get(as_of)

    def _get_historical_indices(self, as_of: str) -> list[dict[str, Any]]:
        method = getattr(self.sdk, "stock_zh_index_daily_em", None)
        if method is None:
            return []
        configured = [
            ("000001.SH", "上证指数"),
            ("399001.SZ", "深证成指"),
            ("399006.SZ", "创业板指"),
            ("000300.SH", "沪深300"),
            ("000688.SH", "科创50"),
        ]
        result: list[dict[str, Any]] = []
        for code, fallback_name in configured:
            cached = self._historical_index_cache.setdefault(code, {})
            if as_of not in cached:
                market = "sh" if code.endswith(".SH") else "sz"
                start_date = (
                    date.fromisoformat(as_of) - timedelta(days=15)
                ).strftime("%Y%m%d")
                frame = method(
                    symbol=f"{market}{code.split('.')[0]}",
                    start_date=start_date,
                    end_date=as_of.replace("-", ""),
                )
                rows = _records(frame)
                previous_close: float | None = None
                for raw in rows:
                    trade_date = str(
                        raw.get("date") or raw.get("日期") or ""
                    )[:10].replace("/", "-")
                    close = _float(raw.get("close") or raw.get("收盘"))
                    if not trade_date or close is None:
                        continue
                    change = (
                        ((close - previous_close) / previous_close * 100)
                        if previous_close not in (None, 0)
                        else None
                    )
                    cached[trade_date] = {
                        "symbol": code,
                        "name": fallback_name,
                        "close": close,
                        "change_pct": change,
                    }
                    previous_close = close
            row = cached.get(as_of)
            if row:
                result.append(row)
        return result

    def _get_historical_sectors(self, as_of: str) -> list[dict[str, Any]]:
        listing_method = getattr(self.sdk, "stock_board_industry_name_em", None)
        history_method = getattr(self.sdk, "stock_board_industry_hist_em", None)
        if listing_method is None or history_method is None:
            return []
        names = [
            str(row.get("板块名称") or row.get("名称") or "").strip()
            for row in _records(listing_method())
        ]
        names = [name for name in names if name][:20]
        result: list[dict[str, Any]] = []
        start_date = (
            date.fromisoformat(as_of) - timedelta(days=15)
        ).strftime("%Y%m%d")
        for name in names:
            cached = self._historical_sector_cache.setdefault(name, {})
            if as_of not in cached:
                try:
                    frame = history_method(
                        symbol=name,
                        start_date=start_date,
                        end_date=as_of.replace("-", ""),
                        period="日k",
                        adjust="",
                    )
                except Exception:
                    continue
                for raw in _records(frame):
                    trade_date = str(
                        raw.get("日期") or raw.get("date") or ""
                    )[:10].replace("/", "-")
                    if trade_date:
                        cached[trade_date] = {
                            "name": name,
                            "change_pct": _float(
                                raw.get("涨跌幅")
                                or raw.get("pct_chg")
                            ) or 0.0,
                            "breadth": 0.5,
                        }
            row = cached.get(as_of)
            if row:
                result.append(row)
        return result

    def get_market_breadth(self, as_of: str) -> dict[str, Any]:
        snapshot = self.get_market_snapshot(as_of)
        return {
            "as_of": snapshot.get("as_of", as_of),
            "snapshot_id": snapshot.get("snapshot_id"),
            "source": snapshot.get("source", self.provider_id),
            "breadth": snapshot.get("breadth"),
            "index_trend": snapshot.get("index_trend"),
        }

    def get_index_series(
        self,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_sdk()
        _validate_date_range(start_date, end_date)
        method = getattr(self.sdk, "stock_zh_index_daily_em", None)
        if method is None:
            raise RuntimeError(
                "CAPABILITY_DISABLED: AKShare index historical endpoint unavailable"
            )
        configured = {
            "000001.SH": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
            "000300.SH": "沪深300",
            "000688.SH": "科创50",
        }
        requested = {
            _canonical_index_symbol(str(symbol))
            for symbol in (symbols or [])
            if str(symbol).strip()
        }
        selected = (
            [symbol for symbol in requested if symbol]
            if requested
            else list(configured)
        )
        series: list[dict[str, Any]] = []
        for symbol in selected:
            code = symbol.split(".", 1)[0]
            market = "sh" if symbol.endswith(".SH") else "sz"
            try:
                frame = method(
                    symbol=f"{market}{code}",
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                )
            except Exception:
                continue
            rows = _records(frame)
            points: list[dict[str, Any]] = []
            previous_close: float | None = None
            for raw in rows:
                trade_date = _date_from_row(raw)
                close = _float(raw.get("close") or raw.get("收盘"))
                if not trade_date or close is None:
                    continue
                if not (start_date <= trade_date <= end_date):
                    continue
                change = _float(
                    raw.get("涨跌幅")
                    or raw.get("pct_chg")
                    or raw.get("change_pct")
                )
                if change is None and previous_close not in (None, 0):
                    change = (close - previous_close) / previous_close * 100
                points.append({
                    "trade_date": trade_date,
                    "open": _float(raw.get("open") or raw.get("开盘")),
                    "high": _float(raw.get("high") or raw.get("最高")),
                    "low": _float(raw.get("low") or raw.get("最低")),
                    "close": close,
                    "volume": _float(raw.get("volume") or raw.get("成交量")),
                    "amount": _float(raw.get("amount") or raw.get("成交额")),
                    "change_pct": change,
                    "source": self.provider_id,
                })
                previous_close = close
            if points:
                points.sort(key=lambda point: point["trade_date"])
                series.append({
                    "symbol": symbol,
                    "name": configured.get(symbol, symbol),
                    "points": points,
                })
        series.sort(key=lambda item: item["symbol"])
        return {
            "provider": self.provider_id,
            "source": self.provider_id,
            "quality": "verified" if series else "unavailable",
            "start_date": start_date,
            "end_date": end_date,
            "as_of": end_date,
            "series": series,
        }

    def get_fundamentals(
        self,
        symbol: str,
        start_year: str = "2000",
        as_of: str | None = None,
    ) -> dict[str, Any]:
        self._require_sdk()
        code = symbol.split(".")[0]
        frame = self.sdk.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
        rows = _records(frame)
        if as_of:
            rows = [
                row
                for row in rows
                if (_date_from_row(row) or "") <= as_of
            ]
        latest = _latest_row(rows)
        return {
            "symbol": _canonical_symbol(symbol),
            "as_of": _date_from_row(latest),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "quality": "verified" if latest else "unavailable",
            "metrics": _json_safe(latest),
        }

    def get_company_profile(
        self,
        symbol: str,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Return provider-backed company metadata for a research task."""
        self._require_sdk()
        code = symbol.split(".")[0]
        rows: list[dict[str, Any]] = []
        source_method = "stock_profile_cninfo"

        method = getattr(self.sdk, "stock_profile_cninfo", None)
        if method is not None:
            try:
                rows = _records(method(symbol=code))
            except Exception:
                rows = []

        if not rows:
            method = getattr(self.sdk, "stock_individual_info_em", None)
            source_method = "stock_individual_info_em"
            if method is not None:
                try:
                    rows = _records(method(symbol=code))
                except Exception:
                    rows = []

        profile: dict[str, Any] = {}
        if len(rows) == 1 and not any(
            key in rows[0] for key in ("item", "项目", "key", "name")
        ):
            profile = dict(rows[0])
        else:
            for row in rows:
                key = str(row.get("item") or row.get("项目") or row.get("key") or "").strip()
                if key:
                    profile[key] = row.get("value") or row.get("值")

        name = str(
            profile.get("公司简称")
            or profile.get("A股简称")
            or profile.get("股票简称")
            or profile.get("name")
            or symbol
        )
        industry = str(
            profile.get("所属行业")
            or profile.get("行业")
            or profile.get("industry")
            or ""
        ).strip()
        listed_at = _listed_at_from_value(
            profile.get("上市日期")
            or profile.get("上市时间")
            or profile.get("list_date")
        )
        quality = "verified" if name != symbol or industry or listed_at else "unavailable"
        return {
            "symbol": _canonical_symbol(symbol),
            "name": name,
            "industry": industry or "unknown",
            "exchange": str(profile.get("所属市场") or profile.get("exchange") or _exchange_for_symbol(symbol)),
            "listed_at": listed_at,
            "as_of": as_of,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": self.provider_id,
            "provider_id": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "source_method": source_method,
            "quality": quality,
        }

    def search_news(self, symbol: str, as_of: str | None = None) -> list[dict[str, Any]]:
        self._require_sdk()
        frame = self.sdk.stock_news_em(symbol=symbol.split(".")[0])
        rows = _records(frame)
        requested_code = symbol.split(".")[0]
        results = []
        for index, row in enumerate(rows[:50], start=1):
            row_code = _row_code(row)
            if row_code and row_code != requested_code:
                continue
            title = str(row.get("新闻标题") or row.get("标题") or "Untitled")
            published_at = str(row.get("发布时间") or row.get("日期") or "")
            if as_of and published_at[:10].replace("/", "-") > as_of:
                continue
            source = str(row.get("文章来源") or row.get("新闻来源") or self.provider_id)
            results.append({
                "id": f"news_{symbol}_{index}",
                "symbol": _canonical_symbol(row_code or requested_code),
                # The endpoint is queried with the requested symbol.  Some
                # AKShare responses omit the code column, but the query itself
                # still provides the symbol binding.
                "symbol_verified": True,
                "quality": "verified" if title and published_at and source else "partial",
                "title": title,
                "published_at": published_at,
                "source": source,
                "excerpt": str(row.get("新闻内容") or row.get("内容") or ""),
            })
        return results

    def search_filings(self, symbol: str, as_of: str) -> list[dict[str, Any]]:
        self._require_sdk()
        frame = self.sdk.stock_notice_report(
            symbol="全部",
            date=as_of.replace("-", ""),
        )
        rows = _records(frame)
        code = symbol.split(".")[0]
        return [
            {
                "id": f"filing_{symbol}_{index}",
                "symbol": _canonical_symbol(code),
                "symbol_verified": True,
                "quality": "verified",
                "title": str(row.get("公告标题") or row.get("标题") or "Filing"),
                "published_at": str(row.get("公告日期") or row.get("日期") or as_of),
                "source": str(row.get("公告链接") or row.get("链接") or self.provider_id),
                "excerpt": str(row.get("公告内容") or row.get("摘要") or ""),
            }
            for index, row in enumerate(rows, start=1)
            if code in str(row.get("代码") or row.get("证券代码") or "")
        ][:50]

    def get_universe(self) -> list[dict[str, Any]]:
        self._require_sdk()
        if self._universe_cache is not None:
            return [dict(row) for row in self._universe_cache]
        rows: list[dict[str, Any]] = []
        stock_spot = getattr(self.sdk, "stock_zh_a_spot_em", None)
        if stock_spot:
            try:
                rows.extend(_records(stock_spot()))
            except Exception:
                rows = []
        if not rows:
            rows.extend(_records(self.sdk.stock_info_a_code_name()))

        listing_metadata = self._get_listing_metadata()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = str(row.get("代码") or row.get("证券代码") or row.get("code") or "").strip()
            if not code:
                continue
            name = str(row.get("名称") or row.get("股票简称") or row.get("name") or code)
            symbol = _canonical_symbol(code)
            metadata = listing_metadata.get(code, {})
            listed_at = (
                _listed_at_from_row(row, "上市日期", "list_date")
                or metadata.get("listed_at")
            )
            exchange = (
                str(row.get("exchange") or metadata.get("exchange") or "")
                or _exchange_for_symbol(symbol)
            )
            suspended = (
                _float(row.get("最新价")) is None
                if "最新价" in row
                else False
            )
            is_delisting = _is_delisting_name(name)
            result[symbol] = {
                "symbol": symbol,
                "name": name,
                "asset_type": "stock",
                "board": _board_for_symbol(code),
                "is_st": "ST" in name.upper() or "＊" in name,
                "is_delisting": is_delisting,
                "suspended": suspended,
                "active": not suspended and not is_delisting,
                "exchange": exchange,
                "listed_at": listed_at,
                "listed_days": _listed_days(listed_at or ""),
            }

        etf_listing_metadata = self._get_etf_listing_metadata()
        etf_spot = getattr(self.sdk, "fund_etf_spot_em", None)
        if etf_spot:
            try:
                for row in _records(etf_spot()):
                    code = str(row.get("代码") or row.get("证券代码") or "").strip()
                    if not code:
                        continue
                    name = str(row.get("名称") or row.get("证券简称") or code)
                    symbol = _canonical_symbol(code)
                    suspended = (
                        _float(row.get("最新价")) is None
                        if "最新价" in row
                        else False
                    )
                    is_delisting = _is_delisting_name(name)
                    result[symbol] = {
                        "symbol": symbol,
                        "name": name,
                        "asset_type": "etf",
                        "board": "etf",
                        "exchange": _exchange_for_symbol(symbol),
                        "listed_at": (
                            _listed_at_from_row(row, "上市日期", "list_date")
                            or etf_listing_metadata.get(code, {}).get("listed_at")
                        ),
                        "is_st": False,
                        "is_delisting": is_delisting,
                        "suspended": suspended,
                        "active": not suspended and not is_delisting,
                        "listed_days": _listed_days(
                            _listed_at_from_row(row, "上市日期", "list_date") or ""
                        ),
                    }
            except Exception:
                # A stock universe remains useful when the optional ETF endpoint is unavailable.
                pass
        self._universe_cache = [dict(row) for row in result.values()]
        return [dict(row) for row in self._universe_cache]

    def _get_etf_listing_metadata(self) -> dict[str, dict[str, str | None]]:
        """Load ETF listing dates from exchange-maintained product lists."""

        if self._etf_listing_metadata is not None:
            return self._etf_listing_metadata

        metadata: dict[str, dict[str, str | None]] = {}
        metadata.update(self._get_sse_etf_listing_metadata())
        metadata.update(self._get_szse_etf_listing_metadata())

        self._etf_listing_metadata = metadata
        return metadata

    def _get_listing_metadata(self) -> dict[str, dict[str, str | None]]:
        """Load stock listing dates from exchange and market metadata sources."""

        if self._listing_metadata is not None:
            return self._listing_metadata

        metadata: dict[str, dict[str, str | None]] = {}
        sources = (
            ("stock_info_sh_name_code", {"symbol": "主板A股"}, "SSE"),
            ("stock_info_sh_name_code", {"symbol": "科创板"}, "SSE"),
            ("stock_info_sz_name_code", {"symbol": "A股列表"}, "SZSE"),
            ("stock_info_bj_name_code", {}, "BSE"),
            ("stock_info_sh_delist", {"symbol": "全部"}, "SSE"),
            ("stock_info_sz_delist", {"symbol": "终止上市公司"}, "SZSE"),
            ("stock_info_sz_delist", {"symbol": "暂停上市公司"}, "SZSE"),
        )
        for method_name, kwargs, exchange in sources:
            method = getattr(self.sdk, method_name, None)
            if not method:
                continue
            try:
                rows = _records(method(**kwargs))
            except Exception:
                continue
            for row in rows:
                code = str(
                    row.get("代码")
                    or row.get("证券代码")
                    or row.get("公司代码")
                    or row.get("A股代码")
                    or ""
                ).strip()
                listed_at = _listed_at_from_row(
                    row,
                    "上市日期",
                    "A股上市日期",
                    "list_date",
                )
                if code and listed_at:
                    metadata[code] = {
                        "exchange": exchange,
                        "listed_at": listed_at,
                    }

        # The exchange lists intentionally omit some historical suspended
        # symbols. Eastmoney's market metadata supplies listing dates for the
        # remaining symbols in one paginated, read-only endpoint.
        if getattr(self.sdk, "__name__", "") == "akshare":
            for code, row in self._get_eastmoney_stock_listing_metadata().items():
                metadata.setdefault(code, row)

        self._listing_metadata = metadata
        return metadata

    def _get_eastmoney_stock_listing_metadata(
        self,
    ) -> dict[str, dict[str, str | None]]:
        base_url = "https://82.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f12",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": "f12,f13,f14,f26",
        }

        def fetch(page: int) -> tuple[int, list[dict[str, Any]]]:
            query = urllib.parse.urlencode({**params, "pn": str(page)})
            request = urllib.request.Request(
                f"{base_url}?{query}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                return 0, []
            rows = data.get("diff") or []
            return int(data.get("total") or 0), [
                row for row in rows if isinstance(row, dict)
            ]

        try:
            total, first_page = fetch(1)
        except (OSError, ValueError, TypeError, urllib.error.URLError):
            return {}

        page_count = max(1, math.ceil(total / 100))
        pages: list[dict[str, Any]] = list(first_page)
        if page_count > 1:
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [
                    executor.submit(fetch, page)
                    for page in range(2, page_count + 1)
                ]
                for future in as_completed(futures):
                    try:
                        _, rows = future.result()
                    except (OSError, ValueError, TypeError, urllib.error.URLError):
                        continue
                    pages.extend(rows)

        metadata: dict[str, dict[str, str | None]] = {}
        for row in pages:
            code = str(row.get("f12") or "").strip()
            listed_at = _listed_at_from_value(row.get("f26"))
            if code and listed_at:
                metadata[code] = {
                    "exchange": _exchange_for_symbol(code),
                    "listed_at": listed_at,
                }
        return metadata

    def _get_szse_etf_listing_metadata(self) -> dict[str, dict[str, str | None]]:
        """Load listing dates from the SZSE-maintained ETF workbook."""

        method = getattr(self.sdk, "fund_etf_scale_szse", None)
        if method:
            try:
                rows = _records(method())
            except Exception:
                rows = []
            metadata = _listing_metadata_from_rows(rows, "SZSE")
            if metadata:
                return metadata

        # Some AKShare releases pass raw bytes to pandas.read_excel and fail
        # on newer Python versions. Read the official workbook here so the
        # adapter does not lose all SZSE ETF listing dates.
        params = {
            "SHOWTYPE": "xlsx",
            "CATALOGID": "1000_lf",
            "TABKEY": "tab1",
            "random": "0.07610353191740105",
        }
        url = (
            "https://fund.szse.cn/api/report/ShowReport?"
            + urllib.parse.urlencode(params)
        )
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://fund.szse.cn/marketdata/fundslist/index.html",
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                content = response.read()
            import io
            import pandas as pd

            frame = pd.read_excel(
                io.BytesIO(content),
                engine="openpyxl",
                dtype={"基金代码": str},
            )
            return _listing_metadata_from_rows(
                frame.to_dict(orient="records"),
                "SZSE",
            )
        except (ImportError, OSError, ValueError, TypeError, urllib.error.URLError):
            return {}

    def _get_sse_etf_listing_metadata(self) -> dict[str, dict[str, str | None]]:
        """Fetch listing dates from the SSE fund list JSON endpoint."""

        params = {
            "isPagination": "true",
            "sqlId": "COMMON_JJZWZ_JJLB_L",
            "pageHelp.cacheSize": "1",
            "pageHelp.pageSize": "10000",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.endPage": "1",
            "FUND_CODE": "",
            "COMPANY_NAME": "",
            "INDEX_NAME": "",
            "START_DATE": "",
            "END_DATE": "",
            "CATEGORY": "F000",
            "CATEGORY_ASC": "1",
            "SUBCLASS": "",
            "SWING_TRADE": "",
            "type": "inParams",
        }
        url = (
            "https://query.sse.com.cn/commonQuery.do?"
            + urllib.parse.urlencode(params)
        )
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://etf.sse.com.cn/fundlist/",
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = response.read().decode("utf-8")
            if payload.startswith("(") and payload.endswith(")"):
                payload = payload[1:-1]
            decoded = json.loads(payload)
        except (OSError, ValueError, TypeError, urllib.error.URLError):
            return {}

        rows = (
            decoded.get("pageHelp", {}).get("data", [])
            if isinstance(decoded, dict)
            else []
        ) or []
        metadata: dict[str, dict[str, str | None]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("FUND_CODE") or "").strip()
            listed_at = _listed_at_from_value(row.get("LISTING_DATE"))
            if code and listed_at:
                metadata[code] = {
                    "exchange": "SSE",
                    "listed_at": listed_at,
                }
        return metadata

    def _get_sectors(self) -> list[dict[str, Any]]:
        try:
            rows = _records(self.sdk.stock_board_industry_name_em())
        except Exception:
            return []
        return [
            {
                "name": str(row.get("板块名称") or row.get("名称") or "unknown"),
                "change_pct": _float(row.get("涨跌幅")) or 0.0,
                "breadth": 0.5,
            }
            for row in rows[:20]
        ]

    def _get_indices(self) -> list[dict[str, Any]]:
        method = getattr(self.sdk, "stock_zh_index_spot_em", None)
        if not method:
            return []
        try:
            frame = method(symbol="沪深重要指数")
        except TypeError:
            frame = method()
        except Exception:
            return []
        indices = []
        for row in _records(frame):
            code = str(row.get("代码") or row.get("指数代码") or "").strip()
            close = _float(row.get("最新价") or row.get("收盘") or row.get("最新"))
            change = _float(row.get("涨跌幅") or row.get("涨跌"))
            if not code or close is None or change is None:
                continue
            indices.append({
                "symbol": _canonical_index_symbol(code),
                "name": str(row.get("名称") or row.get("指数名称") or code),
                "close": close,
                "change_pct": change,
            })
        return indices[:20]


class TushareMarketProvider:
    provider_id = "tushare"

    def __init__(self, token: str | None) -> None:
        self.token = token
        self.sdk = None
        self.client = None
        if self.token and not self.token.startswith("__"):
            try:
                import tushare as sdk  # type: ignore
                self.sdk = sdk
                self.client = sdk.pro_api(self.token)
            except ImportError:
                self.sdk = None

    def health(self) -> ProviderHealth:
        enabled = bool(self.token and not self.token.startswith("__"))
        return ProviderHealth(
            provider_id=self.provider_id,
            status="healthy" if enabled and self.client else "capability_disabled",
            capabilities=[
                "market_snapshot",
                "daily_bars",
                "market_breadth",
                "index_series",
                "trading_calendar",
                "fundamentals",
                "company_profile",
                "news",
                "filings",
                "universe",
            ] if enabled and self.client else [],
            supports_replay=True,
            requires_credentials=True,
        )

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        if _board_for_symbol(symbol) == "etf":
            method = getattr(self.client, "fund_daily", None)
            if method is None:
                raise RuntimeError(
                    "CAPABILITY_DISABLED: Tushare ETF historical endpoint unavailable"
                )
            frame = method(
                ts_code=symbol,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
        else:
            frame = self.client.daily(
                ts_code=symbol,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
        rows = _records(frame)
        for row in rows:
            row.setdefault("ts_code", symbol)
        return normalize_daily_bars(
            rows,
            provider_id=self.provider_id,
            provider_version=getattr(self.sdk, "__version__", "unknown"),
        )

    def get_trading_calendar(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        frame = self.client.trade_cal(
            exchange="SSE",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        return [
            {
                "trade_date": date.fromisoformat(str(row.get("cal_date", ""))).isoformat(),
                "is_open": str(row.get("is_open", "0")) == "1",
                "quality": "verified",
            }
            for row in _records(frame)
        ]

    def get_universe(self) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        frame = self.client.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,exchange,area,industry,list_date",
        )
        result = [
            {
                "symbol": str(row.get("ts_code", "")),
                "name": str(row.get("name", "")),
                "asset_type": "stock",
                "board": _board_for_symbol(str(row.get("symbol", ""))),
                "exchange": str(row.get("exchange") or _exchange_for_symbol(str(row.get("ts_code", "")))),
                "listed_at": _listed_at_from_value(row.get("list_date")),
                "is_st": "ST" in str(row.get("name", "")).upper(),
                "suspended": False,
                "active": True,
                "listed_days": _listed_days(str(row.get("list_date", ""))),
            }
            for row in _records(frame)
            if row.get("ts_code")
        ]
        fund_basic = getattr(self.client, "fund_basic", None)
        if fund_basic:
            try:
                funds = fund_basic(
                    market="E",
                    fields="ts_code,name,listing_date",
                )
            except TypeError:
                funds = fund_basic(market="E")
            except Exception:
                funds = []
            result.extend(
                {
                    "symbol": str(row.get("ts_code", "")),
                    "name": str(row.get("name", "")),
                    "asset_type": "etf",
                    "board": "etf",
                    "exchange": str(
                        row.get("exchange")
                        or _exchange_for_symbol(str(row.get("ts_code", "")))
                    ),
                    "listed_at": _listed_at_from_value(
                        row.get("listing_date") or row.get("list_date")
                    ),
                    "is_st": False,
                    "is_delisting": False,
                    "suspended": False,
                    "active": True,
                    "listed_days": _listed_days(str(row.get("listing_date", ""))),
                }
                for row in _records(funds)
                if row.get("ts_code")
            )
        return result

    def get_market_snapshot(self, as_of: str) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        frame = self.client.daily_basic(
            trade_date=as_of.replace("-", ""),
            fields="ts_code,close,pct_chg,amount",
        )
        records = _records(frame)
        universe_by_symbol: dict[str, dict[str, Any]] = {}
        try:
            universe_by_symbol = {
                str(item["symbol"]): item
                for item in self.get_universe()
                if item.get("symbol")
            }
        except Exception:
            # Snapshot data remains usable when the optional metadata endpoint
            # is unavailable; downstream quality still reflects the fields we
            # could verify.
            universe_by_symbol = {}
        advances = sum(1 for row in records if _float(row.get("pct_chg")) is not None and _float(row.get("pct_chg")) > 0)
        declines = sum(1 for row in records if _float(row.get("pct_chg")) is not None and _float(row.get("pct_chg")) < 0)
        unchanged = max(0, len(records) - advances - declines)
        total = max(1, advances + declines + unchanged)
        observed_at = datetime.now(timezone.utc).isoformat()
        indices = self._get_indices(as_of)
        sectors = self._get_sectors(as_of)
        instruments = [
            {
                "symbol": str(row.get("ts_code", "")),
                "name": str(
                    universe_by_symbol.get(str(row.get("ts_code", "")), {}).get(
                        "name",
                        row.get("ts_code", ""),
                    )
                ),
                "asset_type": "stock",
                "exchange": universe_by_symbol.get(
                    str(row.get("ts_code", "")),
                    {},
                ).get("exchange") or _exchange_for_symbol(str(row.get("ts_code", ""))),
                "listed_at": universe_by_symbol.get(
                    str(row.get("ts_code", "")),
                    {},
                ).get("listed_at"),
                "board": universe_by_symbol.get(
                    str(row.get("ts_code", "")),
                    {},
                ).get("board") or _board_for_symbol(str(row.get("ts_code", ""))),
                "is_st": bool(
                    universe_by_symbol.get(
                        str(row.get("ts_code", "")),
                        {},
                    ).get("is_st", False)
                ),
                "is_delisting": bool(
                    universe_by_symbol.get(
                        str(row.get("ts_code", "")),
                        {},
                    ).get("is_delisting", False)
                ),
                "suspended": _float(row.get("close")) is None,
                "active": _float(row.get("close")) is not None,
                "listed_days": universe_by_symbol.get(
                    str(row.get("ts_code", "")),
                    {},
                ).get("listed_days") or 9999,
                "close": _float(row.get("close")),
                "change_pct": _float(row.get("pct_chg")) or 0.0,
                "average_turnover": (_float(row.get("amount")) or 0.0) * 1000,
            }
            for row in records
            if row.get("ts_code")
        ]
        fund_daily = getattr(self.client, "fund_daily", None)
        if fund_daily:
            try:
                funds = fund_daily(
                    trade_date=as_of.replace("-", ""),
                    fields="ts_code,close,pct_chg,amount",
                )
            except TypeError:
                funds = fund_daily(trade_date=as_of.replace("-", ""))
            except Exception:
                funds = []
            instruments.extend(
                {
                    "symbol": str(row.get("ts_code", "")),
                    "name": str(row.get("ts_code", "")),
                    "asset_type": "etf",
                    "board": "etf",
                    "exchange": _exchange_for_symbol(str(row.get("ts_code", ""))),
                    "listed_at": None,
                    "is_st": False,
                    "is_delisting": False,
                    "suspended": _float(row.get("close")) is None,
                    "active": _float(row.get("close")) is not None,
                    "listed_days": 9999,
                    "close": _float(row.get("close")),
                    "change_pct": _float(row.get("pct_chg")) or 0.0,
                    "average_turnover": (_float(row.get("amount")) or 0.0) * 1000,
                }
                for row in _records(funds)
                if row.get("ts_code")
                and _board_for_symbol(str(row.get("ts_code", ""))) == "etf"
            )
        return {
            "snapshot_id": f"live_{self.provider_id}_{as_of}",
            "as_of": as_of,
            "observed_at": observed_at,
            "source": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "adapter_version": "0.2.0",
            "quality": "verified" if instruments and _volatility([_float(row.get("pct_chg")) for row in records]) is not None else "partial" if instruments else "unavailable",
            "breadth": advances / total,
            "index_trend": "up" if advances >= declines else "down",
            "volatility": _volatility([_float(row.get("pct_chg")) for row in records]),
            "indices": indices,
            "sectors": sectors,
            "instruments": instruments,
            "daily_bars": [],
        }

    def get_market_breadth(self, as_of: str) -> dict[str, Any]:
        snapshot = self.get_market_snapshot(as_of)
        return {
            "as_of": snapshot.get("as_of", as_of),
            "snapshot_id": snapshot.get("snapshot_id"),
            "source": snapshot.get("source", self.provider_id),
            "breadth": snapshot.get("breadth"),
            "index_trend": snapshot.get("index_trend"),
        }

    def get_index_series(
        self,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        _validate_date_range(start_date, end_date)
        method = getattr(self.client, "index_daily", None)
        if method is None:
            raise RuntimeError("CAPABILITY_DISABLED: Tushare index_daily endpoint unavailable")
        configured = {
            "000001.SH": "上证指数",
            "399001.SZ": "深证成指",
            "399006.SZ": "创业板指",
            "000300.SH": "沪深300",
            "000688.SH": "科创50",
        }
        requested = {
            _canonical_index_symbol(str(symbol))
            for symbol in (symbols or [])
            if str(symbol).strip()
        }
        selected = list(requested) if requested else list(configured)
        series: list[dict[str, Any]] = []
        for symbol in selected:
            try:
                rows = _records(method(
                    ts_code=symbol,
                    start_date=start_date.replace("-", ""),
                    end_date=end_date.replace("-", ""),
                ))
            except Exception:
                continue
            points = []
            for raw in rows:
                trade_date = _date_from_row(raw)
                close = _float(raw.get("close"))
                if not trade_date or close is None:
                    continue
                if not (start_date <= trade_date <= end_date):
                    continue
                points.append({
                    "trade_date": trade_date,
                    "open": _float(raw.get("open")),
                    "high": _float(raw.get("high")),
                    "low": _float(raw.get("low")),
                    "close": close,
                    "volume": _float(raw.get("vol") or raw.get("volume")),
                    "amount": _float(raw.get("amount")),
                    "change_pct": _float(raw.get("pct_chg")),
                    "source": self.provider_id,
                })
            if points:
                points.sort(key=lambda point: point["trade_date"])
                series.append({
                    "symbol": symbol,
                    "name": configured.get(symbol, symbol),
                    "points": points,
                })
        series.sort(key=lambda item: item["symbol"])
        return {
            "provider": self.provider_id,
            "source": self.provider_id,
            "quality": "verified" if series else "unavailable",
            "start_date": start_date,
            "end_date": end_date,
            "as_of": end_date,
            "series": series,
        }

    def _get_indices(self, as_of: str) -> list[dict[str, Any]]:
        method = getattr(self.client, "index_daily", None)
        if not method:
            return []
        configured = [
            ("000001.SH", "上证指数"),
            ("399001.SZ", "深证成指"),
            ("399006.SZ", "创业板指"),
            ("000300.SH", "沪深300"),
            ("000688.SH", "科创50"),
        ]
        result: list[dict[str, Any]] = []
        for code, fallback_name in configured:
            try:
                rows = _records(method(
                    ts_code=code,
                    trade_date=as_of.replace("-", ""),
                ))
            except Exception:
                continue
            if not rows:
                continue
            row = max(rows, key=lambda item: str(item.get("trade_date") or ""))
            close = _float(row.get("close"))
            change = _float(row.get("pct_chg"))
            if close is None or change is None:
                continue
            result.append({
                "symbol": code,
                "name": str(row.get("name") or fallback_name),
                "close": close,
                "change_pct": change,
            })
        return result

    def _get_sectors(self, as_of: str) -> list[dict[str, Any]]:
        method = getattr(self.client, "sw_daily", None)
        if not method:
            return []
        try:
            rows = _records(method(trade_date=as_of.replace("-", "")))
        except Exception:
            return []
        return [
            {
                "name": str(row.get("name") or row.get("ts_code") or "unknown"),
                "change_pct": _float(row.get("pct_chg")) or 0.0,
                "breadth": 0.5,
            }
            for row in rows[:20]
            if row.get("ts_code") or row.get("name")
        ]

    def get_fundamentals(
        self,
        symbol: str,
        start_year: str = "2000",
        as_of: str | None = None,
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        frame = self.client.fina_indicator(ts_code=symbol, start_date=f"{start_year}0101")
        rows = _records(frame)
        if as_of:
            rows = [
                row
                for row in rows
                if (_date_from_row(row) or "") <= as_of
            ]
        latest = _latest_row(rows)
        return {
            "symbol": symbol,
            "as_of": _date_from_row(latest),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "quality": "verified" if latest else "unavailable",
            "metrics": _json_safe(latest),
        }

    def get_company_profile(
        self,
        symbol: str,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        fields = "ts_code,symbol,name,exchange,industry,list_date"
        frame = self.client.stock_basic(
            ts_code=symbol,
            list_status="",
            fields=fields,
        )
        rows = _records(frame)
        row = next(
            (
                item for item in rows
                if str(item.get("ts_code") or "").upper() == symbol.upper()
            ),
            rows[0] if rows else {},
        )
        name = str(row.get("name") or symbol)
        industry = str(row.get("industry") or "").strip()
        quality = "verified" if name != symbol or industry or row.get("list_date") else "unavailable"
        return {
            "symbol": str(row.get("ts_code") or symbol),
            "name": name,
            "industry": industry or "unknown",
            "exchange": str(row.get("exchange") or _exchange_for_symbol(symbol)),
            "listed_at": _listed_at_from_value(row.get("list_date")),
            "as_of": as_of,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": self.provider_id,
            "provider_id": self.provider_id,
            "provider_version": getattr(self.sdk, "__version__", "unknown"),
            "source_method": "stock_basic",
            "quality": quality,
        }

    def search_news(self, symbol: str, as_of: str | None = None) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        news_method = getattr(self.client, "news", None)
        if not news_method:
            return []
        try:
            rows = _records(news_method(
                ts_code=symbol,
                src="sina",
                start_date=None,
                end_date=None,
            ))
            symbol_filter_requested = True
        except TypeError:
            rows = _records(news_method(src="sina", start_date=None, end_date=None))
            symbol_filter_requested = False
        return [
            {
                "id": f"news_{symbol}_{index}",
                "symbol": symbol,
                "symbol_verified": symbol_filter_requested and (
                    not row.get("ts_code") or str(row.get("ts_code")) == symbol
                ),
                "quality": "verified" if symbol_filter_requested else "partial",
                "title": str(row.get("title") or "Untitled"),
                "published_at": str(row.get("datetime") or ""),
                "source": str(row.get("source") or self.provider_id),
                "excerpt": str(row.get("content") or ""),
            }
            for index, row in enumerate(rows[:50], start=1)
            if (
                (not row.get("ts_code") or str(row.get("ts_code")) == symbol)
                and (
                    not as_of
                    or str(row.get("datetime") or "")[:10].replace("/", "-") <= as_of
                )
            )
        ]

    def search_filings(self, symbol: str, as_of: str) -> list[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("CAPABILITY_DISABLED: configure TUSHARE_TOKEN and install tushare")
        method = getattr(self.client, "anns_d", None)
        if not method:
            return []
        rows = _records(method(ts_code=symbol, ann_date=as_of.replace("-", "")))
        return [
            {
                "id": f"filing_{symbol}_{index}",
                "symbol": symbol,
                "symbol_verified": True,
                "quality": "verified",
                "title": str(row.get("title") or "Filing"),
                "published_at": str(row.get("ann_date") or as_of),
                "source": str(row.get("url") or self.provider_id),
                "excerpt": str(row.get("content") or row.get("title") or ""),
            }
            for index, row in enumerate(rows[:50], start=1)
        ]


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    return list(frame)


def _is_retryable_provider_error(error: BaseException) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in {408, 425, 429} or 500 <= error.code < 600
    if isinstance(error, (TimeoutError, ConnectionError, OSError, urllib.error.URLError)):
        return True
    message = str(error).lower()
    retryable_markers = (
        "timeout",
        "temporarily unavailable",
        "temporary failure",
        "connection reset",
        "connection refused",
        "rate limit",
        "too many requests",
        " 429",
        " 500",
        " 502",
        " 503",
        " 504",
    )
    return any(marker in message for marker in retryable_markers)


def _float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _canonical_symbol(value: str) -> str:
    text = value.strip().upper()
    if "." in text:
        return text
    if text.startswith(("4", "8", "92")):
        return f"{text}.BJ"
    if text.startswith(("6", "68", "5")):
        return f"{text}.SH"
    return f"{text}.SZ"


def _exchange_for_symbol(value: str) -> str:
    text = value.strip().upper()
    suffix = text.rsplit(".", 1)[-1] if "." in text else ""
    if suffix in {"SH", "SSE"}:
        return "SSE"
    if suffix in {"SZ", "SZSE"}:
        return "SZSE"
    if suffix in {"BJ", "BSE"}:
        return "BSE"
    code = text.split(".", 1)[0]
    if code.startswith(("6", "5")):
        return "SSE"
    if code.startswith(("8", "4")):
        return "BSE"
    return "SZSE"


def _listed_at_from_value(value: Any) -> str | None:
    if value in (None, "", "nan", "NaT"):
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        try:
            value = value.date()
        except Exception:
            pass
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) >= 10:
        candidate = text[:10]
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            return None
    return None


def _listed_at_from_row(
    row: dict[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        listed_at = _listed_at_from_value(row.get(key))
        if listed_at:
            return listed_at
    return None


def _listing_metadata_from_rows(
    rows: list[dict[str, Any]],
    exchange: str,
) -> dict[str, dict[str, str | None]]:
    metadata: dict[str, dict[str, str | None]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(
            row.get("基金代码")
            or row.get("FUND_CODE")
            or row.get("代码")
            or row.get("证券代码")
            or ""
        ).strip()
        listed_at = _listed_at_from_row(
            row, "上市日期", "LISTING_DATE", "list_date"
        )
        if code and listed_at:
            metadata[code] = {
                "exchange": exchange,
                "listed_at": listed_at,
            }
    return metadata


def _canonical_index_symbol(value: str) -> str:
    text = value.strip().upper()
    if "." in text:
        return text
    if text.startswith(("0", "6")):
        return f"{text}.SH"
    return f"{text}.SZ"


def _validate_date_range(start_date: str, end_date: str) -> None:
    try:
        start = date.fromisoformat(str(start_date)[:10])
        end = date.fromisoformat(str(end_date)[:10])
    except ValueError as error:
        raise ValueError("index series dates must use ISO format YYYY-MM-DD") from error
    if start > end:
        raise ValueError("start_date must be on or before end_date")


def _board_for_symbol(value: str) -> str:
    code = value.strip().split(".")[0]
    if code.startswith(("30", "300")):
        return "chinext"
    if code.startswith(("68", "688")):
        return "star"
    if code.startswith(("4", "8", "92")):
        return "bse"
    if code.startswith(("5", "15", "16")):
        return "etf"
    return "main"


def _listed_days(value: str) -> int | None:
    if not value:
        return None
    try:
        listed = datetime.fromisoformat(value[:10])
        return max(0, (datetime.now() - listed).days)
    except ValueError:
        return None


def _listed_on_or_before(value: Any, as_of: str) -> bool:
    if not value:
        return True
    normalized = str(value)[:10].replace("/", "-")
    try:
        return date.fromisoformat(normalized) <= date.fromisoformat(as_of)
    except ValueError:
        return False


def _date_from_row(row: dict[str, Any]) -> str | None:
    for key in ("日期", "报告期", "报告日期", "trade_date", "date"):
        if row.get(key):
            return str(row[key])[:10].replace("/", "-")
    return None


def _latest_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    dated = [(date, row) for row in rows if (date := _date_from_row(row))]
    if not dated:
        return rows[0]
    return max(dated, key=lambda item: item[0])[1]


def _row_code(row: dict[str, Any]) -> str | None:
    value = row.get("代码") or row.get("证券代码") or row.get("股票代码") or row.get("symbol")
    if value in (None, ""):
        return None
    return str(value).split(".")[0].strip()


def _is_delisting_name(name: str) -> bool:
    normalized = name.replace(" ", "").upper()
    return "退市" in normalized or (
        "退" in normalized and ("整理" in normalized or "风险" in normalized)
    )


def _volatility(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if len(cleaned) < 2:
        return None
    # Provider change fields are percentages such as 1.2, while Rules v1 uses fractions.
    normalized = [value / 100 if abs(value) > 1 else value for value in cleaned]
    return round(pstdev(normalized), 6)


def _json_safe(row: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in row.items():
        if value is None:
            result[str(key)] = None
            continue
        try:
            value = value.item()
        except AttributeError:
            pass
        if isinstance(value, float) and not math.isfinite(value):
            result[str(key)] = None
        else:
            result[str(key)] = str(value) if not isinstance(value, (str, int, float, bool)) else value
    return result
