import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "release_manifest.py"
SPEC = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseManifestTest(unittest.TestCase):
    def test_manifest_contains_stable_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "bundle" / "Pia.dmg"
            artifact.parent.mkdir()
            artifact.write_bytes(b"pia-release")

            manifest = MODULE.build_manifest(
                root,
                [Path("bundle")],
                "2026-11-07T00:00:00+00:00",
            )

            self.assertEqual(manifest["product"], "pia")
            self.assertEqual(manifest["generated_at"], "2026-11-07T00:00:00+00:00")
            self.assertEqual(manifest["artifacts"][0]["path"], "bundle/Pia.dmg")
            self.assertEqual(
                manifest["artifacts"][0]["sha256"],
                "5344efdfc6a89f6a38d7d287f02b5e2aab143298f6c425d673d4e850da8ac31e",
            )


if __name__ == "__main__":
    unittest.main()
