#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${PIA_POSTGRES_DSN:?PIA_POSTGRES_DSN is required}"
destination="${1:-.pia/backups/cloud-$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$destination" ]; then
  echo "Backup destination already exists: $destination" >&2
  exit 1
fi
mkdir -p "$destination"

command -v pg_dump >/dev/null 2>&1 || {
  echo "pg_dump is required for cloud backup" >&2
  exit 1
}
pg_dump --format=custom --file="$destination/postgres.dump" "$PIA_POSTGRES_DSN"

"$PWD/scripts/python.sh" - "$destination" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

destination = Path(sys.argv[1])
manifest = {
    "format": "pia-cloud-backup-v2",
    "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "database": {"type": "postgresql"},
    "analytics": {"type": "postgresql"},
    "files": {},
}
for path in sorted(destination.iterdir()):
    if path.is_file():
        manifest["files"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
(destination / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
)
print(destination.resolve())
PY
