import re
import datetime
from typing import Dict, Any, Tuple
from .schema import FeedbackEvent, BoundaryRule, EvidenceLevel

# Common filler noises and emotional outbursts in boss feedback
EMOTIONAL_NOISE_PATTERNS = [
    r"这写的什么狗屁[？！!]*",
    r"太假了[？！!]*",
    r"懂不懂啊[？！!]*",
    r"重新改[？！!]*",
    r"说了多少遍[？！!]*",
    r"全是废话[？！!]*",
    r"what on earth is this[?!]*",
    r"redo it[?!]*"
]

def denoise_feedback(raw_text: str) -> str:
    """Strip away emotional outbursts and keep substantive guidance."""
    cleaned = raw_text
    for pattern in EMOTIONAL_NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def parse_feedback_event(
    reviewer: str,
    raw_text: str,
    topic_context: str,
    evidence_level: EvidenceLevel = EvidenceLevel.L1_DIRECT_QUOTE
) -> Tuple[FeedbackEvent, BoundaryRule]:
    """
    Parse a raw stakeholder feedback into a structured FeedbackEvent
    and automatically hypothesize its BoundaryRule with negative boundary.
    """
    event_id = f"EVT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    rule_id = f"RULE-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    cleaned_intent = denoise_feedback(raw_text)
    
    event = FeedbackEvent(
        event_id=event_id,
        timestamp=datetime.datetime.now().isoformat(),
        reviewer=reviewer,
        evidence_level=evidence_level,
        topic_context=topic_context,
        raw_content=raw_text,
        extracted_intent=cleaned_intent,
        derived_rule_id=rule_id
    )
    
    # Generate boundary rule
    rule = BoundaryRule(
        rule_id=rule_id,
        source_event_ids=[event_id],
        reviewer=reviewer,
        directive=cleaned_intent,
        applicable_topics=[topic_context],
        applicable_objectives=["根据上下文目的匹配"],
        prohibited_topics=["全局泛化", "对立题材篇目"],
        counter_example_rationale="严禁一刀切！在强调工业硬实力或底层验证的篇目中保留实质细节。"
    )
    
    return event, rule
