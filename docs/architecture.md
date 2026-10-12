# Architecture (V0.2)

BossAlign is a Python library with one shared core used by the SDK, CLI, demo, and benchmark.

```text
feedback -> provider proposal -> event + draft rule -> human confirmation
                                      |
task context -> SQLite rules -> exact scope + negative-boundary evaluation
                                      |
                          conflicts / reasons / uncertainty
                                      |
AI output -> configured exact-phrase checks + optional provider findings
```

## Components

- `schema.py`: public dataclasses and status enums. Rules retain submitter, preference owner, source attribution, generic interaction scope, exclusions, validity, confidence, timestamps, and version.
- `providers.py`: offline deterministic proposal provider and an OpenAI Chat Completions-compatible adapter. Provider output can propose fields, but cannot set a rule to confirmed.
- `parser.py`: validates a provider proposal and creates a feedback event plus a draft rule.
- `store.py`: standard-library SQLite tables for events, current rules, and immutable version snapshots.
- `boundary.py`: reviewer filtering, exact normalized scope matching, negative-boundary evaluation, conflict detection, and reason reporting.
- `sandbox.py`: configured exact-phrase checks and optional LLM review findings. Model findings are labelled as inference; neither kind of check means user approval.
- `sdk.py`: framework-independent entry point for ingest, confirmation, rule lifecycle, retrieval, and output checks.
- `cli.py`: a thin argument-parsing layer over the SDK.

## Rule lifecycle

1. `ingest()` stores the feedback event and a `draft` proposal. Sensitive feedback requires storage consent, is minimized by default, and requires separate consent before a remote provider can receive it.
2. A caller reviews the proposed directive, scope, exclusions, source, and confidence.
3. `confirm_rule()` records explicit confirmation and creates a new version. Third-party reports and AI-attributed feedback can only be confirmed by the preference owner. Proposals below confidence `0.60` cannot be confirmed without first being edited.
4. `retrieve()` applies only confirmed, sufficiently confident rules with matching scope and no matching or unresolved negative boundary.
5. Any material `update_rule()` change returns a confirmed rule to `draft` and clears its confirmation; it must be confirmed again. `revoke_rule()`/`deactivate_rule()` preserves history. `delete_rule()` removes the rule, source events, and version snapshots.

## Scope semantics

Supported fields are `project`, `task_type`, `topic`, `audience`, `objective`, `task_id`, `interaction_context`, and `tags`. `interaction_context` is an application-supplied generic field; values such as `workplace` or `personal_relationship` have no hard-coded behavior. Explicit preference owners are isolated by task owner. String values match after whitespace normalization and case-folding; there is no substring or vector similarity. A scope condition is conjunctive. Tag conditions match when any declared tag equals a task tag.

`valid_from` and `valid_until` apply time limits. Without `valid_until`, a confirmed rule is long-lived until updated, revoked, or deleted. Current structured overrides take precedence over conflicting stored rules.

Each object in `negative_boundaries` is a condition set: all fields in one object must match for that exclusion to fire; any matching object excludes the rule. If required task fields are missing, BossAlign returns uncertainty and does not apply the rule. Unstructured legacy `prohibited_topics` are not guessed at; they produce uncertainty until converted to structured conditions.

`communicative_intent` records a provider's structured speech-act label. When a provider sets `rule_candidate=false` for a non-rule act such as venting or advice-seeking, that event remains auditable but cannot be confirmed or applied as a persistent rule. The core stores the label; it does not claim to infer emotional intent in offline mode.

Structured `current_overrides` can use `conflict_key` and `effect`. Conflicting stored rules or a current override are reported, and conflicted rules are omitted from `effective_rules` instead of arbitrarily choosing a reviewer.

## Review semantics

The offline checker only scans exact phrases configured in a rule's `deterministic_checks`. A match includes the exact output excerpt and the directive as a suggestion. A lack of a match is reported as `no_deterministic_violations_found` only when the active rules are covered by such checks; otherwise it is `uncertain`.

An OpenAI-compatible provider may return findings with quoted evidence. BossAlign rejects findings that reference an unknown rule or provide evidence absent from the output. Accepted model findings are still probabilistic and require human judgment.

## Deliberate limits

- No vector database, cloud service, Redis, framework adapter, or generated-content platform is included.
- The offline parser is cue-based, not a general semantic parser.
- The benchmark is a small synthetic functional regression set, not broad empirical evidence.
- Fictional communication cases cover venting, advice requests, temporary requests for space, and boundary updates. The tests inject structured provider outcomes; they do not claim that the default offline parser can infer these intents.
- BossAlign does not diagnose, read minds, infer consent from old behavior, or generate persuasion scripts.
- MCP is deferred until the core APIs have more use and a client compatibility test plan exists.
