"""Command-line interface backed by the same SDK and engine as Python callers."""

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .providers import provider_from_env
from .sanitizer import sanitize_deliverable
from .schema import BoundaryRule, RuleStatus, TaskContext
from .sdk import BossAlign


def _rule_summary(rule: BoundaryRule):
    return {
        "rule_id": rule.rule_id,
        "reviewer": rule.reviewer,
        "preference_owner": rule.preference_owner,
        "attribution": rule.attribution,
        "directive": rule.directive,
        "scope": rule.applicable_scope,
        "negative_boundaries": rule.negative_boundaries,
        "communicative_intent": rule.communicative_intent,
        "valid_from": rule.valid_from,
        "valid_until": rule.valid_until,
        "sensitive": rule.sensitive,
        "confidence": rule.confidence,
        "origin": rule.origin,
        "status": rule.status.value,
        "version": rule.version,
    }


def _report_dict(report):
    return {
        "status": report.status,
        "user_approved": report.user_approved,
        "applicable_rules": [_rule_summary(rule) for rule in report.applicable_rules],
        "active_reasons": [asdict(item) for item in report.active_reasons],
        "violations": [asdict(item) for item in report.violations],
        "excluded_rules": [asdict(item) for item in report.excluded_rules],
        "uncertain_rules": [asdict(item) for item in report.uncertain_rules],
        "conflicts": [asdict(item) for item in report.conflicts],
        "notes": report.notes,
    }


def _parse_json_object(value: str, name: str):
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("%s must be valid JSON: %s" % (name, error.msg)) from None
    if not isinstance(result, dict):
        raise ValueError("%s must be a JSON object" % name)
    return result


def _parse_json_array(value: str, name: str):
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("%s must be valid JSON: %s" % (name, error.msg)) from None
    if not isinstance(result, list):
        raise ValueError("%s must be a JSON array" % name)
    return result


def _context(value: str) -> TaskContext:
    return TaskContext.from_mapping(_parse_json_object(value, "task context"))


def _new_client(database: str, use_provider: bool = False) -> BossAlign:
    return BossAlign(database, provider=provider_from_env() if use_provider else None)


def _cmd_ingest(args) -> int:
    context = _parse_json_object(args.context_json, "context")
    with _new_client(args.db, use_provider=True) as client:
        try:
            rule = client.ingest(
                args.raw,
                reviewer=args.reviewer,
                context=context,
                confirm=args.confirm,
                source=args.source,
                preference_owner=args.preference_owner,
                attribution=args.attribution,
                valid_from=args.valid_from,
                valid_until=args.valid_until,
                sensitive=args.sensitive,
                consent_to_store_sensitive=args.consent_to_store_sensitive,
                allow_external_processing=args.allow_external_processing,
                retain_source_text=args.retain_source_text,
                confirmed_by=args.confirmed_by,
            )
        except ValueError as error:
            print("bossalign: %s" % error, file=sys.stderr)
            return 2
        print(json.dumps(_rule_summary(rule), ensure_ascii=False, indent=2))
        if rule.status == RuleStatus.DRAFT:
            if not rule.rule_candidate:
                print("Stored as a non-rule feedback event. It cannot be confirmed or applied as a persistent rule.")
            else:
                print("Stored as draft. It will not be applied until reviewed and confirmed.")
            if not rule.applicable_scope:
                print("No structured scope was supplied; retrieval will remain uncertain.")
        return 0


