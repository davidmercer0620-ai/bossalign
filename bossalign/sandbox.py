import re
from typing import List, Dict, Any

# Common banned buzzwords that executives hate
SUPERFICIAL_BUZZWORDS = [
    "匠心智造", "领军品牌", "无可比拟", "遥遥领先", "完美无瑕",
    "颠覆性创新", "行业天花板", "业界首创", "永不磨损", "绝对零延迟"
]

class ShadowBossSandbox:
    def __init__(self, reviewer: str = "Boss_Victor"):
        self.reviewer = reviewer

    def review_draft(self, text: str) -> Dict[str, Any]:
        """
        Simulate the executive's critical eye before submitting.
        """
        issues = []
        
        # Check 1: Superlatives & Empty Buzzwords
        for word in SUPERFICIAL_BUZZWORDS:
            if word in text:
                issues.append({
                    "type": "EMPTY_BUZZWORD",
                    "severity": "HIGH",
                    "detail": f"检测到领导禁忌的假大空词汇: '{word}'。建议替换为实测数据或具体操作细节。"
                })

        # Check 2: Unverified Full Assertions (绝对化断言)
        absolute_claims = ["百分之百", "彻底杜绝", "毫无破绽", "秒杀同行"]
        for claim in absolute_claims:
            if claim in text:
                issues.append({
                    "type": "UNVERIFIED_CLAIM",
                    "severity": "MEDIUM",
                    "detail": f"检测到绝对化断言: '{claim}'。领导强调不说满话，需说明测试环境与前置条件。"
                })

        # Check 3: Pacing & Word Length Check (镜头连读估算)
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        long_lines = [l for l in lines if len(l) > 60]
        if long_lines:
            issues.append({
                "type": "PACING_OVERLOAD",
                "severity": "LOW",
                "detail": f"发现 {len(long_lines)} 处单句超过60字，可能导致口播过密或无法留出呼吸停顿。"
            })

        passed = len([i for i in issues if i["severity"] == "HIGH"]) == 0
        return {
            "reviewer": self.reviewer,
            "passed": passed,
            "total_issues": len(issues),
            "issues": issues
        }
