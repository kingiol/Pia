import copy
import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime
from pia_runtime.screening import ScreeningStrategy, execute_scan


class ScreeningTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.runtime = PiaRuntime(Settings(db_path=Path(directory.name) / "db", autostart_tasks=False))
        self.addCleanup(self.runtime.close)

    def test_legacy_formula_and_frozen_replay(self):
        result = self.runtime.scan_candidates(persist=True)
        market = self.runtime.fixture_provider.get_market_snapshot("2026-11-05")
        by_symbol = {row["symbol"]: row for row in market["instruments"]}
        for row in result["candidates"]:
            original = by_symbol[row["symbol"]]
            self.assertEqual(row["score"], round(original["change_pct"] * (1 + market["breadth"]) + original["average_turnover"] / 100_000_000, 4))
            self.assertEqual(round(sum(factor["contribution"] for factor in row["factors"]), 4), row["score"])
        self.runtime.update_profile({"universe": ["nonexistent"]})
        self.assertEqual(self.runtime.candidate_scan(result["scan_id"], replay=True), result)
        empty = self.runtime.scan_candidates()
        self.assertEqual((empty["as_of"], empty["source"], empty["candidates"]), ("2026-11-05", "fixture", []))
        self.assertEqual(len(empty["excluded"]), len(market["instruments"]))
        self.assertTrue(all("PROFILE_UNIVERSE" in row["reason_codes"] for row in empty["excluded"]))
        with self.assertRaises(KeyError):
            self.runtime.candidate_scan(result["scan_id"], "other")

    def test_strict_manifest_and_invalid_numbers(self):
        manifest = copy.deepcopy(next(iter(self.runtime.strategies.values())))
        manifest["expression"] = "__import__('os')"
        with self.assertRaises(ValueError):
            ScreeningStrategy.model_validate(manifest)
        with self.assertRaises(KeyError):
            self.runtime.scan_candidates(strategy_id="../secret")
        manifest.pop("expression")
        market = self.runtime.fixture_provider.get_market_snapshot("2026-11-05")
        market["instruments"][0]["change_pct"] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_NUMBER"):
            execute_scan(manifest, market, {}, self.runtime.rules)

    def test_ties_preserve_input_order_and_missing_values_are_explained(self):
        manifest = next(iter(self.runtime.strategies.values()))
        instrument = {"symbol": "ZZZ", "asset_type": "stock", "board": "main", "listed_days": 1000,
                      "average_turnover": 1_000_000_000, "change_pct": 1}
        market = {"snapshot_id": "s", "as_of": "2026-11-05", "source": "test", "breadth": 0.5,
                  "instruments": [instrument, {**instrument, "symbol": "AAA"}, {**instrument, "symbol": "MISSING", "change_pct": None}]}
        result = execute_scan(manifest, market, {}, self.runtime.rules)
        self.assertEqual([row["symbol"] for row in result["candidates"][:2]], ["ZZZ", "AAA"])
        self.assertIn("MISSING_CHANGE_PCT", result["candidates"][-1]["warnings"])
