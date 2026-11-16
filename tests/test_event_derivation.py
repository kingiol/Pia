import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import ROOT, Settings
from pia_runtime.runtime import PiaRuntime


def _market(snapshot_id: str, breadth: float, change_pct: float) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "as_of": "2026-11-06",
        "observed_at": f"2026-11-06T16:00:00+08:00",
        "source": "test",
        "quality": "verified",
        "breadth": breadth,
        "index_trend": "up",
        "volatility": 0.2,
        "indices": [{"symbol": "000001.SH", "close": 3000, "change_pct": 0.5}],
        "sectors": [{"name": "Bank", "change_pct": 0.5, "breadth": breadth}],
        "instruments": [{
            "symbol": "600000.SH",
            "name": "Test",
            "asset_type": "stock",
            "board": "main",
            "is_st": False,
            "suspended": False,
            "listed_days": 5000,
            "close": 10,
            "change_pct": change_pct,
            "average_turnover": 100000000,
        }],
    }


class EventDerivationTest(unittest.TestCase):
    def _runtime(self, directory: str) -> PiaRuntime:
        return PiaRuntime(Settings(
            db_path=Path(directory) / "pia.sqlite3",
            fixture_dir=ROOT / "tests/fixtures",
            rules_path=ROOT / "rules/baseline.yaml",
            autostart_tasks=False,
        ))

    def test_market_sync_derives_anomaly_breadth_and_filing_events(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self._runtime(directory)
            previous = _market("market-previous", 0.40, 0.0)
            current = _market("market-current", 0.80, 6.5)
            runtime.db.save_market_snapshot(previous)
            runtime.db.save_market_snapshot(current)

            derived = runtime.events.derive_market_events({
                "as_of": "2026-11-06",
                "quality": "verified",
                "market_snapshot_quality": "verified",
                "failures": [],
                "market_snapshot": current,
                "research_sources": [{
                    "source_type": "filing",
                    "external_id": "filing-1",
                    "symbol": "600000.SH",
                    "title": "Test filing",
                    "published_at": "2026-11-06T09:00:00+08:00",
                    "source_uri": "https://example.test/filing-1",
                    "quality": "verified",
                }],
            })

            event_types = {
                row["event_type"]
                for row in runtime.db.fetchall(
                    "SELECT event_type FROM events ORDER BY occurred_at"
                )
            }
            self.assertEqual(
                event_types,
                {"MarketBreadthChanged", "PriceVolumeAnomaly", "FilingPublished"},
            )
            self.assertEqual(len(derived), 3)
            tasks = runtime.db.list_tasks()
            self.assertEqual(len(tasks), 3)
            self.assertTrue(all(
                task.target["_market_snapshot_id"] == "market-current"
                for task in tasks
            ))
            filing_task = next(
                task for task in tasks
                if task.trigger_type == "FilingPublished"
            )

            runtime.run_task(filing_task.id)
            detail = runtime.wait_for_task(filing_task.id)
            self.assertEqual(detail["task"]["data_snapshot_id"], "market-current")

    def test_portfolio_import_derives_risk_event_when_weight_crosses_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self._runtime(directory)
            runtime.import_portfolio("manual", [{
                "symbol": "600000.SH",
                "quantity": 10,
                "avg_cost": 10,
                "market_value": 50,
            }, {
                "symbol": "510300.SH",
                "quantity": 10,
                "avg_cost": 10,
                "market_value": 950,
            }])
            second = runtime.import_portfolio("manual", [{
                "symbol": "600000.SH",
                "quantity": 10,
                "avg_cost": 10,
                "market_value": 500,
            }, {
                "symbol": "510300.SH",
                "quantity": 10,
                "avg_cost": 10,
                "market_value": 500,
            }])

            event = runtime.db.fetchone(
                "SELECT * FROM events WHERE event_type='PortfolioRiskChanged'"
            )
            self.assertIsNotNone(event)
            tasks = runtime.db.list_queued_tasks()
            risk_task = next(
                task for task in tasks
                if task.trigger_type == "PortfolioRiskChanged"
            )
            self.assertEqual(
                risk_task.target["_portfolio_snapshot_id"],
                second["snapshot_id"],
            )

    def test_degraded_market_sync_derives_blocking_quality_event(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self._runtime(directory)
            current = _market("market-degraded", 0.50, 0.0)
            derived = runtime.events.derive_market_events({
                "as_of": "2026-11-06",
                "quality": "partial",
                "market_snapshot_quality": "partial",
                "failures": [{"kind": "fundamentals", "message": "timeout"}],
                "market_snapshot": current,
                "research_sources": [],
            })
            self.assertEqual(len(derived), 1)
            self.assertEqual(derived[0]["status"], "DISPATCHED")
            task = runtime.db.list_queued_tasks()[0]
            self.assertEqual(task.trigger_type, "DataQualityDegraded")

    def test_market_events_use_user_scoped_dedupe_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self._runtime(directory)
            previous = _market("market-previous", 0.40, 0.0)
            current = _market("market-current", 0.80, 6.5)
            runtime.db.save_market_snapshot(previous)
            runtime.db.save_market_snapshot(current)
            payload = {
                "as_of": "2026-11-06",
                "quality": "verified",
                "market_snapshot_quality": "verified",
                "failures": [],
                "market_snapshot": current,
                "research_sources": [{
                    "source_type": "filing",
                    "external_id": "filing-1",
                    "symbol": "600000.SH",
                    "title": "Test filing",
                    "published_at": "2026-11-06T09:00:00+08:00",
                    "source_uri": "https://example.test/filing-1",
                    "quality": "verified",
                }],
            }

            runtime.events.derive_market_events(payload, user_id="default")
            runtime.events.derive_market_events(payload, user_id="user-b")

            rows = runtime.db.fetchall(
                "SELECT user_id, dedupe_key FROM events ORDER BY user_id, dedupe_key"
            )
            self.assertEqual(len(rows), 6)
            self.assertEqual(
                {row["user_id"] for row in rows},
                {"default", "user-b"},
            )
            self.assertTrue(all(
                row["dedupe_key"].endswith(":user-b")
                for row in rows
                if row["user_id"] == "user-b"
            ))


if __name__ == "__main__":
    unittest.main()
