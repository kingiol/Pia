from __future__ import annotations

import os
import platform
import subprocess
from functools import lru_cache


DEFAULT_SERVICE = "pia"


def is_configured(value: str | None) -> bool:
    """Return whether a value is a real credential rather than a placeholder."""
    return bool(value and value.strip() and not value.strip().startswith("__"))


class CredentialStore:
    """Read and write secrets through the host credential manager.

    Saved DeepSeek credentials take precedence over the environment. Other
    credentials retain environment overrides for development and CI.
    Native stores are accessed through argument arrays and short-lived
    subprocesses so secrets never become shell source or logs.
    """

    def __init__(self, service: str = DEFAULT_SERVICE) -> None:
        self.service = service

    def get(self, name: str) -> str | None:
        return self.resolve(name)[0]

    def resolve(self, name: str, *, prefer_saved: bool = False) -> tuple[str | None, str]:
        env_value = os.getenv(name)
        prefer_saved = prefer_saved or name == "DEEPSEEK_API_KEY"
        if prefer_saved:
            saved_value = _native_get(self.service, name)
            if is_configured(saved_value):
                return saved_value.strip(), "saved"
        if is_configured(env_value):
            return env_value.strip(), "environment"
        if not prefer_saved:
            saved_value = _native_get(self.service, name)
            if is_configured(saved_value):
                return saved_value.strip(), "saved"
        return None, "none"

    def set(self, name: str, value: str) -> None:
        if not is_configured(value):
            raise ValueError("credential value must not be empty or a placeholder")
        _native_set(self.service, name, value.strip())
        _native_get.cache_clear()

    def delete(self, name: str) -> None:
        _native_delete(self.service, name)
        _native_get.cache_clear()


def configured_secret(name: str, *, store: CredentialStore | None = None) -> str | None:
    """Resolve a secret using its credential-specific precedence."""
    return (store or CredentialStore()).get(name)


@lru_cache(maxsize=128)
def _native_get(service: str, name: str) -> str | None:
    system = platform.system()
    try:
        if system == "Darwin":
            return _run_get(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    name,
                    "-s",
                    service,
                    "-w",
                ]
            )
        if system == "Linux":
            return _run_get(["secret-tool", "lookup", "service", service, "account", name])
        if system == "Windows":
            return _run_get(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    (
                        "$ErrorActionPreference='Stop'; "
                        "[Windows.Security.Credentials.PasswordVault,Windows.Security.Credentials,"
                        "ContentType=WindowsRuntime]$vault = "
                        "New-Object Windows.Security.Credentials.PasswordVault; "
                        f"$credential = $vault.Retrieve('{_ps_quote(service)}','{_ps_quote(name)}'); "
                        "$credential.RetrievePassword(); "
                        "Write-Output $credential.Password"
                    ),
                ]
            )
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _run_get(command: list[str]) -> str | None:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _native_set(service: str, name: str, value: str) -> None:
    system = platform.system()
    if system == "Darwin":
        _run_mutation(
            [
                "security",
                "add-generic-password",
                "-U",
                "-a",
                name,
                "-s",
                service,
                "-w",
                value,
            ]
        )
        return
    if system == "Linux":
        _run_mutation(
            [
                "secret-tool",
                "store",
                "--label",
                f"{service} credential",
                "service",
                service,
                "account",
                name,
            ],
            stdin=value,
        )
        return
    if system == "Windows":
        _run_mutation(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "[Windows.Security.Credentials.PasswordVault,Windows.Security.Credentials,"
                    "ContentType=WindowsRuntime]$vault = "
                    "New-Object Windows.Security.Credentials.PasswordVault; "
                    "$value = [Console]::In.ReadToEnd(); "
                    f"$credential = New-Object Windows.Security.Credentials.PasswordCredential "
                    f"-ArgumentList @('{_ps_quote(service)}','{_ps_quote(name)}',$value); "
                    "$vault.Add($credential)"
                ),
            ],
            stdin=value,
        )
        return
    raise RuntimeError(f"unsupported credential manager platform: {system}")


def _native_delete(service: str, name: str) -> None:
    system = platform.system()
    if system == "Darwin":
        _run_mutation(
            [
                "security",
                "delete-generic-password",
                "-a",
                name,
                "-s",
                service,
            ],
            allow_missing=True,
        )
        return
    if system == "Linux":
        _run_mutation(
            ["secret-tool", "clear", "service", service, "account", name],
            allow_missing=True,
        )
        return
    if system == "Windows":
        _run_mutation(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "[Windows.Security.Credentials.PasswordVault,Windows.Security.Credentials,"
                    "ContentType=WindowsRuntime]$vault = "
                    "New-Object Windows.Security.Credentials.PasswordVault; "
                    f"$credential = $vault.Retrieve('{_ps_quote(service)}','{_ps_quote(name)}'); "
                    "$vault.Remove($credential)"
                ),
            ],
            allow_missing=True,
        )
        return
    raise RuntimeError(f"unsupported credential manager platform: {system}")


def _run_mutation(
    command: list[str],
    *,
    stdin: str | None = None,
    allow_missing: bool = False,
) -> None:
    try:
        completed = subprocess.run(
            command,
            input=stdin,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("native credential manager is unavailable") from error
    if completed.returncode != 0 and not allow_missing:
        raise RuntimeError("native credential manager rejected the credential operation")


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")
