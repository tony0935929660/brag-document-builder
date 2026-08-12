import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import brag_cli


class Slice3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))
        self.addCleanup(lambda: os.environ.pop("OPENAI_API_KEY", None))

        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir(parents=True)
        code, _ = self.run_cli(["init-vault", "--path", str(self.vault)])
        self.assertEqual(code, 0)

        code2, _ = self.run_cli(["capture-text", "--text", "slice3 sample entry"])
        self.assertEqual(code2, 0)

    def run_cli(self, args: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = brag_cli.main(args)
        return code, buf.getvalue()

    def test_analyze_shows_exact_outbound_content_and_size(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        fake_result = {
            "groups": [
                {
                    "project_or_topic": "proj",
                    "items": [
                        {
                            "classification": "new_candidate",
                            "value_assessment": {
                                "impact": 4,
                                "difficulty": 3,
                                "leadership_ownership": 2,
                                "evidence_strength": 5,
                                "reusability": 4,
                            },
                            "reason": "useful",
                        }
                    ],
                }
            ]
        }

        captured_payload = {"content": None}

        def fake_request(api_key: str, model: str, outbound_content: str) -> dict:
            captured_payload["content"] = outbound_content
            return fake_result

        with patch("builtins.input", return_value="YES"), patch(
            "src.brag_cli.request_openai_analysis", side_effect=fake_request
        ):
            code, output = self.run_cli(["analyze-inbox"])

        self.assertEqual(code, 0)
        self.assertIn("BEGIN OUTBOUND CONTENT", output)
        self.assertIn(captured_payload["content"], output)
        self.assertIn("Approx outbound size (bytes):", output)
        self.assertIn('"provider": "openai"', output)

    def test_decline_confirmation_sends_no_request_and_keeps_inbox(self) -> None:
        before = self._today_inbox().read_text(encoding="utf-8")

        with patch("builtins.input", return_value="NO"), patch(
            "src.brag_cli.request_openai_analysis", side_effect=AssertionError("should not call")
        ):
            code, output = self.run_cli(["analyze-inbox"])

        self.assertEqual(code, 0)
        self.assertIn("No request was sent", output)
        after = self._today_inbox().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_oversize_rejected_before_send(self) -> None:
        with patch("builtins.input", return_value="YES"), patch(
            "src.brag_cli.request_openai_analysis", side_effect=AssertionError("should not call")
        ):
            code, output = self.run_cli(["analyze-inbox", "--max-bytes", "1"])

        self.assertEqual(code, 2)
        self.assertIn("exceeds max bytes", output)

    def test_missing_api_key_keeps_inbox(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)
        before = self._today_inbox().read_text(encoding="utf-8")

        with patch("builtins.input", return_value="YES"):
            code, output = self.run_cli(["analyze-inbox"])

        self.assertEqual(code, 2)
        self.assertIn("OPENAI_API_KEY is missing", output)
        after = self._today_inbox().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_api_unavailable_keeps_inbox(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        before = self._today_inbox().read_text(encoding="utf-8")

        with patch("builtins.input", return_value="YES"), patch(
            "src.brag_cli.request_openai_analysis", side_effect=OSError("OpenAI request failed")
        ):
            code, output = self.run_cli(["analyze-inbox"])

        self.assertEqual(code, 3)
        self.assertIn("filesystem operation failed", output)
        after = self._today_inbox().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_malformed_ai_output_fails_safely(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        before = self._today_inbox().read_text(encoding="utf-8")
        malformed = {"groups": [{"project_or_topic": "x", "items": [{"classification": "bad"}]}]}

        with patch("builtins.input", return_value="YES"), patch(
            "src.brag_cli.request_openai_analysis", return_value=malformed
        ):
            code, output = self.run_cli(["analyze-inbox"])

        self.assertEqual(code, 2)
        self.assertIn("classification is invalid", output)
        after = self._today_inbox().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_fixed_ai_response_shows_grouping_and_value_assessment(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        fake_result = {
            "groups": [
                {
                    "project_or_topic": "release",
                    "items": [
                        {
                            "classification": "supporting_evidence",
                            "value_assessment": {
                                "impact": 3,
                                "difficulty": 4,
                                "leadership_ownership": 3,
                                "evidence_strength": 4,
                                "reusability": 5,
                            },
                            "reason": "helps future review",
                        }
                    ],
                }
            ]
        }

        with patch("builtins.input", return_value="YES"), patch(
            "src.brag_cli.request_openai_analysis", return_value=fake_result
        ):
            code, output = self.run_cli(["analyze-inbox", "--model", "gpt-4o-mini"])

        self.assertEqual(code, 0)
        parsed = json.loads(output.splitlines()[-1] if output.strip().startswith("{") else output[output.find("{"):])
        self.assertEqual(parsed["provider"], "openai")
        self.assertEqual(parsed["model"], "gpt-4o-mini")
        self.assertEqual(parsed["analysis"]["groups"][0]["project_or_topic"], "release")

    def test_output_does_not_leak_api_key(self) -> None:
        os.environ["OPENAI_API_KEY"] = "super-secret-key"
        fake_result = {
            "groups": [
                {
                    "project_or_topic": "safe",
                    "items": [
                        {
                            "classification": "retained_raw_activity",
                            "value_assessment": {
                                "impact": 1,
                                "difficulty": 1,
                                "leadership_ownership": 1,
                                "evidence_strength": 1,
                                "reusability": 1,
                            },
                            "reason": "raw",
                        }
                    ],
                }
            ]
        }

        with patch("builtins.input", return_value="YES"), patch(
            "src.brag_cli.request_openai_analysis", return_value=fake_result
        ):
            code, output = self.run_cli(["analyze-inbox"])

        self.assertEqual(code, 0)
        self.assertNotIn("super-secret-key", output)

    def _today_inbox(self) -> Path:
        day = brag_cli.datetime.now(brag_cli.timezone.utc).strftime("%Y-%m-%d")
        return self.vault / "Brag" / "Inbox" / f"{day}.md"


if __name__ == "__main__":
    unittest.main()