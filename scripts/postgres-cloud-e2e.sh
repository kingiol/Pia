#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

for command in initdb pg_ctl createdb; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "POSTGRES CLOUD E2E SKIP (missing $command)"
    exit 0
  }
done

root_tmp="${PIA_POSTGRES_E2E_ROOT:-$(mktemp -d)}"
owns_root=0
if [ -z "${PIA_POSTGRES_E2E_ROOT:-}" ]; then
  owns_root=1
fi
mkdir -p "$root_tmp"
cluster_dir="$root_tmp/postgres"
postgres_port="${PIA_POSTGRES_E2E_DB_PORT:-$("$PWD/scripts/python.sh" - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)}"
api_port="${PIA_POSTGRES_E2E_API_PORT:-$("$PWD/scripts/python.sh" - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)}"
owns_cluster=0

cleanup() {
  if [ "$owns_cluster" = "1" ]; then
    pg_ctl -D "$cluster_dir" -w stop -m immediate >/dev/null 2>&1 || true
  fi
  if [ "$owns_root" = "1" ]; then
    rm -rf "$root_tmp"
  fi
}
trap cleanup EXIT

initdb -D "$cluster_dir" -U pia -A trust --encoding=UTF8 --locale=C >/dev/null
pg_ctl -D "$cluster_dir" -o "-p ${postgres_port} -h 127.0.0.1" -w start >/dev/null
createdb -h 127.0.0.1 -p "$postgres_port" -U pia pia_cloud_e2e
owns_cluster=1

PIA_POSTGRES_DSN="postgresql://pia@127.0.0.1:${postgres_port}/pia_cloud_e2e" \
PIA_DB_PATH="$root_tmp/fallback.sqlite3" \
PIA_DUCKDB_PATH="$root_tmp/analytics.duckdb" \
PIA_PORT="$api_port" \
  ./scripts/cloud-e2e.sh

PYTHONPATH="$PWD/packages-py/pia_runtime" \
PIA_TEST_POSTGRES_DSN="postgresql://pia@127.0.0.1:${postgres_port}/pia_cloud_e2e" \
  ./scripts/python.sh -m unittest discover -s tests -p test_llm_budget_postgres.py -v

PYTHONPATH="$PWD/packages-py/pia_runtime" \
PIA_TEST_POSTGRES_DSN="postgresql://pia@127.0.0.1:${postgres_port}/pia_cloud_e2e" \
  ./scripts/python.sh -m unittest discover -s tests -p test_postgres_analytics.py -v

PYTHONPATH="$PWD/packages-py/pia_runtime" \
PIA_TEST_POSTGRES_DSN="postgresql://pia@127.0.0.1:${postgres_port}/pia_cloud_e2e" \
  ./scripts/python.sh -m unittest discover -s tests -p test_push_acceptance.py -v

PIA_POSTGRES_DSN="postgresql://pia@127.0.0.1:${postgres_port}/pia_cloud_e2e" \
PIA_PORT="$api_port" ./scripts/cloud-scheduler-e2e.sh

test ! -e "$root_tmp/fallback.sqlite3"
test ! -e "$root_tmp/analytics.duckdb"
echo "POSTGRES CLOUD E2E PASS"
