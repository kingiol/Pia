import importlib.util
import tempfile
import unittest
from datetime import date
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
            today=date(2026, 11, 6),
        )
        self.assertEqual(dates, ["2026-11-03", "2026-11-04", "2026-11-06"])
        self.assertEqual(source, "provider_calendar")

    def test_resolve_freshness_dates_requires_enough_open_dates(self):
        class Provider:
            def get_trading_calendar(self, start_date, end_date):
                return [{"trade_date": "2026-11-06", "is_open": True}]

        with self.assertRaises(ValueError):
            MODULE.resolve_freshness_dates(
                Provider(),
                [],
                2,
                today=date(2026, 11, 6),
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
