import unittest
from datetime import datetime
from unittest.mock import patch

from pia_runtime.notifications import LocalNotificationProvider
from pia_runtime.scheduler import LocalMarketScheduler


class _FakeRuntime:
    def __init__(self):
        self.calls = []
        self.notifications = []
        self.db = type("DB", (), {"audit": lambda *args, **kwargs: None})()
        owner = self

        class Events:
            def notify(self, *args, **kwargs):
                owner.notifications.append((args, kwargs))

        self.events = Events()

    def ingest_event(self, event_type, payload, dedupe_key=None):
        self.calls.append((event_type, payload, dedupe_key))
        return {"status": "DISPATCHED", "task_id": "task_scheduler"}


class _HolidayRuntime(_FakeRuntime):
    def is_trading_day(self, as_of):
        return False


class _DegradedRuntime(_FakeRuntime):
    def __init__(self):
        super().__init__()
        self.settings = type(
            "Settings",
            (),
            {"data_provider": "akshare", "scheduler_symbols": ["600000.SH"]},
        )()

    def sync_market_data(self, as_of, symbols):
        return {"quality": "partial", "failures": [{"kind": "news"}]}


class _SyncedRuntime(_FakeRuntime):
    def __init__(self):
        super().__init__()
        self.settings = type(
            "Settings",
            (),
            {"data_provider": "akshare", "scheduler_symbols": ["600000.SH"]},
        )()

    def sync_market_data(self, as_of, symbols):
        return {
            "quality": "verified",
            "market_snapshot_quality": "verified",
            "failures": [],
            "snapshot_id": "market-synced",
        }


class _CloudRuntime(_FakeRuntime):
    def __init__(self):
        super().__init__()
        owner = self
        self.settings = type(
            "Settings",
            (),
            {"mode": "cloud", "data_provider": "fixture"},
        )()
        self.db = type(
            "DB",
            (),
            {
                "audit": lambda *args, **kwargs: None,
                "list_user_ids": lambda _self: ["default", "user-b"],
            },
        )()

        def ingest_event(event_type, payload, dedupe_key=None, user_id="default"):
            owner.calls.append((event_type, payload, dedupe_key, user_id))
            return {"status": "DISPATCHED", "task_id": f"task_{user_id}"}

        self.ingest_event = ingest_event


class SchedulerTest(unittest.TestCase):
    def test_market_close_dispatches_once_on_weekday(self):
        runtime = _FakeRuntime()
        scheduler = LocalMarketScheduler(
            runtime,
            timezone_name="Asia/Shanghai",
            close_time="15:05",
        )
        now = datetime.fromisoformat("2026-11-06T15:06:00+08:00")
        self.assertIsNotNone(scheduler.dispatch_if_due(now))
        self.assertIsNone(scheduler.dispatch_if_due(now))
        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(runtime.calls[0][0], "MarketClose")
        self.assertEqual(runtime.calls[0][2], "market-close:2026-11-06")

    def test_weekend_and_before_close_do_not_dispatch(self):
        runtime = _FakeRuntime()
        scheduler = LocalMarketScheduler(runtime)
        self.assertIsNone(scheduler.dispatch_if_due(datetime.fromisoformat("2026-11-07T16:00:00+08:00")))
        self.assertIsNone(scheduler.dispatch_if_due(datetime.fromisoformat("2026-11-06T15:04:00+08:00")))
        self.assertEqual(runtime.calls, [])

    def test_native_notifications_are_explicitly_disabled_by_default(self):
        receipt = LocalNotificationProvider(enabled=False).deliver("Pia", "test")
        self.assertEqual(receipt.status, "DISABLED")

    @patch("pia_runtime.notifications.platform.system", return_value="Darwin")
    @patch("pia_runtime.notifications.subprocess.run")
    def test_native_notification_delivers_on_macos(self, run, _system):
        receipt = LocalNotificationProvider(enabled=True).deliver("Pia", "test")
        self.assertEqual(receipt.status, "DELIVERED")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["osascript", "-e", 'display notification "test" with title "Pia"'])

    @patch("pia_runtime.notifications.platform.system", return_value="Windows")
    @patch("pia_runtime.notifications.subprocess.run")
    def test_native_notification_delivers_on_windows(self, run, _system):
        receipt = LocalNotificationProvider(enabled=True).deliver("Pia", "test")
        self.assertEqual(receipt.status, "DELIVERED")
        run.assert_called_once_with(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                run.call_args.args[0][-1],
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("<text>Pia</text><text>test</text>", run.call_args.args[0][-1])

    @patch("pia_runtime.notifications.platform.system", return_value="Windows")
    @patch(
        "pia_runtime.notifications.subprocess.run",
        side_effect=[OSError("Toast unavailable"), None],
    )
    def test_native_notification_falls_back_to_windows_session_message(self, run, _system):
        receipt = LocalNotificationProvider(enabled=True).deliver("Pia", "test")
        self.assertEqual(receipt.status, "DELIVERED")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], ["msg", "*", "Pia: test"])

    @patch("pia_runtime.notifications.platform.system", return_value="Darwin")
    @patch("pia_runtime.notifications.subprocess.run", side_effect=OSError("permission denied"))
    def test_native_notification_reports_delivery_failure(self, _run, _system):
        receipt = LocalNotificationProvider(enabled=True).deliver("Pia", "test")
        self.assertEqual(receipt.status, "FAILED")
        self.assertIn("permission denied", receipt.detail or "")

    def test_provider_calendar_can_suppress_weekday_dispatch(self):
        runtime = _HolidayRuntime()
        scheduler = LocalMarketScheduler(runtime, close_time="15:05")
        now = datetime.fromisoformat("2026-11-06T15:06:00+08:00")
        self.assertIsNone(scheduler.dispatch_if_due(now))
        self.assertEqual(runtime.calls, [])

    def test_degraded_sync_notifies_before_market_close_dispatch(self):
        runtime = _DegradedRuntime()
        scheduler = LocalMarketScheduler(runtime, close_time="15:05")
        now = datetime.fromisoformat("2026-11-06T15:06:00+08:00")
        self.assertIsNotNone(scheduler.dispatch_if_due(now))
        self.assertEqual(len(runtime.notifications), 1)
        self.assertEqual(runtime.notifications[0][0][0], "DataQualityDegraded")

    def test_market_close_reuses_synced_market_snapshot(self):
        runtime = _SyncedRuntime()
        scheduler = LocalMarketScheduler(runtime, close_time="15:05")
        now = datetime.fromisoformat("2026-11-06T15:06:00+08:00")
        self.assertIsNotNone(scheduler.dispatch_if_due(now))
        payload = runtime.calls[0][1]
        self.assertEqual(payload["_market_snapshot_id"], "market-synced")

    def test_cloud_scheduler_dispatches_once_per_user_with_scoped_dedupe(self):
        runtime = _CloudRuntime()
        scheduler = LocalMarketScheduler(runtime, close_time="15:05")
        now = datetime.fromisoformat("2026-11-06T15:06:00+08:00")

        result = scheduler.dispatch_if_due(now)

        self.assertEqual(result["user_ids"], ["default", "user-b"])
        self.assertEqual(
            [(call[2], call[3]) for call in runtime.calls],
            [
                ("market-close:2026-11-06", "default"),
                ("market-close:2026-11-06:user-b", "user-b"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
