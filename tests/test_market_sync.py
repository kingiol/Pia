import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pia_runtime.analytics import AnalyticsStore
from pia_runtime.market_sync import MarketSyncProgress, MarketSyncRuns


class MarketSyncTest(unittest.TestCase):
    def test_receipts_expire_by_stage_and_remain_user_scoped(self):
        as_of = "2026-11-24"
        now = datetime(2026, 11, 24, 7, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            analytics = AnalyticsStore(Path(directory) / "analytics.duckdb")
            initial = MarketSyncProgress(analytics, as_of, now, "first", None, None)
            initial.save("daily_bars", 1, symbol="600000.SH")
            initial.save("filing", 0, symbol="600000.SH")

            reopened = MarketSyncProgress(analytics, as_of, now + timedelta(minutes=30), "first", None, None)
            self.assertEqual(reopened.reuse("filing", "600000.SH")["count"], 0)
            later = MarketSyncProgress(analytics, as_of, now + timedelta(hours=1), "first", None, None)
            self.assertIsNone(later.reuse("filing", "600000.SH"))
            self.assertEqual(later.reuse("daily_bars", "600000.SH")["count"], 1)
            other = MarketSyncProgress(analytics, as_of, now, "other", None, None)
            self.assertIsNone(other.reuse("daily_bars", "600000.SH"))

    def test_identical_request_attaches_to_progress_and_result(self):
        runs = MarketSyncRuns()
        original_started = threading.Event()
        follower_attached = threading.Event()
        key = ("user", "2026-11-24")
        request = (("600000.SH",), False, None)
        updates = []

        def work(report):
            report({"stage": "market_snapshot"})
            original_started.set()
            self.assertTrue(follower_attached.wait(5))
            return {"quality": "verified"}

        def collect(update):
            updates.append(update)
            follower_attached.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            original = pool.submit(runs.run, key, request, work, None)
            self.assertTrue(original_started.wait(5))
            attached = pool.submit(runs.run, key, request, lambda report: self.fail("duplicate work"), collect)
            self.assertEqual(attached.result(timeout=5), original.result(timeout=5))
        self.assertEqual(updates, [{"stage": "market_snapshot"}])
