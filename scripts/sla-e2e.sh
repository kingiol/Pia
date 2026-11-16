#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
export PIA_DATA_PROVIDER=fixture
root_tmp="${PIA_SLA_ROOT:-$(mktemp -d)}"
mkdir -p "$root_tmp"
trap 'rm -rf "$root_tmp"' EXIT
export PIA_DB_PATH="${PIA_DB_PATH:-$root_tmp/pia-sla.sqlite3}"
export PIA_DUCKDB_PATH="${PIA_DUCKDB_PATH:-$root_tmp/pia-sla.duckdb}"
export PIA_TASK_TIMEOUT_SECONDS="${PIA_TASK_TIMEOUT_SECONDS:-300}"

"$PWD/scripts/python.sh" - <<'PY'
import os
from pathlib import Path

from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime

runtime = PiaRuntime(Settings.from_env())
try:
    task_count = int(os.environ.get("PIA_SLA_TASK_COUNT", "20"))
    if task_count < 1:
        raise SystemExit("PIA_SLA_TASK_COUNT must be positive")
    for _ in range(task_count):
        task = runtime.create_task(
            "MarketClose",
            {"as_of": "2026-11-05"},
            {
                "market": "close-2026-11-05.json",
                "portfolio": "default.json",
            },
        )
        detail = runtime.wait_for_task(task.id, timeout=10)
        if not detail or detail["task"]["status"] != "BLOCKED":
            raise SystemExit(f"task did not reach BLOCKED: {task.id}")
    metrics = runtime.metrics()
    if metrics["terminal_success_rate"] is None or metrics["terminal_success_rate"] < 0.99:
        raise SystemExit(f"success rate gate failed: {metrics}")
    if not metrics["p95_within_timeout"]:
        raise SystemExit(f"P95 gate failed: {metrics}")
    print({
        "task_total": metrics["task_total"],
        "requested_task_total": task_count,
        "terminal_success_rate": metrics["terminal_success_rate"],
        "p95_seconds": metrics["task_duration_p95_seconds"],
        "timeout_seconds": metrics["task_timeout_seconds"],
    })
finally:
    runtime.close()
PY
echo "SLA E2E PASS"
