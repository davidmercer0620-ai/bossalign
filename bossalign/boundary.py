"""Conservative, explainable rule selection and conflict detection."""

import re
from typing import List, Mapping, Optional, Sequence

from .schema import BoundaryRule, RuleConflict, RuleDecision, RuleSelection, RuleStatus, TaskContext


MIN_ACTIVE_CONFIDENCE = 0.6
_SCOPE_KEYS = ("project", "task_type", "topic", "audience", "objective", "task_id", "tags")


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _matches(expected: object, actual: object, key: str) -> bool:
    if key == "tags":
        expected_values = expected if isinstance(expected, (list, tuple, set)) else [expected]
        actual_values = actual if isinstance(actual, (list, tuple, set)) else [actual]
        return bool({_norm(item) for item in expected_values} & {_norm(item) for item in actual_values})
    expected_values = expected if isinstance(expected, (list, tuple, set)) else [expected]
    actual_values = actual if isinstance(actual, (list, tuple, set)) else [actual]
    return any(_norm(left) == _norm(right) for left in expected_values for right in actual_values)


def _rule_scope(rule: BoundaryRule) -> dict:
    scope = dict(rule.applicable_scope or {})
    # Translate the V0.1 fields without fuzzy substring matching.
    if not scope and rule.applicable_topics:
        scope["topic"] = list(rule.applicable_topics)
    if not rule.applicable_scope and rule.applicable_objectives:
        scope["objective"] = list(rule.applicable_objectives)
    return scope


class BoundaryEngine:
    def __init__(self, rules: Optional[Sequence[BoundaryRule]] = None):
        self.rules = list(rules or [])

    def add_rule(self, rule: BoundaryRule) -> None:
        self.rules.append(rule)

    def evaluate_task(
        self,
        task: TaskContext,
        reviewer: Optional[str] = None,
    ) -> RuleSelection:
        if not isinstance(task, TaskContext):
            task = TaskContext.from_mapping(task)
        selection = RuleSelection(task=task)
        accepted: List[BoundaryRule] = []

        for rule in self.rules:
            if reviewer is not None and rule.reviewer != reviewer:
                selection.excluded_rules.append(RuleDecision(rule.rule_id, "reviewer scope does not match the requested reviewer"))
                continue
            if rule.status == RuleStatus.INACTIVE:
                selection.excluded_rules.append(RuleDecision(rule.rule_id, "rule is inactive"))
                continue
            if rule.status != RuleStatus.CONFIRMED:
                selection.excluded_rules.append(RuleDecision(rule.rule_id, "rule is unconfirmed; draft proposals are not applied"))
                continue
            if rule.confidence < MIN_ACTIVE_CONFIDENCE:
                selection.uncertain_rules.append(
                    RuleDecision(rule.rule_id, "confidence %.2f is below activation threshold %.2f" % (rule.confidence, MIN_ACTIVE_CONFIDENCE))
                )
                continue

            if rule.prohibited_topics:
                selection.uncertain_rules.append(
                    RuleDecision(rule.rule_id, "legacy unstructured prohibited topics cannot be checked safely; replace them with structured negative boundaries")
                )
                continue

            scope = _rule_scope(rule)
            if not scope:
                selection.uncertain_rules.append(
                    RuleDecision(rule.rule_id, "insufficient context: rule has no structured applicable scope")
                )
                continue

            task_values = task.to_dict()

            missing = []
            mismatch = None
            unsupported = []
            for key, expected in scope.items():
                if key == "global" and expected is True:
                    continue
                if key not in _SCOPE_KEYS:
                    unsupported.append(key)
                    continue
                actual = task_values.get(key)
                if actual in (None, "", []):
                    missing.append(key)
                elif not _matches(expected, actual, key):
                    mismatch = key
                    break
            if mismatch:
                selection.excluded_rules.append(RuleDecision(rule.rule_id, "scope mismatch for %s" % mismatch))
                continue
            if unsupported:
                selection.uncertain_rules.append(
                    RuleDecision(rule.rule_id, "unsupported scope field(s): %s" % ", ".join(unsupported))
                )
                continue
            if missing:
                selection.uncertain_rules.append(
                    RuleDecision(rule.rule_id, "insufficient context for scope field(s): %s" % ", ".join(missing))
                )
                continue

            boundary_excluded = False
            boundary_unknown = False
            for boundary in rule.negative_boundaries:
                if not isinstance(boundary, Mapping) or not boundary:
                    boundary_unknown = True
                    continue
                boundary_missing = []
                boundary_mismatch = False
                for key, expected in boundary.items():
                    actual = task_values.get(key) if key in _SCOPE_KEYS else None
                    if actual in (None, "", []):
                        boundary_missing.append(key)
                    elif not _matches(expected, actual, key):
                        boundary_mismatch = True
                        break
                if not boundary_mismatch and not boundary_missing:
                    boundary_excluded = True
                    break
                if not boundary_mismatch and boundary_missing:
                    boundary_unknown = True

            if boundary_excluded:
                selection.excluded_rules.append(RuleDecision(rule.rule_id, "negative boundary matched; rule is excluded for this task"))
                continue
            if boundary_unknown:
                selection.uncertain_rules.append(
                    RuleDecision(rule.rule_id, "insufficient context to rule out a negative boundary")
                )
                continue
            accepted.append(rule)
            matched = ["%s=%s" % (key, value) for key, value in scope.items() if key != "global"]
            reason = "confirmed rule (confidence %.2f); matched exact scope: %s; no negative boundary matched" % (
                rule.confidence,
                ", ".join(matched) if matched else "global scope",
            )
            selection.active_reasons.append(RuleDecision(rule.rule_id, reason))

        selection.active_rules = accepted
        conflicting_ids = set()
        for index, left in enumerate(accepted):
            for right in accepted[index + 1 :]:
                if left.conflict_key and left.conflict_key == right.conflict_key and left.effect and right.effect and left.effect != right.effect:
                    conflicting_ids.update((left.rule_id, right.rule_id))
                    selection.conflicts.append(
                        RuleConflict(
                            left.rule_id,
                            right.rule_id,
                            left.conflict_key,
                            left.effect,
                            right.effect,
                            explanation="Confirmed rules share a conflict key but prescribe different effects; neither is applied automatically.",
                        )
                    )

        for rule in accepted:
            for current in task.current_overrides:
                if (
                    rule.conflict_key
                    and current.get("conflict_key") == rule.conflict_key
                    and current.get("effect")
                    and rule.effect
                    and current.get("effect") != rule.effect
                ):
                    conflicting_ids.add(rule.rule_id)
                    selection.conflicts.append(
                        RuleConflict(
                            rule.rule_id,
                            "current_task",
                            rule.conflict_key,
                            rule.effect,
                            str(current.get("effect")),
                            kind="current_instruction",
                            explanation="A structured current-task instruction conflicts with this stored rule; current instruction takes precedence.",
                        )
                    )

        selection.effective_rules = [rule for rule in accepted if rule.rule_id not in conflicting_ids]
        return selection
