import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime
from pia_runtime.stage_policy import StageBudget, StageTimeout


class StagePolicyTest(unittest.TestCase):
    def test_monotonic_pause_and_shared_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {"as_of": "2026-11-05"})
            clock = [0.0]
            budget = StageBudget(runtime.db, task, 300, clock=lambda: clock[0])
            budget.start("required_data")
            clock[0] += 20
            budget.add_pause(10)
            self.assertEqual(budget.remaining(), 290)
            clock[0] += 51
            with self.assertRaises(StageTimeout):
                budget.check()
            budget.finish("failed", "STAGE_TIMEOUT")
            self.assertEqual(runtime.db.fetchone("SELECT outcome FROM task_stage_runs")["outcome"], "failed")

    def test_small_budget_does_not_allocate_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {})
            budget = StageBudget(runtime.db, task, 0.01)
            with self.assertRaises(StageTimeout):
                budget.start("required_data")
            self.assertEqual(budget.current["allocated_ms"], 0)

    def test_required_agents_reserved_and_completed_rules_not_reserved_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {})
            budget = StageBudget(runtime.db, task, 100, clock=lambda: 0)
            budget.start("supplemental_data")
            self.assertEqual(budget.current["allocated_ms"], 25000)
            budget.finish()
            budget.start("rules")
            budget.finish()
            budget.total_seconds = 30
            budget.start("llm_research")
            self.assertEqual(budget.current["allocated_ms"], 20000)

    def test_required_llm_reserves_its_stage_before_optional_work(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(db_path=Path(directory) / "db", autostart_tasks=False))
            self.addCleanup(runtime.close)
            task = runtime.create_task("MarketClose", {})
            budget = StageBudget(runtime.db, task, 180, clock=lambda: 0, required_stages=["llm_research"])
            budget.start("supplemental_data")
            self.assertEqual(budget.current["allocated_ms"], 15000)
