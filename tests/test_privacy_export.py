"""Tests for PrivacyExporter, field whitelisting, and strict opt-in export policies."""

import tempfile
import unittest
from pathlib import Path

from bossalign import ExportPolicy, MemoryStore, PrivacyExporter
from bossalign.schema import BoundaryRule, RuleStatus


class TestPrivacyExport(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "privacy.sqlite3"

    def tearDown(self):
        MemoryStore.close_all()

    def test_export_is_disabled_by_default(self):
        rule = BoundaryRule(
            rule_id="r_001",
            source_event_ids=["evt_001"],
            reviewer="actor_secret",
            directive="Use sanitized terminology.",
            original_feedback="Raw confidential statement from client meeting.",
            status=RuleStatus.CONFIRMED,
        )

        # Default policy: allow_export is False
        default_policy = ExportPolicy()
        with self.assertRaises(PermissionError):
            PrivacyExporter.export([rule], default_policy)

    def test_whitelist_projection_strips_raw_feedback_and_identities(self):
        rule = BoundaryRule(
            rule_id="r_001",
            source_event_ids=["evt_001"],
            reviewer="sensitive_reviewer_id",
            preference_owner="sensitive_owner_id",
            directive="Keep outputs under 500 words.",
            original_feedback="Personal note: I was unhappy with the verbose draft yesterday.",
            applicable_scope={"project": "proj_1"},
            status=RuleStatus.CONFIRMED,
        )

        authorized_policy = ExportPolicy(allow_export=True, redact_actor_identity=True)
        bundle = PrivacyExporter.export([rule], authorized_policy)

        self.assertEqual(bundle["count"], 1)
        exported_rule = bundle["rules"][0]

        # Allowed fields
        self.assertEqual(exported_rule["rule_id"], "r_001")
        self.assertEqual(exported_rule["directive"], "Keep outputs under 500 words.")
        self.assertEqual(exported_rule["applicable_scope"], {"project": "proj_1"})

        # Redacted private/raw fields
        self.assertNotIn("original_feedback", exported_rule)
        self.assertNotIn("raw_content", exported_rule)
        self.assertNotIn("reviewer", exported_rule)
        self.assertNotIn("preference_owner", exported_rule)
        self.assertNotIn("source_event_ids", exported_rule)

    def test_preview_manifest_generates_redaction_inventory(self):
        rule = BoundaryRule(
            rule_id="r_002",
            source_event_ids=["evt_002"],
            reviewer="actor_A",
            directive="Avoid jargon.",
            status=RuleStatus.CONFIRMED,
        )
        manifest = PrivacyExporter.preview([rule])
        self.assertEqual(manifest.rule_count, 1)
        self.assertIn("directive", manifest.whitelisted_fields)
        self.assertIn("original_feedback", manifest.redacted_fields)
        self.assertIn("reviewer", manifest.redacted_fields)
        self.assertEqual(len(manifest.preview_items), 1)
        self.assertNotIn("reviewer", manifest.preview_items[0])
