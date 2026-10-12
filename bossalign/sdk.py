"""Small framework-independent public SDK."""

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .boundary import BoundaryEngine, MIN_ACTIVE_CONFIDENCE
from .parser import FeedbackParser
from .providers import DeterministicProvider, FeedbackProvider
from .sandbox import RuleChecker
from .schema import BoundaryRule, CheckReport, RuleSelection, RuleStatus, TaskContext, utc_now
from .store import MemoryStore


class BossAlign:
    """Persist, retrieve, and check scoped human feedback rules.

    The default provider is offline and deterministic. Configure an explicit
    provider instance to use an OpenAI-compatible service.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None, provider: Optional[FeedbackProvider] = None):
        if db_path is None:
            db_path = Path.home() / ".bossalign" / "memory.sqlite3"
        self.db_path = str(db_path)
        self.provider = provider or DeterministicProvider()
        self.store = MemoryStore(self.db_path)
        self.parser = FeedbackParser(self.provider)
        self.checker = RuleChecker()

    def ingest(
        self,
        feedback: str,
        reviewer: str = "default",
        context: Optional[Mapping[str, Any]] = None,
        confirm: bool = False,
        source: str = "user_feedback",
        preference_owner: Optional[str] = None,
        attribution: str = "direct",
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        sensitive: bool = False,
        consent_to_store_sensitive: bool = False,
        allow_external_processing: bool = False,
        retain_source_text: Optional[bool] = None,
        confirmed_by: Optional[str] = None,
    ) -> BoundaryRule:
        """Parse and persist feedback. Proposals remain drafts unless confirmed."""
        if sensitive and not consent_to_store_sensitive:
            raise ValueError("Sensitive feedback requires explicit consent to store a minimized rule")
        if sensitive and not getattr(self.provider, "data_local", False) and not allow_external_processing:
            raise ValueError("Sensitive feedback requires separate external processing consent")
        context_data = dict(context or {})
        event, rule = self.parser.parse(
            reviewer,
            feedback,
            context_data,
            source=source,
            attribution=attribution,
            preference_owner=preference_owner,
            valid_from=valid_from,
            valid_until=valid_until,
            sensitive=sensitive,
        )
        should_retain_source = (not sensitive) if retain_source_text is None else bool(retain_source_text)
        if sensitive and not should_retain_source:
            if rule.directive.strip().casefold() == feedback.strip().casefold():
                raise ValueError(
                    "Sensitive feedback requires a minimized directive when source-text retention is disabled"
                )
            event.raw_content = ""
            event.extracted_intent = "Sensitive feedback converted to a scoped rule."
            rule.original_feedback = ""
        self.store.save_feedback(event, rule)
        if confirm and rule.rule_candidate:
            return self.confirm_rule(rule.rule_id, confirmed_by=confirmed_by)
        return rule

    def confirm_rule(self, rule_id: str, confirmed_by: Optional[str] = None) -> BoundaryRule:
        rule = self.store.get_rule(rule_id)
        if rule is None:
            raise KeyError("Unknown rule: %s" % rule_id)
        if rule.status == RuleStatus.INACTIVE:
            raise ValueError("Inactive rules cannot be confirmed; update or re-ingest feedback first")
        if not rule.rule_candidate:
            raise ValueError("This feedback was classified as not eligible for a persistent rule")
        if confirmed_by is None:
            confirmed_by = rule.reviewer
        owner_confirmation_required = (
            rule.attribution != "direct"
            or (rule.preference_owner is not None and rule.preference_owner != rule.reviewer)
        )
        if owner_confirmation_required and (not rule.preference_owner or confirmed_by != rule.preference_owner):
            raise ValueError("Only the preference owner can confirm third-party, inferred, or other-owner feedback")
        if rule.confidence < MIN_ACTIVE_CONFIDENCE:
            raise ValueError(
                "Rule confidence %.2f is below the %.2f confirmation threshold; review and update it first"
                % (rule.confidence, MIN_ACTIVE_CONFIDENCE)
            )
        updated = replace(
            rule,
            status=RuleStatus.CONFIRMED,
            confirmed_by=confirmed_by,
            version=rule.version + 1,
            updated_at=utc_now(),
        )
        self.store.update_rule(updated)
        return updated

    def store_rule(self, rule: BoundaryRule) -> BoundaryRule:
        """Store an explicitly constructed rule and its initial version."""
        if not isinstance(rule, BoundaryRule):
            raise TypeError("rule must be a BoundaryRule")
        self.store.save_rule(rule)
        return rule

    def update_rule(self, rule_id: str, **changes) -> BoundaryRule:
        allowed = {
            "reviewer", "directive", "original_feedback", "source", "evidence", "origin",
            "applicable_scope", "negative_boundaries", "confidence", "conflict_key", "effect",
            "deterministic_checks", "counter_example_rationale", "applicable_topics",
            "applicable_objectives", "prohibited_topics", "preference_owner", "attribution",
            "communicative_intent", "rule_candidate", "valid_from", "valid_until", "sensitive",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError("Unsupported rule field(s): %s" % ", ".join(sorted(unknown)))
        current = self.store.get_rule(rule_id)
        if current is None:
            raise KeyError("Unknown rule: %s" % rule_id)
        changed_content = any(getattr(current, key) != value for key, value in changes.items())
        reset_confirmation = current.status in (RuleStatus.CONFIRMED, RuleStatus.INACTIVE) and changed_content
        updated = replace(
            current,
            **changes,
            status=RuleStatus.DRAFT if reset_confirmation else current.status,
            confirmed_by=None if reset_confirmation else current.confirmed_by,
            version=current.version + 1,
            updated_at=utc_now(),
        )
        self.store.update_rule(updated)
        return updated

    def deactivate_rule(self, rule_id: str) -> BoundaryRule:
        current = self.store.get_rule(rule_id)
        if current is None:
            raise KeyError("Unknown rule: %s" % rule_id)
        updated = replace(
            current,
            status=RuleStatus.INACTIVE,
            version=current.version + 1,
            updated_at=utc_now(),
        )
        self.store.update_rule(updated)
        return updated

    def revoke_rule(self, rule_id: str) -> BoundaryRule:
        """Revoke a confirmed preference while keeping its audit history."""
        return self.deactivate_rule(rule_id)

    def delete_rule(self, rule_id: str) -> bool:
        """Permanently remove a rule, its versions, and its source feedback."""
        current = self.store.get_rule(rule_id)
        if current is None:
            return False
        return self.store.delete_rule(rule_id, current.source_event_ids)

    def rules(
        self,
        reviewer: Optional[str] = None,
        project: Optional[str] = None,
        preference_owner: Optional[str] = None,
        include_inactive: bool = True,
    ):
        return self.store.list_rules(
            reviewer=reviewer,
            project=project,
            preference_owner=preference_owner,
            include_inactive=include_inactive,
        )

    def feedback_events(self, reviewer: Optional[str] = None):
        return self.store.feedback_events(reviewer=reviewer)

    def rule_versions(self, rule_id: str):
        return self.store.rule_versions(rule_id)

    def retrieve(self, task: Union[TaskContext, Mapping[str, Any]], reviewer: Optional[str] = None) -> RuleSelection:
        if not isinstance(task, TaskContext):
            task = TaskContext.from_mapping(task)
        return BoundaryEngine(self.store.all_rules()).evaluate_task(task, reviewer=reviewer)

    def check(
        self,
        task: Union[TaskContext, Mapping[str, Any]],
        output: str,
        reviewer: Optional[str] = None,
    ) -> CheckReport:
        if not isinstance(task, TaskContext):
            task = TaskContext.from_mapping(task)
        selection = self.retrieve(task, reviewer=reviewer)
        return self.checker.review(selection, output, provider=self.provider)

    def close(self) -> None:
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
