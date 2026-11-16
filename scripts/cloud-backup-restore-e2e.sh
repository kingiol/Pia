#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/packages-py/pia_runtime"

for command in initdb pg_ctl createdb pg_dump pg_restore; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "POSTGRES BACKUP E2E SKIP (missing $command)"
    exit 0
  }
done

root_tmp="$(mktemp -d)"
cluster_dir="$root_tmp/postgres"
backup_dir="$root_tmp/backup"
port="$("$PWD/scripts/python.sh" - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
owns_cluster=0
cleanup() {
  if [ "$owns_cluster" = "1" ]; then
    pg_ctl -D "$cluster_dir" -w stop -m immediate >/dev/null 2>&1 || true
  fi
  rm -rf "$root_tmp"
}
trap cleanup EXIT

initdb -D "$cluster_dir" -U pia -A trust --encoding=UTF8 --locale=C >/dev/null
pg_ctl -D "$cluster_dir" -o "-p ${port} -h 127.0.0.1" -w start >/dev/null
owns_cluster=1
createdb -h 127.0.0.1 -p "$port" -U pia pia_backup_e2e
# Never use a caller's database for this destructive restore test.
export PIA_POSTGRES_DSN="postgresql://pia@127.0.0.1:${port}/pia_backup_e2e"
export PIA_DB_PATH="$root_tmp/unused.sqlite3"
export PIA_DUCKDB_PATH="$root_tmp/unused.duckdb"

"$PWD/scripts/python.sh" - <<'PY'
from pia_runtime.analytics import ANALYTICAL_KEYS
from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime

settings = Settings.from_env()
settings.mode = "cloud"
settings.data_provider = "fixture"
settings.require_llm = False
settings.autostart_tasks = False
runtime = PiaRuntime(settings)
try:
    task = runtime.create_task("MarketClose", {"as_of": "2026-11-05"}, user_id="backup-user")
    runtime.run_task(task.id)
    detail = runtime.wait_for_task(task.id, user_id="backup-user")
    pack = runtime.db.get_context_pack(task.id, "backup-user")
    binding = runtime.db.get_task_binding(task.id, "backup-user")
    assert pack and detail["decision"]
    expected = {
        "task_id": task.id, "pack_hash": pack["content_hash"],
        "binding_hash": binding["content_hash"], "result_metadata": detail["result_metadata"],
        "decision_status": detail["decision"]["status"],
        "counts": {table: runtime.analytics.count(table) for table in ANALYTICAL_KEYS},
    }
    runtime.analytics.save_snapshot(
        snapshot_id="backup-e2e-snapshot", kind="market", as_of="2026-11-05",
        observed_at="2026-11-05T16:10:00+08:00", source="backup-e2e",
        quality="verified", payload=expected,
    )
finally:
    runtime.close()
PY

"$PWD/scripts/cloud-backup.sh" "$backup_dir" >/dev/null
test ! -e "$backup_dir/analytics.duckdb"

"$PWD/scripts/python.sh" - <<'PY'
import os
from pia_runtime.config import ROOT
from pia_runtime.postgres import PostgresDatabase

database = PostgresDatabase(os.environ["PIA_POSTGRES_DSN"], ROOT / "migrations")
database.execute("DELETE FROM analytical_snapshots WHERE snapshot_id=?", ("backup-e2e-snapshot",))
assert not database.fetchone("SELECT snapshot_id FROM analytical_snapshots WHERE snapshot_id=?",
                             ("backup-e2e-snapshot",))
database.close()
PY

"$PWD/scripts/cloud-restore.sh" "$backup_dir" >/dev/null

"$PWD/scripts/python.sh" - <<'PY'
from pia_runtime.config import Settings
from pia_runtime.runtime import PiaRuntime

settings = Settings.from_env()
settings.mode = "cloud"
settings.data_provider = "fixture"
settings.require_llm = False
settings.autostart_tasks = False
runtime = PiaRuntime(settings)
try:
    expected = runtime.analytics.snapshot_bundle("backup-e2e-snapshot")["snapshot"]["payload"]
    task_id = expected["task_id"]
    assert runtime.db.get_context_pack(task_id, "backup-user")["content_hash"] == expected["pack_hash"]
    assert runtime.db.get_task_binding(task_id, "backup-user")["content_hash"] == expected["binding_hash"]
    assert runtime.task_detail(task_id, "backup-user")["result_metadata"] == expected["result_metadata"]
    for table, count in expected["counts"].items():
        assert runtime.analytics.count(table) == count + (table == "analytical_snapshots"), table
    try:
        runtime.task_context(task_id, "another-user", view="full")
    except KeyError:
        pass
    else:
        raise AssertionError("Restored context ownership was not enforced")
    replay = runtime.replay_task(task_id, "backup-user")
    runtime.run_task(replay.id)
    assert runtime.wait_for_task(replay.id, user_id="backup-user")["decision"]["status"] == expected["decision_status"]
finally:
    runtime.close()
PY
test ! -e "$PIA_DB_PATH"
test ! -e "$PIA_DUCKDB_PATH"

echo "POSTGRES BACKUP RESTORE E2E PASS"
