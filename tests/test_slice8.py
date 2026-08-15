import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import brag_cli


class Slice8Tests(unittest.TestCase):
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

        self.repo = Path(self.temp_dir.name) / "repo-a"
        self.repo.mkdir(parents=True)
        self.changelog = self.repo / "CHANGELOG.md"
        self.changelog.write_text(
            "# Changelog\n\n"
            "## 0.3.0\n"
            "- old\n\n"
            "## 0.2.0\n"
            "- middle\n\n"
            "## 0.1.0\n"
            "- first\n",
            encoding="utf-8",
        )

    def run_cli(self, args: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = brag_cli.main(args)
        return code, buf.getvalue()

    def today_inbox(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.vault / "Brag" / "Inbox" / f"{day}.md"

    def test_repo_register_list_remove(self) -> None:
        code1, _ = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(self.repo),
                "--changelog-path",
                str(self.changelog),
            ]
        )
        self.assertEqual(code1, 0)

        code2, out2 = self.run_cli(["repo-list"])
        self.assertEqual(code2, 0)
        rows = json.loads(out2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(Path(rows[0]["repo_path"]).resolve(), self.repo.resolve())
        self.assertEqual(Path(rows[0]["changelog_path"]).resolve(), self.changelog.resolve())

        code3, _ = self.run_cli(["repo-remove", "--repo-path", str(self.repo)])
        self.assertEqual(code3, 0)
        code4, out4 = self.run_cli(["repo-list"])
        self.assertEqual(code4, 0)
        self.assertEqual(json.loads(out4), [])

    def test_invalid_registration_keeps_config_unchanged(self) -> None:
        before = brag_cli.config_file_path().read_text(encoding="utf-8")
        missing = self.repo / "MISSING.md"

        code, output = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(self.repo),
                "--changelog-path",
                str(missing),
            ]
        )

        self.assertEqual(code, 2)
        self.assertIn("Changelog path does not exist", output)
        after = brag_cli.config_file_path().read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_changelog_import_selected_range_only(self) -> None:
        code1, _ = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(self.repo),
                "--changelog-path",
                str(self.changelog),
            ]
        )
        self.assertEqual(code1, 0)

        with patch("builtins.input", side_effect=["IMPORT"]):
            code2, output2 = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "0.2.0",
                    "--to-heading",
                    "0.1.0",
                ]
            )

        self.assertEqual(code2, 0)
        self.assertIn("BEGIN IMPORTED CONTENT", output2)
        content = self.today_inbox().read_text(encoding="utf-8")
        self.assertIn("## 0.2.0", content)
        self.assertIn("- middle", content)
        self.assertNotIn("## 0.3.0", content)
        self.assertNotIn("- old", content)
        self.assertNotIn("## 0.1.0", content)

    def test_import_supports_different_markdown_heading_shapes(self) -> None:
        repo_b = Path(self.temp_dir.name) / "repo-b"
        repo_b.mkdir(parents=True)
        changelog_b = repo_b / "HISTORY.md"
        changelog_b.write_text(
            "# History\n\n"
            "### Sprint 12\n"
            "- delivered search\n\n"
            "### Sprint 11\n"
            "- fixed cache\n",
            encoding="utf-8",
        )
        code1, _ = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(repo_b),
                "--changelog-path",
                str(changelog_b),
            ]
        )
        self.assertEqual(code1, 0)

        with patch("builtins.input", side_effect=["IMPORT"]):
            code2, _ = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(repo_b),
                    "--from-heading",
                    "Sprint 11",
                ]
            )
        self.assertEqual(code2, 0)
        content = self.today_inbox().read_text(encoding="utf-8")
        self.assertIn("### Sprint 11", content)
        self.assertIn("- fixed cache", content)

    def test_import_succeeds_without_network_or_api_key(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)
        code1, _ = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(self.repo),
                "--changelog-path",
                str(self.changelog),
            ]
        )
        self.assertEqual(code1, 0)

        with patch("builtins.input", side_effect=["IMPORT"]):
            code2, _ = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "0.1.0",
                ]
            )
        self.assertEqual(code2, 0)
        self.assertIn("## 0.1.0", self.today_inbox().read_text(encoding="utf-8"))

    def test_analyze_uses_selected_text_and_safety_gate(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"
        code1, _ = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(self.repo),
                "--changelog-path",
                str(self.changelog),
            ]
        )
        self.assertEqual(code1, 0)

        analysis = {
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
                            "reason": "useful",
                        }
                    ],
                }
            ]
        }

        with patch("builtins.input", side_effect=["IMPORT", "YES"]), patch(
            "src.brag_cli.request_openai_analysis", return_value=analysis
        ) as mocked:
            code2, out2 = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "0.2.0",
                    "--to-heading",
                    "0.1.0",
                    "--analyze",
                ]
            )

        self.assertEqual(code2, 0)
        self.assertIn("Outbound content preview (exact payload):", out2)
        sent = mocked.call_args.kwargs["outbound_content"]
        self.assertIn("## 0.2.0", sent)
        self.assertNotIn("## 0.3.0", sent)


if __name__ == "__main__":
    unittest.main()
