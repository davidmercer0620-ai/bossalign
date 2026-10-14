"""Tests for domain-agnostic ConflictResolver and resolution strategies."""

import tempfile
import unittest
from pathlib import Path

from bossalign import MemoryStore, TaskContext
from bossalign.resolver import ConflictResolver
from bossalign.schema import BoundaryRule, ConflictType, RuleStatus


def make_rule(**overrides):
    values = {
        "rule_id": "rule_default",
        "source_event_ids": ["evt_1"],
        "reviewer": "actor_A",
        "directive": "Sample directive.",
        "applicable_scope": {"project": "proj_1"},
        "negative_boundaries": [],
        "confidence": 0.9,
        "status": RuleStatus.CONFIRMED,
        "conflict_key": "param_disclosure",
        "effect": "avoid",
    }
    values.update(overrides)
    return BoundaryRule(**values)


class TestConflictResolver(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "conflicts.sqlite3"

    def tearDown(self):
        MemoryStore.close_all()

    def test_current_explicit_instruction_strictly_overrides_stored_rule(self):
        rule = make_rule(rule_id="rule_hist", effect="include")
        resolver = ConflictResolver()
        task = TaskContext(
            project="proj_1",
            current_overrides=[{"conflict_key": "param_disclosure", "effect": "avoid"}],
        )

        conflicts = resolver.detect_conflicts([rule], task)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].kind, "current_instruction")
        self.assertEqual(conflicts[0].resolution_options[0].strategy, "current_explicit_override")
        self.assertTrue(conflicts[0].resolution_options[0].recommended)

    def test_temporal_contradiction_recommends_newer_confirmed_preference(self):
        older = make_rule(
            rule_id="r_old",
            preference_owner="subject_1",
            effect="include",
            created_at="2026-01-01T08:00:00Z",
            updated_at="2026-01-01T08:00:00Z",
        )
        newer = make_rule(
            rule_id="r_new",
            preference_owner="subject_1",
            effect="avoid",
            created_at="2026-01-02T08:00:00Z",
            updated_at="2026-01-02T08:00:00Z",
        )
        resolver = ConflictResolver()
        task = TaskContext(project="proj_1", preference_owner="subject_1")

        conflicts = resolver.detect_conflicts([older, newer], task)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].kind, ConflictType.TEMPORAL.value)
        recommended = [opt for opt in conflicts[0].resolution_options if opt.recommended]
        self.assertTrue(recommended)
        self.assertEqual(recommended[0].applied_rule_id, "r_new")

    def test_scope_hierarchy_recommends_specific_local_scope_over_broad_policy(self):
        broad = make_rule(rule_id="r_broad", applicable_scope={}, effect="avoid")
        specific = make_rule(rule_id="r_spec", applicable_scope={"project": "proj_1"}, effect="include")
        resolver = ConflictResolver()
        task = TaskContext(project="proj_1")

        conflicts = resolver.detect_conflicts([broad, specific], task)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].kind, ConflictType.SCOPE_HIERARCHY.value)
        recommended = [opt for opt in conflicts[0].resolution_options if opt.recommended]
        self.assertTrue(recommended)
        self.assertEqual(recommended[0].applied_rule_id, "r_spec")

    def test_confirmed_rule_overrules_unconfirmed_inference(self):
        confirmed = make_rule(rule_id="r_conf", status=RuleStatus.CONFIRMED, effect="avoid")
        inferred = make_rule(rule_id="r_inf", status=RuleStatus.DRAFT, effect="include", origin="ai_inference")
        resolver = ConflictResolver()
        task = TaskContext(project="proj_1")

        conflicts = resolver.detect_conflicts([confirmed, inferred], task)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].kind, ConflictType.EVIDENCE_DISPARITY.value)
        self.assertEqual(conflicts[0].resolution_options[0].applied_rule_id, "r_conf")

    def test_multi_actor_conflict_requires_explicit_authority_hierarchy(self):
        rule_a = make_rule(rule_id="r_a", reviewer="actor_A", effect="avoid")
        rule_b = make_rule(rule_id="r_b", reviewer="actor_B", effect="include")

        # Without hierarchy: flags manual clarification
        resolver_no_hierarchy = ConflictResolver()
        task = TaskContext(project="proj_1")
        conflicts = resolver_no_hierarchy.detect_conflicts([rule_a, rule_b], task)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].kind, ConflictType.MULTI_ACTOR.value)
        self.assertEqual(conflicts[0].resolution_options[0].strategy, "manual_clarification")

        # With explicit hierarchy: actor_B over actor_A
        resolver_with_hierarchy = ConflictResolver(authority_hierarchy=["actor_B", "actor_A"])
        conflicts_prio = resolver_with_hierarchy.detect_conflicts([rule_a, rule_b], task)
        self.assertEqual(len(conflicts_prio), 1)
        recommended = [opt for opt in conflicts_prio[0].resolution_options if opt.recommended]
        self.assertTrue(recommended)
        self.assertEqual(recommended[0].applied_rule_id, "r_b")
