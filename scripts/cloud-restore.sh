#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${PIA_POSTGRES_DSN:?PIA_POSTGRES_DSN is required}"
source_dir="${1:?Usage: scripts/cloud-restore.sh BACKUP_DIR}"

command -v pg_restore >/dev/null 2>&1 || {
  echo "pg_restore is required for cloud restore" >&2
  exit 1
}
test -f "$source_dir/postgres.dump" || {
  echo "Missing postgres.dump in $source_dir" >&2
  exit 1
}
test -f "$source_dir/manifest.json" || {
  echo "Missing manifest.json in $source_dir" >&2
  exit 1
}

"$PWD/scripts/python.sh" - "$source_dir" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text())
if manifest.get("format") != "pia-cloud-backup-v2":
    raise SystemExit("Unsupported Cloud backup format")
if "postgres.dump" not in manifest.get("files", {}):
    raise SystemExit("Backup manifest is missing required files")
for name, expected in manifest.get("files", {}).items():
    if Path(name).name != name:
        raise SystemExit("Invalid backup manifest filename")
    path = root / name
    if not path.is_file():
        raise SystemExit(f"missing backup file: {name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected["sha256"] or path.stat().st_size != expected["bytes"]:
        raise SystemExit(f"backup integrity check failed: {name}")
print("BACKUP MANIFEST PASS")
PY

pg_restore --exit-on-error --single-transaction --clean --if-exists --no-owner \
  --dbname="$PIA_POSTGRES_DSN" "$source_dir/postgres.dump"
echo "CLOUD RESTORE PASS PostgreSQL"
