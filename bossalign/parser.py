"""Feedback-to-rule proposal parsing with explicit uncertainty and provenance."""

import re
import uuid
from typing import Any, Mapping, Optional, Tuple

from .providers import DeterministicProvider, FeedbackProvider
from .schema import BoundaryRule, EvidenceLevel, FeedbackEvent, RuleStatus, utc_now


def denoise_feedback(raw_text: str) -> str:
    """Normalize whitespace only; never discard the source feedback."""
    return re.sub(r"\s+", " ", raw_text).strip()


class FeedbackParser:
    def __init__(self, provider: Optional[FeedbackProvider] = None):
        self.provider = provider or DeterministicProvider()

    def parse(
        self,
        reviewer: str,
        raw_feedback: str,
        context: Optional[Mapping[str, Any]] = None,
        source: str = "user_feedback",
    ) -> Tuple[FeedbackEvent, BoundaryRule]:
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer cannot be empty")
        original = raw_feedback.strip()
        if not original:
            raise ValueError("feedback cannot be empty")
        context_data = dict(context or {})
        proposal = self.provider.parse_feedback(original, reviewer, context_data)
        directive = str(proposal.get("directive") or "").strip()
        if not directive:
            directive = original
        origin = str(proposal.get("origin", "hypothesis"))
        allowed_origins = {"explicit_instruction", "user_preference", "ai_inference", "hypothesis"}
        if origin not in allowed_origins:
            origin = "hypothesis"
        confidence = max(0.0, min(1.0, float(proposal.get("confidence", 0.0))))
        scope = proposal.get("applicable_scope", {})
        if not isinstance(scope, Mapping):
            scope = {}
        boundaries = proposal.get("negative_boundaries", [])
        if not isinstance(boundaries, list):
            boundaries = []
        deterministic_checks = proposal.get("deterministic_checks", [])
        if not isinstance(deterministic_checks, list):
            deterministic_checks = []

        event_id = "evt_" + uuid.uuid4().hex
        rule_id = "rule_" + uuid.uuid4().hex
        timestamp = utc_now()
        event_context = context_data.get("topic_context") or context_data.get("task_id") or ""
        if isinstance(context, str):
            event_context = context
        # The source is a verbatim feedback record; interpretation uncertainty
        # is represented separately by origin and confidence.
        evidence_level = EvidenceLevel.L1_DIRECT_QUOTE
        event = FeedbackEvent(
            event_id=event_id,
            timestamp=timestamp,
            reviewer=reviewer,
            evidence_level=evidence_level,
            topic_context=str(event_context),
            raw_content=original,
            extracted_intent=directive,
            derived_rule_id=rule_id,
            source=source,
            origin=origin,
            confidence=confidence,
        )
        rationale = str(context_data.get("counter_example_rationale", ""))
        if not rationale and boundaries:
            rationale = "Structured negative boundaries limit where this rule can apply."
        rule = BoundaryRule(
            rule_id=rule_id,
            source_event_ids=[event_id],
            reviewer=reviewer,
            directive=directive,
            original_feedback=original,
            source=source,
            evidence=[event_id],
            origin=origin,
            applicable_scope=dict(scope),
            negative_boundaries=boundaries,
            confidence=confidence,
            status=RuleStatus.DRAFT,
            created_at=timestamp,
            updated_at=timestamp,
            conflict_key=str(proposal.get("conflict_key") or ""),
            effect=str(proposal.get("effect") or ""),
            deterministic_checks=[str(item).strip() for item in deterministic_checks if str(item).strip()],
            counter_example_rationale=rationale,
        )
        return event, rule


def parse_feedback_event(
    reviewer: str,
    raw_text: str,
    topic_context: str,
    evidence_level: EvidenceLevel = EvidenceLevel.L1_DIRECT_QUOTE,
    provider: Optional[FeedbackProvider] = None,
) -> Tuple[FeedbackEvent, BoundaryRule]:
    """V0.1-compatible wrapper; returned rules are proposals and remain drafts."""
    event, rule = FeedbackParser(provider).parse(
        reviewer,
        raw_text,
        context={"topic_context": topic_context},
    )
    # Keep callers that supplied an explicit evidence level source-compatible.
    if evidence_level != EvidenceLevel.L1_DIRECT_QUOTE:
        event.evidence_level = evidence_level
    return event, rule
