import copy
import tempfile
import unittest
from pathlib import Path

from pia_runtime.config import ROOT, Settings
from pia_runtime.runtime import PiaRuntime


class DecisionJournalTest(unittest.TestCase):
    def test_journal_is_cross_task_filtered_and_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                first = runtime.create_task(
                    "MarketClose",
                    {"as_of": "2026-11-05", "symbols": ["600000.SH", "510300.SH"]},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                )
                second = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                )
                runtime.wait_for_task(first.id)
                runtime.wait_for_task(second.id)
                runtime.record_retrospective(
                    first.id,
                    action_taken="NOT_TAKEN",
                    outcome={"status": "observed", "return_pct": 2.4},
                    observed_at="2026-11-06T09:00:00+08:00",
                )

                journal = runtime.list_journal(limit=10)
                self.assertEqual(len(journal["items"]), 2)
                self.assertTrue(all(
                    item["decision_record"]["task"]["user_id"] == "default"
                    for item in journal["items"]
                ))
                self.assertEqual(
                    len(runtime.list_journal(symbol="510300.SH")["items"]),
                    1,
                )
                self.assertEqual(
                    len(runtime.list_journal(outcome_status="observed")["items"]),
                    1,
                )
                self.assertEqual(
                    len(runtime.list_journal(symbol="999999.SH")["items"]),
                    0,
                )

                other = runtime.create_task(
                    "MarketClose",
                    {"as_of": "2026-11-05", "symbols": ["600000.SH"]},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    user_id="other-user",
                )
                runtime.wait_for_task(other.id)
                self.assertEqual(
                    len(runtime.list_journal(user_id="default")["items"]),
                    2,
                )
                self.assertEqual(
                    len(runtime.list_journal(user_id="other-user")["items"]),
                    1,
                )
                focused = runtime.list_journal(task_id=first.id)["items"]
                self.assertEqual([item["decision_record"]["task"]["id"] for item in focused], [first.id])
                self.assertEqual(focused[0]["retrospectives"][0]["action_taken"], "NOT_TAKEN")
                self.assertEqual(runtime.list_journal(task_id=first.id, user_id="other-user")["items"], [])
            finally:
                runtime.close()

    def test_journal_cursor_paginates_without_repeating_records(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                for symbol in ("600000.SH", "510300.SH"):
                    task = runtime.create_task(
                        "StockResearch",
                        {"as_of": "2026-11-05", "symbol": symbol},
                        {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    )
                    runtime.wait_for_task(task.id)
                first = runtime.list_journal(limit=1)
                self.assertEqual(len(first["items"]), 1)
                self.assertIsNotNone(first["next_cursor"])
                second = runtime.list_journal(limit=1, cursor=first["next_cursor"])
                self.assertEqual(len(second["items"]), 1)
                self.assertNotEqual(
                    first["items"][0]["decision_record"]["task"]["id"],
                    second["items"][0]["decision_record"]["task"]["id"],
                )
                with self.assertRaises(ValueError):
                    runtime.list_journal(cursor="invalid")
            finally:
                runtime.close()

    def test_journal_summary_counts_actions_and_comparable_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                task_ids = []
                for symbol in ("600000.SH", "600000.SH", "600000.SH"):
                    task = runtime.create_task(
                        "StockResearch",
                        {"as_of": "2026-11-05", "symbol": symbol},
                        {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    )
                    runtime.wait_for_task(task.id)
                    task_ids.append(task.id)

                runtime.record_retrospective(
                    task_ids[0],
                    action_taken="APPROVE",
                    outcome={"status": "observed", "return_pct": 2.5},
                    observed_at="2026-11-06T09:00:00+08:00",
                )
                runtime.record_retrospective(
                    task_ids[1],
                    action_taken="NOT_TAKEN",
                    outcome={"status": "observed", "return_pct": -1.5},
                    observed_at="2026-11-06T09:00:00+08:00",
                )
                runtime.record_retrospective(
                    task_ids[2],
                    action_taken="REJECT",
                    outcome={"status": "pending"},
                    observed_at="2026-11-06T09:00:00+08:00",
                )

                summary = runtime.journal_summary()
                self.assertEqual(summary["decision_count"], 3)
                self.assertEqual(summary["retrospective_count"], 3)
                self.assertEqual(summary["comparable_outcome_count"], 2)
                self.assertEqual(summary["average_return_pct"], 0.5)
                self.assertEqual(summary["action_counts"], {"TAKEN": 1, "NOT_TAKEN": 2})
                self.assertEqual(summary["outcome_status_counts"], {
                    "observed": 2,
                    "pending": 1,
                })
                self.assertEqual(summary["intent_counts"], {"BLOCKED": 3})
                self.assertEqual(summary["rule_snapshot_counts"], {"ruleset_v1": 3})
            finally:
                runtime.close()

    def test_journal_patterns_group_by_intent_and_rule_version(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                first_ids = []
                for symbol in ("600000.SH", "600000.SH", "600000.SH"):
                    task = runtime.create_task(
                        "StockResearch",
                        {"as_of": "2026-11-05", "symbol": symbol},
                        {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    )
                    runtime.wait_for_task(task.id)
                    first_ids.append(task.id)
                for task_id, return_pct in zip(first_ids, (1.0, 2.0, 3.0)):
                    runtime.record_retrospective(
                        task_id,
                        action_taken="APPROVE",
                        outcome={"status": "observed", "return_pct": return_pct},
                        observed_at="2026-11-06T09:00:00+08:00",
                    )

                rules = copy.deepcopy(runtime.get_rules()["rules"])
                rules["version"] = "v2"
                runtime.update_rules(rules)
                second = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                )
                runtime.wait_for_task(second.id)
                runtime.record_retrospective(
                    second.id,
                    action_taken="NO_ACTION",
                    outcome={"status": "observed", "return_pct": -2.0},
                    observed_at="2026-11-06T09:00:00+08:00",
                )

                patterns = runtime.journal_patterns()
                self.assertEqual(len(patterns["intent_patterns"]), 1)
                intent_pattern = patterns["intent_patterns"][0]
                self.assertEqual(intent_pattern["key"], "BLOCKED")
                self.assertEqual(intent_pattern["sample_size"], 4)
                self.assertEqual(intent_pattern["comparable_outcome_count"], 4)
                self.assertEqual(intent_pattern["average_return_pct"], 1.0)
                self.assertEqual(intent_pattern["rule_violation_count"], 16)
                self.assertTrue(any(candidate["eligible"] for candidate in patterns["memory_candidates"]))

                rule_patterns = {row["key"]: row for row in patterns["rule_patterns"]}
                self.assertEqual(set(rule_patterns), {"ruleset_v1", "ruleset_v2"})
                self.assertEqual(rule_patterns["ruleset_v1"]["sample_size"], 3)
                self.assertEqual(rule_patterns["ruleset_v2"]["sample_size"], 1)

                other_user = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    user_id="other-user",
                )
                runtime.wait_for_task(other_user.id)
                self.assertEqual(runtime.journal_summary(user_id="other-user")["decision_count"], 1)
                self.assertEqual(runtime.journal_patterns(user_id="other-user")["intent_patterns"][0]["sample_size"], 1)
            finally:
                runtime.close()

    def test_memory_candidate_materialization_is_derived_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                task_ids = []
                for _ in range(3):
                    task = runtime.create_task(
                        "StockResearch",
                        {"as_of": "2026-11-05", "symbol": "600000.SH"},
                        {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    )
                    runtime.wait_for_task(task.id)
                    task_ids.append(task.id)
                for task_id, return_pct in zip(task_ids, (1.0, 2.0, 3.0)):
                    runtime.record_retrospective(
                        task_id,
                        action_taken="APPROVE",
                        outcome={"status": "observed", "return_pct": return_pct},
                        observed_at="2026-11-06T09:00:00+08:00",
                    )

                candidate = runtime.journal_patterns()["memory_candidates"][0]
                self.assertEqual(candidate["candidate_key"], "RETROSPECTIVE_PATTERN:BLOCKED")
                saved = runtime.materialize_journal_memory_candidate(candidate["candidate_key"])
                saved_again = runtime.materialize_journal_memory_candidate(candidate["candidate_key"])

                self.assertEqual(saved["id"], saved_again["id"])
                self.assertEqual(saved["source_type"], "SYSTEM_DERIVED")
                self.assertEqual(saved["status"], "CANDIDATE")
                self.assertEqual(saved["sample_size"], 3)
                self.assertEqual(saved["comparable_outcome_count"], 3)
                self.assertEqual(set(saved["source_task_ids"]), set(task_ids))
                self.assertEqual(len(saved["source_task_ids"]), 3)
                self.assertEqual(saved["source_rule_snapshot_ids"], ["ruleset_v1"])
                self.assertEqual(len(runtime.db.list_memory_candidates()), 1)
                self.assertEqual(runtime.search_memories(), [])

                refreshed = runtime.journal_patterns()["memory_candidates"][0]
                self.assertEqual(refreshed["status"], "CANDIDATE")
                self.assertEqual(refreshed["memory_candidate_id"], saved["id"])
                audit_events = runtime.db.fetchall(
                    "SELECT event_type FROM audit_log WHERE event_type LIKE 'MEMORY_CANDIDATE_%'",
                )
                self.assertEqual(
                    sorted(row["event_type"] for row in audit_events),
                    ["MEMORY_CANDIDATE_CREATED", "MEMORY_CANDIDATE_REFRESHED"],
                )

                other_user = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    user_id="other-user",
                )
                runtime.wait_for_task(other_user.id)
                with self.assertRaisesRegex(ValueError, "minimum threshold"):
                    runtime.materialize_journal_memory_candidate(
                        candidate["candidate_key"],
                        user_id="other-user",
                    )
                self.assertEqual(runtime.db.list_memory_candidates(user_id="other-user"), [])
            finally:
                runtime.close()

    def test_memory_candidate_requires_minimum_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                task = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                )
                runtime.wait_for_task(task.id)
                with self.assertRaisesRegex(ValueError, "minimum threshold"):
                    runtime.materialize_journal_memory_candidate(
                        "RETROSPECTIVE_PATTERN:BLOCKED",
                    )
                self.assertEqual(runtime.db.list_memory_candidates(), [])
            finally:
                runtime.close()

    def test_memory_feedback_is_usage_scoped_and_only_suggests_archiving(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            try:
                candidate = runtime.db.save_memory_candidate({
                    "candidate_key": "RETROSPECTIVE_PATTERN:BLOCKED",
                    "kind": "RETROSPECTIVE_PATTERN",
                    "title": "Review blocked decisions",
                    "content": "Check risk constraints before acting.",
                    "sample_size": 3,
                    "comparable_outcome_count": 3,
                }, user_id="user-a")
                candidate_id = candidate["id"]
                runtime.review_journal_memory_candidate(
                    candidate_id, action="CONFIRM", user_id="user-a",
                )
                self.assertEqual(
                    runtime.journal.feedback_summary(candidate_id, user_id="user-a")[
                        "feedback_recommendation"
                    ],
                    "NO_FEEDBACK",
                )
                with self.assertRaisesRegex(ValueError, "no recorded usage"):
                    runtime.record_journal_memory_candidate_feedback(
                        candidate_id, rating="HELPFUL", user_id="user-a",
                    )
                usages = []
                for _ in range(2):
                    task = runtime.create_task(
                        "StockResearch",
                        {"as_of": "2026-11-05", "symbol": "600000.SH"},
                        user_id="user-a",
                    )
                    usages.append(runtime.db.record_memory_candidate_usage(
                        candidate_id, task.id, user_id="user-a",
                    ))
                for index, usage in enumerate(usages):
                    result = runtime.record_journal_memory_candidate_feedback(
                        candidate_id, usage_id=usage["id"],
                        rating="NOT_HELPFUL", user_id="user-a",
                    )
                    self.assertEqual(result["feedback"]["task_id"], usage["task_id"])
                    self.assertEqual(
                        result["feedback_summary"]["feedback_recommendation"],
                        "REVIEW_SUGGESTED" if index == 0 else "ARCHIVE_SUGGESTED",
                    )
                updated = runtime.record_journal_memory_candidate_feedback(
                    candidate_id, usage_id=usages[0]["id"],
                    rating="HELPFUL", user_id="user-a",
                )
                self.assertEqual(updated["feedback_summary"]["feedback_count"], 2)
                self.assertEqual(updated["feedback_summary"]["helpful_count"], 1)
                self.assertEqual(updated["feedback_summary"]["not_helpful_count"], 1)
                self.assertEqual(
                    updated["feedback_summary"]["feedback_recommendation"],
                    "REVIEW_SUGGESTED",
                )
                with self.assertRaisesRegex(ValueError, "no recorded usage"):
                    runtime.record_journal_memory_candidate_feedback(
                        candidate_id, usage_id="unknown-usage",
                        rating="HELPFUL", user_id="user-a",
                    )
                with self.assertRaises(KeyError):
                    runtime.record_journal_memory_candidate_feedback(
                        candidate_id, usage_id=usages[0]["id"],
                        rating="HELPFUL", user_id="user-b",
                    )
                response = runtime.list_journal_memory_candidate_usages(
                    candidate_id, user_id="user-a",
                )
                self.assertEqual(response["candidate"]["status"], "CONFIRMED")
                self.assertEqual(len(response["feedback"]), 2)
                runtime.review_journal_memory_candidate(
                    candidate_id, action="ARCHIVE", user_id="user-a",
                )
                self.assertEqual(
                    runtime.task_context(usages[0]["task_id"], "user-a")[
                        "confirmed_memories"
                    ],
                    [],
                )
                self.assertEqual(len(runtime.list_journal_memory_candidate_usages(
                    candidate_id, user_id="user-a",
                )["feedback"]), 2)
                with self.assertRaisesRegex(ValueError, "no longer reviewable"):
                    runtime.review_journal_memory_candidate(
                        candidate_id, action="CONFIRM", user_id="user-a",
                    )
            finally:
                runtime.close()

    def test_memory_candidate_review_lifecycle_and_confirmed_context(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                task = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    user_id="user-a",
                )
                candidate = runtime.db.save_memory_candidate({
                    "candidate_key": "RETROSPECTIVE_PATTERN:BLOCKED",
                    "kind": "RETROSPECTIVE_PATTERN",
                    "title": "原始标题",
                    "content": "原始内容",
                    "sample_size": 3,
                    "comparable_outcome_count": 3,
                    "source_task_ids": [task.id],
                    "source_rule_snapshot_ids": ["ruleset_v1"],
                }, user_id="user-a")

                confirmed = runtime.review_journal_memory_candidate(
                    candidate["id"],
                    action="EDIT_AND_CONFIRM",
                    title="确认后的标题",
                    content="确认后的内容",
                    notes="用户复核后确认",
                    user_id="user-a",
                )
                self.assertEqual(confirmed["status"], "CONFIRMED")
                self.assertEqual(confirmed["title"], "确认后的标题")
                self.assertEqual(confirmed["content"], "确认后的内容")
                self.assertEqual(confirmed["review_action"], "EDIT_AND_CONFIRM")
                self.assertEqual(confirmed["reviewed_by"], "user-a")
                self.assertEqual(
                    runtime.task_context(task.id, "user-a", view="full")["confirmed_memories"], [],
                )
                runtime.wait_for_task(task.id, user_id="user-a")
                task = runtime.create_task(
                    "StockResearch", {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                    user_id="user-a",
                )
                self.assertEqual(
                    runtime.task_context(task.id, "user-a", view="full")["confirmed_memories"],
                    [confirmed],
                )
                runtime.run_task(
                    task.id,
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                )
                runtime.wait_for_task(task.id, user_id="user-a")
                usages = runtime.db.list_memory_candidate_usages(
                    confirmed["id"],
                    user_id="user-a",
                )
                self.assertEqual(len(usages), 1)
                self.assertEqual(usages[0]["task_id"], task.id)
                self.assertEqual(usages[0]["usage_type"], "TASK_CONTEXT_INJECTED")
                usage_candidate = next(
                    row for row in runtime.journal_patterns(user_id="user-a")["memory_candidates"]
                    if row["candidate_key"] == "RETROSPECTIVE_PATTERN:BLOCKED"
                )
                self.assertEqual(usage_candidate["usage_count"], 1)
                self.assertEqual(usage_candidate["latest_usage_id"], usages[0]["id"])
                self.assertEqual(usage_candidate["usage_task_ids"], [task.id])
                feedback = runtime.record_journal_memory_candidate_feedback(
                    confirmed["id"],
                    rating="HELPFUL",
                    user_id="user-a",
                )
                self.assertEqual(feedback["feedback"]["rating"], "HELPFUL")
                self.assertEqual(feedback["feedback_summary"]["feedback_count"], 1)
                self.assertEqual(feedback["feedback_summary"]["feedback_recommendation"], "KEEP")
                feedback_again = runtime.record_journal_memory_candidate_feedback(
                    confirmed["id"],
                    rating="UNCERTAIN",
                    user_id="user-a",
                )
                self.assertEqual(feedback_again["feedback_summary"]["uncertain_count"], 1)
                self.assertEqual(
                    len(runtime.db.list_memory_candidate_feedback(
                        confirmed["id"],
                        user_id="user-a",
                    )),
                    1,
                )
                with self.assertRaises(KeyError):
                    runtime.record_journal_memory_candidate_feedback(
                        confirmed["id"],
                        rating="HELPFUL",
                        user_id="other-user",
                    )
                with self.assertRaisesRegex(ValueError, "no longer reviewable"):
                    runtime.review_journal_memory_candidate(
                        candidate["id"],
                        action="REJECT",
                        user_id="user-a",
                    )
                with self.assertRaises(KeyError):
                    runtime.review_journal_memory_candidate(
                        candidate["id"],
                        action="CONFIRM",
                        user_id="other-user",
                    )

                rejected = runtime.db.save_memory_candidate({
                    "candidate_key": "RETROSPECTIVE_PATTERN:REJECTED",
                    "kind": "RETROSPECTIVE_PATTERN",
                    "title": "待拒绝",
                    "content": "待拒绝内容",
                    "sample_size": 3,
                    "comparable_outcome_count": 3,
                }, user_id="user-a")
                archived = runtime.db.save_memory_candidate({
                    "candidate_key": "RETROSPECTIVE_PATTERN:ARCHIVED",
                    "kind": "RETROSPECTIVE_PATTERN",
                    "title": "待归档",
                    "content": "待归档内容",
                    "sample_size": 3,
                    "comparable_outcome_count": 3,
                }, user_id="user-a")
                rejected = runtime.review_journal_memory_candidate(
                    rejected["id"],
                    action="REJECT",
                    user_id="user-a",
                )
                archived = runtime.review_journal_memory_candidate(
                    archived["id"],
                    action="ARCHIVE",
                    user_id="user-a",
                )
                self.assertEqual(rejected["status"], "REJECTED")
                self.assertEqual(archived["status"], "ARCHIVED")
                context_ids = {
                    row["id"]
                    for row in runtime.task_context(task.id, "user-a", view="full")["confirmed_memories"]
                }
                self.assertEqual(context_ids, {confirmed["id"]})
                audit_events = runtime.db.fetchall(
                    "SELECT event_type FROM audit_log WHERE event_type='MEMORY_CANDIDATE_REVIEWED'",
                )
                self.assertEqual(len(audit_events), 3)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
