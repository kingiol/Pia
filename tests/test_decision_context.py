import json
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from pia_runtime.config import ROOT, Settings
from pia_runtime.decision_context import (
    build_context_pack, content_hash, replay_pack, sanitize_context, validate_pack,
)
from pia_runtime.models import Task, TaskStatus, now_iso
from pia_runtime.runtime import PiaRuntime


class DecisionContextTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.runtime = PiaRuntime(Settings(
            db_path=root / "pia.sqlite3", analytics_db_path=root / "pia.duckdb",
            autostart_tasks=False,
        ))
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.runtime.close)

    def complete(self, task):
        self.runtime.run_task(task.id)
        detail = self.runtime.wait_for_task(task.id)
        self.assertNotEqual(detail["task"]["status"], "FAILED", detail["task"]["error"])
        return detail

    def test_creation_freezes_profile_rules_and_memories(self):
        runtime = self.runtime
        task = runtime.create_task(target={"as_of": "2026-11-05"})
        binding = runtime.db.get_task_binding(task.id, "default")
        runtime.db.save_profile({"risk_tolerance": "aggressive"})
        changed_rules = deepcopy(runtime.rules)
        changed_rules["version"] = "changed"
        runtime.update_rules(changed_rules)
        self.complete(task)
        context = runtime.task_context(task.id, view="full")
        self.assertEqual(context["profile"], binding["payload"]["profile"])
        self.assertEqual(context["rules"], binding["payload"]["rules"]["rules"])
        self.assertEqual(context["context_source"], "frozen")
        self.assertEqual(context["confirmed_memories"], binding["payload"]["confirmed_memories"])

    def test_replay_is_offline_immutable_and_preserves_parent_evidence(self):
        runtime = self.runtime
        task = runtime.create_task(target={"as_of": "2026-11-05"})
        original = self.complete(task)
        pack = runtime.db.get_context_pack(task.id, "default")
        runtime.db.save_profile({"risk_tolerance": "changed"})
        with patch.object(runtime, "_provider_call", side_effect=AssertionError("network")), \
                patch.object(runtime, "_load_research", side_effect=AssertionError("research")), \
                patch.object(runtime.llm, "generate_with_tools", side_effect=AssertionError("llm")):
            replay = runtime.replay_task(task.id)
            replayed = self.complete(replay)
        copied = runtime.db.get_context_pack(replay.id, "default")
        self.assertEqual(pack["content_hash"], copied["content_hash"])
        self.assertEqual(copied["source_pack_id"], pack["pack_id"])
        self.assertEqual(replayed["decision"]["status"], original["decision"]["status"])
        self.assertEqual(len(replayed["evidence"]), len(original["evidence"]))
        self.assertEqual(runtime.task_detail(task.id)["evidence"], original["evidence"])

    def test_integrity_legacy_and_user_scope(self):
        runtime = self.runtime
        task = runtime.create_task(target={"as_of": "2026-11-05"})
        self.complete(task)
        pack = runtime.db.get_context_pack(task.id, "default")
        altered = deepcopy(pack)
        altered["blocks"]["market"]["data"]["breadth"] = 1
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            validate_pack(altered)
        with self.assertRaises(sqlite3.IntegrityError):
            runtime.db.execute(
                "UPDATE decision_context_packs SET content_hash='bad' WHERE task_id=?",
                (task.id,),
            )
        runtime.db.connection.rollback()
        with self.assertRaises(KeyError):
            runtime.task_context(task.id, "another-user", view="full")
        with self.assertRaises(KeyError):
            runtime.replay_task(task.id, "another-user")
        legacy = Task(
            id="legacy", user_id="default", trigger_type="MarketClose",
            target={}, status=TaskStatus.DONE, created_at=now_iso(),
        )
        runtime.db.create_task(legacy)
        self.assertEqual(runtime.task_context(legacy.id)["context_source"], "legacy_incomplete")
        with self.assertRaisesRegex(ValueError, "REPLAY_CONTEXT_INCOMPLETE"):
            runtime.replay_task(legacy.id)

    def test_builder_is_pure_finite_and_overview_is_redacted(self):
        task = self.runtime.create_task(target={"as_of": "2026-11-05"})
        self.complete(task)
        overview = self.runtime.task_context(task.id)
        full = self.runtime.task_context(task.id, view="full")
        self.assertNotIn("data", overview["context_pack"]["blocks"]["portfolio"])
        self.assertEqual(overview["profile"], {})
        self.assertTrue(full["context_pack"]["blocks"]["portfolio"]["data"])
        pack = full["context_pack"]
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            copied = replay_pack(pack, "new-task", "new-binding")
        self.assertEqual(copied["content_hash"], pack["content_hash"])
        with self.assertRaises(ValueError):
            content_hash({"number": float("nan")})
        redacted = sanitize_context({
            "source_uri": "https://user:password@example.com/report?token=secret&id=4",
            "headers": {"Authorization": "Bearer private"},
        })
        self.assertEqual(redacted, {"source_uri": "https://example.com/report?id=4"})

    def test_transaction_rolls_back_task_and_binding_together(self):
        with patch.object(self.runtime.db, "save_task_binding", side_effect=ValueError("broken")):
            with self.assertRaisesRegex(ValueError, "broken"):
                self.runtime.create_task()
        self.assertEqual(self.runtime.db.list_tasks(), [])


if __name__ == "__main__":
    unittest.main()
