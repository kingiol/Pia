import os
import unittest
from unittest.mock import patch

from pia_runtime.config import Settings


class SettingsTest(unittest.TestCase):
    def test_default_mode_remains_local(self):
        self.assertEqual(Settings().mode, "local")

    def test_legacy_mode_is_normalized_before_runtime_uses_it(self):
        self.assertEqual(Settings(mode="server").mode, "cloud")

    def test_cloud_configuration_takes_precedence_over_legacy_values(self):
        with (
            patch.dict(os.environ, {
                "PIA_MODE": "cloud",
                "PIA_CLOUD_AUTH_TOKEN": "cloud-token",
                "PIA_CLOUD_USERS": "cloud-user-token=user-a",
                "PIA_SERVER_AUTH_TOKEN": "legacy-token",
                "PIA_SERVER_USERS": "legacy-user-token=user-b",
            }, clear=True),
            patch("pia_runtime.credentials._native_get", return_value=None),
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.mode, "cloud")
        self.assertEqual(settings.cloud_auth_token, "cloud-token")
        self.assertEqual(settings.cloud_users, {
            "cloud-token": "default",
            "cloud-user-token": "user-a",
        })

    def test_legacy_environment_keeps_authentication_and_user_scope(self):
        with (
            patch.dict(os.environ, {
                "PIA_MODE": "server",
                "PIA_SERVER_AUTH_TOKEN": "legacy-token",
                "PIA_SERVER_USERS": "user-token=user-a",
            }, clear=True),
            patch("pia_runtime.credentials._native_get", return_value=None),
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.mode, "cloud")
        self.assertEqual(settings.cloud_auth_token, "legacy-token")
        self.assertEqual(settings.cloud_users, {
            "legacy-token": "default",
            "user-token": "user-a",
        })

    def test_empty_cloud_users_does_not_reactivate_legacy_users(self):
        with (
            patch.dict(os.environ, {
                "PIA_CLOUD_AUTH_TOKEN": "cloud-token",
                "PIA_CLOUD_USERS": "",
                "PIA_SERVER_USERS": "revoked-token=user-a",
            }, clear=True),
            patch("pia_runtime.credentials._native_get", return_value=None),
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.cloud_users, {"cloud-token": "default"})

    def test_legacy_native_credential_remains_readable(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pia_runtime.config.configured_secret", side_effect=lambda name: (
                "legacy-token" if name == "PIA_SERVER_AUTH_TOKEN" else None
            )),
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.cloud_auth_token, "legacy-token")
        self.assertEqual(settings.cloud_users, {"legacy-token": "default"})


if __name__ == "__main__":
    unittest.main()
