#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"
: "${PIA_POSTGRES_DSN:?PIA_POSTGRES_DSN is required for Cloud scheduler acceptance}"

root_tmp="$(mktemp -d)"
port="${PIA_PORT:-8881}"
token="${PIA_CLOUD_AUTH_TOKEN:-cloud-scheduler-e2e-token}"
export PIA_CLOUD_AUTH_TOKEN="$token"
export PIA_START_SCHEDULER=1
export PIA_START_WORKER=0
export PIA_PORT="$port"
export PIA_DB_PATH="${PIA_DB_PATH:-$root_tmp/cloud.sqlite3}"

"$PWD/scripts/cloud.sh" >"$root_tmp/cloud.log" 2>&1 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl --noproxy '*' --connect-timeout 1 --max-time 2 \
    -fsS "http://127.0.0.1:${port}/api/health" >"$root_tmp/health.json" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

curl --noproxy '*' -fsS \
  -H "Authorization: Bearer ${token}" \
  "http://127.0.0.1:${port}/api/scheduler" >"$root_tmp/scheduler.json"
"$PWD/scripts/python.sh" - "$root_tmp/scheduler.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1]).read())
assert payload["enabled"] is True, payload
PY

curl --noproxy '*' -fsS \
  -H "Authorization: Bearer ${token}" \
  -X POST "http://127.0.0.1:${port}/api/scheduler/stop" >"$root_tmp/stopped.json"
"$PWD/scripts/python.sh" - "$root_tmp/stopped.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1]).read())
assert payload["enabled"] is False, payload
PY

curl --noproxy '*' -fsS \
  -H "Authorization: Bearer ${token}" \
  -X POST "http://127.0.0.1:${port}/api/scheduler/start" >"$root_tmp/started.json"
"$PWD/scripts/python.sh" - "$root_tmp/started.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1]).read())
assert payload["enabled"] is True, payload
print("CLOUD SCHEDULER E2E PASS", payload)
PY
