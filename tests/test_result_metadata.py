import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.models import Task, TaskStatus, now_iso
from pia_runtime.result_metadata import build_result_metadata, legacy_metadata
from pia_runtime.runtime import PiaRuntime


class ResultMetadataTest(unittest.TestCase):
    def test_complete_fallback_partial_none_and_legacy_are_distinct(self):
        pack = {"pack_id": "pack", "subject": None, "blocks": {
            "market": {"required": True, "status": "verified", "snapshot_ids": ["snapshot"],
                       "provenance": {"fallback_used": True}},
        }}
        result = build_result_metadata(pack, [], [], has_result=True)
        self.assertEqual(result["completion"], "complete")
        self.assertTrue(result["degraded"])
        self.assertFalse(result["action_eligible"])
        pack["subject"] = "600000.SH"
        pack["blocks"]["sources"] = {"required": False, "status": "unavailable", "snapshot_ids": [], "provenance": {}}
        self.assertEqual(build_result_metadata(pack, [], [], has_result=True)["completion"], "partial")
        self.assertEqual(build_result_metadata(None, [], [], has_result=False)["completion"], "none")
        self.assertEqual(legacy_metadata()["completion"], "unknown")

    def test_persisted_api_export_history_and_terminal_event_match(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {"as_of": "2026-11-05", "suggested_action": "BUY_CANDIDATE"})
            runtime.run_task(task.id, {"market": "close-2026-11-05.json", "portfolio": "empty.json"})
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "WAITING_APPROVAL")
            metadata = detail["result_metadata"]
            self.assertEqual(detail["decision"]["result_metadata"], metadata)
            self.assertEqual(runtime.list_tasks()[0]["result_metadata"], metadata)
            self.assertEqual(runtime.export_task(task.id)["result_metadata"], metadata)
            terminal = [row for row in detail["events"] if row["event_type"] == "TASK_STATUS"][-1]
            self.assertEqual(terminal["payload"]["result_metadata"], metadata)
            with self.assertRaisesRegex(ValueError, "ACTION_NOT_ELIGIBLE"):
                runtime.approve_task(task.id, "APPROVE")
            with self.assertRaises(KeyError):
                runtime.export_task(task.id, "another-user")
            self.assertEqual(runtime.list_journal()["items"][0]["decision_record"]["result_metadata"], metadata)
