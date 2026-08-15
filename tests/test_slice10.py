import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from src import brag_cli


class Slice10Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.config_dir = Path(self.temp_dir.name) / "config"
        os.environ["BRAG_CONFIG_DIR"] = str(self.config_dir)
        self.addCleanup(lambda: os.environ.pop("BRAG_CONFIG_DIR", None))

        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir(parents=True)
        code, _ = self.run_cli(["init-vault", "--path", str(self.vault)])
        self.assertEqual(code, 0)

        self.fixtures = Path(__file__).resolve().parent / "fixtures" / "mvp_eval_cases.json"

    def run_cli(self, args: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = brag_cli.main(args)
        return code, buf.getvalue()

    def inbox_path(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.vault / "Brag" / "Inbox" / f"{day}.md"

    def test_eval_from_clean_state_generates_report(self) -> None:
        code, out = self.run_cli(
            [
                "mvp-eval",
                "--fixtures-file",
                str(self.fixtures),
                "--deterministic",
                "--report-name",
                "mvp-report-a",
            ]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        report_path = Path(payload["report_path"])
        self.assertTrue(report_path.exists())
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("Total examples: 10", report)
        self.assertIn("Traceability", report)

    def test_deterministic_metrics_repeat_consistently(self) -> None:
        c1, out1 = self.run_cli(
            [
                "mvp-eval",
                "--fixtures-file",
                str(self.fixtures),
                "--deterministic",
                "--report-name",
                "mvp-report-b1",
            ]
        )
        c2, out2 = self.run_cli(
            [
                "mvp-eval",
                "--fixtures-file",
                str(self.fixtures),
                "--deterministic",
                "--report-name",
                "mvp-report-b2",
            ]
        )
        self.assertEqual(c1, 0)
        self.assertEqual(c2, 0)
        p1 = json.loads(out1)
        p2 = json.loads(out2)
        t1 = Path(p1["report_path"]).read_text(encoding="utf-8")
        t2 = Path(p2["report_path"]).read_text(encoding="utf-8")

        def summary_slice(text: str) -> str:
            start = text.find("## Summary Metrics")
            end = text.find("## Traceability")
            return text[start:end]

        self.assertEqual(summary_slice(t1), summary_slice(t2))

    def test_simulated_openai_failure_keeps_all_raw_inputs(self) -> None:
        code, _ = self.run_cli(
            [
                "mvp-eval",
                "--fixtures-file",
                str(self.fixtures),
                "--deterministic",
                "--simulate-openai-failure",
                "--report-name",
                "mvp-report-c",
            ]
        )
        self.assertEqual(code, 0)

        inbox = self.inbox_path().read_text(encoding="utf-8")
        self.assertEqual(inbox.count("## Capture"), 10)

    def test_report_traces_and_no_api_key_leak(self) -> None:
        os.environ["OPENAI_API_KEY"] = "SECRET-KEY-SHOULD-NOT-LEAK"
        self.addCleanup(lambda: os.environ.pop("OPENAI_API_KEY", None))

        code, out = self.run_cli(
            [
                "mvp-eval",
                "--fixtures-file",
                str(self.fixtures),
                "--deterministic",
                "--simulate-openai-failure",
                "--report-name",
                "mvp-report-d",
            ]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        report = Path(payload["report_path"]).read_text(encoding="utf-8")
        self.assertIn("case=case-07-capture-during-failure", report)
        self.assertIn("status=openai-failure-simulated", report)
        self.assertNotIn("SECRET-KEY-SHOULD-NOT-LEAK", report)


if __name__ == "__main__":
    unittest.main()
