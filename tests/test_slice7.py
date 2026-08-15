import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from src import brag_cli


class Slice7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))

        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir(parents=True)
        self._run_cli(["init-vault", "--path", str(self.vault)])

        c1 = {
            "candidate_id": "src-1",
            "project_or_topic": "Release Automation",
            "confirmed_answers": {
                "context": "Manual release process.",
                "contribution": "Built CI/CD pipeline.",
                "outcome": "Reduced release time by 40%.",
                "evidence": "Weekly release report.",
            },
        }
        c2 = {
            "candidate_id": "src-2",
            "project_or_topic": "Service Reliability",
            "confirmed_answers": {
                "context": "Frequent incidents.",
                "contribution": "Introduced runbooks and alert tuning.",
                "outcome": "Improved stability",
                "evidence": "Incident log review.",
            },
        }

        self.a1 = self.vault / "Brag" / "Achievements" / "release-automation--ach_100.md"
        self.a2 = self.vault / "Brag" / "Achievements" / "service-reliability--ach_200.md"
        self.a1.write_text(
            brag_cli.render_achievement_markdown(
                achievement_id="ach_100",
                candidate=c1,
                wording="Built pipeline and reduced release time by 40%.",
                language="zh-TW",
                model="gpt-4o-mini",
            ),
            encoding="utf-8",
        )
        self.a2.write_text(
            brag_cli.render_achievement_markdown(
                achievement_id="ach_200",
                candidate=c2,
                wording="Improved stability via runbooks.",
                language="zh-TW",
                model="gpt-4o-mini",
            ),
            encoding="utf-8",
        )

    def _run_cli(self, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = brag_cli.main(args)
        return code, output.getvalue()

    def test_generate_all_three_output_forms(self) -> None:
        code, output = self._run_cli(["generate-outputs", "--achievement-id", "ach_100"])

        self.assertEqual(code, 0)
        self.assertIn("resume_themes", output)
        self.assertIn("Updated generated wording for:", output)
        content = self.a1.read_text(encoding="utf-8")
        self.assertIn("### STAR", content)
        self.assertIn("### Resume Bullet", content)
        self.assertIn("### Performance Summary", content)

    def test_generate_chinese_and_english_variants(self) -> None:
        code_zh, _ = self._run_cli([
            "generate-outputs",
            "--achievement-id",
            "ach_100",
            "--language",
            "zh-TW",
            "--output-types",
            "resume-bullet",
        ])
        self.assertEqual(code_zh, 0)
        zh_content = self.a1.read_text(encoding="utf-8")
        self.assertIn("Generated-Language: zh-TW", zh_content)

        code_en, _ = self._run_cli([
            "generate-outputs",
            "--achievement-id",
            "ach_100",
            "--language",
            "en",
            "--output-types",
            "resume-bullet",
        ])
        self.assertEqual(code_en, 0)
        en_content = self.a1.read_text(encoding="utf-8")
        self.assertIn("Generated-Language: en", en_content)
        self.assertIn("resulting in", en_content)

    def test_missing_metric_uses_placeholder_only(self) -> None:
        code, _ = self._run_cli([
            "generate-outputs",
            "--achievement-id",
            "ach_200",
            "--output-types",
            "resume-bullet,performance-summary",
        ])

        self.assertEqual(code, 0)
        content = self.a2.read_text(encoding="utf-8")
        self.assertIn("[X%]", content)

    def test_reject_unconfirmed_achievement(self) -> None:
        text = self.a2.read_text(encoding="utf-8").replace("state: confirmed", "state: needs-detail")
        self.a2.write_text(text, encoding="utf-8")

        code, output = self._run_cli(["generate-outputs", "--achievement-id", "ach_200"])

        self.assertEqual(code, 2)
        self.assertIn("not confirmed", output)

    def test_generate_aggregate_output_for_multiple_achievements(self) -> None:
        code, output = self._run_cli([
            "generate-outputs",
            "--achievement-id",
            "ach_100",
            "--achievement-id",
            "ach_200",
            "--aggregate-name",
            "quarterly-pack",
            "--output-types",
            "star",
        ])

        self.assertEqual(code, 0)
        self.assertIn("Aggregate output created at:", output)
        aggregate = self.vault / "Brag" / "Outputs" / "quarterly-pack.md"
        text = aggregate.read_text(encoding="utf-8")
        self.assertIn("- ach_100", text)
        self.assertIn("- ach_200", text)
        self.assertIn("### STAR", text)

    def test_regeneration_does_not_change_confirmed_facts(self) -> None:
        before = brag_cli.parse_authoritative_achievement_file(self.a1)["confirmed_block"]

        code, _ = self._run_cli([
            "generate-outputs",
            "--achievement-id",
            "ach_100",
            "--output-types",
            "performance-summary",
        ])

        self.assertEqual(code, 0)
        after = brag_cli.parse_authoritative_achievement_file(self.a1)["confirmed_block"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
