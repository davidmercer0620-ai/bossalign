"""Rule-driven output checks with an explicit, non-approval status model."""

import re
from typing import Any, Dict, List, Optional

from .schema import AuditFinding, CheckReport, RuleSelection, TaskContext


class RuleChecker:
    def review(
        self,
        selection: RuleSelection,
        text: str,
        provider=None,
    ) -> CheckReport:
        findings: List[AuditFinding] = []
        notes = ["System review is not user approval."]
        deterministic_coverage = 0
        uncovered_rules = []

        for rule in selection.effective_rules:
            checks = [item for item in rule.deterministic_checks if item.strip()]
            if not checks:
                uncovered_rules.append(rule.rule_id)
                continue
            deterministic_coverage += 1
            for phrase in checks:
                match = re.search(re.escape(phrase), text, flags=re.IGNORECASE)
                if match:
                    findings.append(
                        AuditFinding(
                            rule_id=rule.rule_id,
                            severity="medium",
                            evidence=text[match.start() : match.end()],
                            suggestion=rule.directive,
                            check_type="deterministic_exact_phrase",
                            confidence=1.0,
                        )
                    )

        semantic_findings = []
        semantic_review_used = bool(provider and getattr(provider, "semantic_review_enabled", False))
        if semantic_review_used and selection.effective_rules:
            candidate_findings = provider.review_output(
                selection.task.to_dict(),
                text,
                [rule.to_dict() for rule in selection.effective_rules],
            )
            known_rules = {rule.rule_id for rule in selection.effective_rules}
            for candidate in candidate_findings:
                if not isinstance(candidate, dict):
                    continue
                rule_id = str(candidate.get("rule_id", ""))
                evidence = str(candidate.get("evidence", ""))
                if rule_id not in known_rules or not evidence or evidence.casefold() not in text.casefold():
                    continue
                severity = str(candidate.get("severity", "medium")).lower()
                if severity not in {"low", "medium", "high"}:
                    severity = "medium"
                confidence = candidate.get("confidence")
                try:
                    confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else None
                except (TypeError, ValueError):
                    confidence = None
                semantic_findings.append(
                    AuditFinding(
                        rule_id=rule_id,
                        severity=severity,
                        evidence=evidence,
                        suggestion=str(candidate.get("suggestion", "Review this passage against the stored rule.")),
                        check_type="llm_inference",
                        confidence=confidence,
                    )
                )
            findings.extend(semantic_findings)
            notes.append("LLM findings are probabilistic review suggestions and require human judgment.")

        if findings and any(finding.check_type == "deterministic_exact_phrase" for finding in findings):
            status = "violations_found"
        elif semantic_findings:
            status = "review_required"
        elif selection.conflicts or selection.uncertain_rules:
            status = "uncertain"
        elif not selection.active_rules:
            status = "no_applicable_rules"
        elif semantic_review_used:
            status = "llm_review_no_findings"
            notes.append("The configured provider reported no supported findings; this is not a guarantee of compliance.")
        elif uncovered_rules:
            status = "uncertain"
        elif deterministic_coverage == len(selection.effective_rules):
            status = "no_deterministic_violations_found"
            notes.append("Only the configured exact-phrase checks ran; no general semantic guarantee is made.")
        else:
            status = "uncertain"

        if uncovered_rules:
            notes.append("No deterministic check is configured for rule(s): %s." % ", ".join(uncovered_rules))
        if selection.conflicts:
            notes.append("Conflicted rules were not enforced automatically.")
        if selection.uncertain_rules:
            notes.append("Some stored rules could not be evaluated with the supplied context or confidence.")

        return CheckReport(
            task=selection.task,
            status=status,
            applicable_rules=selection.active_rules,
            active_reasons=selection.active_reasons,
            violations=findings,
            excluded_rules=selection.excluded_rules,
            uncertain_rules=selection.uncertain_rules,
            conflicts=selection.conflicts,
            notes=notes,
            user_approved=False,
        )


class ShadowBossSandbox:
    """Compatibility facade; without scoped rules it returns an uncertain report."""

    def __init__(self, reviewer: str = "default"):
        self.reviewer = reviewer

    def review_draft(self, text: str, rules=None, task: Optional[TaskContext] = None) -> Dict[str, Any]:
        from .boundary import BoundaryEngine

        selection = BoundaryEngine(rules or []).evaluate_task(task or TaskContext(), reviewer=self.reviewer)
        report = RuleChecker().review(selection, text)
        return {
            "status": report.status,
            "passed": False,
            "total_issues": len(report.violations),
            "issues": [
                {"rule_id": item.rule_id, "severity": item.severity.upper(), "detail": item.evidence, "suggestion": item.suggestion}
                for item in report.violations
            ],
            "user_approved": False,
            "notes": report.notes,
        }
