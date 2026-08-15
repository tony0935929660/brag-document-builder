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


class Slice9Tests(unittest.TestCase):
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

        self.repo = Path(self.temp_dir.name) / "repo"
        self.repo.mkdir(parents=True)
        self.changelog = self.repo / "CHANGELOG.md"
        self.changelog.write_text(
            "# Changelog\n\n"
            "## 1.0.0\n"
            "- first import\n\n"
            "## 0.9.0\n"
            "- old\n",
            encoding="utf-8",
        )

        code2, _ = self.run_cli(
            [
                "repo-register",
                "--repo-path",
                str(self.repo),
                "--changelog-path",
                str(self.changelog),
            ]
        )
        self.assertEqual(code2, 0)

        candidate = {
            "candidate_id": "src-9",
            "project_or_topic": "Release",
            "confirmed_answers": {
                "context": "context",
                "contribution": "contrib",
                "outcome": "outcome",
                "evidence": "evidence",
            },
        }
        ach = self.vault / "Brag" / "Achievements" / "release--ach_9.md"
        ach.write_text(
            brag_cli.render_achievement_markdown(
                achievement_id="ach_9",
                candidate=candidate,
                wording="wording",
                language="zh-TW",
                model="gpt-4o-mini",
            ),
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

    def test_reimport_unchanged_skips_duplicate_and_analysis(self) -> None:
        with patch("builtins.input", side_effect=["IMPORT"]):
            c1, _ = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )
        self.assertEqual(c1, 0)
        first_content = self.today_inbox().read_text(encoding="utf-8")

        with patch("src.brag_cli.request_openai_analysis", side_effect=AssertionError("must not call")):
            c2, out2 = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                    "--analyze",
                ]
            )
        self.assertEqual(c2, 0)
        self.assertIn("Unchanged section detected", out2)
        self.assertEqual(first_content, self.today_inbox().read_text(encoding="utf-8"))

    def test_changed_section_shows_diff_and_affected_achievements(self) -> None:
        with patch("builtins.input", side_effect=["IMPORT"]):
            c1, _ = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )
        self.assertEqual(c1, 0)

        changed = self.changelog.read_text(encoding="utf-8").replace("first import", "first import updated")
        self.changelog.write_text(changed, encoding="utf-8")

        with patch("builtins.input", side_effect=["UPDATE", "IMPORT"]):
            c2, out2 = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )
        self.assertEqual(c2, 0)
        self.assertIn("BEGIN SOURCE DIFF", out2)
        self.assertIn("affected_achievement_ids", out2)

    def test_decline_changed_update_keeps_existing_retained_content(self) -> None:
        with patch("builtins.input", side_effect=["IMPORT"]):
            c1, _ = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )
        self.assertEqual(c1, 0)
        before = self.today_inbox().read_text(encoding="utf-8")

        changed = self.changelog.read_text(encoding="utf-8").replace("first import", "changed text")
        self.changelog.write_text(changed, encoding="utf-8")

        with patch("builtins.input", side_effect=["NO"]):
            c2, out2 = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )
        self.assertEqual(c2, 0)
        self.assertIn("update cancelled", out2)
        self.assertEqual(before, self.today_inbox().read_text(encoding="utf-8"))

    def test_rebuild_ledger_keeps_markdown_authoritative(self) -> None:
        with patch("builtins.input", side_effect=["IMPORT"]):
            c1, _ = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )
        self.assertEqual(c1, 0)

        ach_path = self.vault / "Brag" / "Achievements" / "release--ach_9.md"
        before = ach_path.read_text(encoding="utf-8")

        config = json.loads(brag_cli.config_file_path().read_text(encoding="utf-8"))
        config["import_ledger"] = {}
        brag_cli.write_config_atomic(brag_cli.config_file_path(), config)

        c2, out2 = self.run_cli(["import-ledger-rebuild"])
        self.assertEqual(c2, 0)
        self.assertIn("rebuilt_entries", out2)
        self.assertEqual(before, ach_path.read_text(encoding="utf-8"))

    def test_ledger_write_failure_does_not_lose_achievement_content(self) -> None:
        ach_path = self.vault / "Brag" / "Achievements" / "release--ach_9.md"
        before = ach_path.read_text(encoding="utf-8")

        with patch("builtins.input", side_effect=["IMPORT"]), patch(
            "src.brag_cli.save_operational_config", side_effect=OSError("ledger failed")
        ):
            code, out = self.run_cli(
                [
                    "changelog-import",
                    "--repo-path",
                    str(self.repo),
                    "--from-heading",
                    "1.0.0",
                    "--to-heading",
                    "0.9.0",
                ]
            )

        self.assertEqual(code, 3)
        self.assertIn("filesystem operation failed", out)
        self.assertEqual(before, ach_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
