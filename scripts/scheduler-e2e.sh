#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

"$PWD/scripts/python.sh" - <<'PY'
import tempfile
from datetime import datetime
from pathlib import Path

from pia_runtime.config import ROOT, Settings
from pia_runtime.runtime import PiaRuntime
from pia_runtime.scheduler import LocalMarketScheduler


with tempfile.TemporaryDirectory(prefix="pia-scheduler-e2e-") as directory:
    root = Path(directory)
    runtime = PiaRuntime(
        Settings(
            db_path=root / "pia.sqlite3",
            analytics_db_path=root / "pia.duckdb",
            fixture_dir=ROOT / "tests/fixtures",
            rules_path=ROOT / "rules/baseline.yaml",
            data_provider="fixture",
            autostart_tasks=False,
        )
    )
    try:
        scheduler = LocalMarketScheduler(
            runtime,
            timezone_name="Asia/Shanghai",
            close_time="15:05",
        )
        due = datetime.fromisoformat("2026-11-05T15:06:00+08:00")
        first = scheduler.dispatch_if_due(due)
        second = scheduler.dispatch_if_due(due)
        assert first and first["status"] == "DISPATCHED", first
        assert second is None, second
        task_id = first["task_id"]
        task = runtime.db.get_task(task_id)
        assert task is not None
        assert task.trigger_type == "MarketClose"
        assert task.target["as_of"] == "2026-11-05"

        runtime.run_task(task_id)
        detail = runtime.wait_for_task(task_id, timeout=10)
        assert detail is not None
        assert detail["task"]["status"] in {
            "BLOCKED",
            "NO_ACTION",
            "WAITING_APPROVAL",
            "DONE",
        }, detail["task"]
        events = runtime.db.fetchall(
            "SELECT * FROM events WHERE dedupe_key=?",
            ("default:market-close:2026-11-05",),
        )
        assert len(events) == 1, events
        print(
            "SCHEDULER E2E PASS",
            task_id,
            detail["task"]["status"],
            "dedupe_events=1",
        )
    finally:
        runtime.close()
PY
