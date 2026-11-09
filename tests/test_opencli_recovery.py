import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.opencli_doctor import (
    evaluate_doctor_output,
    parse_profile_list_envelope,
)


class OpenCLIRecoveryTests(unittest.TestCase):
    def test_profile_list_error_envelope_is_exposed(self):
        profiles, error = parse_profile_list_envelope(
            '{"ok":false,"error":{"code":"DAEMON_OFFLINE","message":"daemon is offline","hint":"Start the daemon"}}'
        )

        self.assertIsNone(profiles)
        self.assertEqual(error["code"], "DAEMON_OFFLINE")
        self.assertEqual(error["hint"], "Start the daemon")

    def test_profile_alias_with_shell_characters_is_data(self):
        profiles, error = parse_profile_list_envelope(
            '{"ok":true,"data":{"profiles":[{"contextId":"ctx 1 & 2","alias":"work profile & test","connected":true}]}}'
        )

        self.assertIsNone(error)
        self.assertEqual(profiles[0].label, "work profile & test")

    def test_legacy_doctor_output_still_falls_back(self):
        evaluation, error = evaluate_doctor_output(
            "[OK] Daemon: running\n[OK] Extension: connected\n[OK] Connectivity: connected"
        )

        self.assertIsNone(error)
        self.assertEqual(evaluation.source, "legacy")
        self.assertTrue(evaluation.all_ok)

if __name__ == "__main__":
    unittest.main()

