"""BossAlign: the human feedback alignment engine for AI agents."""

from .export import ExportManifest, ExportPolicy, PrivacyExporter
from .lifecycle import PreferenceLifecycle
from .replay import ReplayEngine, ReplayReport, ReplayStep
from .resolver import ConflictResolver
from .retrieval import (
    EvidenceItem,
    EvidenceQuery,
    EvidenceRetriever,
    InMemoryEvidenceRetriever,
    RetrievalResult,
    RetrievalStatus,
)
from .schema import (
    BoundaryRule,
    CheckReport,
    ConflictResolutionOption,
    ConflictType,
    ContentType,
    EvidenceLevel,
    EvidenceType,
    FeedbackAttribution,
    FeedbackEvent,
    FeedbackKind,
    RuleConflict,
    RuleDecision,
    RuleSelection,
    RuleStatus,
    TaskContext,
)
from .sdk import BossAlign
from .store import MemoryStore

__version__ = "0.2.0"
__all__ = [
    "BossAlign",
    "BoundaryRule",
    "CheckReport",
    "ConflictResolutionOption",
    "ConflictResolver",
    "ConflictType",
    "ContentType",
    "EvidenceItem",
    "EvidenceLevel",
    "EvidenceQuery",
    "EvidenceRetriever",
    "EvidenceType",
    "ExportManifest",
    "ExportPolicy",
    "FeedbackAttribution",
    "FeedbackEvent",
    "FeedbackKind",
    "InMemoryEvidenceRetriever",
    "MemoryStore",
    "PreferenceLifecycle",
    "PrivacyExporter",
    "ReplayEngine",
    "ReplayReport",
    "ReplayStep",
    "RetrievalResult",
    "RetrievalStatus",
    "RuleConflict",
    "RuleDecision",
    "RuleSelection",
    "RuleStatus",
    "TaskContext",
]
