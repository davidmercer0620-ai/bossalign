# Whitepaper 02: The Evidence Ladder — Preventing Hallucinated Stakeholder Profiles

> **Author**: BossAlign Architecture Team  
> **Core Premise**: Why do digital personas of executives hallucinate over time? How does hierarchical evidence management ensure verifiable preference modeling?

---

## 1. The Root Cause: Attribution Pollution

Without strict isolation, multi-turn AI interactions cause severe attribution drift:

1. **Manager says**: *"This section feels too dry."*
2. **Colleague notes**: *"I think he wanted more personal storytelling."*
3. **AI infers**: *"The boss loves sentimental emotional drama. Let's invent a story about an engineer crying in the lab at 3 AM."*
4. **Permanent Persona Updated**: *[Reviewer Persona: Prefers sentimental storytelling]*

In the next proposal review, the executive explodes over the forced melodrama.  
This failure mode is termed **Attribution Pollution**.

---

## 2. The Four-Tier Evidence Ladder

`BossAlign` enforces a strict 4-tier hierarchy for every piece of learned knowledge:

```text
Level 1: Direct Verbatim Quote (Primary Direct Evidence)
  └── Source: Audio transcripts with timestamps, direct redline markups, verbatim chat messages.
  └── Authority: Highest decision weight; directly updates reviewer profile.

Level 2: Factual Grounding (Empirical Grounding)
  └── Source: Lab test logs, ERP inventory, factory machine tolerances signed by tech leads.
  └── Authority: Dictates objective performance claims; overrides marketing rhetoric.

Level 3: Transferred Notes (Secondary Transferred Evidence)
  └── Source: "A colleague heard the VP say...", "The project manager's interpretation".
  └── Authority: Tagged as [TRANSFERRED]; serves as exploratory hypothesis only.

Level 4: AI Speculation (Model Hypotheses)
  └── Source: LLM deductive conclusions derived from above signals.
  └── Authority: Tagged as [HYPOTHESIS]; requires formal human verification before promotion.
```

---

## 3. Immutable Governance Invariants

- **Zero-Promotion Rule**: Level 3 or 4 assumptions can **NEVER** be saved under `Author = "Boss_Victor"`.
- **Audit State Machine**:
  Draft statuses are explicitly tracked as:
  - `DRAFT_INTERNAL`
  - `PRE_FLIGHT_PASSED`
  - `SUBMITTED_AWAITING`
  - `PARTIALLY_ACCEPTED`
  - `APPROVED`

*"AI pre-flight check passed"* does NOT equal *"Approved by stakeholder"*.  
*"Stakeholder voiced no objections"* does NOT equal *"Permanent blanket approval"*.
