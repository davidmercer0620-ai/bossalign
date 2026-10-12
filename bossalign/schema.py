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


class RuleStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    INACTIVE = "inactive"


class FeedbackKind(str, Enum):
    EXPLICIT_INSTRUCTION = "explicit_instruction"
    USER_PREFERENCE = "user_preference"
    AI_INFERENCE = "ai_inference"
    HYPOTHESIS = "hypothesis"


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

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["evidence_level"] = self.evidence_level.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FeedbackEvent":
        data = dict(value)
        data["evidence_level"] = EvidenceLevel(data.get("evidence_level", EvidenceLevel.L1_DIRECT_QUOTE.value))
        return cls(**data)


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

    def __post_init__(self) -> None:
        if not isinstance(self.status, RuleStatus):
            self.status = RuleStatus(str(self.status))
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
        data["status"] = RuleStatus(data.get("status", RuleStatus.DRAFT.value))
        return cls(**data)

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
    tags: List[str] = field(default_factory=list)
    current_overrides: List[Dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskContext":
        allowed = {"project", "task_type", "topic", "audience", "objective", "task_id", "tags", "current_overrides"}
        data = {key: value[key] for key in allowed if key in value}
        data["tags"] = list(data.get("tags") or [])
        data["current_overrides"] = list(data.get("current_overrides") or [])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleDecision:
    rule_id: str
    reason: str


@dataclass
class RuleConflict:
    left_rule_id: str
    right_rule_id: str
    conflict_key: str
    left_effect: str
    right_effect: str
    kind: str = "reviewer_conflict"
    explanation: str = ""


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
