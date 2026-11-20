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

    def request(self, method="GET", body=None, headers=None, *, path=None):
        request = urllib.request.Request(
            self.url if path is None else self.url.replace("/settings/deepseek", path),
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

    def test_tushare_token_hot_reload_limits_local_requests_to_free_stock_daily(self):
        path = "/settings/tushare"
        stock = "600000.SH"
        as_of = "2026-11-05"
        calls = []
        reject_daily = False

        real_urlopen = urllib.request.urlopen

        def open_request(request, *, timeout):
            if request.full_url.startswith("http://127.0.0.1:"):
                return real_urlopen(request, timeout=timeout)
            self.assertEqual(request.full_url, "https://api.tushare.pro")
            self.assertEqual(request.get_method(), "POST")
            payload = json.loads(request.data)
            self.assertEqual(payload["api_name"], "daily")
            calls.append((payload["token"], payload["params"]))
            if reject_daily:
                return io.BytesIO(b'{"code":2002,"data":null}')
            row = {"ts_code": stock, "trade_date": "20261105", "close": 12, "open": 11,
                   "high": 12, "low": 11, "pre_close": 11, "vol": 100, "amount": 200}
            return io.BytesIO(json.dumps({"code": 0, "data": {"fields": list(row), "items": [list(row.values())]}}).encode())

        def invoke(leaf, args, kwargs=None, **_options):
            if args[0] == "akshare":
                if args[2] == "get_daily_bars":
                    return self.runtime.fixture_provider.get_daily_bars(*args[3])
                raise ConnectionError("fixture AKShare is unavailable")
            return leaf(*args, **(kwargs or {}))

        with patch.dict(os.environ, {"TUSHARE_TOKEN": "env-tushare-token"}), patch(
            "pia_runtime.adapters.urllib.request.urlopen", side_effect=open_request,
        ), patch("pia_runtime.isolated_call.isolated_call", side_effect=invoke):
            self.assertEqual(self.request(path=path), (200, {"configured": True, "source": "environment"}))
            self.assertEqual(self.request("POST", {"token": " saved-tushare-token "}, path=path),
                             (200, {"configured": True, "source": "saved"}))
            demo_provider, _ = self.runtime._provider_call("daily_bars", "get_daily_bars", stock, as_of, as_of)
            self.assertEqual(demo_provider.provider_id, "fixture")
            self.assertEqual(calls, [])
            self.runtime.settings.data_provider = "akshare"
            for capability, symbol in (("market_snapshot", ""), ("trading_calendar", ""),
                                       ("daily_bars", "510300.SH"), ("daily_bars", "000001.SH")):
                self.assertEqual([p.provider_id for p in self.runtime._provider_chain(capability, symbol)], ["akshare"])
            synced = self.runtime.sync_market_data(as_of, [stock])
            self.assertEqual(synced["market_snapshot_quality"], "unavailable")
            self.assertEqual(synced["counts"]["daily_bars"], 1)
            daily_attempt = next(attempt for attempt in synced["provider_attempts"] if attempt["capability"] == "daily_bars")
            self.assertEqual((daily_attempt["provider_id"], daily_attempt["outcome"]), ("tushare", "success"))
            self.assertEqual(calls, [("saved-tushare-token", {"ts_code": stock, "start_date": "20261105", "end_date": "20261105"})])
            reject_daily = True
            provider, bars = self.runtime._provider_call("daily_bars", "get_daily_bars", stock, as_of, as_of)
            self.assertEqual(provider.provider_id, "akshare")
            self.assertEqual([attempt["provider_id"] for attempt in bars[0]["provenance"]["attempts"]], ["tushare", "akshare"])
            reject_daily = False
            restarted = PiaRuntime(Settings(db_path=self.directory / "restart.sqlite3", data_provider="akshare"))
            try:
                self.assertEqual(restarted.settings.tushare_token, "saved-tushare-token")
            finally:
                restarted.close()
            self.assertEqual(self.request("DELETE", path=path), (200, {"configured": True, "source": "environment"}))
            _, bars = self.runtime._provider_call("daily_bars", "get_daily_bars", stock, as_of, as_of)
            self.assertEqual(calls[-1][0], "env-tushare-token")
            self.assertEqual((bars[0]["trade_date"], bars[0]["amount"]), (as_of, 200000.0))
            with patch.dict(os.environ, {"TUSHARE_TOKEN": ""}):
                self.assertEqual(self.request("DELETE", path=path), (200, {"configured": False, "source": "none"}))
                self.assertNotIn("tushare", [p.provider_id for p in self.runtime._provider_chain("daily_bars", stock)])

    def test_tushare_settings_reject_invalid_or_untrusted_requests_and_hide_tokens(self):
        path = "/settings/tushare"
        self.assertEqual(self.request("POST", {"token": "__PLACEHOLDER__"}, path=path)[0], 400)
        self.assertEqual(self.request("POST", {"token": "test-token"}, {"Origin": "https://untrusted.example"}, path=path)[0], 403)
        with patch("pia_runtime.credentials._native_set", side_effect=RuntimeError("private-test-token")):
            self.assertEqual(self.request("POST", {"token": "private-test-token"}, path=path),
                             (500, {"error": "credential_store_unavailable"}))
        self.runtime.settings.mode = "cloud"
        self.assertEqual(self.request(path=path)[0], 403)
        self.assertEqual(self.request("DELETE", path=path)[0], 403)

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
