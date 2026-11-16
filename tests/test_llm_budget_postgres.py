import os
import threading
import unittest
from types import SimpleNamespace

from pia_runtime.config import ROOT
from pia_runtime.llm_budget import BudgetExceeded, BudgetLedger
from pia_runtime.models import new_id
from pia_runtime.postgres import PostgresDatabase


@unittest.skipUnless(os.getenv("PIA_TEST_POSTGRES_DSN"), "requires isolated PostgreSQL integration database")
class PostgresBudgetTest(unittest.TestCase):
    def test_parallel_connections_enforce_user_daily_budget(self):
        databases = [PostgresDatabase(os.environ["PIA_TEST_POSTGRES_DSN"], ROOT / "migrations") for _ in range(2)]
        for database in databases:
            self.addCleanup(database.close)
        user_id, ids, blocked = new_id("budget_user"), [], []
        barrier = threading.Barrier(2)
        route = SimpleNamespace(route_id="pg", provider_id="fake", model="fake", token_upper_bound="utf8_bytes",
                                input_cost_per_1k="1", output_cost_per_1k="1")
        def reserve(index):
            context = SimpleNamespace(user_id=user_id, task_id=new_id("task"), request_id=new_id("request"))
            barrier.wait()
            try:
                ids.append(BudgetLedger(databases[index], daily_limit="1.1").reserve(context, route, 10))
            except BudgetExceeded:
                blocked.append(index)
        threads = [threading.Thread(target=reserve, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual((len(ids), len(blocked)), (1, 1))
        ledger = BudgetLedger(databases[0])
        ledger.settle(ids[0], {"prompt_tokens": 10, "completion_tokens": 2})
        self.assertEqual(ledger.summary(user_id)["known_cost_usd"], "0.012")
