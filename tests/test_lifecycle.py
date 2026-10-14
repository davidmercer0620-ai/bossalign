"""Tests for preference lifecycle states, transitions, and expiration."""

import tempfile
import unittest
from pathlib import Path

from bossalign import BossAlign, MemoryStore, TaskContext
from bossalign.lifecycle import PreferenceLifecycle
from bossalign.schema import BoundaryRule, RuleStatus


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "lifecycle.sqlite3"

    def tearDown(self):
        MemoryStore.close_all()

    def test_full_lifecycle_transitions(self):
        with BossAlign(self.db) as client:
            # 1. Propose (draft)
            rule = client.ingest(
                "Avoid technical acronyms in user guides.",
                reviewer="actor_A",
                context={"applicable_scope": {"project": "proj_1"}},
            )
            self.assertEqual(rule.status, RuleStatus.DRAFT)

            # 2. Confirm
            confirmed = client.confirm_rule(rule.rule_id)
            self.assertEqual(confirmed.status, RuleStatus.CONFIRMED)
            self.assertEqual(confirmed.version, 2)

            # 3. Retrieve matches confirmed rule
            selection = client.retrieve(TaskContext(project="proj_1"))
            self.assertEqual(len(selection.active_rules), 1)

            # 4. Revoke
            revoked = client.revoke_rule(rule.rule_id, revoked_by="actor_A", reason="Policy update")
            self.assertEqual(revoked.status, RuleStatus.REVOKED)
            self.assertEqual(revoked.revocation_reason, "Policy update")

            # 5. Revoked rule is excluded from active retrieval
            selection_after_revoke = client.retrieve(TaskContext(project="proj_1"))
            self.assertEqual(selection_after_revoke.active_rules, [])
            self.assertTrue(any("inactive" in r.reason.lower() for r in selection_after_revoke.excluded_rules))

    def test_rejection_marks_rule_as_rejected_and_prevents_confirmation(self):
        with BossAlign(self.db) as client:
            proposal = client.ingest(
                "Always write code without comments.",
                reviewer="actor_A",
                context={"applicable_scope": {"project": "proj_1"}},
            )
            rejected = client.reject_rule(proposal.rule_id, rejected_by="reviewer_lead", reason="Bad practice")
            self.assertEqual(rejected.status, RuleStatus.REJECTED)
            self.assertEqual(rejected.rejection_reason, "Bad practice")

            # Cannot confirm a rejected rule directly
            with self.assertRaises(ValueError):
                client.confirm_rule(proposal.rule_id)

    def test_supersede_rule_links_and_deactivates_older_rule(self):
        with BossAlign(self.db) as client:
            old_rule = client.ingest(
                "Use 2 spaces for indentation.",
                reviewer="actor_A",
                context={"applicable_scope": {"project": "proj_1"}},
                confirm=True,
            )
            new_rule = client.ingest(
                "Use 4 spaces for indentation.",
                reviewer="actor_A",
                context={"applicable_scope": {"project": "proj_1"}},
                confirm=True,
            )

            superseded = client.supersede_rule(
                old_rule.rule_id, new_rule.rule_id, actor="reviewer_lead", reason="Adopt PEP 8"
            )
            self.assertEqual(superseded.status, RuleStatus.SUPERSEDED)
            self.assertEqual(superseded.superseded_by, new_rule.rule_id)

            # Only new rule is active
            selection = client.retrieve(TaskContext(project="proj_1"))
            active_ids = [r.rule_id for r in selection.active_rules]
            self.assertIn(new_rule.rule_id, active_ids)
            self.assertNotIn(old_rule.rule_id, active_ids)

    def test_expiration_based_on_valid_until_timestamp(self):
        with BossAlign(self.db) as client:
            rule = client.ingest(
                "Never use unapproved claims in project copy.",
                reviewer="actor_A",
                valid_until="2026-01-31T23:59:59Z",
                context={"applicable_scope": {"project": "proj_1"}},
                confirm=True,
            )

            # As of Jan 15, 2026: rule is active
            selection_valid = client.retrieve(TaskContext(project="proj_1", as_of="2026-01-15T12:00:00Z"))
            self.assertEqual(len(selection_valid.active_rules), 1)

            # As of Feb 01, 2026: rule is expired
            selection_expired = client.retrieve(TaskContext(project="proj_1", as_of="2026-02-01T12:00:00Z"))
            self.assertEqual(len(selection_expired.active_rules), 0)
            self.assertTrue(any("expired" in r.reason.lower() for r in selection_expired.excluded_rules))