def _cmd_rules(args) -> int:
    with _new_client(args.db) as client:
        if args.action == "delete":
            if not args.rule_id:
                print("rules delete requires --rule-id", file=sys.stderr)
                return 2
            if not client.delete_rule(args.rule_id):
                print("bossalign: Unknown rule: %s" % args.rule_id, file=sys.stderr)
                return 2
            print(json.dumps({"rule_id": args.rule_id, "deleted": True}, ensure_ascii=False))
            return 0
        if args.action in ("confirm", "deactivate", "revoke"):
            if not args.rule_id:
                print("rules %s requires --rule-id" % args.action, file=sys.stderr)
                return 2
            try:
                rule = (
                    client.confirm_rule(args.rule_id, confirmed_by=args.confirmed_by)
                    if args.action == "confirm"
                    else client.revoke_rule(args.rule_id)
                )
            except (KeyError, ValueError) as error:
                print("bossalign: %s" % error, file=sys.stderr)
                return 2
            print(json.dumps(_rule_summary(rule), ensure_ascii=False, indent=2))
            return 0
        if args.action == "update":
            if not args.rule_id:
                print("rules update requires --rule-id", file=sys.stderr)
                return 2
            changes = {}
            if args.directive is not None:
                changes["directive"] = args.directive
            if args.scope_json is not None:
                changes["applicable_scope"] = _parse_json_object(args.scope_json, "scope")
            if args.negative_boundaries_json is not None:
                changes["negative_boundaries"] = _parse_json_array(args.negative_boundaries_json, "negative boundaries")
            if args.deterministic_checks_json is not None:
                changes["deterministic_checks"] = _parse_json_array(args.deterministic_checks_json, "deterministic checks")
            if args.confidence is not None:
                changes["confidence"] = args.confidence
            if args.conflict_key is not None:
                changes["conflict_key"] = args.conflict_key
            if args.effect is not None:
                changes["effect"] = args.effect
            if args.preference_owner is not None:
                changes["preference_owner"] = args.preference_owner
            if args.valid_from is not None:
                changes["valid_from"] = args.valid_from
            if args.valid_until is not None:
                changes["valid_until"] = args.valid_until
            if args.attribution is not None:
                changes["attribution"] = args.attribution
            if not changes:
                print("rules update requires at least one field to change", file=sys.stderr)
                return 2
            try:
                rule = client.update_rule(args.rule_id, **changes)
            except (KeyError, ValueError) as error:
                print("bossalign: %s" % error, file=sys.stderr)
                return 2
            print(json.dumps(_rule_summary(rule), ensure_ascii=False, indent=2))
            return 0
        rules = client.rules(
            reviewer=args.reviewer,
            project=args.project,
            preference_owner=args.preference_owner,
            include_inactive=args.all,
        )
        print(json.dumps([_rule_summary(rule) for rule in rules], ensure_ascii=False, indent=2))
    return 0


def _cmd_check(args) -> int:
    context = _context(args.task_context)
    content = Path(args.file).read_text(encoding="utf-8")
    with _new_client(args.db, use_provider=True) as client:
        report = client.check(context, content, reviewer=args.reviewer)
    print(json.dumps(_report_dict(report), ensure_ascii=False, indent=2))
    if report.status in ("violations_found", "review_required"):
        return 1
    if report.status == "uncertain":
        return 2
    return 0


def _cmd_sanitize(args) -> int:
    content = Path(args.file).read_text(encoding="utf-8")
    cleaned = sanitize_deliverable(content)
    Path(args.out).write_text(cleaned, encoding="utf-8")
    print("Sanitized output written to %s" % args.out)
    return 0


