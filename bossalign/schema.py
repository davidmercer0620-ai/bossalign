"""Public data models used by the BossAlign SDK and storage layer."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceLevel(str, Enum):
    L1_DIRECT_QUOTE = "L1_DIRECT_QUOTE"
    L2_FACTUAL_GROUNDING = "L2_FACTUAL_GROUNDING"
    L3_TRANSFERRED_NOTE = "L3_TRANSFERRED_NOTE"
    L4_AI_SPECULATION = "L4_AI_SPECULATION"


class EvidenceType(str, Enum):
    """Domain-agnostic classification of evidence reliability."""

    DIRECT_EXPLICIT = "direct_explicit"        # Explicit direct statement by subject
    VERIFIED_FACT = "verified_fact"            # Verified objective fact
    THIRD_PARTY_REPORT = "third_party_report"  # Transferred/relayed statement
    AI_INFERENCE = "ai_inference"              # Inferred by agent/model
    UNKNOWN = "unknown"                        # Insufficient evidence


class ContentType(str, Enum):
    """Distinguish subjective preferences from objective facts."""

    PREFERENCE = "preference"  # Subjective preference or taste
    FACT = "fact"              # Verifiable objective truth


class RuleStatus(str, Enum):
    PROPOSED = "proposed"      # Initial proposal (alias for draft)
    DRAFT = "draft"            # Proposed draft, never activated automatically
    CONFIRMED = "confirmed"    # Confirmed by authorized owner/reviewer
    REJECTED = "rejected"      # Explicitly rejected by owner/reviewer
    SUPERSEDED = "superseded"  # Replaced by newer confirmed rule
    REVOKED = "revoked"        # Revoked while keeping audit history
    EXPIRED = "expired"        # Expired due to time window
    INACTIVE = "inactive"      # Legacy deactivated status


class FeedbackKind(str, Enum):
    EXPLICIT_INSTRUCTION = "explicit_instruction"
    USER_PREFERENCE = "user_preference"
    AI_INFERENCE = "ai_inference"
    HYPOTHESIS = "hypothesis"
    OBJECTIVE_FACT = "objective_fact"


class FeedbackAttribution(str, Enum):
    """Who supplied the preference evidence, independent of what it says."""

    DIRECT = "direct"
    THIRD_PARTY = "third_party"
    AI_INFERENCE = "ai_inference"


@dataclass
class FeedbackEvent:
    """Immutable source record for a feedback-to-rule conversion."""

    event_id: str
    timestamp: str
    reviewer: str
    evidence_level: EvidenceLevel
    topic_context: str
    raw_content: str
    extracted_intent: str
    derived_rule_id: Optional[str] = None
    source: str = "user_feedback"
    origin: str = FeedbackKind.HYPOTHESIS.value
    confidence: float = 0.0
    attribution: str = FeedbackAttribution.DIRECT.value
    preference_owner: Optional[str] = None
    communicative_intent: str = "unspecified"
    rule_candidate: bool = True
    sensitive: bool = False
    # V0.2 governance & provenance extensions
    recorded_at: str = field(default_factory=utc_now)
    parent_event_id: Optional[str] = None
    linked_event_ids: List[str] = field(default_factory=list)
    supersedes_event_id: Optional[str] = None
    evidence_type: str = EvidenceType.DIRECT_EXPLICIT.value
    content_type: str = ContentType.PREFERENCE.value
    status: str = "recorded"

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["evidence_level"] = self.evidence_level.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FeedbackEvent":
        data = dict(value)
        data["evidence_level"] = EvidenceLevel(data.get("evidence_level", EvidenceLevel.L1_DIRECT_QUOTE.value))
        data["linked_event_ids"] = list(data.get("linked_event_ids") or [])
        valid_fields = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid_fields})


@dataclass
class BoundaryRule:
    """A scoped, evidence-backed rule. Drafts are stored but never applied."""

    # The first fields keep the original V0.1 constructor shape usable.
    rule_id: str
    source_event_ids: List[str]
    reviewer: str
    directive: str
    applicable_topics: List[str] = field(default_factory=list)
    applicable_objectives: List[str] = field(default_factory=list)
    prohibited_topics: List[str] = field(default_factory=list)
    counter_example_rationale: str = ""
    original_feedback: str = ""
    source: str = "user_feedback"
    evidence: List[str] = field(default_factory=list)
    origin: str = FeedbackKind.HYPOTHESIS.value
    applicable_scope: Dict[str, Any] = field(default_factory=dict)
    negative_boundaries: List[Any] = field(default_factory=list)
    confidence: float = 0.0
    status: RuleStatus = RuleStatus.DRAFT
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    version: int = 1
    conflict_key: str = ""
    effect: str = ""
    deterministic_checks: List[str] = field(default_factory=list)
    confirmed_by: Optional[str] = None
    preference_owner: Optional[str] = None
    attribution: str = FeedbackAttribution.DIRECT.value
    communicative_intent: str = "unspecified"
    rule_candidate: bool = True
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    sensitive: bool = False
    # V0.2 lifecycle, evidence & governance extensions
    rejection_reason: Optional[str] = None
    superseded_by: Optional[str] = None
    revocation_reason: Optional[str] = None
    evidence_type: str = EvidenceType.DIRECT_EXPLICIT.value
    content_type: str = ContentType.PREFERENCE.value
    priority: int = 100
    domain: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RuleStatus):
            self.status = RuleStatus(str(self.status))
        if self.attribution not in {item.value for item in FeedbackAttribution}:
            raise ValueError("Unsupported feedback attribution: %s" % self.attribution)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.version < 1:
            raise ValueError("Rule version must be at least 1")

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BoundaryRule":
        data = dict(value)
        status_val = data.get("status", RuleStatus.DRAFT.value)
        try:
            data["status"] = RuleStatus(status_val)
        except ValueError:
            data["status"] = RuleStatus.DRAFT
        valid_fields = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid_fields})

    def matches_task(self, topic: str, objective: str) -> bool:
        """Compatibility helper; new code should use BoundaryEngine for reasons."""
        topic_value = topic.strip().casefold()
        objective_value = objective.strip().casefold()
        return any(item.strip().casefold() == topic_value for item in self.applicable_topics) or any(
            item.strip().casefold() == objective_value for item in self.applicable_objectives
        )


@dataclass
class TaskContext:
    project: Optional[str] = None
    task_type: Optional[str] = None
    topic: Optional[str] = None
    audience: Optional[str] = None
    objective: Optional[str] = None
    task_id: Optional[str] = None
    interaction_context: Optional[str] = None
    preference_owner: Optional[str] = None
    as_of: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    current_overrides: List[Dict[str, str]] = field(default_factory=list)
    # V0.2 context extensions
    domain: Optional[str] = None
    scenario: Optional[str] = None
    task_intent: Optional[str] = None
    authority_hierarchy: List[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskContext":
        allowed = {
            "project", "task_type", "topic", "audience", "objective", "task_id",
            "interaction_context", "preference_owner", "as_of", "tags", "current_overrides",
            "domain", "scenario", "task_intent", "authority_hierarchy",
        }
        data = {key: value[key] for key in allowed if key in value}
        data["tags"] = list(data.get("tags") or [])
        data["current_overrides"] = list(data.get("current_overrides") or [])
        data["authority_hierarchy"] = list(data.get("authority_hierarchy") or [])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleDecision:
    rule_id: str
    reason: str


class ConflictType(str, Enum):
    MULTI_ACTOR = "multi_actor"              # Disagreement between distinct actors
    TEMPORAL = "temporal"                    # Changed mind over time by same actor
    SCOPE_HIERARCHY = "scope_hierarchy"      # Global policy vs local exception
    EVIDENCE_DISPARITY = "evidence_disparity"# Confirmed rule vs unconfirmed inference
    CURRENT_OVERRIDE = "current_override"    # Current explicit boundary vs historical rule
    REVIEWER_CONFLICT = "reviewer_conflict"  # Generic conflicting directives


@dataclass
class ConflictResolutionOption:
    strategy: str      # Strategy identifier (e.g. override, keep_existing, split_scope)
    description: str   # Human-readable explanation
    recommended: bool = False
    applied_rule_id: Optional[str] = None


@dataclass
class RuleConflict:
    left_rule_id: str
    right_rule_id: str
    conflict_key: str
    left_effect: str
    right_effect: str
    kind: str = "reviewer_conflict"
    explanation: str = ""
    severity: str = "high"
    resolution_options: List[ConflictResolutionOption] = field(default_factory=list)


@dataclass
class RuleSelection:
    task: TaskContext
    active_rules: List[BoundaryRule] = field(default_factory=list)
    effective_rules: List[BoundaryRule] = field(default_factory=list)
    active_reasons: List[RuleDecision] = field(default_factory=list)
    excluded_rules: List[RuleDecision] = field(default_factory=list)
    uncertain_rules: List[RuleDecision] = field(default_factory=list)
    conflicts: List[RuleConflict] = field(default_factory=list)

    @property
    def applicable_rules(self) -> List[BoundaryRule]:
        return self.active_rules


@dataclass
class AuditFinding:
    rule_id: str
    severity: str
    evidence: str
    suggestion: str
    check_type: str = "deterministic_phrase"
    confidence: Optional[float] = None


@dataclass
class CheckReport:
    task: TaskContext
    status: str
    applicable_rules: List[BoundaryRule] = field(default_factory=list)
    active_reasons: List[RuleDecision] = field(default_factory=list)
    violations: List[AuditFinding] = field(default_factory=list)
    excluded_rules: List[RuleDecision] = field(default_factory=list)
    uncertain_rules: List[RuleDecision] = field(default_factory=list)
    conflicts: List[RuleConflict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    user_approved: bool = False


# Backward-compatibility names from the initial schema.
BoundaryRuleStatus = RuleStatus
