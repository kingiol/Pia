import tempfile
import threading
import time
import unittest
from pathlib import Path

from pia_runtime.adapters import FixtureMarketProvider, ProviderCircuitOpen, ProviderHealth, ProviderRegistry
from pia_runtime.config import ROOT, Settings
from pia_runtime.runtime import PiaRuntime


class Provider(FixtureMarketProvider):
    def __init__(self, provider_id):
        super().__init__(ROOT / "tests/fixtures")
        self.provider_id = provider_id
        self.offline = False
        self.news_offline = False
        self.partial_fundamentals = False
        self.calls = []

    def health(self):
        return ProviderHealth(
            self.provider_id, "healthy", ["market_snapshot", "news", "fundamentals"],
            True, False,
        )

    def get_market_snapshot(self, as_of, fixture_name=None):
        self.calls.append("market")
        if self.offline:
            raise ConnectionError("api_key=do-not-log")
        result = super().get_market_snapshot(as_of, fixture_name)
        result.update(source=self.provider_id, provider_id=self.provider_id)
        return result

    def search_news(self, symbol, as_of=None):
        self.calls.append("news")
        if self.news_offline or self.offline:
            raise ConnectionError("token=do-not-log")
        return [{"title": "Verified report", "quality": "verified", "symbol": symbol}]

    def get_fundamentals(self, symbol, as_of=None):
        self.calls.append("fundamentals")
        return {"symbol": symbol, "as_of": as_of, "quality":
                "partial" if self.partial_fundamentals else "verified"}


class ProviderProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.runtime = PiaRuntime(Settings(
            db_path=root / "pia.sqlite3", analytics_db_path=root / "pia.duckdb",
            autostart_tasks=False,
        ))
        self.addCleanup(self.runtime.close)
        self.primary, self.secondary = Provider("primary"), Provider("secondary")
        self.runtime.settings.data_provider = "primary"
        self.runtime.providers = ProviderRegistry(
            [self.primary, self.secondary], retry_attempts=2,
            retry_backoff_seconds=0, circuit_failure_threshold=1,
        )

    def test_capability_failure_does_not_open_other_capabilities(self):
        self.primary.news_offline = True
        selected, rows = self.runtime._provider_call("news", "search_news", "600000.SH", as_of="2026-11-05")
        self.assertEqual(selected.provider_id, "secondary")
        attempts = rows[0]["provenance"]["attempts"]
        self.assertEqual([item["provider_id"] for item in attempts], ["primary", "primary", "secondary"])
        health = self.runtime.providers.health()[0]
        self.assertEqual(health["capability_health"]["news"]["circuit_state"], "open")
        self.assertEqual(health["capability_health"]["market_snapshot"]["circuit_state"], "closed")
        selected, _ = self.runtime._provider_call("market_snapshot", "get_market_snapshot", "2026-11-05")
        self.assertEqual(selected.provider_id, "primary")
        self.assertNotIn("do-not-log", str(health))

    def test_partial_fallback_and_persistent_attempts(self):
        self.primary.partial_fundamentals = True
        _, result = self.runtime._provider_call("fundamentals", "get_fundamentals", "600000.SH", as_of="2026-11-05")
        self.assertEqual(result["quality"], "verified")
        self.assertTrue(result["provenance"]["fallback_used"])
        self.assertEqual(self.primary.calls.count("fundamentals"), 1)
        self.assertEqual(len(self.runtime.db.fetchall("SELECT id FROM provider_attempts")), 2)

    def test_last_good_is_stale_scoped_and_never_future(self):
        self.runtime._provider_call("market_snapshot", "get_market_snapshot", "2026-11-05")
        self.primary.offline = self.secondary.offline = True
        _, result = self.runtime._provider_call("market_snapshot", "get_market_snapshot", "2026-11-06")
        self.assertEqual(result["as_of"], "2026-11-05")
        self.assertEqual(result["quality"], "stale")
        self.assertGreater(result["provenance"]["stale_age_seconds"], 0)
        self.assertEqual(result["provenance"]["source_type"], "last_good_snapshot")
        self.runtime._provider_context.user_id = "other-user"
        with self.assertRaisesRegex(RuntimeError, "CAPABILITY_UNAVAILABLE"):
            self.runtime._provider_call("market_snapshot", "get_market_snapshot", "2026-11-06")
        self.runtime._provider_context.user_id = "default"
        with self.assertRaisesRegex(RuntimeError, "CAPABILITY_UNAVAILABLE"):
            self.runtime._provider_call("market_snapshot", "get_market_snapshot", "2026-11-04")

    def test_half_open_allows_one_probe(self):
        registry = self.runtime.providers
        state = registry._state(self.primary, "news")
        state.opened_until = time.monotonic() - 1
        entered, release = threading.Event(), threading.Event()

        def wait(symbol):
            entered.set()
            release.wait(2)
            return []

        self.primary.search_news = wait
        worker = threading.Thread(target=lambda: registry.call(self.primary, "search_news", "600000.SH"))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(ProviderCircuitOpen):
                registry.call(self.primary, "search_news", "600000.SH")
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(state.to_dict()["circuit_state"], "closed")

    def test_required_transient_capability_failure_is_retryable(self):
        self.primary.offline = self.secondary.offline = True
        task = self.runtime.create_task("MarketClose", {"as_of": "2026-11-05"})
        self.runtime.run_task(task.id)
        detail = self.runtime.wait_for_task(task.id)
        self.assertEqual(detail["task"]["status"], "RETRYABLE")
        self.assertEqual(detail["task"]["error"]["code"], "CAPABILITY_UNAVAILABLE")
        self.assertEqual(detail["result_metadata"]["completion"], "none")
        self.assertIsNone(detail["decision"])


if __name__ == "__main__":
    unittest.main()
