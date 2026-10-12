# 01: Scope and Negative Boundaries

Feedback is not automatically a global preference. “Avoid dense technical details in consumer copy” must not silently become “remove details from every technical document.” BossAlign treats scope and exclusions as part of the rule and returns uncertainty when required context is missing.

## Structured scope

Rules can match `project`, `task_type`, `topic`, `audience`, `objective`, `task_id`, and `tags`. String values are whitespace-normalized and case-folded for exact equality; there is no substring or vector-similarity matching.

```json
{
  "applicable_scope": {
    "project": "sample-product",
    "audience": "consumer"
  },
  "negative_boundaries": [
    {"task_type": "technical_report"}
  ]
}
```

Every condition in `applicable_scope` must match. A rule is excluded when every field in any one `negative_boundaries` object matches. If a field needed to rule out a boundary is missing, the rule is not activated and selection is marked uncertain.

## Explainable outcomes

Selection distinguishes active, excluded, uncertain, and conflicting rules. Reports can show match reasons, exclusions, and conflicts. Legacy unstructured `prohibited_topics` are not fuzzy-matched; callers must convert them to structured conditions.

## Limits

Scope evaluation checks structured fields; it does not fully understand free-form task language. An application can use a Provider for semantic classification, but Provider output remains a proposal or model review suggestion.
