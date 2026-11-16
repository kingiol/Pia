from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import Database


PACKAGE_VERSION = "1"


def create_backup_package(
    db: Database,
    destination: Path,
    *,
    rules_path: Path,
    settings: dict[str, Any],
    analytics_path: Path | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        sqlite_path = Path(directory) / "pia.sqlite3"
        db.backup_to(sqlite_path)
        resolved_analytics = analytics_path or db.path.with_suffix(".duckdb")
        if resolved_analytics.exists():
            try:
                from .analytics import AnalyticsStore

                analytics = AnalyticsStore(resolved_analytics)
                analytics.checkpoint()
                analytics.close()
            except RuntimeError:
                # A database created by an older runtime may not have DuckDB
                # installed. Preserve SQLite-only backups in that environment.
                pass
        files = {
            "pia.sqlite3": sqlite_path.read_bytes(),
            "rules/baseline.yaml": rules_path.read_bytes(),
            "config/settings.json": json.dumps(settings, ensure_ascii=False, sort_keys=True, indent=2).encode(),
        }
        if resolved_analytics.exists():
            files["pia.duckdb"] = resolved_analytics.read_bytes()
        manifest = {
            "package_version": PACKAGE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": {
                name: {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
                for name, content in files.items()
            },
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return destination


def restore_backup_package(
    source: Path,
    destination_db: Path,
    *,
    metadata_root: Path,
    destination_analytics: Path | None = None,
) -> dict[str, Any]:
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, metadata in manifest["files"].items():
            content = archive.read(name)
            digest = hashlib.sha256(content).hexdigest()
            if digest != metadata["sha256"] or len(content) != metadata["size"]:
                raise ValueError(f"backup integrity check failed for {name}")
        with tempfile.TemporaryDirectory() as directory:
            sqlite_path = Path(directory) / "pia.sqlite3"
            sqlite_path.write_bytes(archive.read("pia.sqlite3"))
            Database.restore_from(sqlite_path, destination_db)
            if "pia.duckdb" in archive.namelist():
                analytics_path = destination_analytics or destination_db.with_suffix(".duckdb")
                analytics_path.parent.mkdir(parents=True, exist_ok=True)
                analytics_path.write_bytes(archive.read("pia.duckdb"))
        metadata_root.mkdir(parents=True, exist_ok=True)
        rules_destination = metadata_root / "rules" / "baseline.yaml"
        rules_destination.parent.mkdir(parents=True, exist_ok=True)
        rules_destination.write_bytes(archive.read("rules/baseline.yaml"))
        config_destination = metadata_root / "config" / "settings.json"
        config_destination.parent.mkdir(parents=True, exist_ok=True)
        config_destination.write_bytes(archive.read("config/settings.json"))
    return manifest
