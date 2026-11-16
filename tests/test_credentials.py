from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pia_runtime.credentials import CredentialStore, configured_secret


class CredentialStoreTest(unittest.TestCase):
    def test_environment_value_takes_precedence_without_native_lookup(self) -> None:
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "env-secret"}, clear=False), patch(
            "pia_runtime.credentials._native_get"
        ) as native_get:
            self.assertEqual(configured_secret("TUSHARE_TOKEN"), "env-secret")
            native_get.assert_not_called()

    def test_saved_deepseek_key_takes_precedence_over_environment(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-secret"}), patch(
            "pia_runtime.credentials._native_get", return_value="saved-secret"
        ):
            self.assertEqual(CredentialStore().resolve("DEEPSEEK_API_KEY"), ("saved-secret", "saved"))

    def test_missing_saved_deepseek_key_falls_back_to_environment(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": " env-secret "}), patch(
            "pia_runtime.credentials._native_get", return_value=None
        ):
            self.assertEqual(CredentialStore().resolve("DEEPSEEK_API_KEY"), ("env-secret", "environment"))

    def test_missing_deepseek_credentials_are_explicit(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "__PROVIDE_LATER__"}), patch(
            "pia_runtime.credentials._native_get", return_value=None
        ):
            self.assertEqual(CredentialStore().resolve("DEEPSEEK_API_KEY"), (None, "none"))

    def test_placeholder_environment_value_falls_back_to_native_store(self) -> None:
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "__PROVIDE_LATER__"}, clear=False), patch(
            "pia_runtime.credentials._native_get",
            return_value="keychain-secret",
        ) as native_get:
            self.assertEqual(configured_secret("TUSHARE_TOKEN"), "keychain-secret")
            native_get.assert_called_once_with("pia", "TUSHARE_TOKEN")

    def test_native_get_uses_argument_array_and_does_not_echo_secret(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False), patch(
            "pia_runtime.credentials.platform.system", return_value="Darwin"
        ), patch("pia_runtime.credentials.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "stored-secret\n"
            store = CredentialStore("pia-test")
            self.assertEqual(store.get("DEEPSEEK_API_KEY"), "stored-secret")
            command = run.call_args.args[0]
            self.assertEqual(command[:2], ["security", "find-generic-password"])
            self.assertNotIn("stored-secret", command)

    def test_set_rejects_placeholders(self) -> None:
        with self.assertRaises(ValueError):
            CredentialStore().set("DEEPSEEK_API_KEY", "__LOCAL_SECRET__")

    def test_windows_set_uses_stdin_for_secret_and_argument_list(self) -> None:
        with patch("pia_runtime.credentials.platform.system", return_value="Windows"), patch(
            "pia_runtime.credentials.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            CredentialStore("pia-test").set("DEEPSEEK_API_KEY", "stored-secret")
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["powershell", "-NoProfile", "-NonInteractive"])
            self.assertIn("-ArgumentList", command[-1])
            self.assertNotIn("stored-secret", command[-1])
            self.assertEqual(run.call_args.kwargs["input"], "stored-secret")

    def test_linux_delete_allows_missing_secret_tool_entry(self) -> None:
        with patch("pia_runtime.credentials.platform.system", return_value="Linux"), patch(
            "pia_runtime.credentials.subprocess.run"
        ) as run:
            run.return_value.returncode = 1
            CredentialStore("pia-test").delete("TUSHARE_TOKEN")
            command = run.call_args.args[0]
            self.assertEqual(
                command,
                ["secret-tool", "clear", "service", "pia-test", "account", "TUSHARE_TOKEN"],
            )
