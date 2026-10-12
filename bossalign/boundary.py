from typing import List, Dict, Any, Tuple
from .schema import BoundaryRule

class BoundaryEngine:
    def __init__(self, rules: List[BoundaryRule] = None):
        self.rules = rules or []

    def add_rule(self, rule: BoundaryRule):
        self.rules.append(rule)

    def evaluate_task(self, topic: str, objective: str) -> Dict[str, Any]:
        """
        Evaluate which rules should be active and which are strictly prohibited
        to prevent over-fitting.
        """
        active_rules = []
        clashed_rules = []

        for rule in self.rules:
            # Check if this task clashes with negative boundaries
            is_prohibited = any(p.lower() in topic.lower() for p in rule.prohibited_topics)
            if is_prohibited:
                clashed_rules.append(rule)
                continue

            # Check if this task falls into applicable scope
            if rule.matches_task(topic, objective):
                active_rules.append(rule)

        return {
            "topic": topic,
            "objective": objective,
            "active_rules": active_rules,
            "clashed_rules": clashed_rules
        }
