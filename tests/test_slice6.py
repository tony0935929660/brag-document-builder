import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import brag_cli


class Slice6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))

        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir(parents=True)
        self._run_cli(["init-vault", "--path", str(self.vault)])

        self.existing_candidate = {
            "candidate_id": "existing-source::0",
            "project_or_topic": "Release Automation",
            "confirmed_answers": {
                "context": "Legacy release process was manual.",
                "contribution": "Built a CI/CD pipeline.",
                "outcome": "Reduced release time by 40%.",
                "evidence": "Release dashboard report.",
            },
        }
        self.existing_id = "ach_001"
        self.existing_path = self.vault / "Brag" / "Achievements" / "release-automation--ach_001.md"
        self.existing_path.write_text(
            brag_cli.render_achievement_markdown(
                achievement_id=self.existing_id,
                candidate=self.existing_candidate,
                wording="Built pipeline and reduced release time by 40%.",
                language="zh-TW",
                model="gpt-4o-mini",
            ),
            encoding="utf-8",
        )

        self.incoming_id = "inbox/2026-08-15.md::1"
        self.incoming_candidate = {
            "candidate_id": self.incoming_id,
            "status": "ready-for-confirmation",
            "project_or_topic": "Release Automation",
            "confirmed_answers": {
                "context": "Legacy release process was manual.",
                "contribution": "Built a CI/CD pipeline.",
                "outcome": "Reduced release time by 40%.",
                "evidence": "Release dashboard report.",
            },
            "pending_questions": [],
            "last_suggested_inferences": {},
        }
        brag_cli.save_review_state({"candidates": {self.incoming_id: self.incoming_candidate}})

    def _run_cli(self, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = brag_cli.main(args)
        return code, output.getvalue()

    def _set_incoming_fact(self, key: str, value: str) -> None:
        state = brag_cli.load_review_state()
        state["candidates"][self.incoming_id]["confirmed_answers"][key] = value
        brag_cli.save_review_state(state)

    def test_lookup_by_immutable_id_after_rename(self) -> None:
        moved_dir = self.vault / "Brag" / "Achievements" / "Moved"
        moved_dir.mkdir(parents=True)
        moved_path = moved_dir / "renamed.md"
        self.existing_path.replace(moved_path)

        with patch("builtins.input", side_effect=["YES", "YES"]):
            code, _ = self._run_cli(
                [
                    "attach-candidate",
                    "--candidate-id",
                    self.incoming_id,
                    "--action",
                    "merge",
                    "--achievement-id",
                    self.existing_id,
                ]
            )

        self.assertEqual(code, 0)
        content = moved_path.read_text(encoding="utf-8")
        self.assertIn(self.incoming_id, content)

    def test_merge_conflict_shows_both_sources_and_requires_confirmation(self) -> None:
        self._set_incoming_fact("outcome", "Reduced release time by 70%.")

        with patch("builtins.input", side_effect=["YES", "NO", "YES"]):
            code, output = self._run_cli(
                [
                    "attach-candidate",
                    "--candidate-id",
                    self.incoming_id,
                    "--action",
                    "merge",
                    "--achievement-id",
                    self.existing_id,
                ]
            )

        self.assertEqual(code, 0)
        self.assertIn("Existing source references:", output)
        self.assertIn("Incoming source:", output)
        self.assertIn("Conflict on outcome:", output)
        content = self.existing_path.read_text(encoding="utf-8")
        self.assertIn("Reduced release time by 40%.", content)
        self.assertNotIn("Reduced release time by 70%.", content)

    def test_separate_keeps_existing_unchanged(self) -> None:
        before = self.existing_path.read_text(encoding="utf-8")

        code, output = self._run_cli(
            [
                "attach-candidate",
                "--candidate-id",
                self.incoming_id,
                "--action",
                "separate",
                "--new-achievement-id",
                "ach_002",
            ]
        )

        self.assertEqual(code, 0)
        self.assertIn("Created separate achievement at:", output)
        self.assertEqual(self.existing_path.read_text(encoding="utf-8"), before)
        separate = self.vault / "Brag" / "Achievements" / "release-automation--ach_002.md"
        self.assertTrue(separate.exists())

    def test_ignore_preserves_existing_and_marks_candidate(self) -> None:
        before = self.existing_path.read_text(encoding="utf-8")

        code, output = self._run_cli(
            ["attach-candidate", "--candidate-id", self.incoming_id, "--action", "ignore"]
        )

        self.assertEqual(code, 0)
        self.assertIn("Candidate ignored", output)
        self.assertEqual(self.existing_path.read_text(encoding="utf-8"), before)
        state = brag_cli.load_review_state()
        self.assertEqual(state["candidates"][self.incoming_id]["status"], "ignored")

    def test_manual_edit_remains_authoritative_when_not_replaced(self) -> None:
        edited = self.existing_path.read_text(encoding="utf-8").replace(
            "Built a CI/CD pipeline.", "Manually edited contribution text."
        )
        self.existing_path.write_text(edited, encoding="utf-8")
        self._set_incoming_fact("contribution", "Built a CI/CD pipeline.")

        with patch("builtins.input", side_effect=["YES", "NO", "YES"]):
            code, _ = self._run_cli(
                [
                    "attach-candidate",
                    "--candidate-id",
                    self.incoming_id,
                    "--action",
                    "merge",
                    "--achievement-id",
                    self.existing_id,
                ]
            )

        self.assertEqual(code, 0)
        content = self.existing_path.read_text(encoding="utf-8")
        self.assertIn("Manually edited contribution text.", content)

    def test_regenerate_changes_only_generated_section(self) -> None:
        before = brag_cli.parse_authoritative_achievement_file(self.existing_path)

        with patch("builtins.input", side_effect=["YES", "NO"]):
            code, _ = self._run_cli(
                [
                    "attach-candidate",
                    "--candidate-id",
                    self.incoming_id,
                    "--action",
                    "merge",
                    "--achievement-id",
                    self.existing_id,
                    "--regenerate-generated",
                    "--wording",
                    "NEW GENERATED WORDING",
                ]
            )

        self.assertEqual(code, 0)
        after = brag_cli.parse_authoritative_achievement_file(self.existing_path)
        self.assertEqual(before["confirmed_block"], after["confirmed_block"])
        self.assertNotEqual(before["generated_wording"], after["generated_wording"])
        self.assertEqual(after["generated_wording"], "NEW GENERATED WORDING")

    def test_malformed_files_are_reported_and_skipped(self) -> None:
        bad = self.vault / "Brag" / "Achievements" / "bad.md"
        bad.write_text("this is malformed", encoding="utf-8")

        with patch("builtins.input", side_effect=["YES", "YES"]):
            code, output = self._run_cli(
                [
                    "attach-candidate",
                    "--candidate-id",
                    self.incoming_id,
                    "--action",
                    "merge",
                    "--achievement-id",
                    self.existing_id,
                ]
            )

        self.assertEqual(code, 0)
        self.assertIn("Skipped malformed achievement file:", output)


if __name__ == "__main__":
    unittest.main()
