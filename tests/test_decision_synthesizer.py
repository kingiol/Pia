import copy
import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.decision_synthesizer import graph_opinions, synthesize, valid_evidence_ids
from pia_runtime.models import RuleResult
from pia_runtime.runtime import PiaRuntime


class SynthesizerTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.runtime = PiaRuntime(Settings(db_path=Path(directory.name) / "db", autostart_tasks=False))
        self.addCleanup(self.runtime.close)
        task = self.runtime.create_task("MarketClose", {"as_of": "2026-11-05", "suggested_action": "BUY_CANDIDATE"})
        self.runtime.run_task(task.id, {"market": "close-2026-11-05.json", "portfolio": "empty.json"})
        self.runtime.wait_for_task(task.id)
        self.pack = self.runtime.db.get_context_pack(task.id, "default")
        self.opinions = graph_opinions(self.pack, {"Market Analyst": {}, "Portfolio Analyst": {}, "Risk / Rules Agent": {}})
        self.rules = RuleResult("PASS", [], [], "rules")

    def test_rules_and_conservative_action(self):
        for status in ["BLOCKED", "NO_ACTION"]:
            result = synthesize(self.pack, self.opinions, RuleResult(status, [], [], "rules"))
            self.assertEqual(result.status, status)
        self.assertEqual(synthesize(self.pack, self.opinions, self.rules).status, "WATCH")

    def test_rule_evidence_count_uses_same_time_and_quality_validation(self):
        pack = copy.deepcopy(self.pack)
        valid = valid_evidence_ids(pack)
        self.assertGreater(len(valid), 0)
        row = pack["evidence"][0]
        for field, value in [
            ("quality", "partial"), ("as_of", "2026-11-06"),
            ("expires_at", "2026-11-04T23:59:59+08:00"), ("task_id", "another-task"),
        ]:
            altered = copy.deepcopy(pack)
            altered["evidence"][0][field] = value
            self.assertNotIn(row["id"], valid_evidence_ids(altered))

    def test_bad_evidence_and_order_are_deterministic(self):
        bad = copy.deepcopy(self.opinions[0])
        bad.update(opinion_id="forged", evidence_ids=["does-not-exist"])
        opinions = [*self.opinions, bad]
        left = synthesize(self.pack, opinions, self.rules)
        right = synthesize(self.pack, list(reversed(opinions)), self.rules)
        self.assertEqual(left.synthesis, right.synthesis)
        self.assertEqual(left.synthesis["rejected_opinions"][0]["reason_code"], "EVIDENCE_NOT_IN_PACK")
        self.assertEqual(left.confidence, "low")

    def test_conflicting_claim_and_duplicate_sources_do_not_raise_confidence(self):
        support = dict(self.opinions[0], opinion_id="support", claim_key="market.direction", stance="support")
        oppose = dict(support, opinion_id="oppose", stance="oppose")
        result = synthesize(self.pack, [support, oppose], self.rules)
        self.assertEqual(result.synthesis["conflicts"], ["market.direction"])
        self.assertEqual(result.confidence, "low")
