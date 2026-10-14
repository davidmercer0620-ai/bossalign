import tempfile
import unittest
from pathlib import Path

from bossalign import BossAlign, MemoryStore
from bossalign.schema import BoundaryRule, RuleStatus, TaskContext


def make_rule(**overrides):
    values = {
        "rule_id": "rule-1",
        "source_event_ids": ["event-1"],
        "reviewer": "reviewer-a",
        "directive": "Avoid the phrase 'guaranteed zero downtime'.",
        "applicable_scope": {"project": "alpha", "audience": "consumer"},
        "negative_boundaries": [{"task_type": "incident_report"}],
        "confidence": 0.95,
        "status": RuleStatus.CONFIRMED,
        "origin": "explicit_instruction",
        "conflict_key": "downtime_claim",
        "effect": "avoid",
        "deterministic_checks": ["guaranteed zero downtime"],
    }
    values.update(overrides)
    return BoundaryRule(**values)


class TestCore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.tmp_path = Path(self.tempdir.name)

    def tearDown(self):
        MemoryStore.close_all()

    def test_unconfirmed_feedback_is_stored_but_not_applied(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        rule = client.ingest(
        "Avoid the phrase 'guaranteed zero downtime'.",
        reviewer="reviewer-a",
        context={
            "project": "alpha",
            "audience": "consumer",
            "applicable_scope": {"project": "alpha", "audience": "consumer"},
            "deterministic_checks": ["guaranteed zero downtime"],
        },
    )

        self.assertEqual(rule.status, RuleStatus.DRAFT)
        self.assertTrue(client.rules(reviewer="reviewer-a"))
        selection = client.retrieve(TaskContext(project="alpha", audience="consumer"))
        self.assertEqual(selection.active_rules, [])
        self.assertTrue(any("unconfirmed" in item.reason.lower() for item in selection.excluded_rules))

    def test_feedback_events_preserve_source_and_distinguish_instruction_preference_and_hypothesis(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        instruction = client.ingest("Never use the phrase 'guaranteed'.", reviewer="r1", source="user")
        preference = client.ingest("I prefer concise summaries.", reviewer="r1", source="user")
        hypothesis = client.ingest("Maybe the opening could be shorter.", reviewer="r1", source="meeting_transcript")

        events = client.feedback_events(reviewer="r1")

        self.assertEqual(instruction.origin, "explicit_instruction")
        self.assertEqual(preference.origin, "user_preference")
        self.assertEqual(hypothesis.origin, "hypothesis")
        sources = {event.raw_content: event.source for event in events}
        self.assertEqual(sources["Never use the phrase 'guaranteed'."], "user")
        self.assertEqual(sources["Maybe the opening could be shorter."], "meeting_transcript")

    def test_task_limited_rule_does_not_become_a_global_preference(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        rule = client.ingest(
            "For this task only, use a playful tone.",
            reviewer="reviewer-a",
            context={"applicable_scope": {"task_id": "task-17"}},
            confirm=True,
        )

        same_task = client.retrieve(TaskContext(task_id="task-17"))
        other_task = client.retrieve(TaskContext(task_id="task-18"))

        self.assertEqual([item.rule_id for item in same_task.active_rules], [rule.rule_id])
        self.assertEqual(other_task.active_rules, [])
        self.assertTrue(any("task_id" in item.reason for item in other_task.excluded_rules))


    def test_rule_persists_across_client_restart_and_confirmed_rule_retrieves(self):
        path = self.tmp_path / "memory.sqlite3"
        first = BossAlign(path)
        draft = first.ingest(
        "Avoid the phrase 'guaranteed zero downtime'.",
        reviewer="reviewer-a",
        context={
            "applicable_scope": {"project": "alpha", "audience": "consumer"},
            "deterministic_checks": ["guaranteed zero downtime"],
        },
    )
        confirmed = first.confirm_rule(draft.rule_id)

        restarted = BossAlign(path)
        selection = restarted.retrieve(
        TaskContext(project="alpha", audience="consumer"), reviewer="reviewer-a"
    )

        self.assertEqual(confirmed.status, RuleStatus.CONFIRMED)
        self.assertEqual([rule.rule_id for rule in selection.active_rules], [draft.rule_id])


    def test_negative_boundary_and_project_scope_prevent_overgeneralization(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.store_rule(make_rule())

        in_scope = client.retrieve(TaskContext(project="alpha", audience="consumer", task_type="consumer_copy"))
        excluded = client.retrieve(
        TaskContext(project="alpha", audience="consumer", task_type="incident_report")
    )
        other_project = client.retrieve(TaskContext(project="beta", audience="consumer", task_type="consumer_copy"))
        missing_audience = client.retrieve(TaskContext(project="alpha", task_type="consumer_copy"))

        self.assertEqual(len(in_scope.active_rules), 1)
        self.assertEqual(excluded.active_rules, [])
        self.assertTrue(any("negative boundary" in item.reason.lower() for item in excluded.excluded_rules))
        self.assertEqual(other_project.active_rules, [])
        self.assertTrue(any("project" in item.reason.lower() for item in other_project.excluded_rules))
        self.assertEqual(missing_audience.active_rules, [])
        self.assertTrue(missing_audience.uncertain_rules)


    def test_reviewer_filter_isolates_rules(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.store_rule(make_rule(rule_id="a", reviewer="reviewer-a"))
        client.store_rule(make_rule(rule_id="b", reviewer="reviewer-b"))

        selection = client.retrieve(
            TaskContext(project="alpha", audience="consumer", task_type="consumer_copy"), reviewer="reviewer-a"
    )

        self.assertEqual([rule.rule_id for rule in selection.active_rules], ["a"])


    def test_conflicting_reviewers_are_reported_and_not_arbitrarily_applied(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.store_rule(make_rule(rule_id="a", reviewer="reviewer-a", effect="avoid"))
        client.store_rule(make_rule(rule_id="b", reviewer="reviewer-b", effect="include"))

        selection = client.retrieve(TaskContext(project="alpha", audience="consumer", task_type="consumer_copy"))

        self.assertEqual(len(selection.conflicts), 1)
        self.assertEqual({selection.conflicts[0].left_rule_id, selection.conflicts[0].right_rule_id}, {"a", "b"})
        self.assertEqual(selection.effective_rules, [])


    def test_current_explicit_instruction_conflict_is_reported(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.store_rule(make_rule(effect="include"))

        selection = client.retrieve(
        TaskContext(
            project="alpha",
            task_type="consumer_copy",
            audience="consumer",
            current_overrides=[{"conflict_key": "downtime_claim", "effect": "avoid"}],
        )
    )

        self.assertEqual(selection.effective_rules, [])
        self.assertTrue(any(conflict.kind == "current_instruction" for conflict in selection.conflicts))


    def test_low_confidence_rule_is_not_activated_and_versions_are_retained(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        rule = make_rule(rule_id="low", confidence=0.2, status=RuleStatus.CONFIRMED)
        client.store_rule(rule)

        selection = client.retrieve(TaskContext(project="alpha", audience="consumer"))
        versions = client.rule_versions("low")

        self.assertEqual(selection.active_rules, [])
        self.assertTrue(selection.uncertain_rules)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["version"], 1)

    def test_low_confidence_feedback_cannot_be_confirmed_without_review(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        rule = client.ingest(
            "Maybe the opening could be shorter.",
            reviewer="reviewer-a",
            context={"applicable_scope": {"task_type": "launch_copy"}},
        )

        with self.assertRaisesRegex(ValueError, "below the"):
            client.confirm_rule(rule.rule_id)

        self.assertEqual(client.rules()[0].status, RuleStatus.DRAFT)


    def test_rule_update_creates_version_and_deactivation_stops_retrieval(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.store_rule(make_rule())
        updated = client.update_rule("rule-1", directive="Use evidence instead of guarantees.")
        self.assertEqual(updated.version, 2)
        self.assertEqual(len(client.rule_versions("rule-1")), 2)

        inactive = client.deactivate_rule("rule-1")
        selection = client.retrieve(TaskContext(project="alpha", audience="consumer"))

        self.assertEqual(inactive.status, RuleStatus.INACTIVE)
        self.assertEqual(inactive.version, 3)
        self.assertEqual(selection.active_rules, [])


    def test_missing_context_returns_uncertainty_instead_of_forcing_rule(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.store_rule(make_rule())

        selection = client.retrieve(TaskContext())

        self.assertEqual(selection.active_rules, [])
        self.assertTrue(selection.uncertain_rules)
        self.assertIn("insufficient context", selection.uncertain_rules[0].reason.lower())
