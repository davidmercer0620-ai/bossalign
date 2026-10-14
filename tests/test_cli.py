import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from bossalign.cli import main
from bossalign import BossAlign, MemoryStore


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.tmp_path = Path(self.tempdir.name)

    def tearDown(self):
        MemoryStore.close_all()

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
        self.assertIn('"status": "draft"', updated)
        self.assertIn('"version": 3', updated)

        status, reconfirmed = self.run_cli(
            ["--db", str(database), "rules", "confirm", "--rule-id", rule_id]
        )
        self.assertEqual(status, 0)
        self.assertIn('"status": "confirmed"', reconfirmed)

        status, inactive = self.run_cli(
            ["--db", str(database), "rules", "deactivate", "--rule-id", rule_id]
        )
        self.assertEqual(status, 0)
        self.assertIn('"status": "inactive"', inactive)

        status, all_rules = self.run_cli(["--db", str(database), "rules", "--all"])
        self.assertEqual(status, 0)
        self.assertIn('"inactive"', all_rules)

        status, deleted = self.run_cli(
            ["--db", str(database), "rules", "delete", "--rule-id", rule_id]
        )
        self.assertEqual(status, 0)
        self.assertIn('"deleted": true', deleted)

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

    def test_cli_sensitive_ingest_requires_consent_and_stores_minimized_rule(self):
        database = self.tmp_path / "sensitive.sqlite3"
        raw = "Fictional sensitive personal details omitted from durable storage."
        context = {
            "directive": "Use a brief, neutral response.",
            "applicable_scope": {"interaction_context": "personal_relationship"},
        }
        status, _ = self.run_cli([
            "--db", str(database), "ingest", "--raw", raw, "--sensitive",
            "--context-json", json.dumps(context),
        ])
        self.assertEqual(status, 2)

        status, output = self.run_cli([
            "--db", str(database), "ingest", "--raw", raw, "--sensitive",
            "--consent-to-store-sensitive", "--preference-owner", "person-1",
            "--context-json", json.dumps(context),
        ])
        self.assertEqual(status, 0)
        self.assertNotIn(raw, output)
        with BossAlign(database) as client:
            self.assertEqual(client.feedback_events()[0].raw_content, "")
            self.assertEqual(client.rules()[0].original_feedback, "")

    def test_cli_third_party_rule_requires_named_preference_owner_confirmation(self):
        database = self.tmp_path / "attribution.sqlite3"
        context = {
            "origin": "explicit_instruction",
            "confidence": 0.9,
            "directive": "Ask before calling.",
            "applicable_scope": {"interaction_context": "personal_relationship", "task_type": "calling"},
        }
        status, ingested = self.run_cli([
            "--db", str(database), "ingest", "--reviewer", "reporter", "--raw", "A person said ask before calling.",
            "--preference-owner", "person-2", "--attribution", "third_party", "--context-json", json.dumps(context),
        ])
        self.assertEqual(status, 0)
        rule_id = re.search(r'"rule_id":\s*"([^"]+)"', ingested).group(1)

        status, _ = self.run_cli([
            "--db", str(database), "rules", "confirm", "--rule-id", rule_id, "--confirmed-by", "reporter",
        ])
        self.assertEqual(status, 2)
        status, confirmed = self.run_cli([
            "--db", str(database), "rules", "confirm", "--rule-id", rule_id, "--confirmed-by", "person-2",
        ])
        self.assertEqual(status, 0)
        self.assertIn('"status": "confirmed"', confirmed)

    def test_cli_export_and_preview(self):
        database = self.tmp_path / "export_cli.sqlite3"
        with BossAlign(database) as client:
            client.ingest("Never disclose secret tokens.", reviewer="actor_A", confirm=True)

        # Test preview
        status, preview = self.run_cli(["--db", str(database), "export", "--preview"])
        self.assertEqual(status, 0)
        self.assertIn("whitelisted_fields", preview)
        self.assertIn("redacted_fields", preview)

        # Test export to file
        out_file = self.tmp_path / "exported.json"
        status, export_out = self.run_cli(["--db", str(database), "export", "--out", str(out_file)])
        self.assertEqual(status, 0)
        self.assertTrue(out_file.exists())
        self.assertIn("Exported 1 rules", export_out)

    def test_cli_replay_command(self):
        database = self.tmp_path / "replay_cli.sqlite3"
        steps_file = self.tmp_path / "steps.json"
        steps_file.write_text(
            json.dumps([
                {
                    "step_id": "s1",
                    "action": "ingest",
                    "payload": {
                        "feedback": "Never use guaranteed claims.",
                        "reviewer": "actor_A",
                        "confirm": True,
                        "context": {"applicable_scope": {"project": "p1"}},
                    },
                    "expected": {"status": "confirmed"},
                }
            ]),
            encoding="utf-8",
        )
        status, output = self.run_cli(["--db", str(database), "replay", "--file", str(steps_file)])
        self.assertEqual(status, 0)
        self.assertIn("Replay PASSED", output)

