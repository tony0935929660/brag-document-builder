import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import brag_cli


class Slice1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))

    def run_cli(self, args: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = brag_cli.main(args)
        return code, buf.getvalue()

    def test_init_vault_creates_required_tree(self) -> None:
        vault = Path(self.temp_dir.name) / "vault"
        vault.mkdir(parents=True)

        code, _ = self.run_cli(["init-vault", "--path", str(vault)])

        self.assertEqual(code, 0)
        self.assertTrue((vault / "Brag/Inbox").is_dir())
        self.assertTrue((vault / "Brag/Achievements").is_dir())
        self.assertTrue((vault / "Brag/Archive/Rejected").is_dir())
        self.assertTrue((vault / "Brag/Outputs").is_dir())

    def test_init_vault_is_idempotent(self) -> None:
        vault = Path(self.temp_dir.name) / "vault"
        vault.mkdir(parents=True)
        existing = vault / "Brag" / "existing.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("keep-me", encoding="utf-8")

        code1, _ = self.run_cli(["init-vault", "--path", str(vault)])
        code2, _ = self.run_cli(["init-vault", "--path", str(vault)])

        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep-me")

    def test_init_vault_rejects_invalid_path(self) -> None:
        missing = Path(self.temp_dir.name) / "missing"
        code, output = self.run_cli(["init-vault", "--path", str(missing)])
        self.assertEqual(code, 2)
        self.assertIn("Vault path does not exist", output)
        self.assertFalse(brag_cli.config_file_path().exists())

        some_file = Path(self.temp_dir.name) / "file.txt"
        some_file.write_text("x", encoding="utf-8")
        code2, output2 = self.run_cli(["init-vault", "--path", str(some_file)])
        self.assertEqual(code2, 2)
        self.assertIn("Vault path is not a directory", output2)
        self.assertFalse(brag_cli.config_file_path().exists())

    def test_init_vault_handles_inaccessible_location(self) -> None:
        vault = Path(self.temp_dir.name) / "vault"
        vault.mkdir(parents=True)

        with patch("src.brag_cli.initialize_vault", side_effect=PermissionError("denied")):
            code, output = self.run_cli(["init-vault", "--path", str(vault)])

        self.assertEqual(code, 3)
        self.assertIn("filesystem operation failed", output)
        self.assertFalse(brag_cli.config_file_path().exists())

    def test_config_contains_no_achievement_content(self) -> None:
        vault = Path(self.temp_dir.name) / "vault"
        vault.mkdir(parents=True)

        code, _ = self.run_cli(["init-vault", "--path", str(vault)])
        self.assertEqual(code, 0)

        config = json.loads(brag_cli.config_file_path().read_text(encoding="utf-8"))
        self.assertEqual(
            set(config.keys()),
            {"default_vault_path", "repositories", "updated_at_utc"},
        )
        self.assertEqual(config["default_vault_path"], str(vault.resolve()))
        self.assertEqual(config["repositories"], [])

    def test_show_config_reports_default_vault(self) -> None:
        vault = Path(self.temp_dir.name) / "vault"
        vault.mkdir(parents=True)

        code1, _ = self.run_cli(["init-vault", "--path", str(vault)])
        code2, output = self.run_cli(["show-config"])

        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        shown = json.loads(output)
        self.assertEqual(shown["default_vault_path"], str(vault.resolve()))


if __name__ == "__main__":
    unittest.main()