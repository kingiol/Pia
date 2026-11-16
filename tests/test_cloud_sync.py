import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import ROOT, Settings
from pia_runtime.db import Database
from pia_runtime.models import Task, TaskStatus, now_iso
from pia_runtime.runtime import PiaRuntime


class CloudSyncTest(unittest.TestCase):
    def test_watchlists_and_semantic_memory_are_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            try:
                runtime.save_watchlist("Core", ["600000.SH", "510300.SH"], "user-a")
                runtime.save_memory(
                    {
                        "kind": "fact",
                        "symbol": "600000.SH",
                        "title": "Capital ratio",
                        "content": "Capital ratio remains stable.",
                        "source": "fixture://filing/1",
                        "as_of": "2026-11-05",
                        "quality": "verified",
                    },
                    "user-a",
                )
                runtime.save_memory(
                    {
                        "kind": "fact",
                        "symbol": "600000.SH",
                        "title": "Private note",
                        "content": "User B must not see this.",
                        "source": "user://b",
                    },
                    "user-b",
                )
                self.assertEqual(len(runtime.list_watchlists("user-a")), 1)
                self.assertEqual(runtime.list_watchlists("user-b"), [])
                self.assertEqual(
                    len(runtime.search_memories("capital", user_id="user-a")),
                    1,
                )
                self.assertEqual(runtime.search_memories("capital", user_id="user-b"), [])
            finally:
                runtime.close()

    def _database(self) -> Database:
        root = Path(self.directory.name)
        return Database(root / "pia.sqlite3", Path(__file__).parents[1] / "migrations")

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = self._database()

    def tearDown(self) -> None:
        self.db.close()
        self.directory.cleanup()

    def test_device_cannot_be_reassigned_between_users(self):
        registered = self.db.register_device("device-1", "web", user_id="user-a")
        self.assertEqual(registered["user_id"], "user-a")
        with self.assertRaisesRegex(ValueError, "another user"):
            self.db.register_device("device-1", "ios", user_id="user-b")
        devices = self.db.list_devices("user-a")
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["platform"], "web")
        self.assertEqual(self.db.list_devices("user-b"), [])

    def test_device_unregister_is_audited_and_keeps_row_inactive(self):
        self.db.register_device(
            "device-2",
            "android",
            push_token="push-token",
            user_id="user-a",
        )
        self.db.unregister_device("device-2", "user-a")
        self.assertEqual(self.db.list_devices("user-a"), [])
        row = self.db.fetchone(
            "SELECT active FROM devices WHERE device_id=?",
            ("device-2",),
        )
        self.assertEqual(row["active"], 0)
        audit = self.db.fetchall(
            "SELECT payload_json FROM audit_log WHERE event_type=?",
            ("DEVICE_UNREGISTERED",),
        )
        self.assertEqual(len(audit), 1)
        self.assertIn("device-2", audit[0]["payload_json"])

    def test_sync_is_user_scoped_and_idempotent_response_is_replayed(self):
        task_a = Task(
            id="task_a",
            user_id="user-a",
            trigger_type="MarketClose",
            target={"as_of": "2026-11-05"},
            status=TaskStatus.QUEUED,
            created_at=now_iso(),
        )
        task_b = Task(
            id="task_b",
            user_id="user-b",
            trigger_type="MarketClose",
            target={"as_of": "2026-11-05"},
            status=TaskStatus.QUEUED,
            created_at=now_iso(),
        )
        self.db.create_task(task_a)
        self.db.create_task(task_b)
        response = {"task": {"id": task_a.id}}
        self.assertEqual(
            self.db.save_idempotent_response(
                "user-a",
                "create_task",
                "key-1",
                response,
                request_hash="hash-a",
            ),
            response,
        )
        self.assertEqual(
            self.db.get_idempotent_response(
                "user-a",
                "create_task",
                "key-1",
                request_hash="hash-a",
            ),
            response,
        )
        with self.assertRaisesRegex(ValueError, "different request"):
            self.db.get_idempotent_response(
                "user-a",
                "create_task",
                "key-1",
                request_hash="hash-b",
            )
        self.assertIsNone(self.db.get_idempotent_response("user-b", "create_task", "key-1"))
        sync = self.db.sync_changes(user_id="user-a")
        task_ids = {change["task_id"] for change in sync["changes"]}
        self.assertIn(task_a.id, task_ids)
        self.assertNotIn(task_b.id, task_ids)

    def test_sync_cursor_does_not_skip_user_changes_behind_other_users(self):
        for index in range(3):
            self.db.audit(
                None,
                "USER_B_EVENT",
                {"user_id": "user-b", "index": index},
                user_id="user-b",
            )
        self.db.audit(
            None,
            "USER_A_EVENT",
            {"user_id": "user-a"},
            user_id="user-a",
        )

        first = self.db.sync_changes(cursor=0, limit=1, user_id="user-a")
        self.assertEqual(
            [change["event_type"] for change in first["changes"]],
            ["USER_A_EVENT"],
        )
        self.assertFalse(first["has_more"])
        self.assertGreater(first["next_cursor"], first["cursor"])

    def test_lease_release_audit_preserves_user_scope(self):
        task = Task(
            id="task_lease_user_a",
            user_id="user-a",
            trigger_type="MarketClose",
            target={"as_of": "2026-11-05"},
            status=TaskStatus.QUEUED,
            created_at=now_iso(),
        )
        self.db.create_task(task)
        lease = self.db.acquire_lease(task.id, "worker-a")
        self.db.release_lease(lease["lease_id"], "worker-a", user_id="user-a")

        row = self.db.fetchone(
            """SELECT user_id, task_id, event_type
               FROM audit_log
               WHERE event_type='TASK_LEASE_RELEASED'"""
        )
        self.assertEqual(
            dict(row),
            {
                "user_id": "user-a",
                "task_id": task.id,
                "event_type": "TASK_LEASE_RELEASED",
            },
        )
        self.assertEqual(
            [
                item["event_type"]
                for item in self.db.sync_changes(user_id="user-a")["changes"]
                if item["event_type"] == "TASK_LEASE_RELEASED"
            ],
            ["TASK_LEASE_RELEASED"],
        )
        self.assertEqual(
            [
                item["event_type"]
                for item in self.db.sync_changes(user_id="default")["changes"]
                if item["event_type"] == "TASK_LEASE_RELEASED"
            ],
            [],
        )

    def test_lease_release_rejects_other_user(self):
        task = Task(
            id="task_lease_user_b",
            user_id="user-b",
            trigger_type="MarketClose",
            target={"as_of": "2026-11-05"},
            status=TaskStatus.QUEUED,
            created_at=now_iso(),
        )
        self.db.create_task(task)
        lease = self.db.acquire_lease(task.id, "worker-b")
        with self.assertRaises(KeyError):
            self.db.release_lease(lease["lease_id"], "worker-b", user_id="user-a")

    def test_lease_heartbeat_rejects_other_user(self):
        task = Task(
            id="task_lease_heartbeat_user_b",
            user_id="user-b",
            trigger_type="MarketClose",
            target={"as_of": "2026-11-05"},
            status=TaskStatus.QUEUED,
            created_at=now_iso(),
        )
        self.db.create_task(task)
        lease = self.db.acquire_lease(task.id, "worker-b")
        with self.assertRaises(KeyError):
            self.db.heartbeat_lease(
                lease["lease_id"],
                "worker-b",
                user_id="user-a",
            )

if __name__ == "__main__":
    unittest.main()
