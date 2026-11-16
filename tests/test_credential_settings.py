import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from pia_runtime.api import serve
from pia_runtime.config import Settings
from pia_runtime.llm import LLMAuthenticationFailed
from pia_runtime.runtime import PiaRuntime


class CredentialSettingsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.saved = {}
        for target, side_effect in (
            ("_native_get", lambda _service, name: self.saved.get(name)),
            ("_native_set", lambda _service, name, value: self.saved.__setitem__(name, value)),
            ("_native_delete", lambda _service, name: self.saved.pop(name, None)),
        ):
            patcher = patch(f"pia_runtime.credentials.{target}", side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        environment = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-test-key"})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime = PiaRuntime(Settings(db_path=self.directory / "pia.sqlite3", autostart_tasks=False))
        self.runtime.settings.cloud_users = {"test-session-token": "default"}
        self.addCleanup(self.runtime.close)
        ready = threading.Event()

        def create_server(address, handler):
            self.server = ThreadingHTTPServer(address, handler)
            ready.set()
            return self.server

        with patch("pia_runtime.api.ThreadingHTTPServer", side_effect=create_server):
            self.thread = threading.Thread(target=serve, args=(self.runtime, "127.0.0.1", 0, "test-session-token"), daemon=True)
            self.thread.start()
            self.assertTrue(ready.wait(5))
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/settings/deepseek"

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def request(self, method="GET", body=None, headers=None):
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json", "Origin": "tauri://localhost",
                     "Authorization": "Bearer test-session-token", **(headers or {})},
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_save_and_clear_update_existing_client_and_fall_back_without_restart(self):
        self.assertEqual(self.request(), (200, {"configured": True, "source": "environment"}))
        client = self.runtime.llm.routes[0].client
        self.assertEqual(self.request("POST", {"api_key": " saved-test-key "}),
                         (200, {"configured": True, "source": "saved"}))
        self.assertIs(self.runtime.llm.routes[0].client, client)
        self.assertEqual(self.runtime.settings.deepseek_api_key, "saved-test-key")
        self.assertTrue(self.runtime.health()["llm"]["credentials_configured"])
        self.assertEqual(Settings.from_env().deepseek_api_key, "saved-test-key")
        response = json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()
        with patch("pia_runtime.llm.urllib.request.urlopen", return_value=io.BytesIO(response)) as transport:
            self.assertEqual(client.generate_structured("system", {}), {"ok": True})
            self.assertEqual(transport.call_args.args[0].get_header("Authorization"), "Bearer saved-test-key")
        self.assertEqual(self.request("DELETE"), (200, {"configured": True, "source": "environment"}))
        self.assertEqual(client.api_key, "env-test-key")
        self.assertEqual(Settings.from_env().deepseek_api_key, "env-test-key")
        with patch("pia_runtime.llm.urllib.request.urlopen", return_value=io.BytesIO(response)) as transport:
            client.generate_structured("system", {})
            self.assertEqual(transport.call_args.args[0].get_header("Authorization"), "Bearer env-test-key")

    def test_clear_without_environment_reports_unconfigured(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            self.assertEqual(self.request(), (200, {"configured": False, "source": "none"}))
            self.request("POST", {"api_key": "saved-test-key"})
            self.assertEqual(self.request("DELETE"), (200, {"configured": False, "source": "none"}))
            self.assertIsNone(self.runtime.deepseek.api_key)
            self.assertFalse(self.runtime.health()["llm"]["credentials_configured"])

    def test_invalid_requests_do_not_modify_credentials(self):
        for body in ({}, {"api_key": ""}, {"api_key": "__PLACEHOLDER__"}, {"api_key": 123},
                     {"api_key": "a\nb"}, {"api_key": "x" * 1025}, {"api_key": "key", "other": "value"}):
            with self.subTest(body_type=type(body.get("api_key")).__name__):
                self.assertEqual(self.request("POST", body)[0], 400)
        self.assertEqual(self.saved, {})

    def test_cloud_and_untrusted_origins_cannot_access_credentials(self):
        for headers in ({"Origin": "https://untrusted.example"}, {"Origin": "null"},
                        {"Host": "untrusted.example"}, {"Content-Type": "text/plain"}):
            self.assertIn(self.request("POST", {"api_key": "test-key"}, headers)[0], {400, 403})
        for mode, headers in (("cloud", {}), ("local", {"Origin": "https://untrusted.example"}),
                              ("local", {"Host": "untrusted.example"})):
            self.runtime.settings.mode = mode
            for method in ("GET", "POST", "DELETE"):
                with self.subTest(mode=mode, method=method, headers=headers):
                    self.assertEqual(self.request(method, {"api_key": "test-key"} if method == "POST" else None, headers)[0], 403)
        self.assertEqual(self.saved, {})

    def test_storage_failure_does_not_change_active_client_or_echo_key(self):
        original_key = self.runtime.deepseek.api_key
        with patch("pia_runtime.credentials._native_set", side_effect=RuntimeError("native credential manager is unavailable")):
            status, payload = self.request("POST", {"api_key": "private-test-key"})
        self.assertEqual(status, 500)
        self.assertNotIn("private-test-key", json.dumps(payload))
        self.assertEqual(self.runtime.deepseek.api_key, original_key)
        self.request("POST", {"api_key": "saved-test-key"})
        with patch("pia_runtime.credentials._native_delete"):
            self.assertEqual(self.request("DELETE")[0], 500)
        self.assertEqual(self.runtime.deepseek.api_key, "saved-test-key")

    def test_configured_authentication_is_required_for_all_credential_operations(self):
        for method in ("GET", "POST", "DELETE"):
            self.assertEqual(self.request(method, {"api_key": "test-key"} if method == "POST" else None,
                                          {"Authorization": ""})[0], 401)
        self.assertEqual(self.saved, {})

    def test_authentication_failure_does_not_fall_back_to_environment(self):
        self.request("POST", {"api_key": "saved-test-key"})
        error = urllib.error.HTTPError("https://api.deepseek.com", 401, "Unauthorized", {}, None)
        with patch("pia_runtime.llm.urllib.request.urlopen", side_effect=error) as transport:
            with self.assertRaises(LLMAuthenticationFailed):
                self.runtime.llm.generate_structured("system", {})
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(self.runtime.deepseek.api_key, "saved-test-key")
        error.close()

    def test_custom_routes_update_only_the_matching_credential_reference(self):
        policy_path = self.directory / "policy.json"
        policy_path.write_text(json.dumps({
            "schema_version": "1",
            "routes": [
                {"route_id": str(index), "provider_id": "compatible", "endpoint": "https://example.invalid",
                 "model": "test-model", "credential_ref": reference, "priority": index,
                 "capabilities": ["structured_output"]}
                for index, reference in enumerate(("DEEPSEEK_API_KEY", "OTHER_LLM_KEY"))
            ],
        }))
        self.saved["OTHER_LLM_KEY"] = "other-test-key"
        runtime = PiaRuntime(Settings(
            db_path=self.directory / "policy.sqlite3", autostart_tasks=False, llm_policy_path=policy_path,
        ))
        try:
            runtime.update_deepseek_credential("saved-test-key")
            self.assertEqual([route.client.api_key for route in runtime.llm.routes], ["saved-test-key", "other-test-key"])
            runtime.update_deepseek_credential(None)
            self.assertEqual([route.client.api_key for route in runtime.llm.routes], ["env-test-key", "other-test-key"])
        finally:
            runtime.close()
