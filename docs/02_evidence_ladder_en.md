# 02: Evidence, Rule States, and Confirmation

BossAlign stores the original feedback event and records whether a rule came from an explicit user instruction, a user preference, AI inference, or an unverified hypothesis. Every parsed result starts as `draft`; a Provider cannot activate it by returning high confidence.

| State | Meaning | Retrieved for tasks? |
| --- | --- | --- |
| `draft` | Parsed proposal awaiting review | No |
| `confirmed` | Explicitly confirmed rule | Only when confidence and scope also match |
| `inactive` | Disabled while history is retained | No |

Confirmation checks a default confidence threshold of `0.60` and records the confirmer in a new rule version. A low-confidence proposal should be corrected with `update_rule()` before confirmation. `update_rule()` and `deactivate_rule()` append snapshots; the original feedback event remains available.

## Evidence fields

Events preserve original text, source, reviewer, timestamp, and extracted intent. Rules reference event IDs and retain the source feedback, scope, negative boundaries, confidence, status, and version. Source provenance is separate from interpretation: a model can propose an interpretation but cannot stand in for user confirmation.

## Review states

Deterministic checks scan only exact phrases explicitly configured on a rule. Model findings are marked `llm_inference`. In either mode, `user_approved` remains `false`. A system check with no findings does not mean a human reviewer approved the output.
