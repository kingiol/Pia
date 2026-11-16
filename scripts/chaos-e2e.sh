#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
export PIA_CLOUD_AUTH_TOKEN="${PIA_CLOUD_AUTH_TOKEN:-chaos-e2e-token}"
export PIA_CLOUD_USERS="${PIA_CLOUD_USERS:-chaos-e2e-token=default}"
export PIA_PORT="${PIA_PORT:-8875}"
root_tmp="${PIA_CHAOS_ROOT:-$(mktemp -d)}"
mkdir -p "$root_tmp"
export PIA_DB_PATH="${PIA_DB_PATH:-$root_tmp/pia-chaos.sqlite3}"
export PIA_DUCKDB_PATH="${PIA_DUCKDB_PATH:-$root_tmp/pia-chaos.duckdb}"
export PIA_AUTOSTART_TASKS=0
export PIA_DATA_PROVIDER=fixture
export PIA_TASK_EXECUTION_DELAY_SECONDS="${PIA_TASK_EXECUTION_DELAY_SECONDS:-2}"

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

task_json="$(curl --noproxy '*' -sS \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks" \
  -H 'Content-Type: application/json' \
  -d '{"trigger_type":"MarketClose","target":{"as_of":"2026-11-05"},"fixture":{"market":"close-2026-11-05.json","portfolio":"default.json"}}')"
task_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$task_json")"

"$PWD/scripts/python.sh" -m pia_runtime.cli worker --worker-id chaos-e2e \
  >"$root_tmp/worker.log" 2>&1 &
worker_pid=$!
for _ in $(seq 1 30); do
  task_status="$(curl --noproxy '*' -sS \
    -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
    "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}" \
    | "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
  case "$task_status" in
    PLANNING|RUNNING) break ;;
  esac
  sleep 0.1
done
test "$task_status" = "RUNNING"
kill -9 "$worker_pid" 2>/dev/null || true
wait "$worker_pid" 2>/dev/null || true
worker_pid=""

"$PWD/scripts/python.sh" -m pia_runtime.cli worker --worker-id chaos-recovery --once \
  >"$root_tmp/recovery-worker.log" 2>&1
recovered_status="$(curl --noproxy '*' -sS \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}" \
  | "$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')"
test "$recovered_status" = "RETRYABLE"

retry_json="$(curl --noproxy '*' -sS \
  -H "Authorization: Bearer ${PIA_CLOUD_AUTH_TOKEN}" \
  -X POST "http://127.0.0.1:${PIA_PORT}/api/tasks/${task_id}/retry")"
retry_id="$("$PWD/scripts/python.sh" -c 'import json,sys; print(json.load(sys.stdin)["task"]["id"])' <<<"$retry_json")"
"$PWD/scripts/python.sh" -m pia_runtime.cli worker --worker-id chaos-final --once \
  >"$root_tmp/final-worker.log" 2>&1
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
test "$retry_status" = "BLOCKED"
echo "CHAOS E2E PASS $task_id -> $retry_id"
