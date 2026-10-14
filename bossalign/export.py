"""Privacy-first export engine using strict field whitelisting.

Default posture: All data stays local.
Separates:
1. Open engine code
2. Private runtime data (raw feedback, author identity, paths, internal events)
3. Explicitly authorized export bundles
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from .schema import BoundaryRule, utc_now


DEFAULT_WHITELIST_FIELDS: Set[str] = {
    "rule_id",
    "directive",
    "applicable_scope",
    "negative_boundaries",
    "deterministic_checks",
    "effect",
    "conflict_key",
    "status",
    "version",
    "valid_from",
    "valid_until",
}

DEFAULT_REDACTED_FIELDS: Set[str] = {
    "original_feedback",
    "raw_content",
    "reviewer",
    "preference_owner",
    "evidence",
    "source_event_ids",
    "source",
    "rejection_reason",
    "revocation_reason",
    "counter_example_rationale",
}


@dataclass
class ExportPolicy:
    """Strict opt-in policy for data export across agents or environments."""

    allow_export: bool = False  # Strict default: Disabled
    whitelist_fields: Set[str] = field(default_factory=lambda: set(DEFAULT_WHITELIST_FIELDS))
    redact_actor_identity: bool = True
    include_raw_feedback: bool = False


@dataclass
class ExportManifest:
    """Previewable manifest describing exactly what will be exported and what is redacted."""

    export_id: str
    created_at: str
    rule_count: int
    whitelisted_fields: List[str]
    redacted_fields: List[str]
    preview_items: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "export_id": self.export_id,
            "created_at": self.created_at,
            "rule_count": self.rule_count,
            "whitelisted_fields": self.whitelisted_fields,
            "redacted_fields": self.redacted_fields,
            "preview_items": self.preview_items,
        }


class PrivacyExporter:
    """Safely exports rule states without leaking raw feedback or personal identifiers."""

    @classmethod
    def preview(
        cls,
        rules: Sequence[BoundaryRule],
        policy: Optional[ExportPolicy] = None,
        max_preview: int = 5,
    ) -> ExportManifest:
        active_policy = policy or ExportPolicy()
        rule_list = list(rules)
        export_id = "exp_" + uuid.uuid4().hex
        timestamp = utc_now()

        preview_items: List[Dict[str, Any]] = []
        for r in rule_list[:max_preview]:
            preview_items.append(cls._sanitize_rule(r, active_policy))

        return ExportManifest(
            export_id=export_id,
            created_at=timestamp,
            rule_count=len(rule_list),
            whitelisted_fields=sorted(list(active_policy.whitelist_fields)),
            redacted_fields=sorted(list(DEFAULT_REDACTED_FIELDS)),
            preview_items=preview_items,
        )

    @classmethod
    def export(
        cls,
        rules: Sequence[BoundaryRule],
        policy: ExportPolicy,
    ) -> Dict[str, Any]:
        """Perform export with whitelist projection. Raises PermissionError if not authorized."""
        if not policy.allow_export:
            raise PermissionError(
                "Data export is strictly disabled by default. Set policy.allow_export=True to authorize export."
            )

        sanitized_rules = [cls._sanitize_rule(r, policy) for r in rules]
        return {
            "version": "0.2.0",
            "exported_at": utc_now(),
            "count": len(sanitized_rules),
            "whitelisted_fields": sorted(list(policy.whitelist_fields)),
            "rules": sanitized_rules,
        }

    @classmethod
    def _sanitize_rule(cls, rule: BoundaryRule, policy: ExportPolicy) -> Dict[str, Any]:
        raw_dict = rule.to_dict()
        result: Dict[str, Any] = {}
        for k in policy.whitelist_fields:
            if k in raw_dict:
                result[k] = raw_dict[k]

        # Explicitly ensure no raw feedback leaks unless explicitly requested
        if not policy.include_raw_feedback:
            result.pop("original_feedback", None)
            result.pop("raw_content", None)

        # Explicitly ensure author identities are omitted
        if policy.redact_actor_identity:
            result.pop("reviewer", None)
            result.pop("preference_owner", None)
            result.pop("confirmed_by", None)

        return result
