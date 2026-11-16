#!/usr/bin/env python3
"""Report release readiness without pretending unverified capabilities passed."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "packages-py" / "pia_runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages-py" / "pia_runtime"))

from pia_runtime.credentials import configured_secret, is_configured


def _present(name: str) -> bool:
    value = os.environ.get(name)
    if is_configured(value):
        return True
    return is_configured(configured_secret(name))


def _check_command(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return completed.returncode == 0, output[-1] if output else f"exit={completed.returncode}"


def _artifact(path: str, *, executable: bool = False) -> dict[str, Any]:
    candidate = ROOT / path
    exists = candidate.exists()
    executable_ok = candidate.is_file() and os.access(candidate, os.X_OK) if executable else True
    return {
        "status": "pass" if exists and executable_ok else "missing",
        "path": path,
        "exists": exists,
        "executable": executable_ok if executable else None,
    }


def _artifact_files(directory: str, pattern: str) -> dict[str, Any]:
    """Require at least one real artifact file, not only its output directory."""
    candidate = ROOT / directory
    files = sorted(
        item.relative_to(ROOT).as_posix()
        for item in candidate.glob(pattern)
        if item.is_file()
    ) if candidate.is_dir() else []
    return {
        "status": "pass" if files else "missing",
        "path": directory,
        "pattern": pattern,
        "files": files,
    }


def build_report() -> dict[str, Any]:
    tauri_available = shutil.which("cargo") is not None
    tauri_ok, tauri_detail = (
        _check_command(["cargo", "tauri", "--version"])
        if tauri_available
        else (False, "cargo is not installed")
    )
    checks: dict[str, Any] = {
        "macos_app": _artifact("apps/desktop/src-tauri/target/release/bundle/macos/Pia.app"),
        "macos_dmg": _artifact("apps/desktop/src-tauri/target/release/bundle/dmg/Pia_0.1.0_aarch64.dmg"),
        "macos_sidecar": _artifact(
            "apps/desktop/src-tauri/binaries/pia-runtime-aarch64-apple-darwin",
            executable=True,
        ),
        "windows_msi": _artifact_files(
            "apps/desktop/src-tauri/target/release/bundle/msi",
            "*.msi",
        ),
        "tauri_cli": {
            "status": "pass" if tauri_ok else "missing",
            "detail": tauri_detail,
        },
        "generated_client": {
            "status": "pass",
            "detail": "",
        },
        "deepseek_credentials": {
            "status": "pass" if _present("DEEPSEEK_API_KEY") else "blocked",
            "detail": "DEEPSEEK_API_KEY is available"
            if _present("DEEPSEEK_API_KEY")
            else "set DEEPSEEK_API_KEY for real runtime/stream/tool acceptance",
        },
        "tushare_credentials": {
            "status": "pass" if _present("TUSHARE_TOKEN") else "blocked",
            "detail": "TUSHARE_TOKEN is available"
            if _present("TUSHARE_TOKEN")
            else "set TUSHARE_TOKEN for fallback/provenance acceptance",
        },
        "postgres_credentials": {
            "status": "pass" if _present("PIA_POSTGRES_DSN") else "unverified",
            "detail": "external PostgreSQL DSN is available"
            if _present("PIA_POSTGRES_DSN")
            else "temporary PostgreSQL acceptance is available; external DSN is not configured",
        },
    }
    client_ok, client_detail = _check_command(
        [str(ROOT / "scripts" / "python.sh"), "scripts/generate_ts_client.py", "--check"]
    )
    checks["generated_client"] = {
        "status": "pass" if client_ok else "failed",
        "detail": client_detail,
    }

    platform_name = platform.system().lower()
    checks["windows_host"] = {
        "status": "pass" if platform_name == "windows" else "unverified",
        "detail": f"host={platform.system()}",
    }
    push_channels = {
        "web_push": (
            "PIA_WEB_PUSH_GATEWAY_URL",
            "PIA_WEB_PUSH_GATEWAY_TOKEN",
            "PIA_PUSH_ACCEPTANCE_WEB_TOKEN",
        ),
        "apns": (
            "PIA_APNS_GATEWAY_URL",
            "PIA_APNS_GATEWAY_TOKEN",
            "PIA_PUSH_ACCEPTANCE_IOS_TOKEN",
        ),
        "fcm": (
            "PIA_FCM_GATEWAY_URL",
            "PIA_FCM_GATEWAY_TOKEN",
            "PIA_PUSH_ACCEPTANCE_ANDROID_TOKEN",
        ),
    }
    checks["external_push_credentials"] = {
        channel: {
            "status": "pass" if all(_present(key) for key in keys) else "unverified",
            "detail": "gateway URL, gateway token and acceptance device token are configured"
            if all(_present(key) for key in keys)
            else "local gateway contract is available; gateway or acceptance device credentials are missing",
        }
        for channel, keys in push_channels.items()
    }

    mvp_blockers = [
        key for key in (
            "windows_msi",
            "windows_host",
            "deepseek_credentials",
            "tushare_credentials",
        )
        if checks[key]["status"] != "pass"
    ]
    full_blockers = list(mvp_blockers)
    if any(item["status"] != "pass" for item in checks["external_push_credentials"].values()):
        full_blockers.append("external_push_credentials")
    return {
        "product": "pia",
        "host": platform.system(),
        "checks": checks,
        "mvp_release_ready": not mvp_blockers,
        "mvp_blockers": mvp_blockers,
        "full_milestone_release_ready": not full_blockers,
        "full_milestone_blockers": full_blockers,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["mvp_release_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
