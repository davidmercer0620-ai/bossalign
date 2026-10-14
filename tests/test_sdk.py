import tempfile
import unittest
from pathlib import Path

from bossalign import BossAlign, MemoryStore
from bossalign.schema import BoundaryRule, RuleStatus, TaskContext


class SemanticReviewProvider:
    semantic_review_enabled = True

    def parse_feedback(self, feedback, reviewer, context):
        raise AssertionError("not used by this test")

    def review_output(self, task, output, rules):
        return [{
            "rule_id": rules[0]["rule_id"],
            "severity": "high",
            "evidence": "unsupported promise",
            "suggestion": "Add evidence or remove the promise.",
            "confidence": 0.8,
        }]


class EmptySemanticReviewProvider(SemanticReviewProvider):
    def review_output(self, task, output, rules):
        return []


class TestSDK(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.tmp_path = Path(self.tempdir.name)

    def tearDown(self):
        MemoryStore.close_all()

    def test_check_reports_rule_evidence_and_never_claims_user_approval(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        rule = client.ingest(
        "Avoid 'guaranteed zero downtime' in consumer copy.",
        reviewer="reviewer-a",
        context={
            "applicable_scope": {"project": "alpha", "audience": "consumer"},
            "deterministic_checks": ["guaranteed zero downtime"],
        },
        confirm=True,
    )

        report = client.check(
        TaskContext(project="alpha", audience="consumer"),
        "The product offers guaranteed zero downtime under all conditions.",
        reviewer="reviewer-a",
    )

        self.assertEqual(report.status, "violations_found")
        self.assertEqual(report.violations[0].rule_id, rule.rule_id)
        self.assertEqual(report.violations[0].evidence, "guaranteed zero downtime")
        self.assertTrue(report.violations[0].suggestion)
        self.assertIn("matched exact scope", report.active_reasons[0].reason)
        self.assertFalse(report.user_approved)


    def test_coverage_gap_is_uncertain_not_a_clean_pass(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.ingest(
        "Prefer concise consumer copy.",
        reviewer="reviewer-a",
        context={"applicable_scope": {"audience": "consumer"}},
        confirm=True,
    )

        report = client.check(TaskContext(audience="consumer"), "A short draft.")

        self.assertEqual(report.status, "uncertain")
        self.assertFalse(report.user_approved)
        self.assertTrue(report.notes)


    def test_unrelated_feedback_does_not_affect_task(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3")
        client.ingest(
        "Avoid 'all caps' in consumer copy.",
        reviewer="reviewer-a",
        context={
            "applicable_scope": {"task_type": "consumer_copy"},
            "deterministic_checks": ["all caps"],
        },
        confirm=True,
    )

        report = client.check(
        TaskContext(task_type="python_code"), "Use ALL CAPS for this constant."
    )

        self.assertEqual(report.violations, [])
        self.assertTrue(report.excluded_rules)
        self.assertNotEqual(report.status, "violations_found")

    def test_llm_findings_are_labelled_as_inference_and_require_review(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3", provider=SemanticReviewProvider())
        client.store_rule(
            BoundaryRule(
                rule_id="rule-semantic",
                source_event_ids=["event-semantic"],
                reviewer="reviewer-a",
                directive="Avoid unsupported promises.",
                applicable_scope={"task_type": "consumer_copy"},
                confidence=0.9,
                status=RuleStatus.CONFIRMED,
                origin="explicit_instruction",
            )
        )

        report = client.check(TaskContext(task_type="consumer_copy"), "An unsupported promise.")

        self.assertEqual(report.status, "review_required")
        self.assertEqual(report.violations[0].check_type, "llm_inference")
        self.assertFalse(report.user_approved)
        self.assertTrue(any("probabilistic" in note for note in report.notes))

    def test_empty_llm_report_is_not_presented_as_deterministic_pass(self):
        client = BossAlign(self.tmp_path / "memory.sqlite3", provider=EmptySemanticReviewProvider())
        client.store_rule(
            BoundaryRule(
                rule_id="rule-semantic-empty",
                source_event_ids=["event-semantic-empty"],
                reviewer="reviewer-a",
                directive="Avoid unsupported promises.",
                applicable_scope={"task_type": "consumer_copy"},
                confidence=0.9,
                status=RuleStatus.CONFIRMED,
                origin="explicit_instruction",
            )
        )

        report = client.check(TaskContext(task_type="consumer_copy"), "A simple sentence.")

        self.assertEqual(report.status, "llm_review_no_findings")
        self.assertFalse(report.user_approved)
        self.assertTrue(any("not a guarantee" in note for note in report.notes))
