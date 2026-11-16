import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.release_preflight import _artifact_files, build_report


class ReleasePreflightTest(unittest.TestCase):
    def test_missing_external_credentials_are_reported_without_secret_values(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "",
                "TUSHARE_TOKEN": "",
                "PIA_POSTGRES_DSN": "",
                "PIA_WEB_PUSH_GATEWAY_URL": "",
                "PIA_WEB_PUSH_GATEWAY_TOKEN": "",
                "PIA_APNS_GATEWAY_URL": "",
                "PIA_APNS_GATEWAY_TOKEN": "",
                "PIA_FCM_GATEWAY_URL": "",
                "PIA_FCM_GATEWAY_TOKEN": "",
                "PIA_PUSH_ACCEPTANCE_WEB_TOKEN": "",
                "PIA_PUSH_ACCEPTANCE_IOS_TOKEN": "",
                "PIA_PUSH_ACCEPTANCE_ANDROID_TOKEN": "",
            },
            clear=False,
        ), patch("scripts.release_preflight.configured_secret", return_value=None):
            report = build_report()

        self.assertFalse(report["mvp_release_ready"])
        self.assertIn("deepseek_credentials", report["mvp_blockers"])
        self.assertIn("tushare_credentials", report["mvp_blockers"])
        rendered = str(report)
        self.assertNotIn("DEEPSEEK_API_KEY=", rendered)
        self.assertNotIn("TUSHARE_TOKEN=", rendered)

    def test_local_artifact_checks_are_explicit(self):
        report = build_report()
        self.assertIn("macos_sidecar", report["checks"])
        self.assertIn("windows_msi", report["checks"])
        self.assertIn("full_milestone_release_ready", report)

    def test_windows_msi_check_requires_a_real_msi_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "msi").mkdir()
            with patch("scripts.release_preflight.ROOT", root):
                self.assertEqual(
                    _artifact_files("msi", "*.msi")["status"],
                    "missing",
                )
                (root / "msi" / "Pia_0.1.0_x64_en-US.msi").write_bytes(b"msi")
                result = _artifact_files("msi", "*.msi")
                self.assertEqual(result["status"], "pass")
                self.assertEqual(result["files"], ["msi/Pia_0.1.0_x64_en-US.msi"])


if __name__ == "__main__":
    unittest.main()
