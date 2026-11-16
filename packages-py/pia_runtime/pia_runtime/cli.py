from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .api import serve
from .backup import create_backup_package, restore_backup_package
from .config import Settings
from .credentials import CredentialStore, is_configured
from .db import Database
from .replay import run_replay
from .runtime import PiaRuntime


def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="pia")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--scheduler", action="store_true")
    cloud_parser = subparsers.add_parser("cloud", aliases=["server"])
    cloud_parser.add_argument("--host", default=None)
    cloud_parser.add_argument("--port", type=int, default=None)
    cloud_parser.add_argument("--scheduler", action="store_true")
    worker_parser = subparsers.add_parser("worker")
    worker_parser.add_argument("--worker-id", default="cloud-worker")
    worker_parser.add_argument("--once", action="store_true")
    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("--fixture", default="tests/fixtures/replay/close-review.json")
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("destination")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("source")
    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--json", action="store_true")
    health_parser.add_argument("--isolation-check", action="store_true")
    credentials_parser = subparsers.add_parser(
        "credentials",
        help="manage secrets in the host credential manager",
    )
    credentials_subparsers = credentials_parser.add_subparsers(dest="credentials_action", required=True)
    credentials_set_parser = credentials_subparsers.add_parser("set")
    credentials_set_parser.add_argument("name")
    credentials_status_parser = credentials_subparsers.add_parser("status")
    credentials_status_parser.add_argument("name")
    credentials_delete_parser = credentials_subparsers.add_parser("delete")
    credentials_delete_parser.add_argument("name")
    args = parser.parse_args()
    if args.command == "server":
        args.command = "cloud"
    if args.command == "credentials":
        store = CredentialStore()
        if args.credentials_action == "set":
            value = getpass.getpass(f"Value for {args.name}: ")
            store.set(args.name, value)
            print(json.dumps({"status": "stored", "name": args.name}, ensure_ascii=False))
        elif args.credentials_action == "status":
            print(json.dumps({
                "name": args.name,
                "configured": is_configured(store.get(args.name)),
            }, ensure_ascii=False))
        else:
            store.delete(args.name)
            print(json.dumps({"status": "deleted", "name": args.name}, ensure_ascii=False))
        return
    settings = Settings.from_env()
    if args.command in {"backup", "restore"} and settings.mode == "cloud":
        raise SystemExit("Use scripts/cloud-backup.sh or scripts/cloud-restore.sh for Cloud storage")
    if args.command == "serve" and args.scheduler:
        settings.scheduler_enabled = True
        settings.native_notifications = True
    if args.command == "cloud" and args.scheduler:
        settings.scheduler_enabled = True
    if args.command == "restore":
        source = Path(args.source)
        if source.suffix == ".zip":
            manifest = restore_backup_package(
                source,
                settings.db_path,
                metadata_root=settings.db_path.parent / "restored_metadata",
                destination_analytics=settings.analytics_db_path,
            )
            print(json.dumps({
                "status": "restored",
                "database": str(settings.db_path),
                "manifest": manifest,
            }, ensure_ascii=False))
        else:
            Database.restore_from(source, settings.db_path)
            print(json.dumps({"status": "restored", "database": str(settings.db_path)}, ensure_ascii=False))
        return
    if args.command in {"cloud", "worker"}:
        settings.mode = "cloud"
        settings.autostart_tasks = False
        settings.structured_logs = True
        if args.command == "cloud" and not settings.cloud_auth_token:
            raise SystemExit("PIA_CLOUD_AUTH_TOKEN is required in cloud mode")
        if not settings.postgres_dsn:
            raise SystemExit("PIA_POSTGRES_DSN is required in cloud mode")
        if args.command == "cloud" and args.host:
            settings.host = args.host
        if args.command == "cloud" and args.port:
            settings.port = args.port
        if args.command == "worker":
            settings.autostart_tasks = False
            settings.scheduler_enabled = False
    runtime = PiaRuntime(settings)
    if args.command == "serve":
        serve(runtime, runtime.settings.host, runtime.settings.port)
    elif args.command == "cloud":
        serve(runtime, runtime.settings.host, runtime.settings.port, runtime.settings.cloud_auth_token)
    elif args.command == "worker":
        runtime.worker_loop(args.worker_id, args.once)
    elif args.command == "health":
        health = runtime.health()
        if args.isolation_check:
            from .isolated_call import isolation_health
            health["isolation"] = isolation_health()
        output = json.dumps(health, ensure_ascii=False, indent=2)
        print(output if args.json else f"Pia runtime: {runtime.health()['status']}")
    elif args.command == "replay":
        detail = run_replay(runtime, Path(args.fixture))
        print(json.dumps(detail, ensure_ascii=False, indent=2))
    elif args.command == "backup":
        destination = Path(args.destination)
        if destination.suffix == ".zip":
            package = create_backup_package(
                runtime.db,
                destination,
                rules_path=settings.rules_path,
                settings={
                    "mode": settings.mode,
                    "deepseek_model": settings.deepseek_model,
                    "db_path": str(settings.db_path),
                    "analytics_db_path": str(settings.analytics_db_path),
                    "rules_path": str(settings.rules_path),
                },
                analytics_path=settings.analytics_db_path,
            )
            print(json.dumps({"status": "backed_up", "destination": str(package.resolve()), "package": True}, ensure_ascii=False))
        else:
            runtime.db.backup_to(destination)
            print(json.dumps({"status": "backed_up", "destination": str(destination.resolve()), "package": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
