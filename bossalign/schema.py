from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class EvidenceLevel(str, Enum):
    L1_DIRECT_QUOTE = "L1_DIRECT_QUOTE"
    L2_FACTUAL_GROUNDING = "L2_FACTUAL_GROUNDING"
    L3_TRANSFERRED_NOTE = "L3_TRANSFERRED_NOTE"
    L4_AI_SPECULATION = "L4_AI_SPECULATION"

@dataclass
class FeedbackEvent:
    event_id: str
    timestamp: str
    reviewer: str
    evidence_level: EvidenceLevel
    topic_context: str
    raw_content: str
    extracted_intent: str
    derived_rule_id: Optional[str] = None

@dataclass
class BoundaryRule:
    rule_id: str
    source_event_ids: List[str]
    reviewer: str
    directive: str
    applicable_topics: List[str]
    applicable_objectives: List[str]
    prohibited_topics: List[str]
    counter_example_rationale: str
    
    def matches_task(self, topic: str, objective: str) -> bool:
        """Check if this rule should be active for the current task."""
        # 1. Prohibited check (Clash detection)
        for prohibited in self.prohibited_topics:
            if prohibited.lower() in topic.lower():
                return False
        # 2. Scope check
        for app_topic in self.applicable_topics:
            if app_topic.lower() in topic.lower():
                return True
        for app_obj in self.applicable_objectives:
            if app_obj.lower() in objective.lower():
                return True
        return False
