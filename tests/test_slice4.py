import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import brag_cli


class Slice4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))
        self.addCleanup(lambda: os.environ.pop("OPENAI_API_KEY", None))

        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir(parents=True)
        self._run_cli(["init-vault", "--path", str(self.vault)])
        self._run_cli(["capture-text", "--text", "slice4 input"])
        os.environ["OPENAI_API_KEY"] = "test-key"

    def _run_cli(self, args: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = brag_cli.main(args)
        return code, buf.getvalue()

    def _analysis_fixture(self) -> dict:
        return {
            "groups": [
                {
                    "project_or_topic": "release",
                    "items": [
                        {
                            "classification": "new_candidate",
                            "value_assessment": {
                                "impact": 3,
                                "difficulty": 2,
                                "leadership_ownership": 2,
                                "evidence_strength": 1,
                                "reusability": 4,
                            },
                            "reason": "candidate reason",
                        }
                    ],
                }
            ]
        }

    def test_quick_mode_returns_without_followup_questions(self) -> None:
        with patch("builtins.input", side_effect=["YES"]), patch(
            "src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()
        ):
            code, output = self._run_cli(["review-candidate", "--mode", "quick"])

        self.assertEqual(code, 0)
        self.assertIn("Quick review selected", output)

    def test_immediate_mode_asks_at_most_three_questions(self) -> None:
        answers = ["YES", "a1", "a2", "a3", "a4"]
        with patch("builtins.input", side_effect=answers), patch(
            "src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()
        ):
            code, output = self._run_cli(["review-candidate", "--mode", "immediate", "--max-followups", "3"])

        self.assertEqual(code, 0)
        result = self._extract_last_json(output)
        self.assertEqual(result["asked_questions"], 3)

    def test_skip_all_keeps_questions_for_later_review(self) -> None:
        with patch("builtins.input", side_effect=["YES", "skip", "skip", "skip"]), patch(
            "src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()
        ):
            code, output = self._run_cli(["review-candidate", "--mode", "immediate", "--max-followups", "3"])

        self.assertEqual(code, 0)
        result = self._extract_last_json(output)
        self.assertGreater(len(result["pending_questions"]), 0)
        self.assertEqual(result["status"], "needs-detail")

    def test_answer_enough_moves_status_to_ready_for_confirmation(self) -> None:
        with patch(
            "builtins.input",
            side_effect=["YES", "ctx", "own work", "sk", "none", "done", "proof"],
        ), patch("src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()):
            code, output = self._run_cli(["review-candidate", "--mode", "immediate", "--max-followups", "6"])

        self.assertEqual(code, 0)
        result = self._extract_last_json(output)
        self.assertEqual(result["status"], "ready-for-confirmation")

    def test_ai_inference_not_recorded_as_confirmed_answer(self) -> None:
        followup = {"suggestions": {"context": "AI guess"}}
        with patch(
            "builtins.input",
            side_effect=["YES", "skip", "skip", "skip", "YES"],
        ), patch("src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()), patch(
            "src.brag_cli.request_openai_followup_suggestions", return_value=followup
        ):
            code, output = self._run_cli(
                ["review-candidate", "--mode", "immediate", "--max-followups", "3", "--ask-ai-followup"]
            )

        self.assertEqual(code, 0)
        result = self._extract_last_json(output)
        self.assertEqual(result["last_suggested_inferences"].get("context"), "AI guess")
        self.assertNotIn("context", result["confirmed_answers"])

    def test_decline_followup_cloud_call_loses_no_candidate_state(self) -> None:
        with patch(
            "builtins.input",
            side_effect=["YES", "ctx", "skip", "skip", "NO"],
        ), patch("src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()), patch(
            "src.brag_cli.request_openai_followup_suggestions", side_effect=AssertionError("must not call")
        ):
            code, output = self._run_cli(
                ["review-candidate", "--mode", "immediate", "--max-followups", "3", "--ask-ai-followup"]
            )

        self.assertEqual(code, 0)
        result = self._extract_last_json(output)
        self.assertEqual(result["confirmed_answers"].get("context"), "ctx")
        self.assertIn("scope", result["pending_questions"])

    def test_followup_cloud_calls_apply_slice3_safety_gates(self) -> None:
        with patch("builtins.input", side_effect=["YES", "skip", "skip", "skip", "YES"]), patch(
            "src.brag_cli.request_openai_analysis", return_value=self._analysis_fixture()
        ), patch(
            "src.brag_cli.request_openai_followup_suggestions", return_value={"suggestions": {}}
        ):
            code, output = self._run_cli(
                ["review-candidate", "--mode", "immediate", "--max-followups", "3", "--ask-ai-followup"]
            )

        self.assertEqual(code, 0)
        self.assertIn("Follow-up suggestion payload preview (exact payload):", output)
        self.assertIn("Outbound content preview (exact payload):", output)
        self.assertGreaterEqual(
            output.count("Warning: Review for confidential or sensitive data before sending."),
            2,
        )

    def _extract_last_json(self, output: str) -> dict:
        start = output.rfind("\n{")
        if start == -1:
            start = output.find("{")
        text = output[start:].strip()
        return json.loads(text)


if __name__ == "__main__":
    unittest.main()