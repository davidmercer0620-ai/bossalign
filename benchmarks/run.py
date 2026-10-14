"""Run the small synthetic functional benchmark; no model calls are made."""

import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bossalign import BossAlign  # noqa: E402
from bossalign.schema import TaskContext  # noqa: E402


CASES = Path(__file__).with_name("cases.json")


def _rate(correct, total):
    return round(correct / total, 4) if total else None


def run_benchmark():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    extraction_correct = 0
    scope_correct = 0
    negative_cases = 0
    false_activations = 0
    true_positive = false_positive = false_negative = true_negative = 0

    with tempfile.TemporaryDirectory(prefix="bossalign-benchmark-") as directory:
        for index, case in enumerate(cases):
            database = Path(directory) / ("case-%d.sqlite3" % index)
            with BossAlign(database) as client:
                rule = client.ingest(
                    case["feedback"],
                    reviewer=case["reviewer"],
                    context={
                        "applicable_scope": case["scope"],
                        "negative_boundaries": case["negative_boundaries"],
                        "deterministic_checks": case["deterministic_checks"],
                        "conflict_key": case["conflict_key"],
                        "effect": case["effect"],
                    },
                    confirm=True,
                    source="synthetic_benchmark",
                )
                extracted = (
                    rule.origin == case["expected_origin"]
                    and rule.directive == case["feedback"]
                    and rule.applicable_scope == case["scope"]
                    and rule.negative_boundaries == case["negative_boundaries"]
                    and rule.deterministic_checks == case["deterministic_checks"]
                )
                extraction_correct += int(extracted)

                target = client.retrieve(TaskContext.from_mapping(case["applicable_task"]))
                excluded = client.retrieve(TaskContext.from_mapping(case["excluded_task"]))
                target_ok = any(item.rule_id == rule.rule_id for item in target.active_rules)
                excluded_ok = not any(item.rule_id == rule.rule_id for item in excluded.active_rules)
                scope_correct += int(target_ok) + int(excluded_ok)
                negative_cases += 1
                false_activations += int(not excluded_ok)

                reports = [
                    (case["applicable_task"], case["violation_output"], True),
                    (case["applicable_task"], case["compliant_output"], False),
                    (case["excluded_task"], case["excluded_output"], False),
                ]
                for task_data, output, expected_violation in reports:
                    report = client.check(TaskContext.from_mapping(task_data), output, reviewer=case["reviewer"])
                    predicted = report.status == "violations_found"
                    if predicted and expected_violation:
                        true_positive += 1
                    elif predicted:
                        false_positive += 1
                    elif expected_violation:
                        false_negative += 1
                    else:
                        true_negative += 1

    extraction_total = len(cases)
    scope_total = len(cases) * 2
    outputs_total = len(cases) * 3
    return {
        "dataset": "synthetic functional regression cases",
        "model_calls": 0,
        "sample_counts": {
            "feedback_events": extraction_total,
            "scope_decisions": scope_total,
            "output_checks": outputs_total,
            "negative_scope_cases": negative_cases,
        },
        "rule_extraction_accuracy": {
            "correct": extraction_correct,
            "total": extraction_total,
            "rate": _rate(extraction_correct, extraction_total),
        },
        "scope_accuracy": {
            "correct": scope_correct,
            "total": scope_total,
            "rate": _rate(scope_correct, scope_total),
        },
        "error_generalization_rate": {
            "false_activations": false_activations,
            "negative_cases": negative_cases,
            "rate": _rate(false_activations, negative_cases),
        },
        "violation_detection": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
            "precision": _rate(true_positive, true_positive + false_positive),
            "recall": _rate(true_positive, true_positive + false_negative),
            "accuracy": _rate(true_positive + true_negative, outputs_total),
        },
        "interpretation": "Small synthetic regression set only; not representative of general language or model performance.",
    }


def main():
    print(json.dumps(run_benchmark(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
