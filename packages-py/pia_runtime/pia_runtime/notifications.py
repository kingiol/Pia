from __future__ import annotations

import json
import platform
import smtplib
import subprocess
from email.message import EmailMessage
from urllib.error import URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape as escape_xml


@dataclass(slots=True)
class NotificationReceipt:
    status: str
    provider_id: str
    detail: str | None = None


class WebhookNotificationProvider:
    """Cloud-side delivery adapter for a configured notification gateway."""

    provider_id = "cloud-webhook"

    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 5.0) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "enabled": bool(self.url),
            "status": "ready" if self.url else "disabled",
        }

    def deliver(
        self,
        title: str,
        body: str,
        *,
        user_id: str = "default",
        notification_id: str | None = None,
    ) -> NotificationReceipt:
        if not self.url:
            return NotificationReceipt("DISABLED", self.provider_id)
        payload = json.dumps({
            "notification_id": notification_id,
            "user_id": user_id,
            "title": title,
            "body": body,
        }, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                if status >= 400:
                    return NotificationReceipt("FAILED", self.provider_id, f"HTTP {status}")
        except (OSError, URLError, TimeoutError) as error:
            return NotificationReceipt("FAILED", self.provider_id, str(error))
        return NotificationReceipt("DELIVERED", self.provider_id)


class EmailNotificationProvider:
    """SMTP notification adapter with explicit disabled and failed states."""

    provider_id = "smtp-email"

    def __init__(
        self,
        host: str | None = None,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        *,
        use_ssl: bool = False,
        starttls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.sender = sender
        self.recipient = recipient
        self.use_ssl = use_ssl
        self.starttls = starttls
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        enabled = bool(self.host and self.sender and self.recipient)
        return {
            "provider_id": self.provider_id,
            "enabled": enabled,
            "status": "ready" if enabled else "disabled",
        }

    def deliver(
        self,
        title: str,
        body: str,
        *,
        user_id: str = "default",
        notification_id: str | None = None,
    ) -> NotificationReceipt:
        if not self.health()["enabled"]:
            return NotificationReceipt("DISABLED", self.provider_id)
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(body)
        try:
            client_factory = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
            with client_factory(self.host, self.port, timeout=self.timeout) as client:
                if self.starttls and not self.use_ssl:
                    client.starttls()
                if self.username:
                    client.login(self.username, self.password or "")
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            return NotificationReceipt("FAILED", self.provider_id, str(error))
        return NotificationReceipt("DELIVERED", self.provider_id)


class DeviceGatewayNotificationProvider:
    """Deliver registered Web Push/APNs/FCM device tokens to a configured gateway."""

    provider_id = "device-gateway"

    def __init__(
        self,
        db: Any,
        url: str | None = None,
        token: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.db = db
        self.url = url
        self.token = token
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "enabled": bool(self.url),
            "status": "ready" if self.url else "disabled",
        }

    def deliver(
        self,
        title: str,
        body: str,
        *,
        user_id: str = "default",
        notification_id: str | None = None,
    ) -> NotificationReceipt:
        if not self.url:
            return NotificationReceipt("DISABLED", self.provider_id)
        devices = [
            {
                "device_id": device["device_id"],
                "platform": device["platform"],
                "push_token": device["push_token"],
            }
            for device in self.db.list_devices(user_id)
            if device.get("push_token")
        ]
        if not devices:
            return NotificationReceipt("DISABLED", self.provider_id, "no_registered_devices")
        payload = json.dumps({
            "notification_id": notification_id,
            "user_id": user_id,
            "title": title,
            "body": body,
            "devices": devices,
        }, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                if status >= 400:
                    return NotificationReceipt("FAILED", self.provider_id, f"HTTP {status}")
        except (OSError, URLError, TimeoutError) as error:
            return NotificationReceipt("FAILED", self.provider_id, str(error))
        return NotificationReceipt("DELIVERED", self.provider_id)


class PlatformPushGatewayNotificationProvider:
    """Route registered device tokens to platform-specific push gateways."""

    provider_id = "platform-push-gateway"

    def __init__(
        self,
        db: Any,
        endpoints: dict[str, str | None],
        tokens: dict[str, str | None],
        timeout: float = 5.0,
    ) -> None:
        self.db = db
        self.endpoints = endpoints
        self.tokens = tokens
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        channels = sorted(
            platform
            for platform, url in self.endpoints.items()
            if url
        )
        return {
            "provider_id": self.provider_id,
            "enabled": bool(channels),
            "status": "ready" if channels else "disabled",
            "channels": channels,
        }

    def deliver(
        self,
        title: str,
        body: str,
        *,
        user_id: str = "default",
        notification_id: str | None = None,
    ) -> NotificationReceipt:
        devices_by_platform: dict[str, list[dict[str, str]]] = {}
        for device in self.db.list_devices(user_id):
            platform = str(device.get("platform") or "")
            push_token = device.get("push_token")
            if platform and push_token and self.endpoints.get(platform):
                devices_by_platform.setdefault(platform, []).append({
                    "device_id": str(device["device_id"]),
                    "push_token": str(push_token),
                })
        if not devices_by_platform:
            return NotificationReceipt(
                "DISABLED",
                self.provider_id,
                "no_configured_platform_devices",
            )

        for platform, devices in sorted(devices_by_platform.items()):
            endpoint = self.endpoints[platform]
            if not endpoint:
                continue
            payload = json.dumps({
                "notification_id": notification_id,
                "user_id": user_id,
                "platform": platform,
                "title": title,
                "body": body,
                "devices": devices,
            }, ensure_ascii=False).encode()
            headers = {"Content-Type": "application/json"}
            token = self.tokens.get(platform)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            request = Request(endpoint, data=payload, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", 200))
                    if status >= 400:
                        return NotificationReceipt(
                            "FAILED",
                            self.provider_id,
                            f"{platform}: HTTP {status}",
                        )
            except (OSError, URLError, TimeoutError) as error:
                return NotificationReceipt(
                    "FAILED",
                    self.provider_id,
                    f"{platform}: {error}",
                )
        return NotificationReceipt("DELIVERED", self.provider_id)


class NotificationRouter:
    """Attempt configured delivery providers in deterministic order."""

    def __init__(self, providers: list[Any]) -> None:
        self.providers = providers

    def health(self) -> dict[str, Any]:
        providers = [provider.health() for provider in self.providers]
        enabled = [provider for provider in providers if provider.get("enabled")]
        return {
            "provider_id": "notification-router",
            "status": "ready" if enabled else "disabled",
            "providers": providers,
        }

    def deliver(
        self,
        title: str,
        body: str,
        *,
        user_id: str = "default",
        notification_id: str | None = None,
    ) -> NotificationReceipt:
        receipts: list[NotificationReceipt] = []
        for provider in self.providers:
            receipt = provider.deliver(
                title,
                body,
                user_id=user_id,
                notification_id=notification_id,
            )
            receipts.append(receipt)
            if receipt.status == "DELIVERED":
                return receipt
        return next(
            (receipt for receipt in receipts if receipt.status != "DISABLED"),
            receipts[0] if receipts else NotificationReceipt("DISABLED", "notification-router"),
        )


class LocalNotificationProvider:
    """Best-effort native notifications with an explicit disabled state."""

    provider_id = "local-native"

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "enabled": self.enabled,
            "platform": platform.system().lower(),
            "status": "ready" if self.enabled else "disabled",
        }

    def deliver(
        self,
        title: str,
        body: str,
        *,
        user_id: str = "default",
        notification_id: str | None = None,
    ) -> NotificationReceipt:
        if not self.enabled:
            return NotificationReceipt("DISABLED", self.provider_id)
        try:
            system = platform.system()
            if system == "Darwin":
                script = (
                    "display notification "
                    + _quote_applescript(body)
                    + " with title "
                    + _quote_applescript(title)
                )
                subprocess.run(
                    ["osascript", "-e", script],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            elif system == "Windows":
                _deliver_windows_notification(title, body)
            else:
                return NotificationReceipt("UNSUPPORTED", self.provider_id, system)
        except (OSError, subprocess.SubprocessError) as error:
            return NotificationReceipt("FAILED", self.provider_id, str(error))
        return NotificationReceipt("DELIVERED", self.provider_id)


def _quote_applescript(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _deliver_windows_notification(title: str, body: str) -> None:
    """Try a native Windows Toast, then fall back to a session message."""
    toast_script = _windows_toast_script(title, body)
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                toast_script,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    except (OSError, subprocess.SubprocessError) as toast_error:
        try:
            subprocess.run(
                ["msg", "*", f"{title}: {body}"],
                check=True,
                capture_output=True,
                text=True,
            )
            return
        except (OSError, subprocess.SubprocessError) as fallback_error:
            raise RuntimeError(
                f"Windows Toast failed: {toast_error}; msg fallback failed: {fallback_error}"
            ) from fallback_error


def _windows_toast_script(title: str, body: str) -> str:
    title_xml = escape_xml(str(title))
    body_xml = escape_xml(str(body))
    app_id = escape_xml("Pia")
    return (
        "$ErrorActionPreference = 'Stop'; "
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f"$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\">"
        f"<text>{title_xml}</text><text>{body_xml}</text></binding></visual></toast>'); "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show($toast)"
    )
