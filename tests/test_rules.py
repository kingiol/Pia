import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pia_runtime.rules import evaluate_close_review, load_rules
from pia_runtime.data_quality import (
    validate_snapshot,
    validate_temporal_metadata,
    validate_universe_coverage,
    validate_universe_metadata,
)


ROOT = Path(__file__).resolve().parents[1]


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.market = json.loads((ROOT / "tests/fixtures/market/close-2026-11-05.json").read_text())
        self.portfolio = json.loads((ROOT / "tests/fixtures/portfolio/default.json").read_text())
        self.rules = load_rules(ROOT / "rules/baseline.yaml")

    def test_fixture_is_blocked_by_position_and_etf_limits(self):
        result = evaluate_close_review(self.market, self.portfolio, self.rules, "ruleset_v1")
        self.assertEqual(result.decision, "BLOCKED")
        codes = {reason.code for reason in result.reasons}
        self.assertIn("POSITION_LIMIT_EXCEEDED", codes)
        self.assertIn("ETF_POSITION_LIMIT", codes)

    def test_market_gate_returns_no_action(self):
        market = {**self.market, "breadth": 0.1}
        portfolio = {**self.portfolio, "positions": []}
        result = evaluate_close_review(market, portfolio, self.rules, "ruleset_v1")
        self.assertEqual(result.decision, "NO_ACTION")

    def test_stale_data_has_explicit_stale_code(self):
        market = {**self.market, "quality": "stale"}
        result = evaluate_close_review(market, {**self.portfolio, "positions": []}, self.rules, "ruleset_v1")
        self.assertEqual(result.decision, "BLOCKED")
        self.assertIn("STALE_DATA", {reason.code for reason in result.reasons})

    def test_snapshot_quality_reports_missing_fields(self):
        result = validate_snapshot({"snapshot_id": "x"}, "market")
        self.assertEqual(result["quality"], "unavailable")
        self.assertIn("as_of", result["missing"])
        self.assertLess(result["field_completeness"], result["field_completeness_target"])

    def test_universe_coverage_requires_all_mvp_categories(self):
        result = validate_universe_coverage([
            {"asset_type": "stock", "board": "main"},
            {"asset_type": "stock", "board": "chinext"},
            {"asset_type": "stock", "board": "star"},
            {"asset_type": "stock", "board": "bse"},
            {"asset_type": "etf", "board": "etf"},
        ])
        self.assertTrue(result["pass"])
        self.assertEqual(result["missing"], [])

    def test_universe_coverage_reports_missing_categories(self):
        result = validate_universe_coverage([
            {"asset_type": "stock", "board": "main"},
        ])
        self.assertFalse(result["pass"])
        self.assertIn("etf", result["missing"])

    def test_universe_metadata_reports_missing_listing_dates(self):
        result = validate_universe_metadata([
            {
                "asset_type": "stock",
                "board": "main",
                "exchange": "SSE",
                "listed_at": "1999-11-10",
                "active": True,
            },
            {
                "asset_type": "etf",
                "board": "etf",
                "exchange": "SSE",
                "active": True,
            },
        ])
        self.assertFalse(result["pass"])
        self.assertIn("listed_at", result["missing"])

    def test_universe_metadata_allows_missing_dates_for_inactive_rows(self):
        result = validate_universe_metadata([
            {
                "asset_type": "stock",
                "board": "main",
                "exchange": "SSE",
                "listed_at": None,
                "active": False,
                "suspended": True,
            },
        ])
        self.assertTrue(result["pass"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["inactive_missing_counts"]["listed_at"], 1)

    def test_snapshot_quality_reports_future_temporal_metadata(self):
        snapshot = {
            **self.market,
            "as_of": "2099-01-01",
            "observed_at": "2099-01-01T16:00:00+00:00",
        }
        result = validate_snapshot(snapshot, "market")
        self.assertEqual(result["quality"], "unavailable")
        self.assertFalse(result["valid"])
        self.assertIn("AS_OF_IN_FUTURE", {
            error["code"] for error in result["temporal_errors"]
        })

    def test_portfolio_snapshot_can_omit_observed_at(self):
        portfolio = {
            "snapshot_id": "portfolio-1",
            "user_id": "user-a",
            "as_of": "2026-11-05",
            "source": "fixture",
            "cash": 100,
            "total_value": 100,
            "drawdown": 0,
            "positions": [],
            "quality": "verified",
        }
        result = validate_snapshot(portfolio, "portfolio")
        self.assertTrue(result["valid"])

    def test_expired_evidence_is_reported_as_stale(self):
        result = validate_temporal_metadata(
            {
                "as_of": "2026-11-05",
                "observed_at": "2026-11-05T16:00:00+00:00",
                "expires_at": "2026-11-06T00:00:00+00:00",
            },
            now=datetime(2026, 11, 7, tzinfo=timezone.utc),
        )
        self.assertFalse(result["valid"])
        self.assertTrue(result["expired"])
        self.assertIn("EXPIRED", {error["code"] for error in result["errors"]})

    def test_as_of_after_requested_date_is_rejected(self):
        result = validate_temporal_metadata(
            {
                "as_of": "2026-11-06",
                "observed_at": "2026-11-06T16:00:00+00:00",
            },
            latest_allowed_as_of="2026-11-05",
        )
        self.assertFalse(result["valid"])
        self.assertIn("AS_OF_AFTER_REQUESTED", {
            error["code"] for error in result["errors"]
        })

    def test_published_after_requested_date_is_rejected(self):
        result = validate_temporal_metadata(
            {
                "as_of": "2026-11-05",
                "observed_at": "2026-11-06T16:00:00+00:00",
                "published_at": "2026-11-06T09:00:00+00:00",
            },
            latest_allowed_as_of="2026-11-05",
            published_field="published_at",
        )
        self.assertFalse(result["valid"])
        self.assertIn("PUBLISHED_AFTER_REQUESTED", {
            error["code"] for error in result["errors"]
        })

    def test_rule_cases_fixture_covers_expected_gate_results(self):
        cases = json.loads((ROOT / "rules/rule_cases.yaml").read_text())["cases"]
        for case in cases:
            market = {
                **self.market,
                "quality": case["data_quality"],
                "breadth": case["breadth"],
            }
            portfolio = {
                **self.portfolio,
                "drawdown": case["drawdown"],
                "positions": [] if case["projected_weight"] == 0.05 else [{
                    "symbol": "600000.SH",
                    "weight": case["projected_weight"],
                    "sector": "banking",
                    "asset_type": "stock",
                }],
            }
            result = evaluate_close_review(market, portfolio, self.rules, "ruleset_v1")
            self.assertEqual(result.decision, case["expected"], case["name"])

    def test_missing_data_and_universe_rejection_are_blocking(self):
        missing = evaluate_close_review(
            {**self.market, "quality": "unavailable"},
            {**self.portfolio, "positions": []},
            self.rules,
            "ruleset_v1",
        )
        self.assertEqual(missing.decision, "BLOCKED")
        self.assertIn("DATA_UNAVAILABLE", {reason.code for reason in missing.reasons})

        rejected = evaluate_close_review(
            {**self.market, "instruments": [{**self.market["instruments"][0], "is_st": True}]},
            {**self.portfolio, "positions": []},
            self.rules,
            "ruleset_v1",
        )
        self.assertEqual(rejected.decision, "BLOCKED")
        self.assertIn("UNIVERSE_REJECTED", {reason.code for reason in rejected.reasons})

    def test_profile_scope_blocks_target_outside_allowed_assets(self):
        result = evaluate_close_review(
            self.market,
            {**self.portfolio, "positions": []},
            self.rules,
            "ruleset_v1",
            profile={
                "allowed_asset_types": ["stock"],
                "universe": ["main"],
            },
            target_symbol="510300.SH",
        )
        self.assertEqual(result.decision, "BLOCKED")
        self.assertIn("UNIVERSE_REJECTED", {reason.code for reason in result.reasons})

    def test_profile_scope_ignores_out_of_scope_market_instruments(self):
        result = evaluate_close_review(
            self.market,
            {**self.portfolio, "positions": []},
            self.rules,
            "ruleset_v1",
            profile={
                "allowed_asset_types": ["stock"],
                "universe": ["main"],
            },
        )
        self.assertNotIn("UNIVERSE_REJECTED", {reason.code for reason in result.reasons})


if __name__ == "__main__":
    unittest.main()
