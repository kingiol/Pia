import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pia_provider_freshness",
    ROOT / "scripts" / "provider_freshness.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ProviderFreshnessTest(unittest.TestCase):
    def test_tushare_provider_accepts_native_credential_manager(self):
        with patch.object(MODULE, "configured_secret", return_value="native-token") as configured:
            with patch.object(MODULE, "TushareMarketProvider") as provider:
                MODULE._provider("tushare")

        configured.assert_called_once_with("TUSHARE_TOKEN")
        provider.assert_called_once_with("native-token")

    def test_resolve_freshness_dates_uses_provider_calendar(self):
        class Provider:
            def get_trading_calendar(self, start_date, end_date):
                return [
                    {"trade_date": "2026-11-02", "is_open": True},
                    {"trade_date": "2026-11-03", "is_open": True},
                    {"trade_date": "2026-11-04", "is_open": True},
                    {"trade_date": "2026-11-05", "is_open": False},
                    {"trade_date": "2026-11-06", "is_open": True},
                ]

        dates, source = MODULE.resolve_freshness_dates(
            Provider(),
            [],
            3,
            now=datetime(2026, 11, 6, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(dates, ["2026-11-03", "2026-11-04", "2026-11-06"])
        self.assertEqual(source, "provider_calendar")

    def test_lookback_excludes_today_until_shanghai_market_close(self):
        class Provider:
            def get_trading_calendar(self, start_date, end_date):
                return [
                    {"trade_date": "2026-11-18", "is_open": True},
                    {"trade_date": "2026-11-19", "is_open": True},
                ]

        cases = {
            "2026-11-18T18:15:00+00:00": "2026-11-18",
            "2026-11-19T07:04:59+00:00": "2026-11-18",
            "2026-11-19T07:05:00+00:00": "2026-11-19",
        }
        with patch.dict(MODULE.os.environ, {"PIA_MARKET_CLOSE_TIME": "15:05"}):
            for timestamp, expected in cases.items():
                with self.subTest(timestamp=timestamp):
                    dates, _ = MODULE.resolve_freshness_dates(
                        Provider(), [], 1, now=datetime.fromisoformat(timestamp),
                    )
                    self.assertEqual(dates, [expected])

    def test_resolve_freshness_dates_requires_enough_open_dates(self):
        class Provider:
            def get_trading_calendar(self, start_date, end_date):
                return [{"trade_date": "2026-11-06", "is_open": True}]

        with self.assertRaises(ValueError):
            MODULE.resolve_freshness_dates(
                Provider(),
                [],
                2,
                now=datetime(2026, 11, 6, 9, tzinfo=timezone.utc),
            )

    def test_run_freshness_passes_only_verified_dates(self):
        class Provider:
            provider_id = "test-provider"

        class Worker:
            def __init__(self, provider, store):
                self.provider = provider

            def sync_market_data(self, as_of, symbols):
                return {
                    "provider_id": "test-provider",
                    "quality": "verified",
                    "market_snapshot_quality": "verified",
                    "market_quality": {"field_completeness": 1.0},
                    "counts": {"market_snapshot": 1},
                    "failures": [],
                }

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODULE, "DataWorker", Worker):
                report = MODULE.run_freshness(
                    Provider(),
                    ["2026-11-05", "2026-11-06"],
                    ["600000.SH"],
                    Path(directory) / "freshness.duckdb",
                )
        self.assertTrue(report["passed"])
        self.assertEqual(report["failed_dates"], [])

    def test_run_freshness_reports_degraded_dates(self):
        class Provider:
            provider_id = "test-provider"

        class Worker:
            def __init__(self, provider, store):
                self.provider = provider

            def sync_market_data(self, as_of, symbols):
                return {
                    "provider_id": "test-provider",
                    "quality": "partial" if as_of == "2026-11-06" else "verified",
                    "market_snapshot_quality": "partial" if as_of == "2026-11-06" else "verified",
                    "market_quality": {"field_completeness": 0.5},
                    "counts": {"market_snapshot": 1},
                    "failures": [],
                }

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODULE, "DataWorker", Worker):
                report = MODULE.run_freshness(
                    Provider(),
                    ["2026-11-05", "2026-11-06"],
                    ["600000.SH"],
                    Path(directory) / "freshness.duckdb",
                )
        self.assertFalse(report["passed"])
        self.assertEqual(report["failed_dates"], ["2026-11-06"])

    def test_run_freshness_stops_after_provider_rate_limit(self):
        provider = type("Provider", (), {"provider_id": "akshare"})()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODULE, "DataWorker") as worker:
                sync = worker.return_value.sync_market_data
                sync.return_value = {
                    "quality": "partial",
                    "failures": [{"code": "Push2RateLimitError"}],
                }
                report = MODULE.run_freshness(
                    provider,
                    ["2026-11-05", "2026-11-06"],
                    ["600000.SH"],
                    Path(directory) / "freshness.duckdb",
                )
        sync.assert_called_once_with("2026-11-05", ["600000.SH"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["failed_dates"], ["2026-11-05"])
        self.assertEqual(report["unchecked_dates"], ["2026-11-06"])
