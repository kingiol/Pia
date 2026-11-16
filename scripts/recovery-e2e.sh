#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
export PIA_CLOUD_AUTH_TOKEN="${PIA_CLOUD_AUTH_TOKEN:-recovery-e2e-token}"
export PIA_CLOUD_USERS="${PIA_CLOUD_USERS:-recovery-e2e-token=default}"
export PIA_PORT="${PIA_PORT:-8876}"
root_tmp="${PIA_RECOVERY_ROOT:-$(mktemp -d)}"
mkdir -p "$root_tmp"
export PIA_DB_PATH="${PIA_DB_PATH:-$root_tmp/pia-recovery.sqlite3}"
export PIA_DUCKDB_PATH="${PIA_DUCKDB_PATH:-$root_tmp/pia-recovery.duckdb}"
export PIA_AUTOSTART_TASKS=0
export PIA_DATA_PROVIDER=fixture

"$PWD/scripts/python.sh" - <<'PY'
from pathlib import Path

from pia_runtime.config import ROOT, Settings
from pia_runtime.models import Task, TaskStatus, now_iso
from pia_runtime.runtime import PiaRuntime

runtime = PiaRuntime(Settings.from_env())
task = Task(
    id="task_restart_recovery",
    user_id="default",
    trigger_type="MarketClose",
    target={
        "as_of": "2026-11-05",
        "_fixture": {
            "market": "close-2026-11-05.json",
            "portfolio": "default.json",
        },
    },
    status=TaskStatus.RUNNING,
    created_at=now_iso(),
)
with runtime.db.transaction():
    runtime.db.create_task(task)
    runtime.db.save_task_binding(task, {
        "profile": runtime.get_profile(),
        "rules": {"id": runtime.rule_snapshot_id, "rules": runtime.rules},
        "confirmed_memories": [],
    })
runtime.close()
PY

"$PWD/scripts/python.sh" -m pia_runtime.cli cloud >"$root_tmp/cloud.log" 2>&1 &
api_pid=$!
worker_pid=""
trap 'kill "$api_pid" "$worker_pid" 2>/dev/null || true; rm -rf "$root_tmp"' EXIT

for _ in $(seq 1 30); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS \
    "http://127.0.0.1:${PIA_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

recovered_status="$(curl --noproxy '*' -sS \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  "http://127.0.0.1:${PIA_PORT}/api/tasks/task_restart_recovery" \
  | "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
test "$recovered_status" = "RETRYABLE"

retry_json="$(curl --noproxy '*' -sS \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/task_restart_recovery/retry")"
retry_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$retry_json")"

"$PWD/scripts/python.sh" -m pia_runtime.cli worker --worker-id recovery-e2e --once \
  >"$root_tmp/worker.log" 2>&1 &
worker_pid=$!
for _ in $(seq 1 30); do
  retry_status="$(curl --noproxy '*' -sS \
    -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${retry_id}" \
    | "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  case "$retry_status" in
    BLOCKED|NO_ACTION|WAITING_APPROVAL|FAILED|RETRYABLE|TIMEOUT|DONE) break ;;
  esac
  sleep 0.2
done
wait "$worker_pid"
worker_pid=""
test "$retry_status" = "BLOCKED"
echo "RECOVERY E2E PASS $retry_id"
