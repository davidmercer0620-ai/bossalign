"""Preference lifecycle management and state transitions.

Supported lifecycle:
PROPOSED / DRAFT -> CONFIRMED -> SUPERSEDED / REVOKED / EXPIRED
Also supports explicit REJECTED and historical audit preservation.
"""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from .schema import BoundaryRule, FeedbackAttribution, RuleStatus, utc_now


MIN_ACTIVE_CONFIDENCE = 0.6


def parse_utc_timestamp(value: Optional[str]) -> Optional[datetime]:
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


class PreferenceLifecycle:
    """Manages safe, auditable state transitions for preference rules."""

    @staticmethod
    def is_active(rule: BoundaryRule, as_of: Optional[str] = None) -> bool:
        """Check if a rule is currently active, confirmed, and unexpired."""
        if rule.status != RuleStatus.CONFIRMED:
            return False
        if rule.confidence < MIN_ACTIVE_CONFIDENCE:
            return False

        # Expiry check
        if rule.valid_until:
            as_of_dt = parse_utc_timestamp(as_of) or datetime.now(timezone.utc)
            expiry_dt = parse_utc_timestamp(rule.valid_until)
            if expiry_dt and as_of_dt >= expiry_dt:
                return False

        # Effective start check
        if rule.valid_from:
            as_of_dt = parse_utc_timestamp(as_of) or datetime.now(timezone.utc)
            start_dt = parse_utc_timestamp(rule.valid_from)
            if start_dt and as_of_dt < start_dt:
                return False

        return True

    @staticmethod
    def confirm(
        rule: BoundaryRule,
        confirmed_by: Optional[str] = None,
        as_of: Optional[str] = None,
    ) -> BoundaryRule:
        """Confirm a proposed draft rule. Only the owner can confirm attributed feedback."""
        if rule.status in (RuleStatus.REVOKED, RuleStatus.INACTIVE, RuleStatus.REJECTED, RuleStatus.SUPERSEDED):
            raise ValueError(
                "Rule with status '%s' cannot be confirmed directly; create a new proposal first"
                % rule.status.value
            )
        if not rule.rule_candidate:
            raise ValueError("This feedback was classified as not eligible for a persistent rule")

        if confirmed_by is None:
            confirmed_by = rule.reviewer

        owner_confirmation_required = (
            rule.attribution != FeedbackAttribution.DIRECT.value
            or (rule.preference_owner is not None and rule.preference_owner != rule.reviewer)
        )
        if owner_confirmation_required and (not rule.preference_owner or confirmed_by != rule.preference_owner):
            raise ValueError("Only the preference owner can confirm third-party, inferred, or other-owner feedback")

        if rule.confidence < MIN_ACTIVE_CONFIDENCE:
            raise ValueError(
                "Rule confidence %.2f is below the %.2f confirmation threshold; review and update it first"
                % (rule.confidence, MIN_ACTIVE_CONFIDENCE)
            )

        now_str = as_of or utc_now()
        return replace(
            rule,
            status=RuleStatus.CONFIRMED,
            confirmed_by=confirmed_by,
            version=rule.version + 1,
            updated_at=now_str,
        )

    @staticmethod
    def reject(
        rule: BoundaryRule,
        rejected_by: str,
        reason: str = "",
        as_of: Optional[str] = None,
    ) -> BoundaryRule:
        """Explicitly reject a proposed rule."""
        if not rejected_by or not rejected_by.strip():
            raise ValueError("rejected_by cannot be empty")
        now_str = as_of or utc_now()
        return replace(
            rule,
            status=RuleStatus.REJECTED,
            rejection_reason=reason,
            version=rule.version + 1,
            updated_at=now_str,
        )

    @staticmethod
    def revoke(
        rule: BoundaryRule,
        revoked_by: str,
        reason: str = "",
        as_of: Optional[str] = None,
    ) -> BoundaryRule:
        """Revoke a confirmed rule while keeping its audit history."""
        if not revoked_by or not revoked_by.strip():
            raise ValueError("revoked_by cannot be empty")
        now_str = as_of or utc_now()
        return replace(
            rule,
            status=RuleStatus.REVOKED,
            revocation_reason=reason,
            version=rule.version + 1,
            updated_at=now_str,
        )

    @staticmethod
    def supersede(
        old_rule: BoundaryRule,
        new_rule_id: str,
        superseded_by_actor: str,
        reason: str = "",
        as_of: Optional[str] = None,
    ) -> BoundaryRule:
        """Mark an older rule as superseded by a newer confirmed rule."""
        if not new_rule_id or not new_rule_id.strip():
            raise ValueError("new_rule_id cannot be empty")
        now_str = as_of or utc_now()
        return replace(
            old_rule,
            status=RuleStatus.SUPERSEDED,
            superseded_by=new_rule_id,
            revocation_reason=reason or ("Superseded by rule %s" % new_rule_id),
            version=old_rule.version + 1,
            updated_at=now_str,
        )

    @staticmethod
    def expire_if_due(rule: BoundaryRule, as_of: Optional[str] = None) -> BoundaryRule:
        """Transition rule to EXPIRED if past valid_until."""
        if rule.status != RuleStatus.CONFIRMED or not rule.valid_until:
            return rule
        as_of_dt = parse_utc_timestamp(as_of) or datetime.now(timezone.utc)
        expiry_dt = parse_utc_timestamp(rule.valid_until)
        if expiry_dt and as_of_dt >= expiry_dt:
            return replace(
                rule,
                status=RuleStatus.EXPIRED,
                version=rule.version + 1,
                updated_at=as_of or utc_now(),
            )
        return rule
