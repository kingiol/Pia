import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pia_runtime.config import ROOT, Settings
from pia_runtime.models import TaskStatus
from pia_runtime.runtime import PiaRuntime, PortfolioAsOfUnavailable


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

    def test_market_sync_derives_breadth_and_filing_events(self):
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
                {"MarketBreadthChanged", "FilingPublished"},
            )
            self.assertEqual(len(derived), 2)
            tasks = runtime.db.list_tasks()
            self.assertEqual(len(tasks), 2)
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
            self.assertEqual(len(rows), 4)
            self.assertEqual(
                {row["user_id"] for row in rows},
                {"default", "user-b"},
            )
            self.assertTrue(all(
                row["dedupe_key"].endswith(":user-b")
                for row in rows
                if row["user_id"] == "user-b"
            ))

    def test_market_anomalies_have_one_daily_digest_per_matching_user_and_no_tasks(self):
        with tempfile.TemporaryDirectory() as directory, closing(self._runtime(directory)) as runtime:
            market = _market("market-anomalies", 0.5, -5)
            market["instruments"].extend([
                {"symbol": "000001.SZ", "change_pct": 1, "volume_ratio": 2},
                {"symbol": "300001.SZ", "change_pct": 6, "volume_ratio": "NaN"},
                {"symbol": "300002.SZ", "change_pct": "NaN", "volume_ratio": 1},
            ])
            runtime.db.save_market_snapshot(market)
            runtime.save_watchlist("Focus", ["600000"])
            runtime.import_portfolio("manual", [
                {"symbol": "000001.SZ", "quantity": 2, "avg_cost": 10, "market_value": 20},
            ], as_of=market["as_of"])
            runtime.save_watchlist("Focus", ["300001"], user_id="user-b")
            payload = {"quality": "verified", "market_snapshot_quality": "verified", "market_snapshot": market}

            for user in ("default", "user-b", "user-c"):
                self.assertEqual(runtime.events.derive_market_events(payload, user_id=user), [])
            self.assertEqual(runtime.db.list_tasks(), [])
            self.assertEqual(runtime.db.list_notifications(user_id="user-c"), [])
            self.assertEqual(len(runtime.db.list_notifications(user_id="user-b")), 1)

            market_items = runtime.market_workspace()["price_volume_anomalies"]["items"]
            self.assertEqual([item["symbol"] for item in market_items], ["300001.SZ", "600000.SH", "000001.SZ"])
            self.assertEqual([item["followed"] for item in market_items], [False, True, True])
            digest, = runtime.db.list_notifications()
            self.assertEqual(digest["event_type"], "PriceVolumeDigest")
            self.assertEqual(digest["body"], "1 个涨跌幅达阈值 · 1 个放量")
            self.assertEqual([item["symbol"] for item in digest["data"]["items"]], ["600000.SH", "000001.SZ"])

            runtime.db.mark_notification_read(digest["id"])
            runtime.events.derive_market_events(payload)
            self.assertEqual(runtime.db.list_notifications(unread_only=True), [])
            self.assertEqual(len(runtime.db.list_notifications()), 1)

    def test_legacy_anomalies_group_before_limit_and_do_not_retry_missing_portfolio(self):
        with tempfile.TemporaryDirectory() as directory, closing(self._runtime(directory)) as runtime:
            runtime.events.notify("DataQualityDegraded", "Data quality", "Details")
            events = [
                runtime.events.ingest(
                    "PriceVolumeAnomaly", {"symbol": f"{600000 + index}.SH", "as_of": "2026-11-06"},
                    f"price-volume:market-original:{600000 + index}.SH",
                )
                for index in range(105)
            ]
            runtime.events.ingest(
                "PriceVolumeAnomaly", {"symbol": "000001.SZ", "as_of": "2026-11-06"},
                "price-volume:market-original:000001.SZ", user_id="user-b",
            )
            first = events[0]
            task = runtime.db.get_task(first["task_id"])
            task.error = {"code": "PORTFOLIO_AS_OF_UNAVAILABLE"}
            runtime.db.update_task(task)
            runtime.events.schedule_retry(first["event_id"], str(task.error))
            runtime.db.execute("UPDATE event_deliveries SET next_retry_at='2000-01-01' WHERE event_id=?", (first["event_id"],))
            self.assertEqual(runtime.events.retry_due_events(), 0)
            delivery = runtime.db.fetchone("SELECT status, attempt FROM event_deliveries WHERE event_id=?", (first["event_id"],))
            self.assertEqual((delivery["status"], delivery["attempt"]), ("FAILED", 1))

            alert, group = runtime.db.list_notifications()
            self.assertEqual(alert["event_type"], "DataQualityDegraded")
            self.assertEqual(group["data"], {"as_of": "2026-11-06", "count": 105})
            history = runtime.db.legacy_anomaly_notifications(group["id"], "default")
            self.assertEqual(len(history), 105)
            self.assertIn(task.error, [item["error"] for item in history])
            self.assertEqual(len(runtime.db.legacy_anomaly_notifications(group["id"], "user-b")), 1)
            runtime.db.mark_notification_read(group["id"])
            self.assertEqual([row["id"] for row in runtime.db.list_notifications(unread_only=True)], [alert["id"]])
            self.assertEqual(len(runtime.db.list_notifications(unread_only=True, user_id="user-b")), 1)

    def test_interactive_research_requires_compatible_portfolio_before_creating_task(self):
        with tempfile.TemporaryDirectory() as directory, closing(self._runtime(directory)) as runtime:
            runtime.settings.data_provider = "akshare"
            target = {"symbol": "600000.SH", "as_of": "2026-11-06"}
            positions = [{"symbol": "600000.SH", "quantity": 2, "avg_cost": 10, "market_value": 20}]
            runtime.import_portfolio("manual", positions, as_of="2026-11-07")
            with self.assertRaises(PortfolioAsOfUnavailable):
                runtime.create_task("StockResearch", target, require_portfolio=True)
            self.assertEqual(runtime.db.list_tasks(), [])
            runtime.import_portfolio("manual", positions, as_of=target["as_of"])
            task = runtime.create_task("StockResearch", target, require_portfolio=True)
            self.assertEqual(task.status.value, "QUEUED")

    def test_pending_approval_notification_tracks_task_status_and_user_read_state(self):
        with tempfile.TemporaryDirectory() as directory, closing(self._runtime(directory)) as runtime:
            task = runtime.create_task("StockResearch", {"symbol": "600000.SH"})
            runtime._transition(task, TaskStatus.WAITING_APPROVAL)
            runtime.events.notify("MarketBreadthChanged", "Breadth", "Details")
            approval, ordinary = runtime.db.list_notifications()
            self.assertEqual((approval["event_type"], approval["task_id"]), ("TaskWaitingApproval", task.id))
            self.assertEqual(runtime.db.list_notifications(user_id="user-b"), [])
            with self.assertRaises(KeyError):
                runtime.db.mark_notification_read(approval["id"], user_id="user-b")
            runtime.db.mark_notification_read(approval["id"])
            self.assertEqual([row["id"] for row in runtime.db.list_notifications(unread_only=True)], [ordinary["id"]])

            runtime._transition(task, TaskStatus.REJECTED)
            self.assertEqual([row["id"] for row in runtime.db.list_notifications()], [ordinary["id"]])


if __name__ == "__main__":
    unittest.main()
