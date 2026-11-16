from __future__ import annotations

import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from pia_runtime.notifications import (
    DeviceGatewayNotificationProvider,
    EmailNotificationProvider,
    LocalNotificationProvider,
    NotificationRouter,
    PlatformPushGatewayNotificationProvider,
    WebhookNotificationProvider,
)


class NotificationProviderTest(unittest.TestCase):
    def test_email_provider_delivers_through_smtp(self):
        provider = EmailNotificationProvider(
            "smtp.example.test",
            sender="pia@example.test",
            recipient="user@example.test",
        )
        sent = []

        class FakeSMTP:
            def __init__(self, host, port, timeout):
                self.host = host
                self.port = port
                self.timeout = timeout

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def starttls(self):
                sent.append(("starttls",))

            def send_message(self, message):
                sent.append((message["Subject"], message["From"], message["To"]))

        with patch("pia_runtime.notifications.smtplib.SMTP", FakeSMTP):
            receipt = provider.deliver("Pia", "Quality is ready.")

        self.assertEqual(receipt.status, "DELIVERED")
        self.assertEqual(sent[-1], ("Pia", "pia@example.test", "user@example.test"))

    def test_email_provider_is_disabled_without_required_configuration(self):
        provider = EmailNotificationProvider(sender="pia@example.test")

        self.assertEqual(provider.health()["status"], "disabled")
        self.assertEqual(provider.deliver("Pia", "body").status, "DISABLED")

    def test_webhook_provider_delivers_to_real_local_gateway(self):
        received: list[tuple[dict[str, object], str | None]] = []
        delivered = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode())
                received.append((payload, self.headers.get("Authorization")))
                self.send_response(202)
                self.end_headers()
                delivered.set()

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = WebhookNotificationProvider(
                f"http://127.0.0.1:{server.server_port}/notify",
                "gateway-secret",
            )
            receipt = provider.deliver(
                "Pia",
                "Review ready",
                user_id="user-a",
                notification_id="notification-1",
            )
            self.assertEqual(receipt.status, "DELIVERED")
            self.assertTrue(delivered.wait(timeout=2))
            self.assertEqual(received, [(
                {
                    "notification_id": "notification-1",
                    "user_id": "user-a",
                    "title": "Pia",
                    "body": "Review ready",
                },
                "Bearer gateway-secret",
            )])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_device_gateway_sends_only_user_devices(self):
        class FakeDB:
            def list_devices(self, user_id):
                self.user_id = user_id
                return [
                    {
                        "device_id": "ios-1",
                        "platform": "ios",
                        "push_token": "push-a",
                    },
                    {
                        "device_id": "web-2",
                        "platform": "web",
                        "push_token": None,
                    },
                ]

        provider = DeviceGatewayNotificationProvider(
            FakeDB(),
            "https://push.example.test/send",
            "gateway-secret",
        )
        with patch("pia_runtime.notifications.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.status = 202
            receipt = provider.deliver(
                "Pia",
                "Review ready",
                user_id="user-a",
                notification_id="notification-2",
            )

        self.assertEqual(receipt.status, "DELIVERED")
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer gateway-secret")
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["user_id"], "user-a")
        self.assertEqual(payload["devices"], [{
            "device_id": "ios-1",
            "platform": "ios",
            "push_token": "push-a",
        }])

    def test_router_falls_back_to_webhook_when_native_is_disabled(self):
        native = LocalNotificationProvider(enabled=False)
        webhook = WebhookNotificationProvider("https://notify.example.test/push", "secret")
        router = NotificationRouter([native, webhook])

        with patch("pia_runtime.notifications.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.status = 202
            receipt = router.deliver(
                "Pia",
                "Review ready",
                user_id="user-a",
                notification_id="notification-1",
            )

        self.assertEqual(receipt.status, "DELIVERED")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://notify.example.test/push")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(request.data.decode())["user_id"], "user-a")

    def test_router_is_explicitly_disabled_without_providers(self):
        router = NotificationRouter([
            LocalNotificationProvider(enabled=False),
            WebhookNotificationProvider(),
        ])

        self.assertEqual(router.deliver("Pia", "No delivery").status, "DISABLED")
        self.assertEqual(router.health()["status"], "disabled")

    def test_platform_gateway_routes_tokens_by_channel(self):
        class FakeDB:
            def list_devices(self, user_id):
                self.user_id = user_id
                return [
                    {
                        "device_id": "ios-1",
                        "platform": "ios",
                        "push_token": "apns-token",
                    },
                    {
                        "device_id": "android-1",
                        "platform": "android",
                        "push_token": "fcm-token",
                    },
                    {
                        "device_id": "web-1",
                        "platform": "web",
                        "push_token": "web-token",
                    },
                ]

        calls: list[tuple[str, dict[str, object], str | None]] = []

        def fake_urlopen(request, timeout):
            calls.append((
                request.full_url,
                json.loads(request.data.decode()),
                request.get_header("Authorization"),
            ))
            class Response:
                status = 202

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

            return Response()

        provider = PlatformPushGatewayNotificationProvider(
            FakeDB(),
            {
                "web": "https://push.example.test/web",
                "ios": "https://push.example.test/apns",
                "android": "https://push.example.test/fcm",
            },
            {
                "web": "web-secret",
                "ios": "apns-secret",
                "android": "fcm-secret",
            },
        )
        with patch("pia_runtime.notifications.urlopen", side_effect=fake_urlopen):
            receipt = provider.deliver(
                "Pia",
                "Review ready",
                user_id="user-a",
                notification_id="notification-3",
            )

        self.assertEqual(receipt.status, "DELIVERED")
        self.assertEqual([call[0] for call in calls], [
            "https://push.example.test/fcm",
            "https://push.example.test/apns",
            "https://push.example.test/web",
        ])
        self.assertEqual(calls[0][2], "Bearer fcm-secret")
        self.assertEqual(calls[0][1]["devices"], [{
            "device_id": "android-1",
            "push_token": "fcm-token",
        }])

    def test_platform_gateway_delivers_to_real_local_gateway(self):
        received: list[tuple[dict[str, object], str | None]] = []
        delivered = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode())
                received.append((payload, self.headers.get("Authorization")))
                self.send_response(202)
                self.end_headers()
                if len(received) == 3:
                    delivered.set()

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        class FakeDB:
            def list_devices(self, user_id):
                self.user_id = user_id
                return [
                    {
                        "device_id": "ios-1",
                        "platform": "ios",
                        "push_token": "apns-token",
                    },
                    {
                        "device_id": "android-1",
                        "platform": "android",
                        "push_token": "fcm-token",
                    },
                    {
                        "device_id": "web-1",
                        "platform": "web",
                        "push_token": "web-token",
                    },
                ]

        endpoint = f"http://127.0.0.1:{server.server_port}/push"
        provider = PlatformPushGatewayNotificationProvider(
            FakeDB(),
            {"web": endpoint, "ios": endpoint, "android": endpoint},
            {"web": "web-secret", "ios": "apns-secret", "android": "fcm-secret"},
        )
        try:
            receipt = provider.deliver(
                "Pia",
                "Review ready",
                user_id="user-a",
                notification_id="notification-live",
            )
            self.assertEqual(receipt.status, "DELIVERED")
            self.assertTrue(delivered.wait(timeout=2))
            self.assertEqual(
                {payload["platform"] for payload, _ in received},
                {"web", "ios", "android"},
            )
            self.assertEqual(
                {payload["user_id"] for payload, _ in received},
                {"user-a"},
            )
            self.assertEqual(
                {authorization for _, authorization in received},
                {"Bearer web-secret", "Bearer apns-secret", "Bearer fcm-secret"},
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
