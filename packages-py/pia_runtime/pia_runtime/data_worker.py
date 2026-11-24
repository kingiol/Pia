from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .analytics import AnalyticsStore
from .data_quality import (
    validate_snapshot,
    validate_temporal_metadata,
    validate_universe_coverage,
    validate_universe_metadata,
)
from .market_sync import MARKET_SYNC_STAGES, MarketSyncProgress


class DataWorker:
    """Fetch, normalize and persist provider data without making investment decisions."""

    def __init__(
        self,
        provider: Any,
        analytics: AnalyticsStore,
        observability: Any | None = None,
        call_provider: Any | None = None,
    ) -> None:
        self.provider = provider
        self.analytics = analytics
        self.observability = observability
        self.call_provider = call_provider

    def _call_provider(
        self,
        capability: str,
        method: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if self.call_provider is not None:
            if method is _call_with_optional_as_of:
                method, args = args[0], args[1:]
            selected, result = self.call_provider(capability, method.__name__, *args, **kwargs)
            return result
        started = time.monotonic()
        try:
            result = method(*args, **kwargs)
        except Exception as error:
            if self.observability is not None:
                self.observability.record_provider_call(
                    capability,
                    self.provider.provider_id,
                    getattr(method, "__name__", capability),
                    (time.monotonic() - started) * 1000,
                    success=False,
                    error=error,
                )
            raise
        if self.observability is not None:
            self.observability.record_provider_call(
                capability,
                self.provider.provider_id,
                getattr(method, "__name__", capability),
                (time.monotonic() - started) * 1000,
                success=True,
            )
        return result

    def _save_raw_rows(
        self, kind: str, rows: list[dict], as_of: str, observed_at: str, *, symbol: str = "",
        receipt_scope: str = "",
    ) -> str:
        health = self.provider.health()
        def metadata(key, default):
            values = {str(row.get(key, default)) for row in rows}
            return next(iter(values)) if len(values) == 1 else "mixed"
        provider_id = metadata("provider_id", self.provider.provider_id)
        payload_id = f"raw_{kind}_{provider_id}_{as_of}" + (f"_{symbol}" if symbol else "")
        if receipt_scope:
            payload_id += "_" + hashlib.sha256(f"{receipt_scope}:{observed_at}".encode()).hexdigest()[:20]
        self.analytics.save_raw_payload(
            payload_id=payload_id,
            provider_id=provider_id,
            provider_version=metadata("provider_version", health.provider_version),
            adapter_version=metadata("adapter_version", health.adapter_version),
            as_of=as_of, observed_at=observed_at, payload={"rows": rows},
        )
        return payload_id

    def sync_daily_bars(self, as_of: str, symbols: list[str]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        observed_at = datetime.now(timezone.utc).isoformat()
        request_temporal = validate_temporal_metadata(
            {"as_of": as_of, "observed_at": observed_at},
            expected_as_of=as_of,
        )
        if not request_temporal["valid"]:
            failures.extend(
                _temporal_failure("daily_bars", None, error)
                for error in request_temporal["errors"]
            )
            return {
                "provider_id": self.provider.provider_id,
                "as_of": as_of,
                "stored_rows": 0,
                "failures": failures,
                "quality": "unavailable",
            }
        for symbol in symbols:
            try:
                bars = self._call_provider(
                    "daily_bars",
                    self.provider.get_daily_bars,
                    symbol,
                    as_of,
                    as_of,
                )
                rows.extend(
                    _apply_temporal_quality(
                        {
                            **dict(row),
                            "as_of": dict(row).get("as_of") or as_of,
                            "observed_at": dict(row).get("observed_at") or observed_at,
                        },
                        validate_temporal_metadata(
                            {
                                **dict(row),
                                "as_of": dict(row).get("as_of") or as_of,
                                "observed_at": dict(row).get("observed_at") or observed_at,
                            },
                            expected_as_of=as_of,
                        ),
                    )
                    for row in bars
                )
            except Exception as error:
                failures.append({
                    "symbol": symbol,
                    "code": type(error).__name__,
                    "message": str(error),
                })
        if rows:
            self._save_raw_rows("daily_bars", rows, as_of, observed_at)
            stored = self.analytics.save_daily_bars(rows)
            _append_row_temporal_failures(failures, "daily_bars", rows)
        else:
            stored = 0
        quality = "verified" if stored and not failures else "partial" if stored else "unavailable"
        return {
            "provider_id": self.provider.provider_id,
            "as_of": as_of,
            "stored_rows": stored,
            "failures": failures,
            "quality": quality,
        }

    def sync_market_data(
        self, as_of: str, symbols: list[str], *, include_default_symbols: bool = True,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        scope: str | None = None, refresh_stage: str | None = None,
        save_market: Callable[[dict[str, Any]], Any] | None = None,
        load_market: Callable[[str], dict[str, Any] | None] | None = None,
        reuse_local_daily_bars: bool = False,
    ) -> dict[str, Any]:
        """Synchronize the complete point-in-time market data contract.

        Every provider response is retained as raw JSON and each normalized
        collection receives explicit provenance and quality metadata. A
        missing optional capability is reported as a failure instead of being
        silently treated as verified data.
        """

        health = self.provider.health()
        provider_version = health.provider_version
        adapter_version = health.adapter_version
        now = datetime.now(timezone.utc)
        observed_at = now.isoformat()
        failures: list[dict[str, str]] = []
        counts = {
            "market_snapshot": 0,
            "trading_calendar": 0,
            "universe": 0,
            "daily_bars": 0,
            "fundamentals": 0,
            "research_sources": 0,
        }
        qualities: list[str] = []
        request_temporal = validate_temporal_metadata(
            {"as_of": as_of, "observed_at": observed_at},
            expected_as_of=as_of,
        )
        if not request_temporal["valid"]:
            failures.extend(
                _temporal_failure("request", None, error)
                for error in request_temporal["errors"]
            )
            return {
                "provider_id": self.provider.provider_id,
                "as_of": as_of,
                "quality": "unavailable",
                "market_snapshot_quality": "unavailable",
                "market_snapshot_source": self.provider.provider_id,
                "counts": counts,
                "failures": failures,
                "requested_symbols": [str(symbol) for symbol in symbols if str(symbol).strip()],
                "snapshot_id": f"market_{self.provider.provider_id}_{as_of}",
                "market_snapshot": None,
                "research_sources": [],
                "stages": [],
                "market_quality": {
                    "field_completeness": 0.0,
                    "field_completeness_target": 0.98,
                    "field_completeness_pass": False,
                    "missing": [],
                },
            }

        sync = MarketSyncProgress(
            self.analytics, as_of, now, scope or self.provider.provider_id, refresh_stage, on_progress,
        )
        market_snapshot: dict[str, Any] | None = None
        market_quality_report: dict[str, Any] = {
            "field_completeness": 0.0,
            "field_completeness_target": 0.98,
            "field_completeness_pass": False,
            "missing": [],
            "universe_coverage": validate_universe_coverage([]),
            "universe_metadata": validate_universe_metadata([]),
        }
        sync.start("market_snapshot", 1)
        market_reused = False
        try:
            receipt = sync.reuse("market_snapshot")
            if receipt and receipt.get("artifact"):
                market_snapshot = self.analytics.market_sync_artifact(receipt["artifact"], snapshot=True)
            if not market_snapshot and load_market and refresh_stage != "market_snapshot":
                market_snapshot = load_market(as_of)
            market_reused = bool(market_snapshot and market_snapshot.get("quality") == "verified")
            if not market_reused and not sync.should_fetch("market_snapshot"):
                market_snapshot = None
                sync.publish("market_snapshot", status="skipped", reason="outside_scope")
            else:
                if not market_reused:
                    market_snapshot = self._call_provider("market_snapshot", self.provider.get_market_snapshot, as_of)
                market_snapshot.setdefault("provider_version", provider_version)
                market_snapshot.setdefault("adapter_version", adapter_version)
                market_snapshot.setdefault("observed_at", observed_at)
                market_snapshot.setdefault("source", self.provider.provider_id)
                market_snapshot.setdefault("provider_id", self.provider.provider_id)
                market_snapshot.setdefault("quality", "partial")
                snapshot_id = str(market_snapshot.get("snapshot_id", f"market_{self.provider.provider_id}_{as_of}"))
                market_snapshot["snapshot_id"] = snapshot_id
                temporal = validate_temporal_metadata(
                    market_snapshot,
                    expected_as_of=as_of,
                )
                if not temporal["valid"]:
                    _apply_temporal_quality(market_snapshot, temporal)
                    failures.extend(
                        _temporal_failure("market_snapshot", None, error)
                        for error in temporal["errors"]
                    )
                market_quality_report = validate_snapshot(market_snapshot, "market")
                market_snapshot["field_completeness"] = market_quality_report["field_completeness"]
                if market_quality_report["missing"] and market_snapshot.get("quality") == "verified":
                    market_snapshot["quality"] = "unavailable"
                    failures.extend(
                        {
                            "kind": "market_snapshot",
                            "code": "FIELD_MISSING",
                            "field": field,
                            "message": f"required field is missing: {field}",
                        }
                        for field in market_quality_report["missing"]
                    )
                if not market_reused:
                    self.analytics.save_raw_payload(
                        payload_id=f"raw_market_{market_snapshot['provider_id']}_{as_of}",
                        provider_id=market_snapshot["provider_id"],
                        provider_version=market_snapshot["provider_version"],
                        adapter_version=market_snapshot["adapter_version"],
                        as_of=as_of,
                        observed_at=market_snapshot["observed_at"],
                        payload=market_snapshot,
                    )
                sync.publish("market_snapshot", status="validating")
        except Exception as error:
            failures.append(_failure("market_snapshot", None, error))
            market_snapshot = None
            sync.item_done("market_snapshot", "failed")
            sync.finish("market_snapshot")

        snapshot_id = str(
            (market_snapshot or {}).get(
                "snapshot_id",
                f"market_{self.provider.provider_id}_{as_of}",
            )
        )

        latest_verified_open = None
        calendar_method = getattr(self.provider, "get_trading_calendar", None)
        if calendar_method:
            sync.start("trading_calendar", 1)
            try:
                calendar_end = now.date().isoformat()
                receipt = sync.reuse("trading_calendar")
                cached = (self.analytics.market_sync_artifact(receipt["artifact"])
                          if receipt and receipt.get("artifact") else None)
                if not cached and not sync.should_fetch("trading_calendar"):
                    sync.publish("trading_calendar", status="skipped", reason="outside_scope")
                else:
                    calendar = (
                        cached["rows"] if cached else self._call_provider(
                            "trading_calendar", calendar_method, as_of, calendar_end,
                        )
                    )
                    calendar_rows = [
                        _calendar_row(
                            item,
                            snapshot_id=snapshot_id,
                            as_of=as_of,
                            observed_at=observed_at,
                            provider_id=self.provider.provider_id,
                            provider_version=provider_version,
                            adapter_version=adapter_version,
                        )
                        for item in calendar
                    ]
                    calendar_verified = bool(calendar_rows) and all(row["quality"] == "verified" for row in calendar_rows)
                    if cached:
                        sync.item_done("trading_calendar", "reused")
                    else:
                        artifact = self._save_raw_rows(
                            "calendar", calendar_rows, as_of, observed_at, receipt_scope=sync.scope,
                        )
                        if calendar_verified or ("trading_calendar", "") not in sync.receipts:
                            counts["trading_calendar"] = self.analytics.save_trading_calendar(calendar_rows)
                        if calendar_verified:
                            sync.save("trading_calendar", counts["trading_calendar"], artifact=artifact)
                            sync.item_done("trading_calendar", "fetched", counts["trading_calendar"])
                        else:
                            failures.append(_incomplete("trading_calendar"))
                            sync.item_done("trading_calendar", "failed", counts["trading_calendar"])
                    _append_row_temporal_failures(failures, "trading_calendar", calendar_rows)
                    qualities.extend(row["quality"] for row in calendar_rows)
                    latest_available_open = max(
                        (
                            row["trade_date"]
                            for row in calendar_rows
                            if row["is_open"] and row["quality"] == "verified"
                        ),
                        default=None,
                    )
                    latest_verified_open = latest_available_open
                    latest_open = max(
                        (
                            row["trade_date"]
                            for row in calendar_rows
                            if row["is_open"] and row["quality"] == "verified"
                            and row["trade_date"] <= as_of
                        ),
                        default=None,
                    )
                    if (
                        market_snapshot
                        and not market_reused
                        and market_snapshot.get("point_in_time_scope") == "latest"
                        and latest_available_open != as_of
                    ):
                        market_snapshot["quality"] = "unavailable"
                        market_snapshot.setdefault("quality_errors", []).append(
                            "POINT_IN_TIME_UNAVAILABLE"
                        )
                        failures.append({
                            "kind": "market_snapshot",
                            "code": "POINT_IN_TIME_UNAVAILABLE",
                            "message": (
                                "provider returned a latest-only market snapshot for "
                                f"{as_of}; latest available trading date is "
                                f"{latest_available_open}"
                            ),
                        })
                    if (
                        market_snapshot
                        and market_snapshot["quality"] == "partial"
                        and not market_snapshot.get("quality_errors")
                        and latest_open == as_of
                        and _market_snapshot_complete(market_snapshot)
                    ):
                        market_snapshot["quality"] = "verified"
            except Exception as error:
                failures.append(_failure("trading_calendar", None, error))
                sync.item_done("trading_calendar", "failed")
            if sync.stages["trading_calendar"]["status"] != "skipped":
                sync.finish("trading_calendar")
        else:
            sync.publish("trading_calendar", status="skipped")

        universe_method = getattr(self.provider, "get_universe", None)
        universe: list[dict[str, Any]] = []
        if universe_method:
            sync.start("universe", 1)
            try:
                receipt = sync.reuse("universe")
                cached = (self.analytics.market_sync_artifact(receipt["artifact"])
                          if receipt and receipt.get("artifact") else None)
                if not cached and not sync.should_fetch("universe"):
                    sync.publish("universe", status="skipped", reason="outside_scope")
                else:
                    universe = cached["rows"] if cached else list(self._call_provider("universe", universe_method))
                    universe_rows = [
                        _universe_row(
                            item,
                            snapshot_id=snapshot_id,
                            as_of=as_of,
                            observed_at=observed_at,
                            provider_id=self.provider.provider_id,
                            provider_version=provider_version,
                            adapter_version=adapter_version,
                        )
                        for item in universe
                    ]
                    coverage = validate_universe_coverage(universe_rows)
                    universe_verified = coverage["pass"] and all(row["quality"] == "verified" for row in universe_rows)
                    if not cached:
                        artifact = self._save_raw_rows(
                            "universe", universe_rows, as_of, observed_at, receipt_scope=sync.scope,
                        )
                        if universe_verified or ("universe", "") not in sync.receipts:
                            counts["universe"] = self.analytics.save_universe(universe_rows)
                    _append_row_temporal_failures(failures, "universe", universe_rows)
                    qualities.extend(row["quality"] for row in universe_rows)
                    market_quality_report["universe_coverage"] = coverage
                    market_quality_report["universe_metadata"] = (
                        validate_universe_metadata(universe_rows)
                    )
                    if market_snapshot and not market_quality_report["universe_metadata"]["pass"]:
                        market_snapshot.setdefault("quality_warnings", []).append(
                            "UNIVERSE_METADATA_INCOMPLETE"
                        )
                    if not coverage["pass"]:
                        if market_snapshot and not market_reused:
                            market_snapshot["quality"] = (
                                "unavailable"
                                if market_snapshot.get("quality") == "verified"
                                else "partial"
                            )
                            market_snapshot.setdefault("quality_errors", []).append(
                                "UNIVERSE_COVERAGE_MISSING"
                            )
                        failures.extend(
                            {
                                "kind": "universe",
                                "code": "UNIVERSE_COVERAGE_MISSING",
                                "field": board,
                                "message": f"required MVP universe category is missing: {board}",
                            }
                            for board in coverage["missing"]
                        )
                    if market_snapshot and universe and not market_reused:
                        _merge_universe_metadata(market_snapshot, universe)
                    if cached:
                        sync.item_done("universe", "reused")
                    elif universe_verified:
                        sync.save("universe", counts["universe"], artifact=artifact)
                        sync.item_done("universe", "fetched", counts["universe"])
                    else:
                        sync.item_done("universe", "failed", counts["universe"])
            except Exception as error:
                failures.append(_failure("universe", None, error))
                sync.item_done("universe", "failed")
            if sync.stages["universe"]["status"] != "skipped":
                sync.finish("universe")
        else:
            sync.publish("universe", status="skipped")

        if market_snapshot:
            if (
                not market_reused and market_snapshot.get("point_in_time_scope") == "latest"
                and market_snapshot["quality"] == "verified" and latest_verified_open != as_of
            ):
                market_snapshot["quality"] = "partial"
                failures.append(_incomplete("market_snapshot"))
            quality = str(market_snapshot["quality"])
            try:
                if market_reused and quality == "verified":
                    sync.item_done("market_snapshot", "reused")
                elif quality == "verified" or (
                    ("market_snapshot", "") not in sync.receipts
                    and (not load_market or not load_market(as_of))
                ):
                    self.analytics.save_snapshot(
                        snapshot_id=snapshot_id, kind="market", as_of=as_of,
                        observed_at=market_snapshot["observed_at"], source=market_snapshot["source"],
                        quality=quality, payload=market_snapshot,
                    )
                    if save_market:
                        save_market(market_snapshot)
                    counts["market_snapshot"] = 1
                if not market_reused and quality == "verified":
                    sync.save("market_snapshot", 1, artifact=snapshot_id)
                    sync.item_done("market_snapshot", "fetched", 1)
                elif quality != "verified":
                    if not any(failure["kind"] == "market_snapshot" for failure in failures):
                        failures.append(_incomplete("market_snapshot"))
                    sync.item_done("market_snapshot", "failed", counts["market_snapshot"])
                qualities.append(quality)
            except Exception as error:
                failures.append(_failure("market_snapshot", None, error))
                market_snapshot = None
                sync.item_done("market_snapshot", "failed")
            sync.finish("market_snapshot")

        requested_symbols = [str(symbol) for symbol in symbols if str(symbol).strip()]
        if not requested_symbols and include_default_symbols and universe:
            requested_symbols = [
                str(row["symbol"])
                for row in universe
                if row.get("symbol")
            ][:200]

        row_metadata = {
            "snapshot_id": snapshot_id, "as_of": as_of, "observed_at": observed_at,
            "provider_id": self.provider.provider_id, "provider_version": provider_version,
            "adapter_version": adapter_version,
        }
        source_rows: list[dict[str, Any]] = []
        local_bars = (
            self.analytics.verified_daily_symbols(as_of, self.provider.provider_id)
            if reuse_local_daily_bars and requested_symbols else set()
        )

        def fetch_stage(stage, method, fetch_rows, save_rows, count_key=None, *, accepts_empty=False):
            if not method or not requested_symbols:
                sync.publish(
                    stage, status="skipped",
                    reason="no_symbols" if not requested_symbols else "unsupported",
                )
                return
            if not sync.should_fetch(stage):
                reused = sum(bool(sync.reuse(stage, symbol)) or stage == "daily_bars" and symbol in local_bars
                             for symbol in requested_symbols)
                sync.publish(
                    stage, status="reused" if reused == len(requested_symbols) else "skipped",
                    reason="outside_scope", total=len(requested_symbols), reused=reused,
                )
                return
            sync.start(stage, len(requested_symbols))
            for symbol in requested_symbols:
                sync.publish(stage, symbol=symbol)
                try:
                    if receipt := sync.reuse(stage, symbol):
                        if accepts_empty and receipt.get("artifact"):
                            artifact = self.analytics.market_sync_artifact(receipt["artifact"])
                            if artifact is None:
                                receipt = None
                            else:
                                source_rows.extend(artifact["rows"])
                        if receipt:
                            sync.item_done(stage, "reused")
                            qualities.append("verified")
                            continue
                    has_local_bar = stage == "daily_bars" and symbol in local_bars
                    if has_local_bar and refresh_stage != stage:
                        sync.item_done(stage, "reused")
                        qualities.append("verified")
                        continue
                    rows = fetch_rows(method, symbol)
                    valid = (bool(rows) or accepts_empty) and all(row["quality"] == "verified" for row in rows)
                    count = 0
                    artifact_id = None
                    if rows:
                        artifact_id = self._save_raw_rows(
                            stage, rows, as_of, observed_at, symbol=symbol, receipt_scope=sync.scope,
                        )
                        if valid or not (has_local_bar or (stage, symbol) in sync.receipts):
                            count = save_rows(rows)
                            counts[count_key or stage] += count
                            if accepts_empty:
                                source_rows.extend(rows)
                    if valid:
                        sync.save(stage, count, symbol=symbol, artifact=artifact_id)
                        sync.item_done(stage, "fetched", count)
                        qualities.append("verified")
                    else:
                        qualities.extend(row["quality"] for row in rows)
                        errors = []
                        _append_row_temporal_failures(errors, stage, rows)
                        failures.extend(errors or [_incomplete(stage, symbol)])
                        sync.item_done(stage, "failed", count)
                except Exception as error:
                    failures.append(_failure(stage, symbol, error))
                    sync.item_done(stage, "failed")
            sync.finish(stage)

        def daily_bars(method, symbol):
            rows = self._call_provider("daily_bars", method, symbol, as_of, as_of)
            return [_bar_row(row, **row_metadata) for row in rows]

        def fundamentals(method, symbol):
            row = dict(self._call_provider(
                "fundamentals", _call_with_optional_as_of, method, symbol, as_of=as_of,
            ))
            defaults = row_metadata | {"snapshot_id": f"fundamentals_{self.provider.provider_id}_{symbol}_{as_of}",
                                       "symbol": symbol, "quality": "partial"}
            return [_apply_temporal_quality(
                defaults | row, validate_temporal_metadata(defaults | row, latest_allowed_as_of=as_of),
            )]

        fetch_stage("daily_bars", getattr(self.provider, "get_daily_bars", None),
                    daily_bars, self.analytics.save_daily_bars)
        fetch_stage("fundamentals", getattr(self.provider, "get_fundamentals", None),
                    fundamentals, self.analytics.save_fundamentals)

        for stage, capability, method_name in (("news", "news", "search_news"), ("filing", "filings", "search_filings")):
            def research_sources(method, symbol):
                items = self._call_provider(capability, _call_with_optional_as_of, method, symbol, as_of=as_of)
                return [_source_row(row, symbol=symbol, source_type=stage, **row_metadata) for row in items]

            fetch_stage(
                stage, getattr(self.provider, method_name, None), research_sources,
                self.analytics.save_research_sources, "research_sources", accepts_empty=True,
            )

        quality = _aggregate_quality(qualities, failures)
        return {
            "provider_id": (market_snapshot or {}).get("provider_id", self.provider.provider_id),
            "as_of": as_of,
            "quality": quality,
            "market_snapshot_quality": str(
                (market_snapshot or {}).get("quality", "unavailable")
            ),
            "market_snapshot_source": str(
                (market_snapshot or {}).get("source", self.provider.provider_id)
            ),
            "counts": counts,
            "failures": failures,
            "requested_symbols": requested_symbols,
            "stages": [sync.stages[stage] for stage in MARKET_SYNC_STAGES],
            "snapshot_id": snapshot_id,
            "market_snapshot": market_snapshot,
            "research_sources": source_rows,
            "market_quality": market_quality_report,
        }


def _incomplete(kind: str, symbol: str = "") -> dict[str, str]:
    result = {"kind": kind, "code": "DATA_QUALITY_INCOMPLETE", "message": "No verified data was returned."}
    if symbol:
        result["symbol"] = symbol
    return result


def _failure(kind: str, symbol: str | None, error: Exception) -> dict[str, str]:
    result = {
        "kind": kind,
        "code": getattr(error, "provider_reason", None) or type(error).__name__,
        "message": str(error),
    }
    if provider_id := getattr(error, "provider_id", None):
        result["provider_id"] = provider_id
    if symbol:
        result["symbol"] = symbol
    return result


def _call_with_optional_as_of(
    method: Any,
    *args: Any,
    as_of: str,
) -> Any:
    """Pass point-in-time context to adapters that support it."""

    try:
        return method(*args, as_of=as_of)
    except TypeError as error:
        if "as_of" not in str(error):
            raise
        return method(*args)


def _temporal_failure(
    kind: str,
    symbol: str | None,
    error: dict[str, str],
) -> dict[str, str]:
    result = {
        "kind": kind,
        "code": "TEMPORAL_METADATA_INVALID",
        "reason": error["code"],
        "message": error["message"],
    }
    if symbol:
        result["symbol"] = symbol
    return result


def _append_row_temporal_failures(
    failures: list[dict[str, str]],
    kind: str,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        for error in row.get("quality_errors", []):
            failures.append(
                _temporal_failure(kind, str(row.get("symbol") or "") or None, error)
            )


def _apply_temporal_quality(
    row: dict[str, Any],
    temporal: dict[str, Any],
) -> dict[str, Any]:
    row["quality_errors"] = list(temporal["errors"])
    if not temporal["valid"] and row.get("quality") == "verified":
        row["quality"] = "stale" if temporal["expired"] else "unavailable"
    return row


def _aggregate_quality(qualities: list[str], failures: list[dict[str, str]]) -> str:
    if not qualities and failures:
        return "unavailable"
    if failures or any(value == "unavailable" for value in qualities):
        return "partial" if qualities else "unavailable"
    if any(value in {"partial", "stale"} for value in qualities):
        return "partial"
    return "verified"


def _market_snapshot_complete(snapshot: dict[str, Any]) -> bool:
    return bool(
        snapshot.get("instruments")
        and snapshot.get("indices")
        and snapshot.get("sectors")
        and snapshot.get("breadth") is not None
        and snapshot.get("index_trend")
        and snapshot.get("volatility") is not None
    )


def _bar_row(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    as_of: str,
    observed_at: str,
    provider_id: str,
    provider_version: str,
    adapter_version: str,
) -> dict[str, Any]:
    normalized = dict(row)
    normalized["snapshot_id"] = snapshot_id
    normalized["as_of"] = normalized.get("as_of") or as_of
    normalized["observed_at"] = normalized.get("observed_at") or observed_at
    normalized["provider_id"] = normalized.get("provider_id", provider_id)
    normalized["provider_version"] = normalized.get("provider_version", provider_version)
    normalized["adapter_version"] = normalized.get("adapter_version", adapter_version)
    normalized.setdefault("quality", "partial")
    return _apply_temporal_quality(
        normalized,
        validate_temporal_metadata(normalized, expected_as_of=as_of),
    )


def _universe_row(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    as_of: str,
    observed_at: str,
    provider_id: str,
    provider_version: str,
    adapter_version: str,
) -> dict[str, Any]:
    symbol = str(row.get("symbol", "")).strip().upper()
    required_missing = not symbol
    normalized = {
        "snapshot_id": snapshot_id,
        "symbol": symbol,
        "name": row.get("name"),
        "asset_type": row.get("asset_type", "stock"),
        "board": row.get("board"),
        "exchange": row.get("exchange") or _exchange_from_symbol(symbol),
        "listed_at": row.get("listed_at"),
        "is_st": bool(row.get("is_st", False)),
        "is_delisting": bool(row.get("is_delisting", False)),
        "suspended": bool(row.get("suspended", False)),
        "active": bool(
            row.get(
                "active",
                not bool(row.get("suspended") or row.get("is_delisting")),
            )
        ),
        "listed_days": row.get("listed_days"),
        "provider_id": row.get("provider_id", provider_id),
        "provider_version": row.get("provider_version", provider_version),
        "adapter_version": row.get("adapter_version", adapter_version),
        "provenance": row.get("provenance", {}),
        "as_of": as_of,
        "observed_at": observed_at,
        "quality": "unavailable" if required_missing else "verified",
    }
    return _apply_temporal_quality(
        normalized,
        validate_temporal_metadata(normalized, expected_as_of=as_of),
    )


def _merge_universe_metadata(
    market_snapshot: dict[str, Any],
    universe: list[dict[str, Any]],
) -> None:
    """Fill market instruments with the authoritative universe metadata.

    Spot endpoints often omit listing age and delisting flags. The universe
    endpoint already fetched in the same sync is the least expensive source
    for those fields and keeps Rules behavior consistent across providers.
    """

    by_symbol = {
        str(row.get("symbol")): row
        for row in universe
        if row.get("symbol")
    }
    for instrument in market_snapshot.get("instruments", []):
        metadata = by_symbol.get(str(instrument.get("symbol")))
        if not metadata:
            continue
        for field in (
            "name",
            "asset_type",
            "board",
            "exchange",
            "listed_at",
            "is_st",
            "is_delisting",
            "active",
        ):
            if metadata.get(field) not in (None, ""):
                instrument[field] = metadata[field]
        listed_days = metadata.get("listed_days")
        if listed_days not in (None, "") and (
            instrument.get("listed_days") in (None, "")
            or int(instrument.get("listed_days") or 0) >= 9999
        ):
            instrument["listed_days"] = listed_days
        if metadata.get("suspended") is True:
            instrument["suspended"] = True


def _exchange_from_symbol(symbol: str) -> str:
    suffix = symbol.rsplit(".", 1)[-1].upper() if "." in symbol else ""
    return {
        "SH": "SSE",
        "SSE": "SSE",
        "SZ": "SZSE",
        "SZSE": "SZSE",
        "BJ": "BSE",
        "BSE": "BSE",
    }.get(suffix, "SZSE")


def _calendar_row(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    as_of: str,
    observed_at: str,
    provider_id: str,
    provider_version: str,
    adapter_version: str,
) -> dict[str, Any]:
    trade_date = str(row.get("trade_date") or row.get("date") or as_of)[:10].replace("/", "-")
    normalized = {
        "snapshot_id": snapshot_id,
        "trade_date": trade_date,
        "is_open": bool(row.get("is_open", row.get("is_trading", False))),
        "provider_id": row.get("provider_id", provider_id),
        "provider_version": row.get("provider_version", provider_version),
        "adapter_version": row.get("adapter_version", adapter_version),
        "provenance": row.get("provenance", {}),
        "as_of": as_of,
        "observed_at": observed_at,
        "quality": row.get("quality", "verified") if trade_date else "unavailable",
    }
    return _apply_temporal_quality(
        normalized,
        validate_temporal_metadata(normalized, expected_as_of=as_of),
    )


def _source_row(
    row: dict[str, Any],
    *,
    symbol: str,
    source_type: str,
    snapshot_id: str,
    as_of: str,
    observed_at: str,
    provider_id: str,
    provider_version: str,
    adapter_version: str,
) -> dict[str, Any]:
    external_id = str(row.get("id") or row.get("url") or row.get("title") or f"{source_type}-{symbol}")
    title = str(row.get("title") or "Untitled")
    excerpt = str(row.get("excerpt") or "")
    source_uri = row.get("source_uri") or row.get("source")
    published_at = row.get("published_at") or observed_at
    source_quality = row.get("quality")
    quality = (
        str(source_quality)
        if source_quality in {"verified", "partial", "stale", "unavailable"}
        else "verified"
        if title and source_uri and published_at and row.get("symbol_verified", True)
        else "partial"
    )
    content_hash = hashlib.sha256(
        json.dumps(
            {
                "symbol": symbol,
                "source_type": source_type,
                "external_id": external_id,
                "title": title,
                "published_at": published_at,
                "excerpt": excerpt,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    normalized = {
        "snapshot_id": snapshot_id,
        "symbol": symbol,
        "source_type": source_type,
        "external_id": external_id,
        "title": title,
        "published_at": published_at,
        "source_uri": source_uri,
        "excerpt": excerpt,
        "content_hash": content_hash,
        "provider_id": row.get("provider_id", provider_id),
        "provider_version": row.get("provider_version", provider_version),
        "adapter_version": row.get("adapter_version", adapter_version),
        "provenance": row.get("provenance", {}),
        "as_of": as_of,
        "observed_at": observed_at,
        "quality": quality,
    }
    return _apply_temporal_quality(
        normalized,
        validate_temporal_metadata(
            normalized,
            expected_as_of=as_of,
            latest_allowed_as_of=as_of,
            published_field="published_at",
        ),
    )
