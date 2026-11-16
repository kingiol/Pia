import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from pia_runtime.config import ROOT
from pia_runtime.db import Database
from pia_runtime.llm_budget import BudgetExceeded, BudgetLedger


class LLMBudgetTest(unittest.TestCase):
    def test_daily_boundary_and_restart_preserve_unknown_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db"
            db = Database(path, ROOT / "migrations")
            context = SimpleNamespace(user_id="user", task_id="task", request_id="request")
            route = SimpleNamespace(route_id="primary", provider_id="fake", model="fake", token_upper_bound="utf8_bytes",
                                    input_cost_per_1k="1", output_cost_per_1k="1")
            BudgetLedger(db, daily_limit="1.1").reserve(context, route, 10, day="2026-11-11")
            db.close()
            restored = Database(path, ROOT / "migrations")
            self.addCleanup(restored.close)
            ledger = BudgetLedger(restored, daily_limit="1.1")
            with self.assertRaises(BudgetExceeded):
                ledger.reserve(context, route, 10, day="2026-11-11")
            ledger.reserve(context, route, 10, day="2026-11-12")
            self.assertEqual(ledger.summary("user")["unknown_count"], 2)
            other_user = SimpleNamespace(user_id="other", task_id="other", request_id="other")
            ledger.reserve(other_user, route, 10, day="2026-11-12")
            self.assertEqual(ledger.summary("other")["conservative_reserved_usd"], "1.034")

    def test_concurrent_reservations_unknown_usage_and_idempotent_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db"
            db = Database(path, ROOT / "migrations")
            other = Database(path, ROOT / "migrations")
            self.addCleanup(db.close)
            self.addCleanup(other.close)
            route = SimpleNamespace(route_id="primary", provider_id="fake", model="fake", token_upper_bound="utf8_bytes",
                                    input_cost_per_1k="1", output_cost_per_1k="1")
            ids, rejected = [], []
            barrier = threading.Barrier(2)
            def reserve(connection, task_id):
                context = SimpleNamespace(user_id="user", task_id=task_id, request_id=task_id)
                barrier.wait()
                try:
                    ids.append(BudgetLedger(connection, daily_limit="1.1").reserve(context, route, 10))
                except BudgetExceeded:
                    rejected.append(task_id)
            threads = [threading.Thread(target=reserve, args=(connection, str(index))) for index, connection in enumerate([db, other])]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(3)
            self.assertEqual((len(ids), len(rejected)), (1, 1))
            ledger = BudgetLedger(db)
            ledger.settle(ids[0], None, "LLM_STREAM_INTERRUPTED")
            ledger.settle(ids[0], {"prompt_tokens": 0, "completion_tokens": 0})
            summary = ledger.summary("user")
            self.assertEqual(summary["unknown_count"], 1)
            self.assertEqual(summary["conservative_reserved_usd"], "1.034")

    def test_unknown_price_and_missing_token_bound_fail_before_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "db", ROOT / "migrations")
            self.addCleanup(db.close)
            route = SimpleNamespace(input_cost_per_1k=0, output_cost_per_1k=0)
            with self.assertRaises(BudgetExceeded):
                BudgetLedger(db, task_limit="1").reserve(SimpleNamespace(), route, 100)
            self.assertEqual(db.fetchall("SELECT * FROM llm_attempts"), [])
