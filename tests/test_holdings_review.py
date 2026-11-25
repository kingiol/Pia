import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pia_runtime import holdings_review
from pia_runtime.adapters import FixtureMarketProvider, ProviderHealth, ProviderRegistry
from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime
from scripts import holdings_freshness


AS_OF = "2026-11-05"
STOCK = "600000.SH"
ETF = "510300.SH"


class HoldingsReviewTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.runtime = PiaRuntime(Settings(
            db_path=root / "pia.sqlite3", analytics_db_path=root / "pia.duckdb",
            autostart_tasks=False, require_llm=True,
        ))
        self.addCleanup(self.runtime.close)
        self.rows = [
            {"symbol": STOCK, "quantity": 10, "avg_cost": 10, "market_value": 5, "sector": "Banking"},
            {"symbol": ETF, "quantity": 50, "avg_cost": 3, "market_value": 5},
        ]
        self.prices = {STOCK: 20, ETF: 5}
        self.snapshot = self.runtime.import_portfolio("manual", self.rows, as_of="2026-11-04")

    def provider_call(self, capability, method_name, *args, **kwargs):
        if capability == "trading_calendar":
            return self.runtime.fixture_provider, [{"trade_date": AS_OF, "is_open": True}]
        if capability != "daily_bars":
            raise AssertionError(f"Unexpected capability: {capability}")
        symbol = args[0]
        return self.runtime.fixture_provider, [
            {"symbol": symbol, "close": self.prices[symbol], "quality": "verified",
             "trade_date": AS_OF, "observed_at": f"{AS_OF}T16:00:00+08:00", "provider_id": "fixture"},
        ] if symbol in self.prices else []

    def start(self, *, cash=None, **kwargs):
        return self.runtime.start_holdings_review(
            cash=cash, as_of=AS_OF, expected_session=AS_OF, expected_snapshot_id=self.snapshot["snapshot_id"],
            **kwargs,
        )

    def finish(self, task):
        with patch.object(self.runtime, "_provider_call", side_effect=self.provider_call):
            self.runtime.run_task(task.id)
            self.runtime.wait_for_task(task.id)
        detail = self.runtime.task_detail(task.id)
        self.assertIsNone(detail["task"]["error"], detail["task"])
        return detail["holdings_review"]

    def test_reprices_positions_and_replays_frozen_inputs_without_providers(self):
        baseline = self.finish(self.start(cash=2000))
        self.assertEqual(baseline["result"]["calculation"], "clear")
        self.assertEqual(baseline["result"]["nav"], 2450)
        with self.assertRaisesRegex(ValueError, "HOLDINGS_INPUT_CONFIRMATION_REQUIRED"):
            holdings_review.confirm(self.runtime, baseline["task_id"], "default", unchanged=False)
        self.assertTrue(holdings_review.confirm(self.runtime, baseline["task_id"], "default", unchanged=True)["confirmed_at"])
        self.prices[STOCK] = 200
        self.snapshot = self.runtime.import_portfolio("manual", self.rows, as_of=AS_OF)
        reviewed = self.finish(self.start(cash=100))
        self.assertEqual(reviewed["result"]["calculation"], "breach")
        self.assertEqual([check["status"] for check in reviewed["result"]["checks"]], ["breach", "clear", "breach"])
        self.assertEqual(self.start(cash=100).id, reviewed["task_id"])
        replay = self.runtime.replay_task(baseline["task_id"])
        with patch.object(self.runtime, "_provider_call", side_effect=AssertionError("Offline replay used network")):
            self.runtime.run_task(replay.id)
            self.runtime.wait_for_task(replay.id)
        replayed = self.runtime.task_detail(replay.id)
        self.assertEqual(replayed["holdings_review"]["result"], baseline["result"])
        self.assertTrue(replayed["holdings_review"]["replay"])
        self.assertTrue(replayed["evidence"])

    def test_reports_missing_cash_missing_close_and_missing_sector(self):
        no_cash = self.finish(self.start())
        self.assertIn("CASH_REQUIRED", no_cash["result"]["issues"])
        self.assertIsNone(no_cash["result"]["nav"])
        etf_price = self.prices.pop(ETF)
        missing_close = self.finish(self.start(cash=0))
        self.assertEqual(missing_close["result"]["covered"], 1)
        self.assertIn("CLOSES_UNAVAILABLE", missing_close["result"]["issues"])
        self.assertEqual([check["status"] for check in missing_close["result"]["checks"]], ["unavailable"] * 3)
        self.prices[ETF] = etf_price
        missing_close_retry = self.finish(self.start())
        self.assertNotEqual(missing_close_retry["task_id"], missing_close["task_id"])
        self.assertEqual(missing_close_retry["result"]["cash"], 0)
        self.rows[0].pop("sector")
        self.snapshot = self.runtime.import_portfolio("manual", self.rows, as_of=AS_OF)
        missing_sector = self.finish(self.start(cash=0))
        self.assertEqual([check["status"] for check in missing_sector["result"]["checks"]], ["breach", "breach", "unavailable"])
        self.assertIn("SECTOR_UNAVAILABLE", missing_sector["result"]["issues"])
        self.assertIsNone(self.runtime.task_detail(missing_sector["task_id"], "other"))
        with self.assertRaises(KeyError):
            holdings_review.confirm(self.runtime, missing_sector["task_id"], "other", unchanged=True)

    def test_scheduler_and_manual_creation_share_one_attempt(self):
        scheduled_time = datetime.fromisoformat(f"{AS_OF}T15:10:00").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        self.runtime.scheduler.dispatch_if_due(scheduled_time)
        with ThreadPoolExecutor(max_workers=4) as workers:
            ids = set(workers.map(lambda _: self.start().id, range(8)))
        self.assertEqual(len(ids), 1)
        record = holdings_review.summary(self.runtime, "default")["attempt"]
        self.assertEqual(ids, {record["task_id"]})
        self.assertEqual(self.runtime.db.fetchone("SELECT COUNT(*) AS total FROM holdings_review_attempts")["total"], 1)

    def test_rejects_wrong_date_adjusted_and_suspended_prices(self):
        bar = {"symbol": STOCK, "trade_date": AS_OF, "observed_at": f"{AS_OF}T16:00:00+08:00",
               "quality": "verified", "close": 11.0}
        for changes in (
            {"trade_date": "2026-11-04"}, {"adjustment": "qfq"},
            {"suspended": True}, {"symbol": ETF}, {"quality": "stale"},
        ):
            self.assertIsNone(holdings_review._close_bar([{**bar, **changes}], STOCK, AS_OF))
        self.assertEqual(holdings_review._close_bar([bar], STOCK, AS_OF), bar)

    def test_missing_primary_symbol_uses_routed_fallback(self):
        class DataSource(FixtureMarketProvider):
            def __init__(self, fixtures, provider_id, available):
                super().__init__(fixtures)
                self.provider_id = provider_id
                self.available = available

            def health(self):
                return ProviderHealth(self.provider_id, "healthy", ["trading_calendar", "daily_bars"], True, False)

            def get_daily_bars(self, symbol, start_date, end_date):
                return super().get_daily_bars(symbol, start_date, end_date) if self.available else []

        self.runtime.settings.data_provider = "primary"
        fixtures = self.runtime.settings.fixture_dir
        self.runtime.providers = ProviderRegistry(
            [DataSource(fixtures, "primary", False), DataSource(fixtures, "secondary", True)],
            retry_attempts=1, retry_backoff_seconds=0,
        )
        calendar, bars = holdings_review.session_inputs(self.runtime, AS_OF, [STOCK])
        self.assertTrue(calendar["is_open"])
        self.assertEqual(bars[STOCK]["provider_id"], "secondary")
        self.assertEqual([attempt["provider_id"] for attempt in bars[STOCK]["provenance"]["attempts"]],
                         ["primary", "secondary"])
        self.assertTrue(self.runtime.analytics.verified_trading_days(AS_OF, AS_OF)[AS_OF])

    def test_five_session_gate_rejects_missing_or_late_observation(self):
        monday = date(2026, 11, 16)
        days = [(monday + timedelta(days=offset)).isoformat() for offset in range(5)]
        calendar = [{"trade_date": day, "is_open": True, "quality": "verified"} for day in days]
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            self.runtime, "_provider_call", return_value=(self.runtime.fixture_provider, calendar),
        ), redirect_stdout(io.StringIO()):
            report_dir = Path(temporary)
            for day in days:
                report = {
                    "as_of": day, "status": "passed",
                    "coverage": {
                        symbol: {"as_of": day, "provider_id": "primary", "close": 10,
                                 "observed_at": f"{day}T17:55:00+08:00"}
                        for symbol in holdings_freshness.SYMBOLS
                    },
                }
                entry = report_dir / f"{day}-175500.json"
                entry.write_text(json.dumps(report))
            through = date.fromisoformat(days[-1])
            self.assertTrue(holdings_freshness.verify(self.runtime, report_dir, through))
            symbol = holdings_freshness.SYMBOLS[0]
            report["coverage"][symbol]["observed_at"] = f"{days[-1]}T18:00:01+08:00"
            entry.write_text(json.dumps(report))
            self.assertFalse(holdings_freshness.verify(self.runtime, report_dir, through))
            entry.unlink()
            self.assertFalse(holdings_freshness.verify(self.runtime, report_dir, through))
