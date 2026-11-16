import sys
import unittest
from unittest.mock import patch

from pia_runtime import cli
from pia_runtime.config import Settings


class CliTest(unittest.TestCase):
    def test_cloud_scheduler_flag_enables_scheduler(self):
        settings = Settings(cloud_auth_token="test-token", postgres_dsn="postgresql://test")
        with (
            patch.object(cli.Settings, "from_env", return_value=settings),
            patch.object(cli, "PiaRuntime"),
            patch.object(cli, "serve"),
            patch.object(sys, "argv", ["pia", "cloud", "--scheduler"]),
        ):
            cli.main()

        self.assertEqual(settings.mode, "cloud")
        self.assertFalse(settings.autostart_tasks)
        self.assertTrue(settings.scheduler_enabled)
        self.assertTrue(settings.structured_logs)

    def test_cloud_requires_authentication_before_creating_runtime(self):
        with (
            patch.object(cli.Settings, "from_env", return_value=Settings()),
            patch.object(cli, "PiaRuntime") as runtime,
            patch.object(sys, "argv", ["pia", "cloud"]),
        ):
            with self.assertRaisesRegex(SystemExit, "PIA_CLOUD_AUTH_TOKEN is required"):
                cli.main()
        runtime.assert_not_called()

    def test_legacy_command_uses_authenticated_cloud_runtime(self):
        settings = Settings(cloud_auth_token="test-token", postgres_dsn="postgresql://test")
        with (
            patch.object(cli.Settings, "from_env", return_value=settings),
            patch.object(cli, "PiaRuntime") as runtime,
            patch.object(cli, "serve") as serve,
            patch.object(sys, "argv", ["pia", "server", "--port", "9876"]),
        ):
            runtime.return_value.settings = settings
            cli.main()

        self.assertEqual(settings.mode, "cloud")
        self.assertFalse(settings.autostart_tasks)
        serve.assert_called_once_with(runtime.return_value, settings.host, 9876, "test-token")

    def test_worker_never_starts_scheduler(self):
        settings = Settings(scheduler_enabled=True, postgres_dsn="postgresql://test")
        runtime = type("Runtime", (), {"worker_loop": lambda self, *_args: None})()
        with (
            patch.object(cli.Settings, "from_env", return_value=settings),
            patch.object(cli, "PiaRuntime", return_value=runtime),
            patch.object(sys, "argv", ["pia", "worker", "--once"]),
        ):
            cli.main()

        self.assertFalse(settings.scheduler_enabled)
        self.assertEqual(settings.mode, "cloud")

    def test_cloud_and_worker_require_postgres_before_creating_runtime(self):
        for command in ("cloud", "worker", "server"):
            with (
                self.subTest(command=command),
                patch.object(cli.Settings, "from_env", return_value=Settings(cloud_auth_token="test-token")),
                patch.object(cli, "PiaRuntime") as runtime,
                patch.object(sys, "argv", ["pia", command]),
            ):
                with self.assertRaisesRegex(SystemExit, "PIA_POSTGRES_DSN"):
                    cli.main()
                runtime.assert_not_called()

    def test_cloud_rejects_local_backup_and_restore(self):
        for command in ("backup", "restore"):
            with (
                self.subTest(command=command),
                patch.object(cli.Settings, "from_env", return_value=Settings(mode="cloud")),
                patch.object(cli, "PiaRuntime") as runtime,
                patch.object(sys, "argv", ["pia", command, "test.zip"]),
            ):
                with self.assertRaisesRegex(SystemExit, "scripts/cloud-"):
                    cli.main()
                runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
