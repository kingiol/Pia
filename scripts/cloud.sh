#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PIA_CLOUD_AUTH_TOKEN="${PIA_CLOUD_AUTH_TOKEN:-${PIA_SERVER_AUTH_TOKEN:-}}"
if [ -z "${PIA_CLOUD_AUTH_TOKEN:-}" ]; then
  echo "PIA_CLOUD_AUTH_TOKEN is required" >&2
  exit 2
fi
export PYTHONPATH="$PWD/packages-py/pia_runtime"
: "${PIA_POSTGRES_DSN:?PIA_POSTGRES_DSN is required in cloud mode}"
scheduler_enabled="${PIA_SCHEDULER_ENABLED:-0}"
if [ "${PIA_START_SCHEDULER:-0}" = "1" ]; then
  scheduler_enabled=1
fi
PIA_MODE=cloud PIA_AUTOSTART_TASKS=0 PIA_SCHEDULER_ENABLED="$scheduler_enabled" \
  "$PWD/scripts/python.sh" -m pia_runtime.cli cloud &
api_pid=$!
worker_pid=""
if [ "${PIA_START_WORKER:-1}" = "1" ]; then
  PIA_MODE=cloud PIA_AUTOSTART_TASKS=0 PIA_SCHEDULER_ENABLED=0 \
    "$PWD/scripts/python.sh" -m pia_runtime.cli worker &
  worker_pid=$!
fi
trap 'kill "$api_pid" "$worker_pid" 2>/dev/null || true' EXIT
wait "$api_pid"
