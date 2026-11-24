import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pia_runtime.credentials import CredentialStore


CLI = [sys.executable, "-m", "pia_runtime.cli"]


def desktop(*, channel, provider, directory):
    return [*CLI, "desktop", "--channel", channel, "--provider", provider, "--data-dir", str(directory)]


@contextmanager
def running_desktop(command, env):
    with subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          encoding="utf-8", errors="replace") as process:
        lines = queue.Queue()

        def read():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        try:
            while True:
                line = lines.get(timeout=25)
                if line is None or line.startswith("PIA_DESKTOP_ERROR "):
                    raise AssertionError(f"Desktop runtime did not start: {line}")
                if line.startswith("PIA_DESKTOP_READY "):
                    yield process, json.loads(line.removeprefix("PIA_DESKTOP_READY "))
                    return
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def request(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=10) as response:
        return json.load(response)


class DesktopRuntimeTest(unittest.TestCase):
    def test_market_sync_streams_progress_and_preserves_json_response(self):
        with tempfile.TemporaryDirectory() as directory:
            command = desktop(channel="debug", provider="fixture", directory=Path(directory))
            env = dict(os.environ, PIA_SCHEDULER_ENABLED="0", PIA_AUTOSTART_TASKS="0")
            with running_desktop(command, env) as (_, runtime):
                url = runtime["base_url"] + "/data/sync"
                payload = {"as_of": "2026-11-05", "include_default_symbols": False}
                with urlopen(Request(url, data=json.dumps(payload).encode(), headers={
                    "Content-Type": "application/json", "Accept": "application/x-ndjson",
                }), timeout=10) as response:
                    self.assertEqual(response.status, 202)
                    self.assertEqual(response.headers.get_content_type(), "application/x-ndjson")
                    frames = [json.loads(line) for line in response]
                self.assertEqual(frames[0]["progress"]["stage"], "market_snapshot")
                self.assertEqual(frames[0]["progress"]["status"], "running")
                self.assertEqual(frames[-2], {"progress": {"stage": "finalizing", "status": "running"}})
                self.assertEqual(frames[-1]["result"]["counts"]["market_snapshot"], 1)
                self.assertEqual(frames[-1]["result"]["requested_symbols"], [])
                repeated = request(url, payload)
                self.assertEqual(repeated["counts"]["trading_calendar"], 0)
                self.assertEqual(repeated["stages"][1]["status"], "reused")
                self.assertNotEqual(repeated["stages"][0]["status"], "reused")

    @unittest.skipIf(os.name == "nt", "Windows uses a job object to tie the runtime to the desktop")
    def test_debug_runtime_releases_data_when_desktop_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            command = desktop(channel="debug", provider="fixture", directory=Path(directory))
            env = dict(os.environ, PIA_SCHEDULER_ENABLED="0", PIA_AUTOSTART_TASKS="0")
            with running_desktop([*command, "--exit-on-stdin-close"], env) as (process, first):
                process.stdin.close()
                self.assertEqual(process.wait(timeout=10), 0)
            with running_desktop(command, env) as (_, reopened):
                self.assertNotEqual(reopened["instance_id"], first["instance_id"])

    def test_desktop_instances_isolate_data_and_release_reopens_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_dir = root / "release"
            debug_command = desktop(channel="debug", provider="fixture", directory=root / "debug")
            release_command = desktop(channel="release", provider="akshare", directory=release_dir)
            env = dict(os.environ, PIA_SCHEDULER_ENABLED="0", PIA_AUTOSTART_TASKS="0", PIA_PORT="1",
                       PIA_DB_PATH=str(root / "legacy.sqlite3"), PIA_DUCKDB_PATH=str(root / "legacy.duckdb"))
            with running_desktop(release_command, env) as (_, release), running_desktop(debug_command, env) as (_, debug):
                debug_base, release_base = debug["base_url"], release["base_url"]
                self.assertNotEqual(debug_base.split("/")[2], release_base.split("/")[2])
                self.assertEqual(request(release_base + "/health")["desktop_runtime"]["channel"], "release")
                wrong_instance = release_base.replace(release["instance_id"], debug["instance_id"])
                with self.assertRaises(HTTPError) as wrong:
                    request(wrong_instance + "/watchlists", {"name": "Wrong", "symbols": ["000001.SZ"]})
                self.assertEqual(wrong.exception.code, 404)
                wrong.exception.close()
                request(debug_base + "/watchlists", {"name": "Debug", "symbols": ["510300.SH"]})
                request(release_base + "/watchlists", {"name": "Release", "symbols": ["600000.SH"]})
                portfolio = request(release_base + "/portfolio/import", {
                    "format": "csv", "content": "symbol,quantity,avg_cost,market_value\n600000.SH,10,9,100",
                    "as_of": "2026-11-05",
                })["portfolio"]
                task = request(release_base + "/tasks", {
                    "trigger_type": "StockResearch", "target": {"symbol": "600000.SH"},
                })["task"]
                self.assertEqual([row["name"] for row in request(debug_base + "/watchlists")["watchlists"]], ["Debug"])
                self.assertEqual([row["name"] for row in request(release_base + "/watchlists")["watchlists"]], ["Release"])
                self.assertEqual(request(debug_base + "/portfolio")["status"], "unavailable")
                self.assertEqual(request(debug_base + "/tasks")["tasks"], [])

                duplicate = subprocess.run(release_command, env=env, capture_output=True, timeout=15)
                self.assertNotEqual(duplicate.returncode, 0)
                self.assertIn("此数据目录正在使用", json.loads(duplicate.stdout.removeprefix(b"PIA_DESKTOP_ERROR ")))
                backup_env = {**env, "PIA_DB_PATH": str(release_dir / "pia.sqlite3")}
                busy_backup = subprocess.run([*CLI, "backup", str(root / "busy.zip")], env=backup_env,
                                             capture_output=True, timeout=15)
                self.assertNotEqual(busy_backup.returncode, 0)
                self.assertFalse((root / "busy.zip").exists())

            wrong_profile = desktop(channel="debug", provider="fixture", directory=release_dir)
            rejected = subprocess.run(wrong_profile, env=env, capture_output=True, timeout=15)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("当前应用与数据目录的环境不一致", json.loads(rejected.stdout.removeprefix(b"PIA_DESKTOP_ERROR ")))
            with running_desktop(release_command, env) as (_, reopened):
                self.assertNotEqual(reopened["instance_id"], release["instance_id"])
                rows = request(reopened["base_url"] + "/watchlists")["watchlists"]
                self.assertEqual(rows[0]["symbols"], ["600000.SH"])
                self.assertEqual(request(reopened["base_url"] + "/portfolio")["snapshot_id"], portfolio["snapshot_id"])
                self.assertEqual(request(reopened["base_url"] + "/tasks")["tasks"][0]["id"], task["id"])
            self.assertFalse((root / "legacy.sqlite3").exists())
            self.assertFalse((root / "legacy.duckdb").exists())
            self.assertTrue((release_dir / "pia.duckdb").exists())

    def test_debug_credentials_have_an_independent_environment_and_store(self):
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "release-value", "PIA_DEBUG_TUSHARE_TOKEN": "debug-value"}), \
                patch("pia_runtime.credentials._native_get", return_value=None) as native_get:
            self.assertEqual(CredentialStore("pia").get("TUSHARE_TOKEN"), "release-value")
            self.assertEqual(CredentialStore("pia.debug").get("TUSHARE_TOKEN"), "debug-value")
            del os.environ["PIA_DEBUG_TUSHARE_TOKEN"]
            self.assertIsNone(CredentialStore("pia.debug").get("TUSHARE_TOKEN"))
            native_get.assert_called_once_with("pia.debug", "TUSHARE_TOKEN")
