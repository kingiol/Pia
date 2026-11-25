import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path
from inspect import signature

from pia_runtime.adapters import ProviderHealth
from pia_runtime.analytics import AnalyticsStore
from pia_runtime.data_worker import DataWorker
from pia_runtime.normalization import normalize_daily_bar
from pia_runtime.observability import RuntimeObservability


class _Provider:
    provider_id = "mock"

    def health(self):
        return ProviderHealth(
            provider_id=self.provider_id,
            status="healthy",
            capabilities=[
                "daily_bars",
                "market_breadth",
                "trading_calendar",
                "fundamentals",
                "news",
                "filings",
                "universe",
            ],
            supports_replay=True,
            requires_credentials=False,
            provider_version="mock-1",
            adapter_version="mock-adapter-1",
        )

    def get_market_snapshot(self, as_of):
        return {
            "snapshot_id": "mock-market-2026-11-06",
            "as_of": as_of,
            "observed_at": f"{as_of}T16:00:00+08:00",
            "source": self.provider_id,
            "quality": "verified",
            "breadth": 0.6,
            "index_trend": "up",
            "volatility": 0.2,
            "indices": [],
            "sectors": [],
            "instruments": [{
                "symbol": "600000.SH",
                "name": "spot-name",
                "asset_type": "stock",
                "board": "main",
                "is_st": False,
                "suspended": False,
                "listed_days": 9999,
                "close": 10.5,
                "change_pct": 0.2,
                "average_turnover": 10000,
            }],
        }

    def get_trading_calendar(self, start_date, end_date):
        return [{"trade_date": start_date, "is_open": True}]

    def get_universe(self):
        return [{
            "symbol": "600000.SH",
            "name": "Pudong Development Bank",
            "asset_type": "stock",
            "board": "main",
            "is_st": False,
            "suspended": False,
            "listed_days": 6000,
        }, {
            "symbol": "300001.SZ",
            "name": "Chinext fixture",
            "asset_type": "stock",
            "board": "chinext",
            "is_st": False,
            "suspended": False,
            "listed_days": 6000,
        }, {
            "symbol": "688001.SH",
            "name": "STAR fixture",
            "asset_type": "stock",
            "board": "star",
            "is_st": False,
            "suspended": False,
            "listed_days": 6000,
        }, {
            "symbol": "830001.BJ",
            "name": "BSE fixture",
            "asset_type": "stock",
            "board": "bse",
            "is_st": False,
            "suspended": False,
            "listed_days": 6000,
        }, {
            "symbol": "510300.SH",
            "name": "ETF fixture",
            "asset_type": "etf",
            "board": "etf",
            "is_st": False,
            "suspended": False,
            "listed_days": 6000,
        }]

    def get_daily_bars(self, symbol, start_date, end_date):
        return [normalize_daily_bar(
            {
                "symbol": symbol,
                "trade_date": start_date,
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
                "amount": 10000,
            },
            provider_id=self.provider_id,
            provider_version="mock-1",
            adapter_version="mock-adapter-1",
            observed_at=f"{start_date}T16:00:00+08:00",
        )]

    def get_fundamentals(self, symbol):
        return {
            "symbol": symbol,
            "as_of": "2026-09-30",
            "observed_at": "2026-11-06T16:00:00+08:00",
            "quality": "verified",
            "metrics": {"roe": 0.12},
        }

    def search_news(self, symbol):
        return [{
            "id": "news-1",
            "title": "Quarterly update",
            "published_at": "2026-11-06T10:00:00+08:00",
            "source": "https://example.test/news-1",
            "excerpt": "A short excerpt.",
        }]

    def search_filings(self, symbol, as_of):
        return [{
            "id": "filing-1",
            "title": "Filing",
            "published_at": f"{as_of}T09:00:00+08:00",
            "source": "https://example.test/filing-1",
            "excerpt": "A filing excerpt.",
        }]


