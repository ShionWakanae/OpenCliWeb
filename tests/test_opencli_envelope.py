import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.opencli_envelope import (
    describe_error,
    detect_envelope,
    format_error,
    parse_envelope,
    parse_payload,
)


class OpenCLIEnvelopeTests(unittest.TestCase):
    def test_success_envelope_is_detected_and_unwrapped(self):
        ok, data, error = parse_envelope('{"ok":true,"data":{"count":2}}')

        self.assertTrue(ok)
        self.assertEqual(data, {"count": 2})
        self.assertIsNone(error)

    def test_error_envelope_is_detected_and_exposes_details(self):
        ok, data, error = parse_envelope(
            '{"ok":false,"error":{"code":"NOT_FOUND","message":"nothing here",'
            '"exitCode":1,"hint":"try another"}}'
        )

        self.assertFalse(ok)
        self.assertIsNone(data)
        self.assertEqual(error["code"], "NOT_FOUND")
        self.assertEqual(error["message"], "nothing here")
        self.assertEqual(error["hint"], "try another")

    def test_bare_payload_is_not_mistaken_for_envelope(self):
        # `-f yaml` / `--help -f json` 都会输出不带信封的裸内容
        self.assertIsNone(detect_envelope("name: opencli\ndescription: x\n"))
        self.assertIsNone(detect_envelope('{"name":"opencli","commands":[]}'))
        # 普通站点数据里恰好有 ok 字段，但缺少 data/error，不算信封
        self.assertIsNone(detect_envelope('{"ok":true,"items":[1,2]}'))

    def test_noisy_stdout_still_yields_envelope(self):
        raw = 'some log line\n{"ok":false,"error":{"code":"X","message":"m"}}\ntrailing'

        ok, _, error = parse_envelope(raw)

        self.assertFalse(ok)
        self.assertEqual(error["code"], "X")

    def test_error_text_is_human_readable(self):
        text = format_error(
            {"code": "NOT_FOUND", "message": "nothing here", "hint": "try another"}
        )

        self.assertEqual(
            text,
            "opencli 错误 [NOT_FOUND]: nothing here\n提示: try another",
        )

    def test_error_text_without_optional_fields(self):
        self.assertEqual(format_error({"message": "boom"}), "opencli 错误: boom")

    def test_describe_error_falls_back_to_stderr_then_stdout(self):
        error, code, hint = describe_error(None, stdout="", stderr="boom", returncode=2)

        self.assertEqual(error, "boom")
        self.assertEqual(code, "")
        self.assertEqual(hint, "")

    def test_parse_payload_unwraps_envelope_and_parses_bare_output(self):
        self.assertEqual(parse_payload('{"ok":true,"data":{"a":1}}', "json"), {"a": 1})
        self.assertEqual(parse_payload("- a: 1\n", "yaml"), [{"a": 1}])
        self.assertEqual(parse_payload('{"a":1}', "json"), {"a": 1})


if __name__ == "__main__":
    unittest.main()