def _cmd_demo(_args) -> int:
    """Run a real local SDK flow on temporary synthetic data."""
    with tempfile.TemporaryDirectory(prefix="bossalign-demo-") as directory:
        database = str(Path(directory) / "demo.sqlite3")
        with BossAlign(database) as client:
            rule = client.ingest(
                "Avoid the phrase 'guaranteed zero downtime' in consumer copy.",
                reviewer="synthetic-reviewer",
                context={
                    "project": "demo-app",
                    "task_type": "consumer_copy",
                    "audience": "consumer",
                    "applicable_scope": {"project": "demo-app", "audience": "consumer"},
                    "negative_boundaries": [{"task_type": "technical_report"}],
                    "deterministic_checks": ["guaranteed zero downtime"],
                },
                confirm=True,
                source="synthetic_demo",
            )
            consumer = client.check(
                TaskContext(project="demo-app", task_type="consumer_copy", audience="consumer"),
                "This consumer copy says 'guaranteed zero downtime' without test evidence.",
                reviewer="synthetic-reviewer",
            )
            technical = client.check(
                TaskContext(project="demo-app", task_type="technical_report", audience="technical"),
                "The technical report includes 'guaranteed zero downtime' as a test phrase.",
                reviewer="synthetic-reviewer",
            )

    print("Synthetic local demo; no external model call and no real user approval.")
    print("Rule: %s (%s, v%d)" % (rule.rule_id, rule.status.value, rule.version))
    print("Consumer task status: %s" % consumer.status)
    print("Technical report status: %s" % technical.status)
    print("Consumer-task evidence: %s" % json.dumps([item.evidence for item in consumer.violations], ensure_ascii=False))
    print("Technical task applicable rules: %d" % len(technical.applicable_rules))
    print("user_approved: false")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bossalign",
        description="Human feedback alignment for AI agents: scoped rules, persistent evidence, and explainable checks.",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("BOSSALIGN_DB", str(Path.home() / ".bossalign" / "memory.sqlite3")),
        help="SQLite database path (default: BOSSALIGN_DB or ~/.bossalign/memory.sqlite3)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Parse and persist a feedback proposal")
    ingest.add_argument("--reviewer", default="default")
    ingest.add_argument("--raw", required=True, help="Verbatim feedback text")
    ingest.add_argument("--context-json", default="{}", help="Structured source context and proposed scope")
    ingest.add_argument("--source", default="user_feedback")
    ingest.add_argument("--attribution", choices=("direct", "third_party", "ai_inference"), default="direct")
    ingest.add_argument("--preference-owner", help="Identity of the person whose preference this rule concerns")
    ingest.add_argument("--valid-from", help="ISO-8601 start time for a temporary rule")
    ingest.add_argument("--valid-until", help="ISO-8601 expiry time for a temporary rule")
    ingest.add_argument("--sensitive", action="store_true", help="Apply local-first storage consent checks")
    ingest.add_argument("--consent-to-store-sensitive", action="store_true", help="Explicitly allow storing a minimized sensitive rule")
    ingest.add_argument("--allow-external-processing", action="store_true", help="Explicitly allow a configured remote provider to receive sensitive feedback")
    ingest.add_argument("--retain-source-text", action="store_true", default=None, help="Retain source text; sensitive input is minimized by default")
    ingest.add_argument("--confirm", action="store_true", help="Confirm the rule after parsing and confidence checks")
    ingest.add_argument("--confirmed-by", help="Identity of the human confirming the proposed rule")
    ingest.set_defaults(func=_cmd_ingest)

    rules = commands.add_parser("rules", help="List, update, confirm, or deactivate rules")
    rules.add_argument("action", nargs="?", choices=("list", "update", "confirm", "deactivate", "revoke", "delete"), default="list")
    rules.add_argument("--rule-id", help="Existing rule ID for update/confirm/deactivate")
    rules.add_argument("--confirmed-by", help="Identity of the human confirming the proposed rule")
    rules.add_argument("--reviewer")
    rules.add_argument("--project")
    rules.add_argument("--preference-owner")
    rules.add_argument("--all", action="store_true", help="Include inactive rules")
    rules.add_argument("--directive")
    rules.add_argument("--scope-json")
    rules.add_argument("--negative-boundaries-json")
    rules.add_argument("--deterministic-checks-json")
    rules.add_argument("--confidence", type=float)
    rules.add_argument("--conflict-key")
    rules.add_argument("--effect")
    rules.add_argument("--valid-from")
    rules.add_argument("--valid-until")
    rules.add_argument("--attribution", choices=("direct", "third_party", "ai_inference"))
    rules.set_defaults(func=_cmd_rules)

    check = commands.add_parser("check", help="Retrieve applicable rules and check a generated output")
    check.add_argument("--file", required=True, help="Text file containing the output to review")
    check.add_argument(
        "--task-context",
        default="{}",
        help="JSON task context: project, audience, task_type, objective, interaction_context, preference_owner, as_of, tags, current_overrides",
    )
    check.add_argument("--reviewer", help="Limit rule selection to this reviewer; omit to detect cross-reviewer conflicts")
    check.set_defaults(func=_cmd_check)

    demo = commands.add_parser("demo", help="Run a local synthetic feedback, retrieval, and review flow")
    demo.set_defaults(func=_cmd_demo)

    sanitize = commands.add_parser("sanitize", help="Remove BossAlign tags from a deliverable")
    sanitize.add_argument("--file", required=True)
    sanitize.add_argument("--out", required=True)
    sanitize.set_defaults(func=_cmd_sanitize)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print("bossalign: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
