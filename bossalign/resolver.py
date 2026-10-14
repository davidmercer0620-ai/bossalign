"""Domain-agnostic conflict resolution engine for human feedback alignment."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .schema import (
    BoundaryRule,
    ConflictResolutionOption,
    ConflictType,
    RuleConflict,
    RuleSelection,
    RuleStatus,
    TaskContext,
)


def _parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


class ConflictResolver:
    """Detects, categorizes, and provides resolution strategies for rule conflicts.

    Never assumes one actor is universally superior to another unless explicitly
    configured via authority_hierarchy.
    """

    def __init__(self, authority_hierarchy: Optional[Sequence[str]] = None):
        # Explicit priority order: items earlier in sequence have higher authority
        self.authority_hierarchy = list(authority_hierarchy or [])

    def detect_conflicts(
        self,
        rules: Sequence[BoundaryRule],
        task: TaskContext,
    ) -> List[RuleConflict]:
        conflicts: List[RuleConflict] = []
        rule_list = list(rules)

        # 1. Compare pairwise for stored rule vs stored rule conflicts
        for i in range(len(rule_list)):
            left = rule_list[i]
            for j in range(i + 1, len(rule_list)):
                right = rule_list[j]
                conflict = self._check_pair_conflict(left, right, task)
                if conflict is not None:
                    conflicts.append(conflict)

        # 2. Check current task overrides vs stored rules
        current_conflicts = self._check_current_overrides(rule_list, task)
        conflicts.extend(current_conflicts)

        return conflicts

    def _check_pair_conflict(
        self,
        left: BoundaryRule,
        right: BoundaryRule,
        task: TaskContext,
    ) -> Optional[RuleConflict]:
        # Both must declare a conflict key and different non-empty effects
        if not (left.conflict_key and right.conflict_key):
            return None
        if left.conflict_key != right.conflict_key:
            return None
        if not (left.effect and right.effect) or left.effect == right.effect:
            return None

        # Determine conflict kind and options
        options: List[ConflictResolutionOption] = []
        kind = ConflictType.REVIEWER_CONFLICT.value
        explanation = "Rules prescribe opposing effects for key '%s'." % left.conflict_key

        # Case A: Evidence disparity (confirmed rule vs unconfirmed inference/draft)
        if left.status == RuleStatus.CONFIRMED and right.status in (RuleStatus.DRAFT, RuleStatus.PROPOSED):
            kind = ConflictType.EVIDENCE_DISPARITY.value
            explanation = "Confirmed rule '%s' conflicts with unconfirmed draft inference '%s'." % (
                left.rule_id, right.rule_id
            )
            options.append(
                ConflictResolutionOption(
                    strategy="prefer_confirmed",
                    description="Apply confirmed rule '%s'; discard unconfirmed draft '%s'." % (
                        left.rule_id, right.rule_id
                    ),
                    recommended=True,
                    applied_rule_id=left.rule_id,
                )
            )
            return RuleConflict(
                left_rule_id=left.rule_id,
                right_rule_id=right.rule_id,
                conflict_key=left.conflict_key,
                left_effect=left.effect,
                right_effect=right.effect,
                kind=kind,
                explanation=explanation,
                severity="medium",
                resolution_options=options,
            )
        elif right.status == RuleStatus.CONFIRMED and left.status in (RuleStatus.DRAFT, RuleStatus.PROPOSED):
            kind = ConflictType.EVIDENCE_DISPARITY.value
            explanation = "Confirmed rule '%s' conflicts with unconfirmed draft inference '%s'." % (
                right.rule_id, left.rule_id
            )
            options.append(
                ConflictResolutionOption(
                    strategy="prefer_confirmed",
                    description="Apply confirmed rule '%s'; discard unconfirmed draft '%s'." % (
                        right.rule_id, left.rule_id
                    ),
                    recommended=True,
                    applied_rule_id=right.rule_id,
                )
            )
            return RuleConflict(
                left_rule_id=left.rule_id,
                right_rule_id=right.rule_id,
                conflict_key=left.conflict_key,
                left_effect=left.effect,
                right_effect=right.effect,
                kind=kind,
                explanation=explanation,
                severity="medium",
                resolution_options=options,
            )

        # Case B: Same preference owner (temporal contradiction / changed mind)
        same_owner = (
            left.preference_owner is not None
            and right.preference_owner is not None
            and left.preference_owner == right.preference_owner
        )
        if same_owner:
            kind = ConflictType.TEMPORAL.value
            left_time = _parse_timestamp(left.updated_at or left.created_at)
            right_time = _parse_timestamp(right.updated_at or right.created_at)
            if left_time and right_time:
                newer, older = (left, right) if left_time > right_time else (right, left)
                explanation = (
                    "Subject '%s' gave contradictory instructions over time for key '%s'. Newer rule is '%s'."
                    % (left.preference_owner, left.conflict_key, newer.rule_id)
                )
                options.append(
                    ConflictResolutionOption(
                        strategy="prefer_newer_preference",
                        description="Supersede older rule '%s' with newer confirmed instruction '%s'." % (
                            older.rule_id, newer.rule_id
                        ),
                        recommended=True,
                        applied_rule_id=newer.rule_id,
                    )
                )
            else:
                explanation = "Subject '%s' has contradictory rules for key '%s'." % (
                    left.preference_owner, left.conflict_key
                )
            options.append(
                ConflictResolutionOption(
                    strategy="manual_clarification",
                    description="Pause automated application and request confirmation from subject.",
                    recommended=False,
                )
            )
            return RuleConflict(
                left_rule_id=left.rule_id,
                right_rule_id=right.rule_id,
                conflict_key=left.conflict_key,
                left_effect=left.effect,
                right_effect=right.effect,
                kind=kind,
                explanation=explanation,
                severity="high",
                resolution_options=options,
            )

        # Case C: Scope hierarchy (broad/global vs specific local scope)
        left_specific = len(left.applicable_scope or {})
        right_specific = len(right.applicable_scope or {})
        if left_specific != right_specific and (left_specific == 0 or right_specific == 0):
            kind = ConflictType.SCOPE_HIERARCHY.value
            more_specific, broader = (left, right) if left_specific > right_specific else (right, left)
            explanation = "Specific scoped rule '%s' conflicts with broader policy '%s' on key '%s'." % (
                more_specific.rule_id, broader.rule_id, left.conflict_key
            )
            options.append(
                ConflictResolutionOption(
                    strategy="prefer_specific_scope",
                    description="Allow local scope in '%s' to override broad policy in '%s'." % (
                        more_specific.rule_id, broader.rule_id
                    ),
                    recommended=True,
                    applied_rule_id=more_specific.rule_id,
                )
            )
            options.append(
                ConflictResolutionOption(
                    strategy="strict_global_policy",
                    description="Enforce broad policy in '%s' across all scopes." % broader.rule_id,
                    recommended=False,
                    applied_rule_id=broader.rule_id,
                )
            )
            return RuleConflict(
                left_rule_id=left.rule_id,
                right_rule_id=right.rule_id,
                conflict_key=left.conflict_key,
                left_effect=left.effect,
                right_effect=right.effect,
                kind=kind,
                explanation=explanation,
                severity="medium",
                resolution_options=options,
            )

        # Case D: Multi-actor conflict (different reviewers/owners)
        kind = ConflictType.MULTI_ACTOR.value
        hierarchy = task.authority_hierarchy or self.authority_hierarchy
        explanation = "Reviewers '%s' and '%s' demand conflicting effects for key '%s'." % (
            left.reviewer, right.reviewer, left.conflict_key
        )
        if hierarchy:
            left_prio = hierarchy.index(left.reviewer) if left.reviewer in hierarchy else 9999
            right_prio = hierarchy.index(right.reviewer) if right.reviewer in hierarchy else 9999
            if left_prio < right_prio:
                options.append(
                    ConflictResolutionOption(
                        strategy="authority_hierarchy",
                        description="Apply rule from higher authority '%s' over '%s'." % (
                            left.reviewer, right.reviewer
                        ),
                        recommended=True,
                        applied_rule_id=left.rule_id,
                    )
                )
            elif right_prio < left_prio:
                options.append(
                    ConflictResolutionOption(
                        strategy="authority_hierarchy",
                        description="Apply rule from higher authority '%s' over '%s'." % (
                            right.reviewer, left.reviewer
                        ),
                        recommended=True,
                        applied_rule_id=right.rule_id,
                    )
                )

        options.append(
            ConflictResolutionOption(
                strategy="manual_clarification",
                description="Do not apply either conflicting rule automatically without explicit resolution.",
                recommended=(len(options) == 0),
            )
        )

        return RuleConflict(
            left_rule_id=left.rule_id,
            right_rule_id=right.rule_id,
            conflict_key=left.conflict_key,
            left_effect=left.effect,
            right_effect=right.effect,
            kind=kind,
            explanation=explanation,
            severity="high",
            resolution_options=options,
        )

    def _check_current_overrides(
        self,
        rules: Sequence[BoundaryRule],
        task: TaskContext,
    ) -> List[RuleConflict]:
        conflicts: List[RuleConflict] = []
        for current in task.current_overrides:
            current_key = current.get("conflict_key")
            current_effect = current.get("effect")
            if not (current_key and current_effect):
                continue

            for rule in rules:
                if rule.conflict_key == current_key and rule.effect and rule.effect != current_effect:
                    explanation = (
                        "Current explicit instruction for key '%s' (%s) directly overrides stored rule '%s' (%s)."
                        % (current_key, current_effect, rule.rule_id, rule.effect)
                    )
                    options = [
                        ConflictResolutionOption(
                            strategy="current_explicit_override",
                            description="Honor current explicit refusal/preference; exclude stored rule '%s'." % rule.rule_id,
                            recommended=True,
                            applied_rule_id="current_task",
                        )
                    ]
                    conflicts.append(
                        RuleConflict(
                            left_rule_id=rule.rule_id,
                            right_rule_id="current_task",
                            conflict_key=current_key,
                            left_effect=rule.effect,
                            right_effect=str(current_effect),
                            kind="current_instruction",
                            explanation=explanation,
                            severity="high",
                            resolution_options=options,
                        )
                    )
        return conflicts
