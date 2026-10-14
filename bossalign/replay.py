"""Deterministic event replay engine for historical regression and boundary verification."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .schema import BoundaryRule, RuleSelection, RuleStatus, TaskContext


@dataclass
class ReplayStep:
    step_id: str
    action: str  # "ingest", "confirm", "reject", "revoke", "supersede", "evaluate_task", "check_output"
    payload: Dict[str, Any]
    expected: Optional[Dict[str, Any]] = None


@dataclass
class ReplayStepResult:
    step_id: str
    action: str
    passed: bool
    actual: Dict[str, Any]
    discrepancies: List[str] = field(default_factory=list)


@dataclass
class ReplayReport:
    total_steps: int
    passed_steps: int
    failed_steps: int
    step_results: List[ReplayStepResult]
    regressions: List[str]
    passed: bool
    summary: str


class ReplayEngine:
    """Replays chronological feedback events against task test suites.

    Verifies:
    1. Revoked or rejected rules are NEVER active.
    2. Unconfirmed inferences are NEVER applied as facts.
    3. Conflicts are detected and not silently ignored.
    4. New feedback does not cause regressions on historical benchmark tasks.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path

    def run(self, steps: Sequence[ReplayStep]) -> ReplayReport:
        from .sdk import BossAlign

        step_results: List[ReplayStepResult] = []
        regressions: List[str] = []
        rule_map: Dict[str, str] = {}  # alias/name -> rule_id

        with BossAlign(self.db_path) as client:
            for step in steps:
                passed = True
                discrepancies: List[str] = []
                actual: Dict[str, Any] = {}

                action = step.action.lower().strip()
                payload = dict(step.payload)
                expected = dict(step.expected or {})

                try:
                    if action == "ingest":
                        feedback = payload["feedback"]
                        reviewer = payload.get("reviewer", "reviewer_1")
                        context = payload.get("context", {})
                        confirm = payload.get("confirm", False)
                        alias = payload.get("alias")
                        rule = client.ingest(
                            feedback,
                            reviewer=reviewer,
                            context=context,
                            confirm=confirm,
                            source=payload.get("source", "user_feedback"),
                            preference_owner=payload.get("preference_owner"),
                            attribution=payload.get("attribution", "direct"),
                            valid_from=payload.get("valid_from"),
                            valid_until=payload.get("valid_until"),
                        )
                        if alias:
                            rule_map[alias] = rule.rule_id
                        actual = {
                            "rule_id": rule.rule_id,
                            "status": rule.status.value,
                            "confidence": rule.confidence,
                        }
                        if expected.get("status") and actual["status"] != expected["status"]:
                            passed = False
                            discrepancies.append(
                                "Expected status '%s', got '%s'" % (expected["status"], actual["status"])
                            )

                    elif action == "confirm":
                        rule_ref = payload.get("rule_id") or rule_map.get(payload.get("alias", ""))
                        if not rule_ref:
                            raise KeyError("Missing rule_id or known alias for confirm step")
                        confirmed_by = payload.get("confirmed_by")
                        rule = client.confirm_rule(rule_ref, confirmed_by=confirmed_by)
                        actual = {"rule_id": rule.rule_id, "status": rule.status.value}
                        if expected.get("status") and actual["status"] != expected["status"]:
                            passed = False
                            discrepancies.append("Expected status '%s', got '%s'" % (expected["status"], actual["status"]))

                    elif action == "reject":
                        rule_ref = payload.get("rule_id") or rule_map.get(payload.get("alias", ""))
                        rejected_by = payload.get("rejected_by", "reviewer")
                        reason = payload.get("reason", "")
                        rule = client.reject_rule(rule_ref, rejected_by=rejected_by, reason=reason)
                        actual = {"rule_id": rule.rule_id, "status": rule.status.value}
                        if expected.get("status") and actual["status"] != expected["status"]:
                            passed = False
                            discrepancies.append("Expected status '%s', got '%s'" % (expected["status"], actual["status"]))

                    elif action == "revoke":
                        rule_ref = payload.get("rule_id") or rule_map.get(payload.get("alias", ""))
                        revoked_by = payload.get("revoked_by", "reviewer")
                        reason = payload.get("reason", "")
                        rule = client.revoke_rule(rule_ref, revoked_by=revoked_by, reason=reason)
                        actual = {"rule_id": rule.rule_id, "status": rule.status.value}
                        if expected.get("status") and actual["status"] != expected["status"]:
                            passed = False
                            discrepancies.append("Expected status '%s', got '%s'" % (expected["status"], actual["status"]))

                    elif action == "supersede":
                        old_ref = payload.get("old_rule_id") or rule_map.get(payload.get("old_alias", ""))
                        new_ref = payload.get("new_rule_id") or rule_map.get(payload.get("new_alias", ""))
                        actor = payload.get("actor", "system")
                        rule = client.supersede_rule(old_ref, new_ref, actor=actor)
                        actual = {"rule_id": rule.rule_id, "status": rule.status.value, "superseded_by": rule.superseded_by}

                    elif action == "evaluate_task":
                        task_data = payload.get("task", {})
                        task = TaskContext.from_mapping(task_data)
                        reviewer = payload.get("reviewer")
                        selection: RuleSelection = client.retrieve(task, reviewer=reviewer)
                        actual_active_ids = [r.rule_id for r in selection.active_rules]
                        actual_effective_ids = [r.rule_id for r in selection.effective_rules]
                        actual_conflicts_count = len(selection.conflicts)
                        actual = {
                            "active_rule_ids": actual_active_ids,
                            "effective_rule_ids": actual_effective_ids,
                            "conflicts_count": actual_conflicts_count,
                            "conflict_keys": [c.conflict_key for c in selection.conflicts],
                        }

                        # Check must_not_include_aliases or must_not_include_ids
                        forbidden_aliases = payload.get("must_not_include_aliases", [])
                        forbidden_ids = [rule_map.get(a) for a in forbidden_aliases if rule_map.get(a)]
                        forbidden_ids.extend(payload.get("must_not_include_ids", []))
                        for fid in forbidden_ids:
                            if fid in actual_effective_ids:
                                passed = False
                                msg = "Regression: forbidden/revoked rule '%s' was active in effective_rules" % fid
                                discrepancies.append(msg)
                                regressions.append(msg)

                        # Check expected active aliases
                        expected_aliases = expected.get("expected_effective_aliases", [])
                        for exp_alias in expected_aliases:
                            exp_id = rule_map.get(exp_alias)
                            if exp_id and exp_id not in actual_effective_ids:
                                passed = False
                                discrepancies.append("Expected effective rule '%s' (%s) missing" % (exp_alias, exp_id))

                        if "has_conflicts" in expected:
                            has_conflicts = actual_conflicts_count > 0
                            if has_conflicts != bool(expected["has_conflicts"]):
                                passed = False
                                discrepancies.append(
                                    "Expected has_conflicts=%s, got %s" % (expected["has_conflicts"], has_conflicts)
                                )

                    elif action == "check_output":
                        task = TaskContext.from_mapping(payload.get("task", {}))
                        output_text = payload.get("output", "")
                        reviewer = payload.get("reviewer")
                        report = client.check(task, output_text, reviewer=reviewer)
                        actual = {
                            "status": report.status,
                            "violations_count": len(report.violations),
                            "violations": [v.rule_id for v in report.violations],
                        }
                        if expected.get("status") and report.status != expected["status"]:
                            passed = False
                            discrepancies.append("Expected check status '%s', got '%s'" % (expected["status"], report.status))
                        if "violations_count" in expected and len(report.violations) != expected["violations_count"]:
                            passed = False
                            discrepancies.append(
                                "Expected %d violations, got %d" % (expected["violations_count"], len(report.violations))
                            )

                    else:
                        passed = False
                        discrepancies.append("Unknown replay action: '%s'" % action)

                except Exception as err:
                    passed = False
                    discrepancies.append("Exception during step execution: %s" % str(err))

                step_results.append(
                    ReplayStepResult(
                        step_id=step.step_id,
                        action=step.action,
                        passed=passed,
                        actual=actual,
                        discrepancies=discrepancies,
                    )
                )

        total = len(step_results)
        passed_count = sum(1 for s in step_results if s.passed)
        failed_count = total - passed_count
        overall_passed = (failed_count == 0 and len(regressions) == 0)
        summary = "Replay %s: %d total, %d passed, %d failed, %d regressions" % (
            "PASSED" if overall_passed else "FAILED",
            total,
            passed_count,
            failed_count,
            len(regressions),
        )

        return ReplayReport(
            total_steps=total,
            passed_steps=passed_count,
            failed_steps=failed_count,
            step_results=step_results,
            regressions=regressions,
            passed=overall_passed,
            summary=summary,
        )
