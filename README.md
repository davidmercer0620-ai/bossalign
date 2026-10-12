# BossAlign

> **The Feedback Alignment Layer for AI Agents.**
> Turn human feedback into persistent, scoped rules. Stop agents from repeating the same mistakes.

[![CI](https://github.com/davidmercer0620-ai/bossalign/actions/workflows/ci.yml/badge.svg?branch=dev%2Fv0.2)](https://github.com/davidmercer0620-ai/bossalign/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

BossAlign (蛔虫引擎) is a small, framework-independent layer between agent memory and agent behavior. It stores corrections as **proposed rules with evidence, scope, and exclusions**, then retrieves and checks only the rules that fit a new task.

Unlike a chat-history memory, BossAlign is designed to remember what should be repeated, where it applies, and where it must not be generalized. A system check is never presented as user approval.

| Ordinary conversation memory | BossAlign |
| --- | --- |
| Saves statements or summaries | Converts feedback into a rule proposal with its source |
| Often retrieves by broad similarity | Matches declared project, task, audience, objective, and task ID fields |
| Can spread a local correction to unrelated tasks | Stores explicit negative boundaries and returns uncertainty when context is missing |
| Usually has no rule lifecycle | Keeps draft, confirmed, and inactive states plus version history |
| May say an output “passes” | Reports deterministic evidence and coverage; never claims human approval |

## Quickstart

Python 3.9+; the core package has no runtime dependencies. From a clone:

```bash
git clone https://github.com/davidmercer0620-ai/bossalign.git
cd bossalign
python -m pip install -e .
```

Try the local synthetic demo. It uses the real SDK and a temporary SQLite database; it makes no model call and does not simulate a person's approval.

```bash
bossalign demo
```

### Python SDK

```python
from bossalign import BossAlign, TaskContext

with BossAlign("bossalign.sqlite3") as align:
    proposal = align.ingest(
        "For consumer onboarding copy, avoid 'guaranteed zero downtime'. "
        "Do not apply this to technical incident reports.",
        reviewer="reviewer-1",
        context={
            "applicable_scope": {
                "project": "sample-app",
                "task_type": "consumer_copy",
                "audience": "consumer",
            },
            "negative_boundaries": [{"task_type": "technical_incident_report"}],
            "deterministic_checks": ["guaranteed zero downtime"],
            "conflict_key": "downtime_claim",
            "effect": "avoid",
        },
    )
    print(proposal.status)  # draft: stored, but not active

    rule = align.confirm_rule(proposal.rule_id)  # explicit confirmation step
    task = TaskContext(
        project="sample-app",
        task_type="consumer_copy",
        audience="consumer",
    )
    selection = align.retrieve(task, reviewer="reviewer-1")
    report = align.check(task, "This copy promises guaranteed zero downtime.", reviewer="reviewer-1")

    print([item.rule_id for item in selection.active_rules])
    print(report.status)  # violations_found
    print(report.violations[0].evidence)  # exact matched phrase
    print(report.user_approved)  # False
```

Feedback events, rule records, and version snapshots are stored in SQLite. A new `BossAlign("bossalign.sqlite3")` instance can retrieve the same confirmed rules after restart. `update_rule()` creates another version; `deactivate_rule()` preserves history and stops retrieval.

### Before / after: keeping a correction in its lane

History: “For consumer onboarding copy, avoid ‘guaranteed zero downtime’. Do not apply this to technical incident reports.”

| New task | Ordinary broad memory | BossAlign result |
| --- | --- | --- |
| Consumer onboarding copy in `sample-app` | May repeat the phrase, or retrieve a vague “avoid claims” memory | Applies the confirmed rule; exact configured phrase checks can flag the phrase |
| Technical incident report in `sample-app` | May incorrectly remove a useful incident detail | Excludes the rule because `task_type` matches a negative boundary |
| Task with no audience or project context | May apply based on vague similarity | Returns uncertainty; it does not force the rule onto the task |

The offline provider does **not** understand arbitrary semantics. It recognizes a small set of instruction/preference cues and checks only exact phrases explicitly configured for deterministic checking. For broader language interpretation, configure an OpenAI-compatible provider; its findings remain model inferences and still require human review.

## CLI

The database path is selected with `--db` before the command, or with `BOSSALIGN_DB`.

```bash
# Store a proposal. Supply structured scope; otherwise it will not be activated.
bossalign --db ./memory.sqlite3 ingest \
  --reviewer reviewer-1 \
  --raw "Avoid 'guaranteed zero downtime' in consumer copy." \
  --context-json '{"applicable_scope":{"project":"sample-app","audience":"consumer"},"negative_boundaries":[{"task_type":"technical_incident_report"}],"deterministic_checks":["guaranteed zero downtime"]}'

# Confirm only after reviewing the stored proposal
bossalign --db ./memory.sqlite3 rules confirm --rule-id RULE_ID

bossalign --db ./memory.sqlite3 rules --reviewer reviewer-1
bossalign --db ./memory.sqlite3 rules update --rule-id RULE_ID --directive "Keep the measurement context"
bossalign --db ./memory.sqlite3 rules deactivate --rule-id RULE_ID
bossalign --db ./memory.sqlite3 check --file draft.md \
  --task-context '{"project":"sample-app","task_type":"consumer_copy","audience":"consumer"}' \
  --reviewer reviewer-1
bossalign --db ./memory.sqlite3 sanitize --file draft.md --out clean.md
```

Commands: `ingest`, `rules`, `check`, `demo`, and `sanitize`. There is no `generate` command in V0.2. Check exit codes are `0` for no reported issue/no applicable rule, `1` for a reported violation or model finding requiring review, and `2` when evaluation is uncertain or cannot run.

## LLM provider

The SDK accepts a provider object. The included adapter uses the OpenAI Chat Completions-compatible request shape and Python's standard library; no vendor SDK is required.

```python
import os
from bossalign import BossAlign
from bossalign.providers import OpenAICompatibleProvider

provider = OpenAICompatibleProvider(
    base_url=os.environ.get("BOSSALIGN_BASE_URL", "https://api.openai.com/v1"),
    model=os.environ["BOSSALIGN_MODEL"],
    api_key=os.environ["BOSSALIGN_API_KEY"],
)
align = BossAlign("memory.sqlite3", provider=provider)
```

The adapter returns a proposal; the SDK still stores it as `draft`. The provider can also return review findings, which are labelled `llm_inference`, include output evidence, and require human judgment. No real provider call is made unless an application explicitly configures and invokes one.

For CLI parsing/review, set `BOSSALIGN_PROVIDER=openai`, `BOSSALIGN_API_KEY`, and `BOSSALIGN_MODEL`; set `BOSSALIGN_BASE_URL` for a compatible endpoint. Listing rules, sanitizing, and the synthetic demo do not need provider credentials.

## Benchmark

Run the public synthetic regression set locally:

```bash
python benchmarks/run.py
```

It contains 4 fictional cases (software development, content writing, product design, and data analysis): 4 feedback events, 8 scope decisions, and 12 output checks. The script reports extraction accuracy, scope accuracy, error-generalization rate, and violation precision/recall with sample counts. It makes zero model calls. This small fixture checks expected code paths; it is not a representative language benchmark or a model comparison.

## Architecture

```text
Feedback -> provider proposal -> SQLite event + draft rule
                                   |
                         human confirmation
                                   |
Task context -> exact scope + negative-boundary evaluation
                                   |
                   conflict/uncertainty report
                                   |
Output -> configured phrase checks + optional LLM findings
```

The SDK, CLI, and demo share the same parser, store, boundary engine, and checker. SQLite is the only runtime storage. The existing clean-room helper remains a small tag sanitizer; it is not a general privacy scanner or export pipeline.

## Current limits

- Offline parsing is heuristic and English/Chinese cue-based, not general semantic extraction.
- Scope matching uses normalized exact values, not embeddings or fuzzy matching.
- Unstructured negative boundaries are treated as uncertain; supply condition objects such as `{"audience":"technical"}`.
- Deterministic output checks look for configured exact phrases. They do not prove semantic compliance.
- LLM provider compatibility is defined by the OpenAI Chat Completions request shape; no third-party client has been integration-tested here.
- MCP is deferred until the V0.2 SDK and core behavior have broader validation. No MCP client compatibility is claimed.
- The benchmark is a small fictional regression set, not evidence of production reliability or broad accuracy.

## FAQ

**Does BossAlign call a model by default?** No. The default provider is deterministic and offline. Set up a provider explicitly for model-assisted parsing or review.

**Does a `no_deterministic_violations_found` result mean the draft is approved?** No. It means only that the configured exact-phrase checks did not find a match. `user_approved` remains `false`.

**Can it generate or rewrite content?** V0.2 does not generate drafts. Use your existing agent to write content, then pass that output and its task context to `check()`.

**Where is memory stored?** In the SQLite file passed to `BossAlign`, or by default at `~/.bossalign/memory.sqlite3`. Storage is local. If you explicitly configure and invoke an external Provider, the input to that provider call is sent to that service.

**What happens when context is missing?** BossAlign returns uncertainty and does not force a scoped rule onto the task.

**Does it include MCP support?** No. MCP is deferred; no MCP client compatibility is claimed.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check bossalign tests benchmarks
python -m bossalign demo
python benchmarks/run.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [Architecture](docs/architecture.md), and the [Chinese README](README_CN.md). Licensed under MIT; see [LICENSE](LICENSE).
