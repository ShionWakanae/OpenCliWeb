import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.version_text import clean_version, format_versions


class VersionTextTests(unittest.TestCase):
    def test_clean_version_strips_v_prefix(self):
        self.assertEqual(clean_version("v22.11.0"), "22.11.0")
        self.assertEqual(clean_version("V2.1.0"), "2.1.0")
        self.assertEqual(clean_version("  v2.1.0  "), "2.1.0")

    def test_clean_version_is_idempotent(self):
        self.assertEqual(clean_version("2.1.0"), "2.1.0")
        self.assertEqual(clean_version(clean_version("v2.1.0")), "2.1.0")

    def test_clean_version_handles_empty(self):
        self.assertEqual(clean_version(None), "")
        self.assertEqual(clean_version(""), "")

    def test_format_versions_mixes_prefixed_and_bare(self):
        self.assertEqual(
            format_versions(
                {
                    "cliVersion": "v2.1.0",
                    "daemonVersion": "2.0.1",
                    "extensionVersion": "v1.3.2-beta.1",
                }
            ),
            "cli 2.1.0, daemon 2.0.1, extension 1.3.2-beta.1",
        )

    def test_format_versions_skips_missing(self):
        self.assertEqual(format_versions({"cliVersion": "v2.1.0"}), "cli 2.1.0")
        self.assertEqual(format_versions({}), "")


if __name__ == "__main__":
    unittest.main()
