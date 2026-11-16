import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime


class RunFlowTest(unittest.TestCase):
    def test_terminal_status_closes_running_nodes_in_increment(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {})
            runtime.db.append_event(task.id, "AGENT_STARTED", {"agent_name": "Research"})
            initial = runtime.task_flow(task.id)
            runtime.db.append_event(task.id, "TASK_STATUS", {"status": "CANCELLED"})
            final = runtime.task_flow(task.id, after_seq=initial["next_after_seq"])
            self.assertEqual(len(final["nodes"]), 1)
            self.assertEqual(final["nodes"][0]["status"], "failed")
            self.assertEqual(final["nodes"][0]["reason_codes"], ["TASK_CANCELLED"])

    def test_paging_upserts_and_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {"as_of": "2026-11-05"})
            runtime.run_task(task.id, {"market": "close-2026-11-05.json", "portfolio": "empty.json"})
            runtime.wait_for_task(task.id)
            whole = runtime.task_flow(task.id, limit=500)
            nodes, cursor, snapshot = {}, 0, whole["snapshot_seq"]
            while True:
                page = runtime.task_flow(task.id, after_seq=cursor, limit=3, snapshot_seq=snapshot)
                nodes.update({row["id"]: row for row in page["nodes"]})
                cursor = page["next_after_seq"]
                if not page["has_more"]:
                    break
            self.assertEqual(nodes, {row["id"]: row for row in whole["nodes"]})
            self.assertTrue(any(node["stage_id"] == "synthesize" for node in nodes.values()))
            with self.assertRaises(KeyError):
                runtime.task_flow(task.id, "another-user")
