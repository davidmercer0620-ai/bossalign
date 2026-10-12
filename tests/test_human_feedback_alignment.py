import json
import tempfile
import unittest
from pathlib import Path

from bossalign import BossAlign
from bossalign.schema import EvidenceLevel, RuleStatus, TaskContext


FIXTURE = Path(__file__).parents[1] / "examples" / "communication_feedback_cases.json"


class ScenarioProvider:
    """Test provider for known, fictional structured extraction outcomes."""

    data_local = True
    semantic_review_enabled = False

    def __init__(self, scenarios):
        self.scenarios = {item["feedback"]: item for item in scenarios}

    def parse_feedback(self, feedback, reviewer, context):
        scenario = self.scenarios[feedback]
        return {
            "directive": scenario["directive"],
            "origin": scenario["origin"],
            "confidence": 0.95,
            "communicative_intent": scenario["communicative_intent"],
            "rule_candidate": scenario["rule_candidate"],
            "applicable_scope": scenario["scope"],
            "valid_from": scenario.get("valid_from"),
            "valid_until": scenario.get("valid_until"),
            "negative_boundaries": scenario.get("negative_boundaries", []),
            "conflict_key": scenario.get("conflict_key", ""),
            "effect": scenario.get("effect", ""),
        }

    def review_output(self, task, output, rules):
        return []


class ExternalProvider(ScenarioProvider):
    data_local = False

    def __init__(self):
        super().__init__([{
            "feedback": "Sensitive instruction",
            "directive": "Use a short response.",
            "origin": "user_preference",
            "communicative_intent": "preference",
            "rule_candidate": True,
            "scope": {"task_type": "reply"},
            "preference_owner": "person-1",
        }])
        self.calls = 0

    def parse_feedback(self, feedback, reviewer, context):
        self.calls += 1
        return super().parse_feedback(feedback, reviewer, context)


