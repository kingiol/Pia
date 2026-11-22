import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pia_runtime.adapters import ProviderHealth, ProviderRegistry
from pia_runtime.config import ROOT, Settings
from pia_runtime.analytics import AnalyticsStore
from pia_runtime.backup import create_backup_package, restore_backup_package
from pia_runtime.db import Database
from pia_runtime.llm import GenerationEvent, LLMRateLimited
from pia_runtime.models import Task, TaskStatus, now_iso
from pia_runtime.notifications import NotificationReceipt
from pia_runtime.replay import run_replay
from pia_runtime.runtime import PiaRuntime


class RuntimeTest(unittest.TestCase):
    def cloud_policy_runtime(self, settings):
        # Unit-test Cloud task policies locally; PostgreSQL storage has integration tests.
        settings.mode = "local"
        settings.autostart_tasks = False
        runtime = PiaRuntime(settings)
        runtime.settings.mode = "cloud"
        self.addCleanup(runtime.close)
        return runtime

    def test_cloud_requires_postgres_without_creating_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "PIA_POSTGRES_DSN"):
                PiaRuntime(Settings(mode="cloud", db_path=root / "pia.sqlite3"))
            self.assertEqual(list(root.iterdir()), [])

    def test_rule_retrospective_is_persisted_audited_and_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                task = runtime.create_task(
                    "MarketClose",
                    {
                        "as_of": "2026-11-05",
                        "_fixture": {
                            "market": "close-2026-11-05.json",
                            "portfolio": "default.json",
                        },
                    },
                )
                detail = runtime.wait_for_task(task.id)
                self.assertIsNotNone(detail)
                retrospective = runtime.record_retrospective(
                    task.id,
                    action_taken="NOT_TAKEN",
                    outcome={"status": "mixed", "return_pct": -1.25},
                    notes="Waiting for a cleaner setup.",
                    observed_at="2026-11-06T09:00:00+08:00",
                )
                self.assertEqual(retrospective["task_id"], task.id)
                self.assertEqual(retrospective["outcome"]["return_pct"], -1.25)
                refreshed = runtime.task_detail(task.id)
                self.assertEqual(len(refreshed["retrospectives"]), 1)
                self.assertTrue(any(
                    event["event_type"] == "RETROSPECTIVE_RECORDED"
                    for event in refreshed["events"]
                ))
                audit = runtime.db.fetchall(
                    "SELECT * FROM audit_log WHERE task_id=? AND event_type=?",
                    (task.id, "RETROSPECTIVE_RECORDED"),
                )
                self.assertEqual(len(audit), 1)
                self.assertEqual(runtime.db.list_retrospectives(task.id, "other-user"), [])
                with self.assertRaises(KeyError):
                    runtime.record_retrospective(
                        task.id,
                        action_taken="APPROVE",
                        outcome={"status": "positive"},
                        user_id="other-user",
                    )
                with self.assertRaises(ValueError):
                    runtime.record_retrospective(
                        task.id,
                        action_taken="APPROVE",
                        outcome={"status": "positive"},
                        observed_at="2099-01-01T00:00:00+00:00",
                    )
            finally:
                runtime.close()

    def test_retrospective_structured_windows_and_benchmark_are_normalized(self):
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
                t5 = runtime.record_retrospective(
                    task.id,
                    action_taken="APPROVE",
                    outcome={
                        "status": "positive",
                        "horizon": "T+5",
                        "return_pct": 4.25,
                        "benchmark_return_pct": 2.0,
                        "market_regime": "震荡上行",
                        "position_size_pct": 25,
                    },
                    observed_at="2026-11-06T09:00:00+08:00",
                )
                t20 = runtime.record_retrospective(
                    task.id,
                    action_taken="APPROVE",
                    outcome={
                        "status": "mixed",
                        "horizon": "T+20",
                        "return_pct": 3.0,
                        "benchmark_return_pct": 4.0,
                    },
                    observed_at="2026-11-09T09:00:00+08:00",
                )
                self.assertEqual(t5["outcome"]["excess_return_pct"], 2.25)
                self.assertEqual(t20["outcome"]["excess_return_pct"], -1.0)
                summary = runtime.journal_summary()
                self.assertEqual(summary["retrospective_count"], 2)
                self.assertEqual(summary["horizon_counts"], {"T+5": 1, "T+20": 1})
                self.assertEqual(summary["average_benchmark_return_pct"], 3.0)
                self.assertEqual(summary["average_excess_return_pct"], 0.625)
                with self.assertRaisesRegex(ValueError, "outcome.horizon"):
                    runtime.record_retrospective(
                        task.id,
                        action_taken="APPROVE",
                        outcome={"horizon": "T+10", "return_pct": 1},
                    )
                with self.assertRaisesRegex(ValueError, "must be numeric"):
                    runtime.record_retrospective(
                        task.id,
                        action_taken="APPROVE",
                        outcome={"return_pct": "unknown"},
                    )
                with self.assertRaisesRegex(ValueError, "between 0 and 100"):
                    runtime.record_retrospective(
                        task.id,
                        action_taken="APPROVE",
                        outcome={"position_size_pct": 120},
                    )
            finally:
                runtime.close()

    def test_paper_order_preview_and_submission_are_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                preview = runtime.preview_order({
                    "symbol": "600000.SH",
                    "side": "BUY",
                    "quantity": 100,
                    "limit_price": 8,
                })
                self.assertEqual(preview["status"], "PREVIEW")
                receipt = runtime.paper_submit_order({
                    "symbol": "600000.SH",
                    "side": "BUY",
                    "quantity": 100,
                    "limit_price": 8,
                    "client_order_id": "runtime-paper-order",
                })
                self.assertEqual(receipt["status"], "PAPER_ACCEPTED")
                self.assertEqual(receipt["order_id"], "runtime-paper-order")
                audit = runtime.db.fetchall(
                    "SELECT * FROM audit_log WHERE event_type=?",
                    ("PAPER_ORDER_RECORDED",),
                )
                self.assertEqual(len(audit), 1)
            finally:
                runtime.close()

    def test_live_provider_selection_initializes_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                data_provider="akshare",
            ))
            try:
                self.assertIn(runtime.provider.provider_id, {"akshare", "fixture"})
            finally:
                runtime.close()

    def test_live_tasks_reuse_persisted_market_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules" / "baseline.yaml",
                data_provider="akshare",
            ))
            try:
                market = runtime.fixture_provider.get_market_snapshot("2026-11-05")
                market.update({
                    "snapshot_id": "market_akshare_2026-11-05_cached",
                    "source": "akshare",
                    "provider_id": "akshare",
                    "quality": "verified",
                    "trading_calendar": [{"trade_date": "2026-11-05", "is_open": True}],
                })
                runtime.db.save_market_snapshot(market)
                runtime.db.save_portfolio_snapshot(
                    {**runtime.fixture_provider.get_portfolio_snapshot("empty.json"), "source": "import"}
                )

                def unexpected_provider_call(*args, **kwargs):
                    raise AssertionError(
                        f"unexpected live provider call: args={args}, kwargs={kwargs}"
                    )

                with patch.object(
                    runtime,
                    "_provider_call",
                    side_effect=unexpected_provider_call,
                ):
                    candidates = runtime.scan_candidates("2026-11-05")
                self.assertEqual(candidates["snapshot_id"], market["snapshot_id"])
                self.assertTrue(candidates["candidates"])

                with patch.object(
                    runtime,
                    "_provider_call",
                    side_effect=unexpected_provider_call,
                ), patch.object(
                    runtime,
                    "_load_research",
                    return_value=runtime._load_research_fixture(
                        "600000.SH",
                        "2026-11-05",
                    ),
                ):
                    task = runtime.create_task(
                        "StockResearch",
                        {"as_of": "2026-11-05", "symbol": "600000.SH"},
                    )
                    detail = runtime.wait_for_task(task.id)
                self.assertIsNotNone(detail)
                self.assertEqual(
                    detail["task"]["data_snapshot_id"],
                    market["snapshot_id"],
                )
            finally:
                runtime.close()

    def test_required_llm_runtime_result_is_recorded_without_overriding_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                require_llm=True,
            ))
            calls = []

            def generate_with_tools(system_prompt, payload, tools, executor):
                calls.append({
                    "system_prompt": system_prompt,
                    "payload": payload,
                    "tool_count": len(tools),
                })
                return {
                    "summary": "Structured model review",
                    "status": "BUY_CANDIDATE",
                    "confidence": "medium",
                }

            with patch.object(
                type(runtime.llm),
                "generate_with_tools",
                side_effect=generate_with_tools,
            ):
                task = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                )
                detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "BLOCKED")
            self.assertEqual(len(calls), 1)
            self.assertTrue(any(
                row["agent_name"] == "Research Manager"
                for row in detail["trace"]
            ))
            self.assertEqual(detail["decision"]["status"], "BLOCKED")

    def test_streaming_llm_runtime_emits_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                require_llm=True,
                llm_streaming=True,
            ))

            def stream_with_tools(system_prompt, payload, tools, executor):
                yield GenerationEvent(kind="delta", delta='{"summary":"streamed"}')
                yield GenerationEvent(
                    kind="completed",
                    result={"summary": "streamed", "status": "BUY_CANDIDATE"},
                )

            with patch.object(
                type(runtime.llm),
                "stream_with_tools",
                side_effect=stream_with_tools,
            ):
                task = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                )
                detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "BLOCKED")
            self.assertTrue(any(
                event["event_type"] == "LLM_DELTA"
                for event in detail["events"]
            ))

    def test_retryable_llm_error_keeps_task_recoverable_with_stable_code(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                require_llm=True,
            ))
            with patch.object(
                type(runtime.llm),
                "generate_with_tools",
                side_effect=LLMRateLimited("provider is busy", provider_id="deepseek"),
            ):
                task = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                )
                detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "RETRYABLE")
            self.assertEqual(detail["task"]["error"]["code"], "LLM_RATE_LIMITED")
            self.assertTrue(detail["task"]["error"]["retryable"])
            runtime.close()

    def test_metrics_reports_terminal_success_rate_and_p95(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            detail = run_replay(runtime, ROOT / "tests/fixtures/replay/close-review.json")
            metrics = runtime.metrics()
            self.assertEqual(metrics["task_total"], 1)
            self.assertEqual(metrics["task_counts"][detail["task"]["status"]], 1)
            self.assertEqual(metrics["terminal_success_rate"], 1.0)
            self.assertIsNotNone(metrics["task_duration_p95_seconds"])
            self.assertTrue(metrics["p95_within_timeout"])
            self.assertIn("system", metrics)
            self.assertIn("storage_bytes", metrics["system"])

    def test_llm_usage_is_persisted_and_exposed_in_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                deepseek_input_cost_per_1k=1.0,
                deepseek_output_cost_per_1k=2.0,
            ))
            try:
                task = runtime.create_task(
                    "StockResearch",
                    {"as_of": "2026-11-05", "symbol": "600000.SH"},
                )
                runtime.llm.last_usage = {
                    "prompt_tokens": 100,
                    "completion_tokens": 25,
                    "total_tokens": 125,
                }
                runtime.llm.usage_history = [
                    {"prompt_tokens": 60, "completion_tokens": 10, "total_tokens": 70},
                    {"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55},
                ]
                runtime._record_llm_usage(task)
                summary = runtime.metrics()["llm_usage"]
                self.assertEqual(summary["request_count"], 2)
                self.assertEqual(summary["total_tokens"], 125)
                self.assertEqual(summary["cost_usd"], 0.15)
                audit = runtime.db.fetchall(
                    "SELECT event_type FROM audit_log WHERE event_type='LLM_USAGE_RECORDED'"
                )
                self.assertEqual(len(audit), 1)
            finally:
                runtime.close()

    def test_replay_persists_trace_evidence_and_block(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            detail = run_replay(runtime, ROOT / "tests/fixtures/replay/close-review.json")
            self.assertEqual(detail["task"]["status"], "BLOCKED")
            self.assertEqual(detail["decision"]["status"], "BLOCKED")
            self.assertGreaterEqual(len(detail["evidence"]), 3)
            self.assertGreaterEqual(len(detail["trace"]), 8)
            self.assertEqual(len(detail["tool_calls"]), len(detail["trace"]))
            self.assertIn("Bull Case Analyst", detail["debate"])
            self.assertIn("Bear Case Analyst", detail["debate"])
            self.assertIn("市场广度", detail["debate"]["Bull Case Analyst"]["points"][0])
            self.assertTrue(any(item["title"] == "持仓风险快照" for item in detail["evidence"]))
            self.assertTrue(any(item.get("used_by") for item in detail["evidence"]))
            self.assertTrue(any(
                "Final decision" in item.get("used_by", [])
                for item in detail["evidence"]
            ))
            self.assertTrue(any(event["event_type"] == "DECISION_CREATED" for event in detail["events"]))

    def test_task_data_bundle_and_replay_preserve_input_and_parent_link(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                original = runtime.create_task(
                    "MarketClose",
                    {"as_of": "2026-11-05"},
                    {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                )
                detail = runtime.wait_for_task(original.id)
                self.assertIsNotNone(detail)
                data = runtime.task_data(original.id)
                self.assertEqual(data["task_id"], original.id)
                self.assertIn(original.data_snapshot_id or detail["task"]["data_snapshot_id"], data["snapshot_ids"])
                self.assertTrue(data["bundles"])
                self.assertTrue(any(bundle["raw_payloads"] for bundle in data["bundles"]))

                replayed = runtime.replay_task(original.id)
                self.assertEqual(replayed.parent_task_id, original.id)
                self.assertEqual(replayed.target["_replay_of"], original.id)
                self.assertEqual(replayed.target["_fixture"], original.target["_fixture"])
                replay_detail = runtime.wait_for_task(replayed.id)
                self.assertIsNotNone(replay_detail)
                self.assertTrue(any(
                    event["event_type"] == "TASK_REPLAY_REQUESTED"
                    for event in replay_detail["events"]
                ))
            finally:
                runtime.close()

    def test_profile_is_versioned_and_recovery_marks_running_tasks_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "pia.sqlite3"
            runtime = PiaRuntime(Settings(
                db_path=db_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            first = runtime.get_profile()
            second = runtime.update_profile({**first["payload"], "risk_tolerance": "low"})
            self.assertEqual(second["version"], first["version"] + 1)
            task = Task(
                id="task_interrupted",
                user_id="default",
                trigger_type="MarketClose",
                target={"as_of": "2026-11-05"},
                status=TaskStatus.RUNNING,
                created_at=now_iso(),
            )
            runtime.db.create_task(task)
            recovered = PiaRuntime(Settings(
                db_path=db_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            detail = recovered.task_detail("task_interrupted")
            self.assertEqual(detail["task"]["status"], "RETRYABLE")
            self.assertEqual(detail["task"]["error"]["code"], "RUNTIME_RESTARTED")

    def test_sqlite_backup_can_restore_task_and_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.sqlite3"
            backup_path = root / "backup.sqlite3"
            restored_path = root / "restored.sqlite3"
            runtime = PiaRuntime(Settings(
                db_path=source_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            self.addCleanup(runtime.close)
            task = runtime.create_task(target={"as_of": "2026-11-05"})
            original = runtime.wait_for_task(task.id)
            pack = runtime.db.get_context_pack(task.id, "default")
            runtime.db.backup_to(backup_path)
            Database.restore_from(backup_path, restored_path)
            restored = PiaRuntime(Settings(
                db_path=restored_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            self.addCleanup(restored.close)
            self.assertEqual(restored.get_profile()["version"], 1)
            self.assertEqual(restored.db.get_context_pack(task.id, "default")["content_hash"], pack["content_hash"])
            self.assertEqual(restored.task_detail(task.id)["result_metadata"], original["result_metadata"])
            replay = restored.replay_task(task.id)
            self.assertEqual(restored.wait_for_task(replay.id)["decision"]["status"], original["decision"]["status"])

    def test_backup_package_restores_database_and_metadata_with_integrity_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.sqlite3"
            package_path = root / "pia-backup.zip"
            restored_path = root / "restored.sqlite3"
            metadata_root = root / "restored_metadata"
            runtime = PiaRuntime(Settings(
                db_path=source_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            manifest_path = create_backup_package(
                runtime.db,
                package_path,
                rules_path=ROOT / "rules/baseline.yaml",
                settings={"mode": "local"},
            )
            manifest = restore_backup_package(
                manifest_path,
                restored_path,
                metadata_root=metadata_root,
            )
            self.assertEqual(manifest["package_version"], "1")
            self.assertIn("pia.duckdb", manifest["files"])
            restored = PiaRuntime(Settings(
                db_path=restored_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=metadata_root / "rules" / "baseline.yaml",
            ))
            self.assertEqual(restored.get_profile()["version"], 1)
            self.assertTrue((metadata_root / "config" / "settings.json").exists())

    def test_duckdb_stores_and_restores_analytical_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "pia.sqlite3"
            analytics_path = root / "pia.duckdb"
            runtime = PiaRuntime(Settings(
                db_path=db_path,
                analytics_db_path=analytics_path,
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            detail = run_replay(runtime, ROOT / "tests/fixtures/replay/close-review.json")
            self.assertEqual(detail["task"]["status"], "BLOCKED")
            analytics = AnalyticsStore(analytics_path)
            self.assertGreaterEqual(analytics.count("raw_provider_payloads"), 2)
            self.assertGreaterEqual(analytics.count("analytical_snapshots"), 2)
            analytics.close()

            package_path = root / "pia-backup.zip"
            restored_db = root / "restored.sqlite3"
            restored_analytics = root / "restored.duckdb"
            manifest = create_backup_package(
                runtime.db,
                package_path,
                rules_path=ROOT / "rules/baseline.yaml",
                settings={"mode": "local"},
                analytics_path=analytics_path,
            )
            restore_backup_package(
                manifest,
                restored_db,
                metadata_root=root / "restored_metadata",
                destination_analytics=restored_analytics,
            )
            restored_store = AnalyticsStore(restored_analytics)
            self.assertEqual(restored_store.count("analytical_snapshots"), analytics.count("analytical_snapshots"))
            restored_store.close()

    def test_cloud_mode_reports_mode_and_supports_task_leases(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.cloud_policy_runtime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                mode="cloud",
            ))
            self.assertEqual(runtime.health()["runtime"], "cloud")
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "close-2026-11-05.json", "portfolio": "default.json"},
            )
            self.assertEqual(runtime.task_detail(task.id)["task"]["status"], "QUEUED")
            runtime.worker_loop("worker-a", once=True)
            self.assertIn(
                runtime.task_detail(task.id)["task"]["status"],
                {"BLOCKED", "NO_ACTION", "WAITING_APPROVAL", "FAILED", "RETRYABLE"},
            )

    def test_task_takeover_and_context_export_are_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.cloud_policy_runtime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                mode="cloud",
            ))
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "close-2026-11-05.json", "portfolio": "default.json"},
                user_id="user-a",
            )
            exported = runtime.task_context(task.id, "user-a", view="full")
            self.assertEqual(exported["task_detail"]["task"]["id"], task.id)
            self.assertEqual(
                exported["profile"]["payload"]["risk_tolerance"],
                "moderate",
            )
            taken_over = runtime.takeover_task(task.id, "user-a", "Investigate provider failure")
            self.assertEqual(taken_over["task_detail"]["task"]["id"], task.id)
            self.assertTrue(any(
                event["event_type"] == "TASK_MANUAL_TAKEOVER"
                for event in taken_over["task_detail"]["events"]
            ))
            audit = runtime.db.fetchall(
                "SELECT event_type, user_id FROM audit_log WHERE task_id=?",
                (task.id,),
            )
            self.assertTrue(any(
                row["event_type"] == "TASK_MANUAL_TAKEOVER" and row["user_id"] == "user-a"
                for row in audit
            ))

    def test_candidate_scan_is_ranked_and_replayable(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            result = runtime.scan_candidates("2026-11-05", "close-2026-11-05.json")
            self.assertEqual(result["snapshot_id"], "snap_20261105_close_fixture")
            self.assertEqual([item["symbol"] for item in result["candidates"]], ["510300.SH", "600000.SH"])

    def test_candidate_scan_respects_user_profile_universe_and_asset_types(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            runtime.update_profile({
                "risk_tolerance": "low",
                "investment_objective": "capital preservation",
                "allowed_asset_types": ["stock"],
                "universe": ["main"],
            }, user_id="user-a")
            result = runtime.scan_candidates(
                "2026-11-05",
                "close-2026-11-05.json",
                user_id="user-a",
            )
            self.assertEqual(result["user_id"], "user-a")
            self.assertEqual([item["symbol"] for item in result["candidates"]], ["600000.SH"])

    def test_stock_research_target_outside_profile_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            runtime.update_profile({
                "risk_tolerance": "low",
                "investment_objective": "capital preservation",
                "allowed_asset_types": ["stock"],
                "universe": ["main"],
            }, user_id="user-a")
            task = runtime.create_task(
                "StockResearch",
                {"as_of": "2026-11-05", "symbol": "510300.SH"},
                {"market": "close-2026-11-05.json", "portfolio": "empty.json"},
                user_id="user-a",
            )
            detail = runtime.wait_for_task(task.id, user_id="user-a")
            self.assertEqual(detail["task"]["status"], "BLOCKED")
            self.assertIn(
                "UNIVERSE_REJECTED",
                {reason["code"] for reason in detail["decision"]["rationale"]["rules"]["reasons"]},
            )

    def test_task_timeout_is_explicit_and_audit_is_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                task_timeout_seconds=0,
            ))
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "close-2026-11-05.json", "portfolio": "default.json"},
            )
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "TIMEOUT")
            with self.assertRaises(sqlite3.IntegrityError):
                runtime.db.execute("DELETE FROM audit_log")

    def test_task_expiration_is_terminal_and_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            try:
                task = runtime.create_task(
                    target={
                        "as_of": "2026-11-05",
                        "expires_at": "2020-01-01T00:00:00+00:00",
                    },
                    fixture={
                        "market": "close-2026-11-05.json",
                        "portfolio": "default.json",
                    },
                )
                detail = runtime.wait_for_task(task.id)
                self.assertEqual(detail["task"]["status"], "EXPIRED")
                self.assertEqual(detail["task"]["error"]["code"], "TASK_EXPIRED")
                self.assertTrue(any(
                    event["event_type"] == "TASK_STATUS"
                    and event["payload"]["status"] == "EXPIRED"
                    for event in detail["events"]
                ))
                audit = runtime.db.fetchall(
                    "SELECT event_type FROM audit_log WHERE task_id=?",
                    (task.id,),
                )
                self.assertIn("TASK_STATE_CHANGED", {row["event_type"] for row in audit})
            finally:
                runtime.close()

    def test_stock_research_persists_news_filing_and_research_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            task = runtime.create_task(
                "StockResearch",
                {"as_of": "2026-11-05", "symbol": "600000.SH"},
                {"market": "close-2026-11-05.json", "portfolio": "default.json"},
            )
            detail = runtime.wait_for_task(task.id)
            names = {row["agent_name"] for row in detail["trace"]}
            self.assertIn("Stock Researcher", names)
            self.assertIn("News Analyst", names)
            self.assertGreaterEqual(len(detail["evidence"]), 5)

    def test_live_evidence_preserves_provider_and_quality(self):
        class LiveProvider:
            provider_id = "live-test"

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=[
                        "market_snapshot",
                        "fundamentals",
                        "company_profile",
                        "news",
                        "filings",
                        "trading_calendar",
                    ],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_market_snapshot(self, as_of):
                snapshot = json.loads(
                    (ROOT / "tests/fixtures/market/close-2026-11-05.json").read_text()
                )
                snapshot["source"] = self.provider_id
                snapshot["quality"] = "partial"
                return snapshot

            def get_fundamentals(self, symbol, as_of=None):
                return {
                    "symbol": symbol,
                    "as_of": as_of,
                    "quality": "partial",
                    "observed_at": "2026-11-05T16:00:00+08:00",
                    "metrics": {},
                }

            def get_company_profile(self, symbol, as_of=None):
                return {
                    "symbol": symbol,
                    "name": "Live Company",
                    "industry": "Banking",
                    "as_of": as_of,
                    "quality": "verified",
                    "source": "live-test",
                    "observed_at": "2026-11-05T16:00:00+08:00",
                }

            def search_news(self, symbol, as_of=None):
                return [{
                    "id": "news_live_1",
                    "title": "Live update",
                    "published_at": f"{as_of}T10:00:00+08:00",
                    "source": "https://example.test/live-news",
                    "quality": "partial",
                    "symbol_verified": False,
                    "excerpt": "Unverified symbol provenance.",
                }]

            def search_filings(self, symbol, as_of):
                return []

            def get_trading_calendar(self, start_date, end_date):
                return [{"trade_date": start_date, "is_open": True}]

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            provider = LiveProvider()
            runtime.settings.data_provider = provider.provider_id
            runtime.providers = ProviderRegistry([provider])
            runtime.provider = provider
            runtime.db.save_portfolio_snapshot(
                {**runtime.fixture_provider.get_portfolio_snapshot("default.json"), "source": "import"}
            )
            task = runtime.create_task(
                "StockResearch",
                {"as_of": "2026-11-05", "symbol": "600000.SH"},
            )
            detail = runtime.wait_for_task(task.id)
            market_evidence = next(
                item for item in detail["evidence"] if item["source_type"] == "market"
            )
            news_evidence = next(
                item for item in detail["evidence"] if item["source_type"] == "news"
            )
            self.assertEqual(market_evidence["source"], "live-test")
            self.assertEqual(market_evidence["provider_id"], "live-test")
            self.assertEqual(market_evidence["quality"], "partial")
            company_evidence = next(
                item for item in detail["evidence"] if item["source_type"] == "company"
            )
            self.assertEqual(company_evidence["quality"], "verified")
            self.assertEqual(news_evidence["provider_id"], "live-test")
            self.assertEqual(news_evidence["quality"], "partial")
            self.assertEqual(news_evidence["source_uri"], "https://example.test/live-news")

    def test_research_provenance_tracks_provider_per_capability(self):
        class Provider:
            def __init__(self, provider_id):
                self.provider_id = provider_id

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                data_provider="akshare",
            ))
            try:
                fundamentals = {
                    "symbol": "600000.SH",
                    "quality": "verified",
                    "observed_at": "2026-11-05T16:00:00+08:00",
                    "metrics": {"pe": 8.2},
                }
                news = [{
                    "id": "news-provider-specific",
                    "title": "Provider-specific news",
                    "excerpt": "A cited update.",
                    "quality": "verified",
                }]
                filings = [{
                    "id": "filing-provider-specific",
                    "title": "Provider-specific filing",
                    "excerpt": "A cited filing.",
                    "quality": "verified",
                }]
                company_profile = {
                    "symbol": "600000.SH",
                    "name": "浦发银行",
                    "industry": "银行",
                    "source": "akshare",
                    "quality": "verified",
                    "observed_at": "2026-11-05T16:00:00+08:00",
                }
                calls = []

                def provider_call(capability, method_name, *args, **kwargs):
                    del method_name, args, kwargs
                    calls.append(capability)
                    if capability == "fundamentals":
                        return Provider("tushare"), fundamentals
                    if capability == "news":
                        return Provider("akshare"), news
                    if capability == "filings":
                        return Provider("tushare"), filings
                    if capability == "company_profile":
                        return Provider("akshare"), company_profile
                    raise AssertionError(capability)

                with patch.object(runtime, "_provider_call", side_effect=provider_call):
                    research = runtime._load_research("600000.SH", "2026-11-05")
                    cached_research = runtime._load_research("600000.SH", "2026-11-05")

                self.assertEqual(
                    research["provider_ids"],
                    {
                        "fundamentals": "tushare",
                        "news": "akshare",
                        "filings": "tushare",
                        "company_profile": "akshare",
                    },
                )
                self.assertEqual(research["company_profile"]["source"], "mixed")
                self.assertEqual(research["company_profile"]["name"], "浦发银行")
                self.assertEqual(research["company_profile"]["industry"], "银行")
                self.assertEqual(research["company_profile"]["provider_ids"], ["akshare", "tushare"])
                self.assertEqual(research["fundamentals"]["provider_id"], "tushare")
                self.assertEqual(research["news"][0]["provider_id"], "akshare")
                self.assertEqual(research["filings"][0]["provider_id"], "tushare")
                self.assertEqual(
                    cached_research["provider_ids"],
                    research["provider_ids"],
                )
                self.assertEqual(
                    calls,
                    ["fundamentals", "news", "filings", "company_profile"],
                )
            finally:
                runtime.close()

    def test_research_provider_calls_are_scoped_to_task_as_of(self):
        class Provider:
            def __init__(self):
                self.provider_id = "point-in-time-test"
                self.fundamentals_as_of = None
                self.news_as_of = None

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["fundamentals", "news", "filings"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_fundamentals(self, symbol, as_of=None):
                self.fundamentals_as_of = as_of
                return {
                    "symbol": symbol,
                    "as_of": as_of,
                    "observed_at": f"{as_of}T16:00:00+08:00",
                    "quality": "verified",
                    "metrics": {"pe": 8.2},
                }

            def search_news(self, symbol, as_of=None):
                self.news_as_of = as_of
                return [{
                    "id": "news-point-in-time",
                    "symbol": symbol,
                    "title": "Historical update",
                    "published_at": f"{as_of}T10:00:00+08:00",
                    "source": "https://example.test/historical-news",
                    "quality": "verified",
                    "excerpt": "Bound to the requested date.",
                }]

            def search_filings(self, symbol, as_of):
                return []

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                data_provider="fixture",
            ))
            provider = Provider()
            runtime.settings.data_provider = provider.provider_id
            runtime.providers = ProviderRegistry([provider])
            runtime.provider = provider
            research = runtime._load_research("600000.SH", "2026-11-04")
            self.assertEqual(provider.fundamentals_as_of, "2026-11-04")
            self.assertEqual(provider.news_as_of, "2026-11-04")
            self.assertEqual(research["fundamentals"]["as_of"], "2026-11-04")
            self.assertEqual(research["news"][0]["published_at"][:10], "2026-11-04")
            runtime.close()

    def test_provider_call_falls_back_after_request_failure(self):
        class Provider:
            def __init__(self, provider_id, fail):
                self.provider_id = provider_id
                self.fail = fail

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["market_snapshot"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_market_snapshot(self, as_of):
                if self.fail:
                    raise TimeoutError("upstream timeout")
                return {
                    "snapshot_id": "fallback-snapshot", "source": self.provider_id,
                    "as_of": as_of, "observed_at": f"{as_of}T16:00:00+08:00",
                    "quality": "verified", "breadth": 0.6, "index_trend": "up",
                    "volatility": 0.2,
                }

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            primary = Provider("primary-test", fail=True)
            secondary = Provider("secondary-test", fail=False)
            runtime.settings.data_provider = primary.provider_id
            runtime.settings.provider_fallback_enabled = True
            runtime.providers = ProviderRegistry([primary, secondary])
            runtime.provider = primary
            provider, snapshot = runtime._provider_call(
                "market_snapshot",
                "get_market_snapshot",
                "2026-11-05",
            )
            self.assertEqual(provider.provider_id, "secondary-test")
            self.assertEqual(snapshot["source"], "secondary-test")
            audit = runtime.db.fetchall(
                "SELECT event_type, payload_json FROM audit_log "
                "WHERE event_type='PROVIDER_ATTEMPT' AND payload_json LIKE '%secondary-test%'"
            )
            self.assertEqual(len(audit), 1)

    def test_provider_call_falls_back_after_degraded_research_quality(self):
        class Provider:
            def __init__(self, provider_id, quality):
                self.provider_id = provider_id
                self.quality = quality

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["fundamentals"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_fundamentals(self, symbol, as_of=None):
                return {
                    "symbol": symbol,
                    "as_of": as_of,
                    "quality": self.quality,
                    "metrics": {"pe": 8.2} if self.quality == "verified" else {},
                }

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            primary = Provider("primary-test", "partial")
            secondary = Provider("secondary-test", "verified")
            runtime.settings.data_provider = primary.provider_id
            runtime.settings.provider_fallback_enabled = True
            runtime.providers = ProviderRegistry([primary, secondary])
            provider, fundamentals = runtime._provider_call(
                "fundamentals",
                "get_fundamentals",
                "600000.SH",
                as_of="2026-11-05",
            )
            self.assertEqual(provider.provider_id, "secondary-test")
            self.assertEqual(fundamentals["quality"], "verified")
            degraded = runtime.db.fetchall(
                "SELECT event_type FROM audit_log "
                "WHERE event_type='PROVIDER_ATTEMPT' AND payload_json LIKE '%degraded%'"
            )
            self.assertEqual(len(degraded), 1)

    def test_live_provider_does_not_fallback_to_fixture(self):
        class Provider:
            provider_id = "primary-test"

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["market_snapshot"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_market_snapshot(self, as_of):
                raise TimeoutError("upstream timeout")

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            primary = Provider()
            runtime.settings.data_provider = primary.provider_id
            runtime.settings.provider_fallback_enabled = True
            runtime.providers = ProviderRegistry([primary, runtime.fixture_provider])
            runtime.provider = primary

            with self.assertRaisesRegex(RuntimeError, "CAPABILITY_UNAVAILABLE"):
                runtime._provider_call(
                    "market_snapshot",
                    "get_market_snapshot",
                    "2026-11-05",
                )

    def test_market_sync_falls_back_after_degraded_quality_without_exception(self):
        class Provider:
            def __init__(self, provider_id):
                self.provider_id = provider_id

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["market_snapshot"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_market_snapshot(self, as_of):
                return {
                    "snapshot_id": f"{self.provider_id}-snapshot",
                    "as_of": as_of, "observed_at": f"{as_of}T16:00:00+08:00",
                    "source": self.provider_id, "breadth": 0.6,
                    "index_trend": "up", "volatility": 0.2,
                    "quality": "partial" if self.provider_id == "primary-test" else "verified",
                }

        class StubWorker:
            def __init__(self, provider, analytics, observability=None, call_provider=None):
                self.provider = provider
                self.call_provider = call_provider

            def sync_market_data(self, as_of, symbols):
                provider, snapshot = self.call_provider("market_snapshot", "get_market_snapshot", as_of)
                quality = snapshot["quality"]
                return {
                    "provider_id": provider.provider_id,
                    "as_of": as_of,
                    "quality": quality,
                    "market_snapshot_quality": quality,
                    "market_snapshot": snapshot,
                    "failures": [],
                    "derived_events": [],
                }

        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            primary = Provider("primary-test")
            secondary = Provider("secondary-test")
            runtime.settings.data_provider = primary.provider_id
            runtime.settings.provider_fallback_enabled = True
            runtime.providers = ProviderRegistry([primary, secondary])
            with patch("pia_runtime.runtime.DataWorker", StubWorker):
                with patch.object(runtime.db, "save_market_snapshot"):
                    result = runtime.sync_market_data("2026-11-05", [])
            self.assertEqual(result["provider_id"], "secondary-test")
            self.assertEqual(result["quality"], "verified")
            self.assertEqual(
                [attempt["provider_id"] for attempt in result["provider_attempts"]],
                ["primary-test", "secondary-test"],
            )

    def test_approval_cannot_bypass_block(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            detail = run_replay(runtime, ROOT / "tests/fixtures/replay/close-review.json")
            with self.assertRaises(ValueError):
                runtime.approve_task(detail["task"]["id"], "APPROVE")

    def test_no_action_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "close-low-breadth.json", "portfolio": "empty.json"},
            )
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "NO_ACTION")
            with self.assertRaises(ValueError):
                runtime.approve_task(task.id, "APPROVE")

    def test_approval_can_request_follow_up_research(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            task = runtime.create_task(
                target={
                    "as_of": "2026-11-05",
                    "symbol": "600000.SH",
                    "suggested_action": "BUY_CANDIDATE",
                },
                fixture={"market": "close-2026-11-05.json", "portfolio": "empty.json"},
            )
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "WAITING_APPROVAL")
            result = runtime.approve_task(
                task.id,
                "REQUEST_MORE_RESEARCH",
                "Check the latest filing before deciding.",
            )
            self.assertEqual(result["task"]["status"], "NO_ACTION")
            self.assertEqual(result["follow_up_task"]["parent_task_id"], task.id)
            self.assertTrue(
                any(
                    event["event_type"] == "FOLLOW_UP_RESEARCH_REQUESTED"
                    for event in runtime.task_detail(task.id)["events"]
                )
            )

    def test_approval_can_mark_symbol_as_watch(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            task = runtime.create_task(
                target={
                    "as_of": "2026-11-05",
                    "symbol": "600000.SH",
                    "suggested_action": "BUY_CANDIDATE",
                },
                fixture={"market": "close-2026-11-05.json", "portfolio": "empty.json"},
            )
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "WAITING_APPROVAL")
            result = runtime.approve_task(task.id, "MARK_AS_WATCH")
            self.assertEqual(result["task"]["status"], "NO_ACTION")
            self.assertEqual(result["watchlist"]["name"], "Research watchlist")
            self.assertIn("600000.SH", result["watchlist"]["symbols"])
            self.assertEqual(
                runtime.list_watchlists()[0]["symbols"],
                ["600000.SH"],
            )

    def test_cancel_task_is_terminal_and_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.cloud_policy_runtime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                mode="cloud",
            ))
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "close-2026-11-05.json", "portfolio": "default.json"},
                user_id="user-a",
            )
            cancelled = runtime.cancel_task(task.id, "user-a", "No longer needed")
            self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
            detail = runtime.task_detail(task.id, "user-a")
            self.assertEqual(detail["task"]["status"], "CANCELLED")
            self.assertEqual(detail["task"]["error"]["code"], "TASK_CANCELLED")
            self.assertTrue(any(
                event["event_type"] == "TASK_CANCELLED"
                for event in detail["events"]
            ))
            audit = runtime.db.fetchall(
                "SELECT event_type, user_id FROM audit_log WHERE task_id=?",
                (task.id,),
            )
            self.assertTrue(any(
                row["event_type"] == "TASK_CANCELLED" and row["user_id"] == "user-a"
                for row in audit
            ))
            with self.assertRaises(ValueError):
                runtime.cancel_task(task.id, "user-a")

    def test_wait_for_task_returns_immediately_for_cancelled_task(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            task = runtime.create_task(target={"as_of": "2026-11-05"})
            runtime.cancel_task(task.id, reason="cancelled in test")
            detail = runtime.wait_for_task(task.id, timeout=0.01)
            self.assertEqual(detail["task"]["status"], "CANCELLED")

    def test_retry_preserves_fixture_and_parent_link(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "missing.json", "portfolio": "default.json"},
            )
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "FAILED")
            retry = runtime.retry_task(task.id)
            self.assertEqual(retry.parent_task_id, task.id)
            self.assertEqual(retry.target["_fixture"]["market"], "missing.json")
            self.assertEqual(runtime.wait_for_task(retry.id)["task"]["status"], "FAILED")

    def test_retry_inherits_completed_snapshot_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                require_llm=True,
                autostart_tasks=True,
            ))
            task = runtime.create_task(target={"as_of": "2026-11-05"})
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "RETRYABLE")
            self.assertEqual(detail["task"]["error"]["code"], "CREDENTIALS_REQUIRED")
            self.assertEqual(detail["task"]["target"]["_checkpoint_stage"], "snapshots_ready")
            retry = runtime.retry_task(task.id)
            self.assertEqual(
                retry.target["_market_snapshot_id"],
                detail["task"]["data_snapshot_id"],
            )
            self.assertEqual(
                retry.target["_portfolio_snapshot_id"],
                "portfolio_20261105_fixture",
            )
            audit = runtime.db.fetchall(
                "SELECT * FROM audit_log WHERE task_id=? AND event_type='TASK_RETRY_CREATED'",
                (retry.id,),
            )
            self.assertEqual(len(audit), 1)
            runtime.close()

    def test_explicit_portfolio_fixture_overrides_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            runtime.import_portfolio("manual", [{
                "symbol": "600000.SH",
                "quantity": 30000,
                "avg_cost": 11.82,
                "market_value": 373200,
            }])
            task = runtime.create_task(
                target={"as_of": "2026-11-05", "suggested_action": "BUY_CANDIDATE"},
                fixture={
                    "market": "close-2026-11-05.json",
                    "portfolio": "empty.json",
                },
            )
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "WAITING_APPROVAL")
            snapshot_ready = next(
                event for event in detail["events"]
                if event["event_type"] == "DATA_SNAPSHOT_READY"
            )
            self.assertEqual(
                snapshot_ready["payload"]["portfolio_snapshot_id"],
                "portfolio_20261105_empty",
            )

    def test_event_engine_deduplicates_market_close(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            payload = {
                "as_of": "2026-11-05",
                "fixture": {"market": "close-2026-11-05.json", "portfolio": "default.json"},
            }
            first = runtime.ingest_event("MarketClose", payload, "market-close-2026-11-05")
            second = runtime.ingest_event("MarketClose", payload, "market-close-2026-11-05")
            runtime.wait_for_task(first["task_id"])
            self.assertEqual(first["status"], "DISPATCHED")
            self.assertEqual(second["status"], "DEDUPED")
            self.assertEqual(first["task_id"], second["task_id"])

    def test_event_cooldown_uses_event_time_and_expires_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            first = runtime.ingest_event(
                "MarketBreadthChanged",
                {"as_of": "2026-11-05", "breadth": 0.5, "cooldown_seconds": 86400},
            )
            second = runtime.ingest_event(
                "MarketBreadthChanged",
                {"as_of": "2026-11-05", "breadth": 0.2, "cooldown_seconds": 86400},
            )
            self.assertEqual(first["status"], "DISPATCHED")
            self.assertEqual(second["status"], "DEDUPED")
            expired = runtime.ingest_event(
                "FilingPublished",
                {
                    "as_of": "2026-11-05",
                    "expires_at": "2020-01-01T00:00:00+00:00",
                },
            )
            self.assertEqual(expired["status"], "EXPIRED")
            self.assertIsNone(expired["task_id"])

    def test_priority_event_preemption_is_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.cloud_policy_runtime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                mode="cloud",
                autostart_tasks=False,
            ))
            low_a = runtime.create_task(
                target={"_priority": 10},
                user_id="user-a",
            )
            low_b = runtime.create_task(
                target={"_priority": 10},
                user_id="user-b",
            )
            runtime.ingest_event(
                "PortfolioRiskChanged",
                {"account_id": "user-a", "as_of": "2026-11-05"},
                user_id="user-a",
            )
            self.assertEqual(runtime.task_detail(low_a.id, "user-a")["task"]["status"], "CANCELLED")
            self.assertEqual(runtime.task_detail(low_b.id, "user-b")["task"]["status"], "QUEUED")

    def test_queued_tasks_are_ordered_by_event_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            ordinary = runtime.create_task(
                target={"as_of": "2026-11-05", "_priority": 60},
            )
            urgent = runtime.create_task(
                "PortfolioRiskChanged",
                {"as_of": "2026-11-05", "_priority": 100},
            )
            self.assertEqual(runtime.db.list_queued_tasks()[0].id, urgent.id)
            self.assertEqual(runtime.db.list_queued_tasks()[1].id, ordinary.id)

    def test_expired_lease_can_be_reclaimed_and_is_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            task = runtime.create_task(target={"as_of": "2026-11-05"})
            first = runtime.db.acquire_lease(task.id, "worker-a", ttl_seconds=0)
            second = runtime.db.acquire_lease(task.id, "worker-b", ttl_seconds=60)
            self.assertNotEqual(first["lease_id"], second["lease_id"])
            audit = runtime.db.connection.execute(
                "SELECT event_type FROM audit_log WHERE task_id=? ORDER BY id",
                (task.id,),
            ).fetchall()
            self.assertIn("TASK_LEASE_EXPIRED", {row["event_type"] for row in audit})

    def test_failed_event_delivery_is_retried_with_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            result = runtime.ingest_event(
                "MarketClose",
                {
                    "as_of": "2026-11-05",
                    "fixture": {"market": "missing.json", "portfolio": "default.json"},
                },
                "retryable-market-close",
            )
            task = runtime.db.get_task(result["task_id"])
            runtime.run_task(task.id, task.target["_fixture"])
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["task"]["status"], "FAILED")
            delivery = runtime.db.connection.execute(
                "SELECT status, attempt, next_retry_at FROM event_deliveries WHERE event_id=?",
                (result["event_id"],),
            ).fetchone()
            self.assertEqual(delivery["status"], "RETRY_SCHEDULED")
            self.assertEqual(delivery["attempt"], 1)
            runtime.db.execute(
                "UPDATE event_deliveries SET next_retry_at=? WHERE event_id=?",
                ("2000-01-01T00:00:00+00:00", result["event_id"]),
            )
            self.assertEqual(runtime.events.retry_due_events(), 1)
            tasks = runtime.db.list_tasks()
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0].target["_event_id"], result["event_id"])

    def test_worker_once_processes_due_event_retry_without_queued_task(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.cloud_policy_runtime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                mode="cloud",
                autostart_tasks=False,
            ))
            result = runtime.ingest_event(
                "MarketClose",
                {
                    "as_of": "2026-11-05",
                    "fixture": {"market": "missing.json", "portfolio": "default.json"},
                },
                "worker-once-retry",
            )
            runtime.worker_loop("worker-once", once=True)
            task = runtime.db.get_task(result["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.status, TaskStatus.FAILED)
            runtime.db.execute(
                "UPDATE event_deliveries SET next_retry_at=? WHERE event_id=?",
                ("2000-01-01T00:00:00+00:00", result["event_id"]),
            )
            runtime.worker_loop("worker-once", once=True)
            tasks = runtime.db.list_tasks()
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0].target["_event_id"], result["event_id"])
            self.assertEqual(tasks[1].target["_event_id"], result["event_id"])

    def test_user_scoped_tasks_profiles_and_approvals_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            profile = {
                "risk_tolerance": "low",
                "investment_objective": "preserve capital",
                "allowed_asset_types": ["stock"],
                "universe": ["main"],
            }
            runtime.update_profile(profile, "user-b")
            task_a = runtime.create_task(
                target={"as_of": "2026-11-05"},
                user_id="default",
            )
            task_b = runtime.create_task(
                target={"as_of": "2026-11-05"},
                user_id="user-b",
            )
            self.assertEqual([item["id"] for item in runtime.list_tasks("default")], [task_a.id])
            self.assertEqual([item["id"] for item in runtime.list_tasks("user-b")], [task_b.id])
            self.assertIsNone(runtime.task_detail(task_a.id, "user-b"))
            self.assertEqual(runtime.get_profile("user-b")["payload"], profile)
            with self.assertRaises(KeyError):
                runtime.approve_task(task_a.id, "REJECT", user_id="user-b")

    def test_user_approval_audit_keeps_user_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            task = runtime.create_task(
                target={"as_of": "2026-11-05", "suggested_action": "BUY_CANDIDATE"},
                fixture={
                    "market": "close-2026-11-05.json",
                    "portfolio": "empty.json",
                },
                user_id="user-b",
            )
            detail = runtime.wait_for_task(task.id, user_id="user-b")
            self.assertEqual(detail["task"]["status"], "WAITING_APPROVAL")
            with self.assertRaisesRegex(ValueError, "ACTION_NOT_ELIGIBLE"):
                runtime.approve_task(task.id, "APPROVE", user_id="user-b")
            runtime.approve_task(task.id, "NO_ACTION", user_id="user-b")
            audit = runtime.db.fetchall(
                "SELECT user_id, event_type, payload_json FROM audit_log WHERE task_id=?",
                (task.id,),
            )
            approval_audit = next(
                row for row in audit if row["event_type"] == "APPROVAL_RECORDED"
            )
            self.assertEqual(approval_audit["user_id"], "user-b")
            self.assertIn('"user_id": "user-b"', approval_audit["payload_json"])

    def test_user_tasks_use_user_profile_and_latest_portfolio_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            imported = runtime.import_portfolio("manual", [
                {
                    "symbol": "600000.SH",
                    "quantity": 10,
                    "avg_cost": 10,
                    "market_value": 100,
                },
            ], user_id="user-b", as_of="2026-11-05")
            task = runtime.create_task(
                target={"as_of": "2026-11-05"},
                fixture={"market": "close-2026-11-05.json"},
                user_id="user-b",
            )
            runtime.run_task(task.id, task.target["_fixture"])
            detail = runtime.wait_for_task(task.id, user_id="user-b")
            self.assertEqual(
                next(item["snapshot_id"] for item in detail["evidence"] if item["source_type"] == "portfolio"),
                imported["snapshot_id"],
            )
            self.assertEqual(runtime.get_profile("user-b")["user_id"], "user-b")

    def test_risk_event_dispatches_a_task(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            result = runtime.ingest_event(
                "PortfolioRiskChanged",
                {
                    "as_of": "2026-11-05",
                    "fixture": {"market": "close-2026-11-05.json", "portfolio": "default.json"},
                },
                "risk-2026-11-05",
            )
            detail = runtime.wait_for_task(result["task_id"])
            self.assertEqual(result["status"], "DISPATCHED")
            self.assertEqual(detail["task"]["trigger_type"], "PortfolioRiskChanged")
            notifications = runtime.db.list_notifications(unread_only=True)
            notification = next(item for item in notifications if item["task_id"] == result["task_id"])
            self.assertEqual(notification["title"], "持仓风险变化任务已创建")
            notification_id = notification["id"]
            deliveries = runtime.db.list_notification_deliveries(
                notification_id,
                user_id="default",
            )
            self.assertTrue(deliveries)
            self.assertEqual(deliveries[0]["notification_id"], notification_id)
            self.assertEqual(deliveries[0]["user_id"], "default")

    def test_notification_failure_audit_keeps_user_scope_without_task(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            try:
                class FailingNotifier:
                    def deliver(self, *args, **kwargs):
                        return NotificationReceipt(
                            "FAILED",
                            "test-gateway",
                            "gateway unavailable",
                        )

                runtime.notifier = FailingNotifier()
                result = runtime.ingest_event(
                    "UnknownEvent",
                    {"reason": "test"},
                    dedupe_key="notification-user-scope",
                    user_id="user-b",
                )
                self.assertEqual(result["status"], "RECEIVED")
                rows = runtime.db.fetchall(
                    "SELECT * FROM audit_log WHERE event_type=? AND user_id=?",
                    ("NOTIFICATION_DELIVERY_FAILED", "user-b"),
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(
                    runtime.db.fetchall(
                        "SELECT * FROM audit_log WHERE event_type=? AND user_id=?",
                        ("NOTIFICATION_DELIVERY_FAILED", "default"),
                    ),
                    [],
                )
            finally:
                runtime.close()

    def test_ruleset_versions_are_user_scoped_and_task_snapshots_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            first = runtime.create_task(user_id="default")
            updated = dict(runtime.rules)
            updated["version"] = "v2"
            updated["max_position_weight"] = 0.05
            result = runtime.update_rules(updated, "default")
            second = runtime.create_task(user_id="default")
            user_b = dict(runtime.rules)
            user_b["version"] = "v1-user-b"
            user_b_result = runtime.update_rules(user_b, "user-b")
            user_b_task = runtime.create_task(user_id="user-b")

            self.assertEqual(first.rule_snapshot_id, "ruleset_v1")
            self.assertEqual(second.rule_snapshot_id, result["rule_snapshot_id"])
            self.assertNotEqual(first.rule_snapshot_id, second.rule_snapshot_id)
            self.assertEqual(user_b_task.rule_snapshot_id, user_b_result["rule_snapshot_id"])
            self.assertEqual(runtime.task_context(first.id, view="full")["rules"]["version"], "v1")
            self.assertEqual(runtime.task_context(second.id, view="full")["rules"]["version"], "v2")

    def test_data_quality_event_forces_a_blocked_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            result = runtime.ingest_event(
                "DataQualityDegraded",
                {
                    "as_of": "2026-11-05",
                    "quality": "unavailable",
                    "reason": "provider field contract changed",
                    "fixture": {"market": "close-2026-11-05.json", "portfolio": "empty.json"},
                },
                "quality-2026-11-05",
            )
            detail = runtime.wait_for_task(result["task_id"])
            self.assertEqual(detail["decision"]["status"], "BLOCKED")
            self.assertIn(
                "DATA_UNAVAILABLE",
                {reason["code"] for reason in detail["decision"]["rationale"]["rules"]["reasons"]},
            )

    def test_manual_portfolio_import_normalizes_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
            ))
            snapshot = runtime.import_portfolio("manual", [
                {"symbol": "600000.SH", "quantity": 10, "avg_cost": 10, "market_value": 100},
                {"symbol": "510300.SH", "quantity": 20, "avg_cost": 5, "market_value": 100},
            ])
            self.assertEqual(snapshot["total_value"], 200)
            self.assertAlmostEqual(snapshot["positions"][0]["weight"], 0.5)

    def test_pause_resume_preserves_task_and_emits_control_events(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = PiaRuntime(Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            ))
            entered = threading.Event()
            release = threading.Event()
            original = runtime._run_agent

            def paused_agent(task, name, input_data, output_data, **kwargs):
                if not entered.is_set():
                    entered.set()
                    release.wait(timeout=2)
                return original(task, name, input_data, output_data, **kwargs)

            runtime._run_agent = paused_agent
            task = runtime.create_task(
                target={"as_of": "2026-11-05", "suggested_action": "BUY_CANDIDATE"},
                fixture={"market": "close-2026-11-05.json", "portfolio": "empty.json"},
            )
            runtime.run_task(task.id, task.target["_fixture"])
            self.assertTrue(entered.wait(timeout=2))
            self.assertEqual(runtime.pause_task(task.id).status, TaskStatus.PAUSED)
            self.assertEqual(runtime.task_detail(task.id)["task"]["status"], "PAUSED")
            self.assertEqual(runtime.resume_task(task.id).status, TaskStatus.RUNNING)
            release.set()
            detail = runtime.wait_for_task(task.id)
            self.assertEqual(detail["decision"]["status"], "WATCH")
            event_types = {event["event_type"] for event in detail["events"]}
            self.assertIn("TASK_PAUSED", event_types)
            self.assertIn("TASK_RESUMED", event_types)

    def test_pause_resume_controls_worker_from_separate_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                db_path=Path(directory) / "pia.sqlite3",
                fixture_dir=ROOT / "tests/fixtures",
                rules_path=ROOT / "rules/baseline.yaml",
                autostart_tasks=False,
            )
            api_runtime = PiaRuntime(settings)
            worker_runtime = PiaRuntime(settings)
            entered = threading.Event()
            release = threading.Event()
            original = worker_runtime._run_agent

            def blocked_agent(task, name, input_data, output_data, **kwargs):
                if not entered.is_set():
                    entered.set()
                    release.wait(timeout=2)
                return original(task, name, input_data, output_data, **kwargs)

            worker_runtime._run_agent = blocked_agent
            try:
                task = api_runtime.create_task(
                    target={"as_of": "2026-11-05", "suggested_action": "BUY_CANDIDATE"},
                    fixture={
                        "market": "close-2026-11-05.json",
                        "portfolio": "empty.json",
                    },
                )
                worker_runtime.run_task(task.id, task.target["_fixture"])
                self.assertTrue(entered.wait(timeout=2))

                paused = api_runtime.pause_task(task.id)
                self.assertEqual(paused.status, TaskStatus.PAUSED)
                release.set()
                for _ in range(20):
                    if api_runtime.db.get_task(task.id).status == TaskStatus.PAUSED:
                        break
                    time.sleep(0.05)
                self.assertEqual(api_runtime.db.get_task(task.id).status, TaskStatus.PAUSED)

                resumed = api_runtime.resume_task(task.id)
                self.assertEqual(resumed.status, TaskStatus.RUNNING)
                detail = worker_runtime.wait_for_task(task.id, timeout=5)
                self.assertEqual(detail["decision"]["status"], "WATCH")
            finally:
                api_runtime.close()
                worker_runtime.close()


if __name__ == "__main__":
    unittest.main()
