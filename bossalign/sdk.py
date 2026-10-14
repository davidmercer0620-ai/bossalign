"""Small framework-independent public SDK."""

from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .boundary import BoundaryEngine
from .export import ExportManifest, ExportPolicy, PrivacyExporter
from .lifecycle import PreferenceLifecycle
from .parser import FeedbackParser
from .providers import DeterministicProvider, FeedbackProvider
from .replay import ReplayEngine, ReplayReport, ReplayStep
from .retrieval import EvidenceRetriever, InMemoryEvidenceRetriever
from .sandbox import RuleChecker
from .schema import BoundaryRule, CheckReport, FeedbackEvent, RuleSelection, RuleStatus, TaskContext, utc_now
from .store import MemoryStore


class BossAlign:
    """Persist, retrieve, and check scoped human feedback rules.

    The default provider is offline and deterministic. Configure an explicit
    provider instance to use an OpenAI-compatible service.
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        provider: Optional[FeedbackProvider] = None,
        retriever: Optional[EvidenceRetriever] = None,
    ):
        if db_path is None:
            db_path = Path.home() / ".bossalign" / "memory.sqlite3"
        self.db_path = str(db_path)
        self.provider = provider or DeterministicProvider()
        self.store = MemoryStore(self.db_path)
        self.parser = FeedbackParser(self.provider)
        self.checker = RuleChecker()
        self.retriever = retriever or InMemoryEvidenceRetriever()

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
        updated = PreferenceLifecycle.confirm(rule, confirmed_by=confirmed_by)
        self.store.update_rule(updated)
        return updated

    def reject_rule(self, rule_id: str, rejected_by: str, reason: str = "") -> BoundaryRule:
        rule = self.store.get_rule(rule_id)
        if rule is None:
            raise KeyError("Unknown rule: %s" % rule_id)
        updated = PreferenceLifecycle.reject(rule, rejected_by=rejected_by, reason=reason)
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
            "domain", "priority", "rejection_reason", "superseded_by", "revocation_reason",
            "evidence_type", "content_type", "source_event_ids",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError("Unsupported rule field(s): %s" % ", ".join(sorted(unknown)))
        current = self.store.get_rule(rule_id)
        if current is None:
            raise KeyError("Unknown rule: %s" % rule_id)
        changed_content = any(getattr(current, key) != value for key, value in changes.items())
        reset_confirmation = current.status in (RuleStatus.CONFIRMED, RuleStatus.INACTIVE, RuleStatus.REVOKED) and changed_content
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

    def revoke_rule(self, rule_id: str, revoked_by: str = "reviewer", reason: str = "") -> BoundaryRule:
        """Revoke a confirmed preference while keeping its audit history."""
        rule = self.store.get_rule(rule_id)
        if rule is None:
            raise KeyError("Unknown rule: %s" % rule_id)
        updated = PreferenceLifecycle.revoke(rule, revoked_by=revoked_by, reason=reason)
        self.store.update_rule(updated)
        return updated

    def supersede_rule(self, old_rule_id: str, new_rule_id: str, actor: str = "system", reason: str = "") -> BoundaryRule:
        """Mark an older preference as superseded by a newer confirmed rule."""
        old_rule = self.store.get_rule(old_rule_id)
        if old_rule is None:
            raise KeyError("Unknown rule: %s" % old_rule_id)
        updated = PreferenceLifecycle.supersede(old_rule, new_rule_id, superseded_by_actor=actor, reason=reason)
        self.store.update_rule(updated)
        return updated

    def get_evidence_chain(self, rule_id: str) -> List[FeedbackEvent]:
        """Trace a rule back through its source events and provenance."""
        return self.store.get_rule_evidence_chain(rule_id)

    def export_rules(
        self,
        policy: Optional[ExportPolicy] = None,
        rules: Optional[Sequence[BoundaryRule]] = None,
    ) -> Dict[str, Any]:
        """Safely export whitelisted rule fields with explicit opt-in policy."""
        target_rules = self.rules() if rules is None else list(rules)
        active_policy = policy if policy is not None else ExportPolicy(allow_export=True)
        return PrivacyExporter.export(target_rules, active_policy)

    def preview_export(
        self,
        policy: Optional[ExportPolicy] = None,
        rules: Optional[Sequence[BoundaryRule]] = None,
    ) -> ExportManifest:
        """Preview sanitized manifest before exporting rules."""
        target_rules = self.rules() if rules is None else list(rules)
        return PrivacyExporter.preview(target_rules, policy)

    def replay(self, steps: Sequence[ReplayStep]) -> ReplayReport:
        """Replay chronological events and verify regression safety."""
        return ReplayEngine(self.db_path).run(steps)

    def verify_claim(self, claim: str, domain: Optional[str] = None):
        """Verify factual claim using configured pluggable evidence retriever."""
        return self.retriever.verify_claim(claim, domain=domain)

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
