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

- `schema.py`: public dataclasses and status enums. Rules retain source, reviewer, scope, exclusions, confidence, timestamps, and version.
- `providers.py`: offline deterministic proposal provider and an OpenAI Chat Completions-compatible adapter. Provider output can propose fields, but cannot set a rule to confirmed.
- `parser.py`: validates a provider proposal and creates a feedback event plus a draft rule.
- `store.py`: standard-library SQLite tables for events, current rules, and immutable version snapshots.
- `boundary.py`: reviewer filtering, exact normalized scope matching, negative-boundary evaluation, conflict detection, and reason reporting.
- `sandbox.py`: configured exact-phrase checks and optional LLM review findings. Model findings are labelled as inference; neither kind of check means user approval.
- `sdk.py`: framework-independent entry point for ingest, confirmation, rule lifecycle, retrieval, and output checks.
- `cli.py`: a thin argument-parsing layer over the SDK.

## Rule lifecycle

1. `ingest()` stores the verbatim feedback event and a `draft` proposal.
2. A caller reviews the proposed directive, scope, exclusions, source, and confidence.
3. `confirm_rule()` records explicit confirmation and creates a new version. Proposals below confidence `0.60` cannot be confirmed without first being edited.
4. `retrieve()` applies only confirmed, sufficiently confident rules with matching scope and no matching or unresolved negative boundary.
5. `update_rule()` and `deactivate_rule()` create version snapshots; neither deletes the original feedback event.

## Scope semantics

Supported fields are `project`, `task_type`, `topic`, `audience`, `objective`, `task_id`, and `tags`. String values match after whitespace normalization and case-folding; there is no substring or vector similarity. A scope condition is conjunctive. Tag conditions match when any declared tag equals a task tag.

Each object in `negative_boundaries` is a condition set: all fields in one object must match for that exclusion to fire; any matching object excludes the rule. If required task fields are missing, BossAlign returns uncertainty and does not apply the rule. Unstructured legacy `prohibited_topics` are not guessed at; they produce uncertainty until converted to structured conditions.

Structured `current_overrides` can use `conflict_key` and `effect`. Conflicting stored rules or a current override are reported, and conflicted rules are omitted from `effective_rules` instead of arbitrarily choosing a reviewer.

## Review semantics

The offline checker only scans exact phrases configured in a rule's `deterministic_checks`. A match includes the exact output excerpt and the directive as a suggestion. A lack of a match is reported as `no_deterministic_violations_found` only when the active rules are covered by such checks; otherwise it is `uncertain`.

An OpenAI-compatible provider may return findings with quoted evidence. BossAlign rejects findings that reference an unknown rule or provide evidence absent from the output. Accepted model findings are still probabilistic and require human judgment.

## Deliberate limits

- No vector database, cloud service, Redis, framework adapter, or generated-content platform is included.
- The offline parser is cue-based, not a general semantic parser.
- The benchmark is a small synthetic functional regression set, not broad empirical evidence.
- MCP is deferred until the core APIs have more use and a client compatibility test plan exists.
