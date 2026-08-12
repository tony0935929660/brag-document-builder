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


class Slice2Tests(unittest.TestCase):
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

    def run_cli(self, args: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = brag_cli.main(args)
        return code, buf.getvalue()

    def today_inbox(self, vault: Path | None = None) -> Path:
        target = vault or self.vault
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return target / "Brag" / "Inbox" / f"{day}.md"

    def test_capture_text_writes_daily_inbox(self) -> None:
        message = "完成 slice2 收件流程"
        code, _ = self.run_cli(["capture-text", "--text", message])
        self.assertEqual(code, 0)

        inbox = self.today_inbox()
        self.assertTrue(inbox.exists())
        content = inbox.read_text(encoding="utf-8")
        self.assertIn(message, content)

    def test_capture_prompted_accepts_partial_answers(self) -> None:
        code, _ = self.run_cli(["capture-prompted", "--action", "修復部署問題"])
        self.assertEqual(code, 0)

        content = self.today_inbox().read_text(encoding="utf-8")
        self.assertIn("- context: ", content)
        self.assertIn("- action: 修復部署問題", content)
        self.assertIn("- impact: ", content)
        self.assertIn("- evidence: ", content)

    def test_multiple_captures_same_day_append_not_overwrite(self) -> None:
        code1, _ = self.run_cli(["capture-text", "--text", "first"])
        code2, _ = self.run_cli(["capture-text", "--text", "second"])
        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)

        content = self.today_inbox().read_text(encoding="utf-8")
        self.assertIn("first", content)
        self.assertIn("second", content)
        self.assertGreaterEqual(content.count("## Capture"), 2)

    def test_capture_works_without_openai_key_or_network(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)
        code, _ = self.run_cli(["capture-text", "--text", "no-key required"])
        self.assertEqual(code, 0)
        self.assertIn("no-key required", self.today_inbox().read_text(encoding="utf-8"))

    def test_capture_reports_resulting_file_path(self) -> None:
        code, output = self.run_cli(["capture-text", "--text", "report-path"])
        self.assertEqual(code, 0)
        self.assertIn("Captured to:", output)
        reported = output.split("Captured to:", 1)[1].strip()
        self.assertEqual(Path(reported).resolve(), self.today_inbox().resolve())

    def test_capture_write_failure_preserves_previous_content(self) -> None:
        code1, _ = self.run_cli(["capture-text", "--text", "stable-before-failure"])
        self.assertEqual(code1, 0)
        before = self.today_inbox().read_text(encoding="utf-8")

        with patch("src.brag_cli.write_text_atomic", side_effect=OSError("disk-failure")):
            code2, output2 = self.run_cli(["capture-text", "--text", "should-not-appear"])

        self.assertEqual(code2, 3)
        self.assertIn("filesystem operation failed", output2)
        after = self.today_inbox().read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertNotIn("should-not-appear", after)

    def test_capture_vault_override_does_not_persist_config(self) -> None:
        alt_vault = Path(self.temp_dir.name) / "alt-vault"
        alt_vault.mkdir(parents=True)
        code_init, _ = self.run_cli(["init-vault", "--path", str(alt_vault)])
        self.assertEqual(code_init, 0)

        # Reset default back to primary vault to verify override does not persist.
        code_reset, _ = self.run_cli(["init-vault", "--path", str(self.vault)])
        self.assertEqual(code_reset, 0)

        code_capture, _ = self.run_cli(
            ["capture-text", "--text", "to-alt", "--vault", str(alt_vault)]
        )
        self.assertEqual(code_capture, 0)
        self.assertIn("to-alt", self.today_inbox(alt_vault).read_text(encoding="utf-8"))

        code_show, output_show = self.run_cli(["show-config"])
        self.assertEqual(code_show, 0)
        shown = json.loads(output_show)
        self.assertEqual(shown["default_vault_path"], str(self.vault.resolve()))


if __name__ == "__main__":
    unittest.main()