class DataWorkerTest(unittest.TestCase):
    def test_market_only_sync_reports_progress_and_keeps_universe_when_snapshot_fails(self):
        provider = _Provider()
        provider.get_market_snapshot = Mock(side_effect=ConnectionError("upstream unavailable"))
        provider.get_daily_bars = Mock(wraps=provider.get_daily_bars)
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-06", [], include_default_symbols=False, on_progress=progress.append,
            )

        provider.get_daily_bars.assert_not_called()
        self.assertEqual(result["requested_symbols"], [])
        self.assertEqual(result["quality"], "partial")
        self.assertEqual(result["counts"]["market_snapshot"], 0)
        self.assertEqual(result["counts"]["universe"], 5)
        self.assertEqual([failure["kind"] for failure in result["failures"]], ["market_snapshot"])
        self.assertEqual([update["stage"] for update in progress if update["status"] == "running" and not update["fetched"] and not update["failed"]], [
            "market_snapshot", "trading_calendar", "universe",
        ])
        self.assertEqual([step["status"] for step in result["stages"]], [
            "failed", "done", "done", "skipped", "skipped", "skipped", "skipped",
        ])

    def test_sync_reports_the_symbol_it_is_requesting(self):
        provider = _Provider()
        progress = []

        def call_provider(capability, method_name, *args, **kwargs):
            method = getattr(provider, method_name)
            if "as_of" not in signature(method).parameters:
                kwargs.pop("as_of", None)
            return provider, method(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store, call_provider=call_provider).sync_market_data(
                "2026-11-06", ["600000.SH", "300001.SZ"], on_progress=progress.append,
            )
        self.assertFalse(result["failures"])
        self.assertTrue(any(row["source_type"] == "filing" for row in result["research_sources"]))
        daily = [update for update in progress if update["stage"] == "daily_bars"]
        self.assertEqual([(step.get("symbol"), step["fetched"]) for step in daily], [
            (None, 0), ("600000.SH", 0), ("600000.SH", 1), ("300001.SZ", 1), ("300001.SZ", 2), (None, 2),
        ])
        self.assertEqual(daily[-1]["status"], "done")

    def test_resume_after_restart_only_fetches_missing_symbols_and_can_refresh_one_stage(self):
        provider = _Provider()
        get_bars = provider.get_daily_bars
        symbols = ["600000.SH", "300001.SZ"]
        provider.get_daily_bars = Mock(side_effect=[
            get_bars(symbols[0], "2026-11-06", "2026-11-06"), ConnectionError(),
        ])
        provider.get_market_snapshot = Mock(wraps=provider.get_market_snapshot)
        provider.search_filings = Mock(return_value=[])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analytics.duckdb"
            first = DataWorker(provider, AnalyticsStore(path)).sync_market_data("2026-11-06", symbols)
            self.assertEqual(first["stages"][3]["status"], "partial")
            provider.get_daily_bars = Mock(wraps=get_bars)
            worker = DataWorker(provider, AnalyticsStore(path))
            resumed = worker.sync_market_data("2026-11-06", symbols)
            provider.get_daily_bars.assert_called_once_with(symbols[1], "2026-11-06", "2026-11-06")
            self.assertEqual(resumed["stages"][3] | {}, {
                "stage": "daily_bars", "status": "done", "total": 2,
                "fetched": 1, "reused": 1, "failed": 0, "saved_rows": 1, "symbol": None,
            })
            self.assertEqual(resumed["stages"][6]["status"], "reused")
            self.assertEqual(provider.search_filings.call_count, 2)

            refresh = worker.sync_market_data("2026-11-06", symbols, refresh_stage="filing")
            self.assertEqual(refresh["stages"][6]["status"], "done")
            self.assertEqual(refresh["stages"][3]["status"], "reused")
            self.assertEqual(refresh["counts"]["market_snapshot"], 0)
            self.assertEqual(provider.search_filings.call_count, 4)
            self.assertEqual(provider.get_market_snapshot.call_count, 1)

    def test_raw_batches_preserve_actual_mixed_provider_attribution(self):
        analytics = Mock()
        worker = DataWorker(_Provider(), analytics)
        rows = [
            {"provider_id": "primary", "provider_version": "v1", "adapter_version": "a1", "provenance": {"fallback_used": False}},
            {"provider_id": "secondary", "provider_version": "v2", "adapter_version": "a2", "provenance": {"fallback_used": True}},
        ]
        worker._save_raw_rows("daily_bars", rows, "2026-11-05", "2026-11-05T16:00:00+08:00")
        saved = analytics.save_raw_payload.call_args.kwargs
        self.assertEqual(saved["provider_id"], "mixed")
        self.assertEqual(saved["provider_version"], "mixed")
        self.assertEqual(saved["payload"]["rows"], rows)

    def test_future_as_of_is_unavailable_before_provider_calls(self):
        provider = _Provider()
        calls = {"snapshot": 0}
        original = provider.get_market_snapshot

        def get_market_snapshot(as_of):
            calls["snapshot"] += 1
            return original(as_of)

        provider.get_market_snapshot = get_market_snapshot
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2099-01-01",
                ["600000.SH"],
            )

            self.assertEqual(result["quality"], "unavailable")
            self.assertEqual(result["market_snapshot_quality"], "unavailable")
            self.assertEqual(calls["snapshot"], 0)
            self.assertTrue(any(
                failure.get("reason") == "AS_OF_IN_FUTURE"
                for failure in result["failures"]
            ))

    def test_invalid_market_time_metadata_is_downgraded_and_recorded(self):
        provider = _Provider()
        original = provider.get_market_snapshot

        def get_market_snapshot(as_of):
            snapshot = original(as_of)
            snapshot["observed_at"] = f"{as_of.replace('-', '/')[:4]}-01-01T00:00:00+00:00"
            return snapshot

        provider.get_market_snapshot = get_market_snapshot
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-06",
                ["600000.SH"],
            )

            self.assertEqual(result["market_snapshot_quality"], "unavailable")
            self.assertTrue(any(
                failure.get("reason") == "OBSERVED_AT_BEFORE_AS_OF"
                for failure in result["failures"]
            ))

    def test_future_news_publication_is_not_verified(self):
        provider = _Provider()

        def search_news(symbol):
            return [{
                "id": "future-news",
                "title": "Future update",
                "published_at": "2099-01-01T00:00:00+00:00",
                "source": "https://example.test/future-news",
                "excerpt": "Should be rejected.",
            }]

        provider.search_news = search_news
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-06",
                ["600000.SH"],
            )

            future_source = next(
                source for source in result["research_sources"]
                if source["external_id"] == "future-news"
            )
            self.assertEqual(future_source["quality"], "unavailable")
            self.assertTrue(any(
                failure.get("reason") == "PUBLISHED_AT_IN_FUTURE"
                for failure in result["failures"]
            ))

    def test_latest_only_market_snapshot_is_not_reused_for_older_dates(self):
        provider = _Provider()
        original_snapshot = provider.get_market_snapshot

        def get_market_snapshot(as_of):
            snapshot = original_snapshot(as_of)
            snapshot["point_in_time_scope"] = "latest"
            snapshot["indices"] = [{
                "symbol": "000001.SH",
                "close": 3000,
                "change_pct": 0.5,
            }]
            snapshot["sectors"] = [{
                "name": "Bank",
                "change_pct": 0.5,
                "breadth": 0.6,
            }]
            return snapshot

        provider.get_market_snapshot = get_market_snapshot
        provider.get_trading_calendar = lambda start_date, end_date: [
            {"trade_date": "2026-11-04", "is_open": True},
            {"trade_date": "2026-11-06", "is_open": True},
        ]
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-04",
                ["600000.SH"],
            )

            self.assertEqual(result["market_snapshot_quality"], "unavailable")
            self.assertTrue(any(
                failure.get("code") == "POINT_IN_TIME_UNAVAILABLE"
                for failure in result["failures"]
            ))

    def test_latest_trading_day_promotes_complete_partial_snapshot(self):
        provider = _Provider()
        original = provider.get_market_snapshot

        def get_market_snapshot(as_of):
            snapshot = original(as_of)
            snapshot.update({
                "quality": "partial",
                "indices": [{"symbol": "000001.SH", "close": 3000, "change_pct": 0.5}],
                "sectors": [{"name": "Bank", "change_pct": 0.5, "breadth": 0.6}],
                "volatility": 0.2,
                "instruments": [{
                    "symbol": "600000.SH",
                    "name": "Pudong Development Bank",
                    "asset_type": "stock",
                    "board": "main",
                    "is_st": False,
                    "suspended": False,
                    "listed_days": 6000,
                    "close": 10,
                    "change_pct": 0.5,
                    "average_turnover": 100000000,
                }],
            })
            return snapshot

        provider.get_market_snapshot = get_market_snapshot
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-06",
                ["600000.SH"],
            )

            self.assertEqual(result["quality"], "verified")

    def test_full_market_sync_persists_raw_and_normalized_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(_Provider(), store).sync_market_data(
                "2026-11-06",
                ["600000.SH"],
            )

            self.assertEqual(result["quality"], "verified")
            self.assertEqual(result["market_snapshot"]["snapshot_id"], "mock-market-2026-11-06")
            self.assertEqual(result["market_snapshot"]["provider_id"], "mock")
            self.assertEqual(result["counts"]["market_snapshot"], 1)
            self.assertEqual(result["counts"]["trading_calendar"], 1)
            self.assertEqual(result["counts"]["universe"], 5)
            self.assertEqual(result["counts"]["daily_bars"], 1)
            self.assertEqual(result["counts"]["fundamentals"], 1)
            self.assertEqual(result["counts"]["research_sources"], 2)
            self.assertEqual(result["market_quality"]["field_completeness"], 1.0)
            self.assertTrue(result["market_quality"]["field_completeness_pass"])
            self.assertTrue(result["market_quality"]["universe_coverage"]["pass"])
            instrument = result["market_snapshot"]["instruments"][0]
            self.assertEqual(instrument["name"], "Pudong Development Bank")
            self.assertEqual(instrument["listed_days"], 6000)
            self.assertGreaterEqual(store.count("raw_provider_payloads"), 6)
            self.assertEqual(store.count("normalized_universe"), 5)
            self.assertEqual(store.count("normalized_fundamentals"), 1)
            self.assertEqual(store.count("normalized_research_sources"), 2)
            self.assertEqual(store.count("normalized_trading_calendar"), 1)

    def test_market_sync_records_capability_provider_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            observability = RuntimeObservability()
            result = DataWorker(
                _Provider(),
                store,
                observability,
            ).sync_market_data("2026-11-06", ["600000.SH"])

            self.assertEqual(result["quality"], "verified")
            calls = observability.snapshot()["provider_calls"]
            self.assertEqual(
                calls["mock:market_snapshot:get_market_snapshot"]["call_count"],
                1,
            )
            self.assertEqual(
                calls["mock:trading_calendar:get_trading_calendar"]["call_count"],
                1,
            )
            self.assertEqual(
                calls["mock:daily_bars:get_daily_bars"]["call_count"],
                1,
            )
            self.assertEqual(
                calls["mock:fundamentals:_call_with_optional_as_of"]["call_count"],
                1,
            )
            self.assertEqual(
                calls["mock:news:_call_with_optional_as_of"]["call_count"],
                1,
            )

    def test_historical_trading_day_ignores_later_calendar_rows(self):
        provider = _Provider()
        original_snapshot = provider.get_market_snapshot

        def get_market_snapshot(as_of):
            snapshot = original_snapshot(as_of)
            snapshot["quality"] = "partial"
            snapshot["indices"] = [{"symbol": "000001.SH", "close": 3000, "change_pct": 0.5}]
            snapshot["sectors"] = [{"symbol": "bank", "name": "Bank", "change_pct": 0.2}]
            snapshot["volatility"] = 0.2
            return snapshot

        provider.get_market_snapshot = get_market_snapshot
        provider.get_trading_calendar = lambda start_date, end_date: [
            {"trade_date": start_date, "is_open": True},
            {"trade_date": "2026-11-06", "is_open": True},
        ]
        provider.search_news = lambda symbol: [{
            "id": "news-1",
            "title": "Historical update",
            "published_at": "2026-11-04T10:00:00+08:00",
            "source": "https://example.test/news-1",
            "excerpt": "A historical excerpt.",
        }]
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-04",
                ["600000.SH"],
            )

            self.assertEqual(result["market_snapshot_quality"], "verified")
            self.assertEqual(result["quality"], "verified")

    def test_sync_reports_partial_when_one_symbol_fails(self):
        provider = _Provider()
        original = provider.get_daily_bars

        def get_daily_bars(symbol, start_date, end_date):
            if symbol == "BAD.SZ":
                raise RuntimeError("upstream timeout")
            return original(symbol, start_date, end_date)

        provider.get_daily_bars = get_daily_bars
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-06",
                ["600000.SH", "BAD.SZ"],
            )

            self.assertEqual(result["quality"], "partial")
            self.assertTrue(any(item.get("symbol") == "BAD.SZ" for item in result["failures"]))

    def test_missing_universe_category_degrades_market_quality(self):
        provider = _Provider()
        provider.get_universe = lambda: [{
            "symbol": "600000.SH",
            "name": "Pudong Development Bank",
            "asset_type": "stock",
            "board": "main",
            "is_st": False,
            "suspended": False,
            "listed_days": 6000,
        }]
        with tempfile.TemporaryDirectory() as directory:
            store = AnalyticsStore(Path(directory) / "analytics.duckdb")
            result = DataWorker(provider, store).sync_market_data(
                "2026-11-06",
                ["600000.SH"],
            )

            self.assertEqual(result["market_snapshot_quality"], "unavailable")
            self.assertFalse(result["market_quality"]["universe_coverage"]["pass"])
            self.assertIn("chinext", result["market_quality"]["universe_coverage"]["missing"])
            self.assertTrue(any(
                failure.get("code") == "UNIVERSE_COVERAGE_MISSING"
                for failure in result["failures"]
            ))


if __name__ == "__main__":
    unittest.main()