class TestHumanFeedbackAlignment(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "memory.sqlite3"

    def test_same_core_api_handles_code_workplace_and_personal_feedback(self):
        client = BossAlign(self.db)
        cases = [
            (
                "Never change unrelated modules in this patch; only change the parser.",
                {"task_type": "code_review", "project": "demo"},
                TaskContext(task_type="code_review", project="demo", preference_owner="person-1"),
            ),
            (
                "Always keep weekly status updates concise.",
                {"task_type": "status_update", "interaction_context": "workplace"},
                TaskContext(task_type="status_update", interaction_context="workplace", preference_owner="person-1"),
            ),
            (
                "When I am venting, always ask before offering advice.",
                {"task_type": "conversation", "interaction_context": "personal_relationship"},
                TaskContext(task_type="conversation", interaction_context="personal_relationship", preference_owner="person-1"),
            ),
        ]
        for feedback, scope, task in cases:
            with self.subTest(scope=scope):
                rule = client.ingest(
                    feedback,
                    reviewer="agent",
                    preference_owner="person-1",
                    context={"applicable_scope": scope},
                    confirm=True,
                    confirmed_by="person-1",
                )
                selection = client.retrieve(task)
                self.assertEqual(rule.status, RuleStatus.CONFIRMED)
                self.assertEqual([item.rule_id for item in selection.active_rules], [rule.rule_id])

    def test_material_update_of_confirmed_rule_requires_reconfirmation(self):
        client = BossAlign(self.db)
        rule = client.ingest(
            "Keep replies brief in the specified conversation context.",
            reviewer="agent",
            preference_owner="person-1",
            context={"applicable_scope": {"interaction_context": "personal_relationship"}},
            confirm=True, confirmed_by="person-1",
        )

        updated = client.update_rule(
            rule.rule_id,
            directive="Ask before offering advice.",
            applicable_scope={"interaction_context": "personal_relationship", "task_type": "venting"},
        )

        self.assertEqual(updated.status, RuleStatus.DRAFT)
        self.assertIsNone(updated.confirmed_by)
        self.assertEqual(updated.version, rule.version + 1)
        self.assertEqual(client.retrieve(TaskContext(
            interaction_context="personal_relationship", task_type="venting", preference_owner="person-1"
        )).active_rules, [])
        re_confirmed = client.confirm_rule(rule.rule_id, confirmed_by="person-1")
        self.assertEqual(re_confirmed.status, RuleStatus.CONFIRMED)

    def test_preference_owner_and_interaction_context_isolate_rules(self):
        client = BossAlign(self.db)
        first = client.ingest(
            "Use a calm tone in personal conversations.", reviewer="agent", preference_owner="person-1",
            context={"applicable_scope": {"interaction_context": "personal_relationship"}},
            confirm=True, confirmed_by="person-1",
        )
        second = client.ingest(
            "Use direct language in personal conversations.", reviewer="agent", preference_owner="person-2",
            context={"applicable_scope": {"interaction_context": "personal_relationship"}},
            confirm=True, confirmed_by="person-2",
        )

        selection = client.retrieve(TaskContext(
            interaction_context="personal_relationship", preference_owner="person-1"
        ))
        other_context = client.retrieve(TaskContext(
            interaction_context="workplace", preference_owner="person-1"
        ))
        missing_owner = client.retrieve(TaskContext(interaction_context="personal_relationship"))

        self.assertEqual([rule.rule_id for rule in selection.active_rules], [first.rule_id])
        self.assertTrue(any(item.rule_id == second.rule_id for item in selection.excluded_rules))
        self.assertEqual(other_context.active_rules, [])
        self.assertTrue(any("preference owner is unknown" in item.reason for item in missing_owner.uncertain_rules))

    def test_third_party_report_is_not_confirmed_as_the_subjects_fact(self):
        client = BossAlign(self.db)
        rule = client.ingest(
            "A friend said they prefer no calls without notice.",
            reviewer="reporter",
            preference_owner="person-2",
            attribution="third_party",
            context={"applicable_scope": {"interaction_context": "personal_relationship"}},
            confirmed_by="person-2",
        )

        self.assertEqual(rule.attribution, "third_party")
        event = client.feedback_events(reviewer="reporter")[0]
        self.assertEqual(event.evidence_level, EvidenceLevel.L3_TRANSFERRED_NOTE)
        self.assertEqual(event.preference_owner, "person-2")
        self.assertEqual(client.retrieve(TaskContext(
            interaction_context="personal_relationship", preference_owner="person-2"
        )).active_rules, [])
        with self.assertRaisesRegex(ValueError, "preference owner"):
            client.confirm_rule(rule.rule_id, confirmed_by="reporter")
        confirmed = client.confirm_rule(rule.rule_id, confirmed_by="person-2")
        self.assertEqual(confirmed.status, RuleStatus.CONFIRMED)

    def test_ai_inference_requires_confirmation_by_the_preference_owner(self):
        client = BossAlign(self.db)
        rule = client.ingest(
            "The agent inferred a preference from prior behavior.",
            reviewer="agent",
            preference_owner="person-2",
            attribution="ai_inference",
            context={
                "origin": "ai_inference",
                "confidence": 0.95,
                "directive": "Use concise replies.",
                "applicable_scope": {"task_type": "reply"},
            },
        )

        event = client.feedback_events(reviewer="agent")[0]
        self.assertEqual(event.evidence_level, EvidenceLevel.L4_AI_SPECULATION)
        self.assertEqual(rule.status, RuleStatus.DRAFT)
        with self.assertRaisesRegex(ValueError, "preference owner"):
            client.confirm_rule(rule.rule_id, confirmed_by="agent")
        self.assertEqual(client.confirm_rule(rule.rule_id, confirmed_by="person-2").status, RuleStatus.CONFIRMED)

    def test_expired_temporary_preference_is_not_applied(self):
        client = BossAlign(self.db)
        rule = client.ingest(
            "Do not message me during this quiet period.",
            reviewer="agent",
            preference_owner="person-1",
            valid_from="2026-10-01T00:00:00+00:00",
            valid_until="2026-10-10T00:00:00+00:00",
            context={"applicable_scope": {"interaction_context": "personal_relationship"}},
            confirm=True, confirmed_by="person-1",
        )
        during = client.retrieve(TaskContext(
            interaction_context="personal_relationship", preference_owner="person-1",
            as_of="2026-10-09T12:00:00+00:00",
        ))
        after = client.retrieve(TaskContext(
            interaction_context="personal_relationship", preference_owner="person-1",
            as_of="2026-10-11T12:00:00+00:00",
        ))

        self.assertEqual([item.rule_id for item in during.active_rules], [rule.rule_id])
        self.assertTrue(any("expired" in item.reason for item in after.excluded_rules))

    def test_current_refusal_overrides_old_confirmed_preference(self):
        client = BossAlign(self.db)
        old = client.ingest(
            "Always check in by phone in this context.", reviewer="agent", preference_owner="person-1",
            context={
                "applicable_scope": {"interaction_context": "personal_relationship", "task_type": "calling"},
                "conflict_key": "contact", "effect": "call",
            }, confirm=True,
            confirmed_by="person-1",
        )

        selection = client.retrieve(TaskContext(
            interaction_context="personal_relationship", task_type="calling", preference_owner="person-1",
            current_overrides=[{"conflict_key": "contact", "effect": "no_contact"}],
        ))

        self.assertEqual(selection.active_rules, [old])
        self.assertEqual(selection.effective_rules, [])
        self.assertTrue(any(item.kind == "current_instruction" for item in selection.conflicts))

    def test_sensitive_feedback_requires_consent_and_minimizes_persisted_source(self):
        client = BossAlign(self.db)
        raw = "Sensitive personal details that should not be retained verbatim."
        with self.assertRaisesRegex(ValueError, "consent to store"):
            client.ingest(raw, reviewer="agent", sensitive=True)

        rule = client.ingest(
            raw,
            reviewer="agent",
            preference_owner="person-1",
            sensitive=True,
            consent_to_store_sensitive=True,
            context={
                "directive": "Use a brief, neutral response.",
                "topic_context": raw,
                "applicable_scope": {"interaction_context": "personal_relationship"},
            },
        )
        event = client.feedback_events(reviewer="agent")[0]
        self.assertEqual(event.raw_content, "")
        self.assertEqual(event.topic_context, "sensitive_feedback")
        self.assertEqual(rule.original_feedback, "")
        self.assertNotIn(raw, json.dumps(event.to_dict(), ensure_ascii=False))
        self.assertNotIn(raw, json.dumps(rule.to_dict(), ensure_ascii=False))

    def test_sensitive_feedback_needs_separate_external_processing_consent(self):
        provider = ExternalProvider()
        client = BossAlign(self.db, provider=provider)
        arguments = {
            "feedback": "Sensitive instruction",
            "reviewer": "agent",
            "preference_owner": "person-1",
            "sensitive": True,
            "consent_to_store_sensitive": True,
        }
        with self.assertRaisesRegex(ValueError, "external processing consent"):
            client.ingest(**arguments)
        self.assertEqual(provider.calls, 0)

        client.ingest(**arguments, allow_external_processing=True)
        self.assertEqual(provider.calls, 1)

    def test_delete_rule_removes_rule_versions_and_source_feedback(self):
        client = BossAlign(self.db)
        rule = client.ingest(
            "Use a concise response.", reviewer="agent", confirm=True,
        )
        self.assertEqual(len(client.feedback_events()), 1)
        self.assertTrue(client.delete_rule(rule.rule_id))
        self.assertIsNone(client.store.get_rule(rule.rule_id))
        self.assertEqual(client.rule_versions(rule.rule_id), [])
        self.assertEqual(client.feedback_events(), [])

    def test_revoked_rule_can_be_revised_only_as_a_new_draft(self):
        client = BossAlign(self.db)
        rule = client.ingest("Use concise replies.", reviewer="agent", confirm=True)
        revoked = client.revoke_rule(rule.rule_id)
        self.assertEqual(revoked.status, RuleStatus.INACTIVE)
        revised = client.update_rule(rule.rule_id, directive="Ask before offering advice.")
        self.assertEqual(revised.status, RuleStatus.DRAFT)
        self.assertEqual(client.confirm_rule(rule.rule_id).status, RuleStatus.CONFIRMED)

    def test_fictional_communication_cases_distinguish_expression_and_boundaries(self):
        scenarios = json.loads(FIXTURE.read_text(encoding="utf-8"))
        client = BossAlign(self.db, provider=ScenarioProvider(scenarios))
        rules = {}
        for scenario in scenarios:
            rule = client.ingest(
                scenario["feedback"], reviewer="agent", preference_owner=scenario["preference_owner"],
                attribution="direct", valid_from=scenario.get("valid_from"),
                valid_until=scenario.get("valid_until"),
                context={"applicable_scope": scenario["scope"], "conflict_key": scenario.get("conflict_key"),
                         "negative_boundaries": scenario.get("negative_boundaries", []),
                         "effect": scenario.get("effect")},
                confirm=True,
                confirmed_by=scenario["preference_owner"],
            )
            rules[scenario["id"]] = rule

        for scenario_id in ("venting", "advice-request"):
            scenario = next(item for item in scenarios if item["id"] == scenario_id)
            rule = rules[scenario_id]
            event = next(item for item in client.feedback_events() if item.derived_rule_id == rule.rule_id)
            self.assertFalse(rule.rule_candidate)
            self.assertEqual(event.communicative_intent, scenario["communicative_intent"])
            selection = client.retrieve(TaskContext.from_mapping({
                **scenario["scope"], "preference_owner": scenario["preference_owner"],
            }))
            self.assertNotIn(rule.rule_id, [item.rule_id for item in selection.active_rules])
            self.assertTrue(any("not eligible" in item.reason for item in selection.excluded_rules))
            with self.assertRaisesRegex(ValueError, "not eligible"):
                client.confirm_rule(rule.rule_id, confirmed_by="person-1")

        for scenario_id in ("temporary-space", "boundary-change"):
            scenario = next(item for item in scenarios if item["id"] == scenario_id)
            task_context = dict(scenario["scope"])
            if scenario_id == "boundary-change":
                task_context["task_type"] = "calling"
            task = TaskContext.from_mapping({
                **task_context, "preference_owner": scenario["preference_owner"],
                "as_of": "2026-10-12T12:00:00+00:00",
            })
            selection = client.retrieve(task)
            self.assertIn(rules[scenario_id].rule_id, [item.rule_id for item in selection.active_rules])
            if scenario_id == "boundary-change":
                excluded = client.retrieve(TaskContext(
                    interaction_context="personal_relationship", task_type="emergency_call",
                    preference_owner=scenario["preference_owner"],
                ))
                self.assertNotIn(rules[scenario_id].rule_id, [item.rule_id for item in excluded.active_rules])
                self.assertTrue(any("negative boundary" in item.reason for item in excluded.excluded_rules))


if __name__ == "__main__":
    unittest.main()
