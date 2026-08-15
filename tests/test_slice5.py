import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import brag_cli


class Slice5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))

        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir(parents=True)
        self._run_cli(["init-vault", "--path", str(self.vault)])

        self.candidate_id = "inbox/2026-08-15.md::0"
        self.candidate = {
            "candidate_id": self.candidate_id,
            "status": "ready-for-confirmation",
            "project_or_topic": "Release Automation",
            "confirmed_answers": {
                "context": "Releases were manual.",
                "contribution": "Built the deployment workflow.",
                "outcome": "Reduced release time by 40%.",
                "evidence": "Pipeline duration report.",
            },
            "pending_questions": ["scope", "constraints"],
            "last_suggested_inferences": {"scope": "AI guess"},
        }
        brag_cli.save_review_state({"candidates": {self.candidate_id: self.candidate}})

    def _run_cli(self, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = brag_cli.main(args)
        return code, output.getvalue()

    def _confirm_args(self) -> list[str]:
        return [
            "confirm-candidate",
            "--candidate-id",
            self.candidate_id,
            "--achievement-id",
            "achievement-001",
            "--wording",
            "Automated releases and reduced release time by 40%.",
        ]

    def _all_confirmation_answers(self) -> list[str]:
        return ["YES", "YES", "YES", "YES", "YES", "YES", "YES"]

    def test_confirm_creates_authoritative_achievement(self) -> None:
        with patch("builtins.input", side_effect=self._all_confirmation_answers()):
            code, output = self._run_cli(self._confirm_args())

        self.assertEqual(code, 0)
        path = self.vault / "Brag" / "Achievements" / "release-automation--achievement-001.md"
        content = path.read_text(encoding="utf-8")
        self.assertIn('id: "achievement-001"', content)
        self.assertIn("state: confirmed", content)
        self.assertIn("date:", content)
        self.assertIn(self.candidate_id, content)
        self.assertIn("## Confirmed Facts", content)
        self.assertIn("## Source Material", content)
        self.assertIn("## Generated Wording", content)
        self.assertIn("ai_provider: openai", content)
        self.assertIn('generated_language: "zh-TW"', content)
        self.assertNotIn("AI guess", content)
        self.assertIn("Confirmed achievement created at:", output)

        saved = brag_cli.load_review_state()["candidates"][self.candidate_id]
        self.assertEqual(saved["status"], "confirmed")
        self.assertEqual(saved["achievement_id"], "achievement-001")

    def test_reject_creates_record_with_source_and_reason(self) -> None:
        with patch("builtins.input", side_effect=["YES", "NO", "Not material enough"]):
            code, output = self._run_cli(
                ["confirm-candidate", "--candidate-id", self.candidate_id]
            )

        self.assertEqual(code, 0)
        records = list((self.vault / "Brag" / "Archive" / "Rejected").glob("*.md"))
        self.assertEqual(len(records), 1)
        content = records[0].read_text(encoding="utf-8")
        self.assertIn(self.candidate_id, content)
        self.assertIn("Not material enough", content)
        self.assertIn("Rejected candidate recorded at:", output)
        self.assertEqual(
            brag_cli.load_review_state()["candidates"][self.candidate_id]["status"],
            "rejected",
        )

    def test_cancel_at_each_stage_creates_no_achievement(self) -> None:
        cases = [
            ["NO"],
            ["YES", "YES", "NO"],
            ["YES", "YES", "YES", "YES", "YES", "YES", "NO"],
        ]
        for answers in cases:
            with self.subTest(answers=answers), patch("builtins.input", side_effect=answers):
                code, _ = self._run_cli(self._confirm_args())
                self.assertEqual(code, 0)
                self.assertEqual(
                    list((self.vault / "Brag" / "Achievements").glob("*.md")),
                    [],
                )
                self.assertEqual(
                    brag_cli.load_review_state()["candidates"][self.candidate_id]["status"],
                    "ready-for-confirmation",
                )

    def test_failed_atomic_write_leaves_candidate_retryable_and_no_file(self) -> None:
        with patch("builtins.input", side_effect=self._all_confirmation_answers()), patch(
            "src.brag_cli.write_text_atomic", side_effect=OSError("disk full")
        ):
            code, output = self._run_cli(self._confirm_args())

        self.assertEqual(code, 3)
        self.assertIn("filesystem operation failed", output)
        self.assertEqual(list((self.vault / "Brag" / "Achievements").glob("*.md")), [])
        self.assertEqual(
            brag_cli.load_review_state()["candidates"][self.candidate_id]["status"],
            "ready-for-confirmation",
        )

    def test_malformed_existing_achievement_is_not_overwritten(self) -> None:
        path = self.vault / "Brag" / "Achievements" / "release-automation--achievement-001.md"
        path.write_text("not authoritative markdown", encoding="utf-8")

        with patch("builtins.input", side_effect=self._all_confirmation_answers()):
            code, output = self._run_cli(self._confirm_args())

        self.assertEqual(code, 2)
        self.assertIn("Malformed authoritative achievement Markdown", output)
        self.assertEqual(path.read_text(encoding="utf-8"), "not authoritative markdown")
        self.assertEqual(
            brag_cli.load_review_state()["candidates"][self.candidate_id]["status"],
            "ready-for-confirmation",
        )

    def test_candidate_needs_detail_cannot_be_confirmed(self) -> None:
        state = brag_cli.load_review_state()
        state["candidates"][self.candidate_id]["status"] = "needs-detail"
        brag_cli.save_review_state(state)

        code, output = self._run_cli(self._confirm_args())

        self.assertEqual(code, 2)
        self.assertIn("must be ready-for-confirmation", output)
        self.assertEqual(list((self.vault / "Brag" / "Achievements").glob("*.md")), [])

    def test_invalid_achievement_id_is_rejected_before_write(self) -> None:
        args = self._confirm_args()
        args[args.index("achievement-001")] = "../outside"

        with patch("builtins.input", side_effect=self._all_confirmation_answers()):
            code, output = self._run_cli(args)

        self.assertEqual(code, 2)
        self.assertIn("achievement-id may contain only", output)
        self.assertEqual(list((self.vault / "Brag" / "Achievements").glob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
