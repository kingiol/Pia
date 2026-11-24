from __future__ import annotations

import argparse
import getpass
import json
import os
import signal
import sys
from contextlib import nullcontext
from pathlib import Path
from threading import Thread
from uuid import uuid4

from .api import serve
from .backup import create_backup_package, restore_backup_package
from .config import Settings
from .credentials import CredentialStore, is_configured
from .db import Database
from .desktop_runtime import DesktopDataError, PROFILE_FILE, claim_desktop_profile, lock_desktop_data
from .replay import run_replay
from .runtime import PiaRuntime


def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="pia")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--scheduler", action="store_true")
    desktop_parser = subparsers.add_parser("desktop")
    desktop_parser.add_argument("--channel", choices=("debug", "release"), required=True)
    desktop_parser.add_argument("--data-dir", type=Path, required=True)
    desktop_parser.add_argument("--provider", required=True)
    desktop_parser.add_argument("--exit-on-stdin-close", action="store_true")
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
    if args.command == "desktop":
        try:
            _serve_desktop(args)
        except KeyboardInterrupt:
            pass
        except DesktopDataError as error:
            print("PIA_DESKTOP_ERROR " + json.dumps(str(error)), flush=True)
            raise SystemExit(1) from error
        except (OSError, RuntimeError, ValueError):
            print("PIA_DESKTOP_ERROR " + json.dumps("桌面运行时启动失败，请检查数据目录和运行时日志。"), flush=True)
            raise
        return
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
    data_dir = settings.db_path.resolve().parent
    uses_desktop_data = settings.mode == "local" and args.command not in {"cloud", "worker"} and (data_dir / PROFILE_FILE).exists()
    with lock_desktop_data(data_dir) if uses_desktop_data else nullcontext():
        _run_command(args, settings)


def _serve_desktop(args: argparse.Namespace) -> None:
    channel = args.channel
    provider = args.provider
    if channel == "release" and provider == "fixture":
        raise ValueError("Release requires a live data provider")
    directory = args.data_dir.resolve()
    profile = "fixture" if provider == "fixture" else "live"
    os.environ["PIA_CREDENTIAL_SERVICE"] = "pia.debug" if channel == "debug" else "pia"
    settings = Settings.from_env()
    settings.mode = "local"
    settings.host = "127.0.0.1"
    settings.port = 0
    settings.db_path = directory / "pia.sqlite3"
    settings.analytics_db_path = directory / "pia.duckdb"
    settings.data_provider = provider
    if channel == "release":
        if "PIA_SCHEDULER_ENABLED" not in os.environ:
            settings.scheduler_enabled = True
        if "PIA_NATIVE_NOTIFICATIONS" not in os.environ:
            settings.native_notifications = True

    def terminate(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    if args.exit_on_stdin_close:
        def watch_desktop():
            # The desktop owns the write end, including when Tauri dev kills it on reload.
            if not os.read(sys.stdin.fileno(), 1):
                os.kill(os.getpid(), signal.SIGTERM)

        Thread(target=watch_desktop, daemon=True).start()
    with lock_desktop_data(directory):
        claim_desktop_profile(directory, f"{channel}:{profile}")
        runtime = PiaRuntime(settings)
        try:
            serve(runtime, settings.host, settings.port, desktop_identity={
                "channel": channel, "instance_id": uuid4().hex,
            })
        finally:
            runtime.close()


def _run_command(args: argparse.Namespace, settings: Settings) -> None:
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
