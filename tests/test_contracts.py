import json
import unittest
from pathlib import Path

import yaml
from pia_runtime.api import SSE_TERMINAL_TASK_STATUSES
from pia_runtime.security import AGENT_TOOL_PERMISSIONS


ROOT = Path(__file__).resolve().parents[1]


class ContractTest(unittest.TestCase):
    def test_sse_stream_closes_for_all_terminal_task_statuses(self):
        self.assertTrue({"DONE", "EXPIRED"} <= SSE_TERMINAL_TASK_STATUSES)

    def test_agent_contracts_match_runtime_permissions(self):
        contracts = list((ROOT / "agents").glob("*.yaml"))
        self.assertTrue(contracts)
        expected_agents = {
            "Investment Chief",
            "Market Analyst",
            "Sector Analyst",
            "Stock Researcher",
            "Technical Analyst",
            "Portfolio Analyst",
            "News Analyst",
            "Risk / Rules Agent",
            "Decision Agent",
            "Research Manager",
            "Bull Case Analyst",
            "Bear Case Analyst",
            "Debate Chair",
        }
        declared_agents = set()
        for path in contracts:
            contract = json.loads(path.read_text())
            name = contract["name"]
            declared_agents.add(name)
            self.assertIn(name, AGENT_TOOL_PERMISSIONS, path.name)
            for tool_name in contract["tools"]:
                self.assertIn(
                    tool_name,
                    AGENT_TOOL_PERMISSIONS[name],
                    f"{path.name}: {name} cannot call {tool_name}",
                )
        self.assertTrue(expected_agents <= declared_agents)

    def test_mobile_approval_actions_match_cloud_contract(self):
        actions = ("APPROVE", "REJECT", "NO_ACTION", "REQUEST_MORE_RESEARCH", "MARK_AS_WATCH")
        clients = {
            "desktop": (ROOT / "apps/desktop/src/App.tsx").read_text(),
            "ios": (ROOT / "apps/ios/PiaMobileClient/Sources/PiaApp/PiaApp.swift").read_text(),
            "android": "\n".join(path.read_text() for path in (ROOT / "apps/android/app/src/main/java/com/pia/mobile").rglob("*.kt")),
        }
        for client, source in clients.items():
            for action in actions:
                self.assertIn(action, source, f"{client} is missing approval action {action}")

    def test_android_approval_actions_are_forwarded_to_api(self):
        source = "\n".join(path.read_text() for path in (ROOT / "apps/android/app/src/main/java/com/pia/mobile").rglob("*.kt"))
        self.assertRegex(source, r'"REQUEST_MORE_RESEARCH",\s*"MARK_AS_WATCH"\s*->\s*client\.approve')

    def test_mobile_failure_state_exposes_task_takeover(self):
        clients = {
            "ios": (ROOT / "apps/ios/PiaMobileClient/Sources/PiaApp/PiaApp.swift").read_text(),
            "android": "\n".join(path.read_text() for path in (ROOT / "apps/android/app/src/main/java/com/pia/mobile").rglob("*.kt")),
        }
        for client, source in clients.items():
            self.assertTrue(
                "Take over" in source or "人工接管" in source,
                f"{client} is missing task takeover UI",
            )
        self.assertIn(
            'try await client.takeover(\n                                taskID: task.id,',
            clients["ios"],
        )
        self.assertIn(
            '"TAKEOVER" -> client.takeover(task.id, "Taken over from Android")',
            clients["android"],
        )

    def test_openapi_declares_every_runtime_api_operation(self):
        document = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text())
        paths = document["paths"]
        expected = {
            ("/api/health", "get"),
            ("/api/settings/deepseek", "get"),
            ("/api/settings/deepseek", "post"),
            ("/api/settings/deepseek", "delete"),
            ("/api/providers", "get"),
            ("/api/metrics", "get"),
            ("/api/rules", "get"),
            ("/api/rules", "post"),
            ("/api/profile", "get"),
            ("/api/profile", "post"),
            ("/api/portfolio", "get"),
            ("/api/market", "get"),
            ("/api/audit", "get"),
            ("/api/scheduler", "get"),
            ("/api/scheduler/start", "post"),
            ("/api/scheduler/stop", "post"),
            ("/api/data/sync", "post"),
            ("/api/tasks", "get"),
            ("/api/tasks", "post"),
            ("/api/journal", "get"),
            ("/api/journal/summary", "get"),
            ("/api/journal/patterns", "get"),
            ("/api/journal/memory-candidates", "post"),
            ("/api/journal/memory-candidates/{candidate_id}/review", "post"),
            ("/api/journal/memory-candidates/{candidate_id}/usage", "get"),
            ("/api/journal/memory-candidates/{candidate_id}/feedback", "post"),
            ("/api/tasks/{task_id}", "get"),
            ("/api/tasks/{task_id}/context", "get"),
            ("/api/tasks/{task_id}/retrospectives", "get"),
            ("/api/tasks/{task_id}/retrospectives", "post"),
            ("/api/tasks/{task_id}/events", "get"),
            ("/api/tasks/{task_id}/lease", "get"),
            ("/api/tasks/{task_id}/approve", "post"),
            ("/api/tasks/{task_id}/retry", "post"),
            ("/api/tasks/{task_id}/cancel", "post"),
            ("/api/tasks/{task_id}/takeover", "post"),
            ("/api/tasks/{task_id}/pause", "post"),
            ("/api/tasks/{task_id}/resume", "post"),
            ("/api/leases/{lease_id}/heartbeat", "post"),
            ("/api/leases/{lease_id}/release", "post"),
            ("/api/events", "get"),
            ("/api/events", "post"),
            ("/api/portfolio/import", "post"),
            ("/api/portfolio/positions", "post"),
            ("/api/candidates", "get"),
            ("/api/notifications", "get"),
            ("/api/notifications/{notification_id}/anomalies", "get"),
            ("/api/notifications/{notification_id}/read", "post"),
            ("/api/notifications/{notification_id}/deliveries", "get"),
            ("/api/devices", "get"),
            ("/api/devices", "post"),
            ("/api/devices/{device_id}", "delete"),
            ("/api/sync", "get"),
        }
        declared = {
            (path, method)
            for path, operations in paths.items()
            for method in operations
            if method in {"get", "post", "delete", "put", "patch"}
        }
        self.assertTrue(expected <= declared, sorted(expected - declared))

    def test_openapi_metrics_declares_runtime_system_fields(self):
        document = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text())
        metrics = document["components"]["schemas"]["MetricsResponse"]
        self.assertTrue(
            {
                "task_total",
                "terminal_success_rate",
                "task_duration_p95_seconds",
                "p95_within_timeout",
                "system",
                "llm_usage",
                "observability",
            }.issubset(metrics["required"])
        )
        self.assertTrue(
            {
                "queue_depth",
                "active_task_count",
                "oldest_active_task_age_seconds",
                "storage_bytes",
                "database_backend",
            }.issubset(metrics["properties"]["system"]["required"])
        )

    def test_schema_files_are_valid_json(self):
        for path in (ROOT / "contracts/schemas").glob("*.json"):
            payload = json.loads(path.read_text())
            self.assertIn("$schema", payload)
            self.assertIn("properties", payload)

    def test_device_contract_matches_repository_response_fields(self):
        schema = json.loads((ROOT / "contracts/schemas/device.json").read_text())
        self.assertIn("last_seen_at", schema["properties"])
        self.assertNotIn("updated_at", schema["properties"])
        openapi = (ROOT / "contracts/openapi.yaml").read_text()
        self.assertIn("last_seen_at: {type: string, format: date-time}", openapi)
        self.assertNotIn("updated_at: {type: string, format: date-time}", openapi)

    def test_desktop_shell_exposes_documented_tray_controls(self):
        source = (ROOT / "apps/desktop/src-tauri/src/main.rs").read_text()
        for menu_id in ("status", "pause-scheduler", "resume-scheduler", "quit"):
            self.assertIn(f'"{menu_id}"', source)
        self.assertIn('app.emit("pia://tray"', source)
        self.assertIn("api.prevent_close()", source)

    def test_desktop_workspace_exposes_documented_shortcuts(self):
        source = (ROOT / "apps/desktop/src/App.tsx").read_text()
        search = (ROOT / "apps/desktop/src/components/WorkspaceSearch.tsx").read_text()
        self.assertIn('key === "k"', source)
        self.assertIn('key === "p"', source)
        self.assertIn('event.key === "Enter"', source)
        self.assertIn('data-shortcut="new-review"', source)
        self.assertIn('aria-label="搜索名称、代码或研究"', search)
        self.assertIn("visibleTasks", source)
        for chart in ("市场宽度", "指数趋势", "持仓暴露", "回撤", "研究过程时间线"):
            self.assertIn(f'<ChartFrame title="{chart}"', source)

    def test_migration_contains_audit_and_task_tables(self):
        migration = (ROOT / "migrations/001_initial.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS research_tasks", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS audit_log", migration)

    def test_event_scope_migration_contains_user_partition(self):
        migration = (ROOT / "migrations/010_event_user_scope.sql").read_text()
        self.assertIn("ALTER TABLE events ADD COLUMN user_id", migration)
        postgres_migration = (ROOT / "migrations/postgres/002_event_user_scope.sql").read_text()
        self.assertIn("ADD COLUMN IF NOT EXISTS user_id", postgres_migration)

    def test_audit_scope_migration_contains_user_partition(self):
        migration = (ROOT / "migrations/011_audit_user_scope.sql").read_text()
        self.assertIn("ALTER TABLE audit_log ADD COLUMN user_id", migration)
        postgres_migration = (ROOT / "migrations/postgres/003_audit_user_scope.sql").read_text()
        self.assertIn("ADD COLUMN IF NOT EXISTS user_id", postgres_migration)

    def test_llm_usage_migration_has_sqlite_and_postgres_parity(self):
        sqlite_migration = (ROOT / "migrations/014_llm_usage.sql").read_text()
        postgres_migration = (ROOT / "migrations/postgres/014_llm_usage.sql").read_text()
        for migration in (sqlite_migration, postgres_migration):
            self.assertIn("CREATE TABLE IF NOT EXISTS llm_usage", migration)
            self.assertIn("prompt_tokens", migration)
            self.assertIn("completion_tokens", migration)
            self.assertIn("cost_usd", migration)

    def test_retrospective_migration_has_sqlite_and_postgres_parity(self):
        sqlite_migration = (ROOT / "migrations/015_retrospectives.sql").read_text()
        postgres_migration = (ROOT / "migrations/postgres/015_retrospectives.sql").read_text()
        for migration in (sqlite_migration, postgres_migration):
            self.assertIn("CREATE TABLE IF NOT EXISTS task_retrospectives", migration)
            self.assertIn("action_taken", migration)
            self.assertIn("outcome_json", migration)

    def test_evidence_provider_migration_has_sqlite_and_postgres_parity(self):
        sqlite_migration = (ROOT / "migrations/016_evidence_provider.sql").read_text()
        postgres_migration = (ROOT / "migrations/postgres/016_evidence_provider.sql").read_text()
        self.assertIn("ALTER TABLE evidence ADD COLUMN provider_id", sqlite_migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS provider_id", postgres_migration)
        for migration in (sqlite_migration, postgres_migration):
            self.assertIn("idx_evidence_provider", migration)


if __name__ == "__main__":
    unittest.main()
