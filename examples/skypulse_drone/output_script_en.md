# Synthetic Scope-Check Example

> The scenario, organization, roles, and feedback below are fictional. This is a scope fixture, not a human-approved deliverable or a real drone performance test.

## Historical feedback and rule

- Feedback: Do not use “guaranteed zero downtime” in consumer onboarding copy. The rule does not apply to technical incident reports.
- Applicable scope: `project=sample-app`, `audience=consumer`
- Negative boundary: `task_type=technical_incident_report`
- Deterministic check: exact phrase `guaranteed zero downtime`

## New task A: consumer onboarding copy

Output: `This copy promises guaranteed zero downtime.`

Expected system result: the rule applies, the exact configured phrase is found, and the status is `violations_found`. This means the system found a configured issue; it does not mean a reviewer approved or rejected the draft.

## New task B: technical incident report

The task still belongs to `sample-app` and has the `consumer` audience, but `task_type=technical_incident_report`. The negative boundary should exclude the rule, even if the same phrase appears in the text.
