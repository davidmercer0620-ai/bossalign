"""BossAlign: the feedback alignment layer for AI agents."""

from .schema import BoundaryRule, CheckReport, FeedbackEvent, FeedbackKind, RuleStatus, TaskContext
from .sdk import BossAlign

__version__ = "0.2.0"
__all__ = [
    "BossAlign",
    "BoundaryRule",
    "CheckReport",
    "FeedbackEvent",
    "FeedbackKind",
    "RuleStatus",
    "TaskContext",
]
