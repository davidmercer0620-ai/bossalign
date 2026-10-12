import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from bossalign.cli import main


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.tmp_path = Path(self.tempdir.name)

    def run_cli(self, args):
        output = StringIO()
        with redirect_stdout(output):
            status = main(args)
        return status, output.getvalue()

    def test_cli_ingest_rules_and_check_share_persistent_database(self):
        database = self.tmp_path / "cli.sqlite3"
        context = {
            "project": "alpha",
            "audience": "consumer",
            "applicable_scope": {"project": "alpha", "audience": "consumer"},
            "deterministic_checks": ["guaranteed zero downtime"],
        }

        status, ingested = self.run_cli(
            [
                "--db", str(database), "ingest", "--reviewer", "reviewer-a",
                "--raw", "Avoid 'guaranteed zero downtime'.", "--context-json", json.dumps(context),
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("draft", ingested.lower())
        rule_id = re.search(r'"rule_id":\s*"([^"]+)"', ingested).group(1)

        status, confirmed = self.run_cli(
            ["--db", str(database), "rules", "confirm", "--rule-id", rule_id]
        )
        self.assertEqual(status, 0)
        self.assertIn("confirmed", confirmed.lower())

        status, listed = self.run_cli(["--db", str(database), "rules", "--reviewer", "reviewer-a"])
        self.assertEqual(status, 0)
        self.assertIn("guaranteed zero downtime", listed)

        draft = self.tmp_path / "draft.md"
        draft.write_text("This is guaranteed zero downtime.", encoding="utf-8")
        task = json.dumps({"project": "alpha", "audience": "consumer"})
        status, output = self.run_cli(
            ["--db", str(database), "check", "--file", str(draft), "--task-context", task]
        )
        self.assertEqual(status, 1)
        self.assertIn("violations_found", output)
        self.assertIn("user approval", output.lower())

        status, updated = self.run_cli(
            [
                "--db", str(database), "rules", "update", "--rule-id", rule_id,
                "--directive", "Use evidence instead of absolute claims.",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("Use evidence", updated)
        self.assertIn('"version": 3', updated)

        status, inactive = self.run_cli(
            ["--db", str(database), "rules", "deactivate", "--rule-id", rule_id]
        )
        self.assertEqual(status, 0)
        self.assertIn('"status": "inactive"', inactive)

        status, all_rules = self.run_cli(["--db", str(database), "rules", "--all"])
        self.assertEqual(status, 0)
        self.assertIn('"inactive"', all_rules)

    def test_cli_demo_runs_a_synthetic_real_sdk_flow(self):
        status, output = self.run_cli(["demo"])
        self.assertEqual(status, 0)
        self.assertIn("synthetic", output.lower())
        self.assertIn("user_approved: false", output.lower())
        self.assertIn("violations_found", output)

    def test_cli_sanitize_keeps_existing_clean_room_command(self):
        source = self.tmp_path / "source.md"
        output = self.tmp_path / "clean.md"
        source.write_text("Text [RULE-abc]\n\n<!-- bossalign: internal -->\n", encoding="utf-8")

        status, _ = self.run_cli(["sanitize", "--file", str(source), "--out", str(output)])

        self.assertEqual(status, 0)
        self.assertEqual(output.read_text(encoding="utf-8").strip(), "Text")
