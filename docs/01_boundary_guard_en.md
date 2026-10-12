# Whitepaper 01: Negative Boundary Guard — Eliminating LLM Over-fitting

> **Author**: BossAlign Architecture Team  
> **Core Premise**: Why do large language models constantly swing to opposing extremes after receiving human feedback? How do negative boundaries establish production-grade alignment?

---

## 1. The Phenomenon: Naive Over-Correction

In enterprise editorial review cycles, human creators frequently encounter this failure mode:

- **Scenario A**: An executive reviews an intro video script for catalog selection and remarks:  
  *"This video is for apparel buyers choosing fabrics. Don't waste half the runtime detailing circular knitting machine tension calibrations. Buyers don't care."*
- **Naive LLM Reaction**:  
  The LLM summarizes this feedback into an unchecked global negative rule:  
  `[Never mention knitting machinery or factory processes]`.  
  Consequently, in the very next script dedicated to **hardcore manufacturing R&D credentials**, the LLM strips away every piece of engineering machinery, triggering another executive meltdown.

This is the classic **Over-correction / Hallucinated Generalization**. Standard LLMs cannot distinguish between **contextual reduction** and **global prohibition**.

---

## 2. The Solution: Tripartite Boundary Architecture

In `BossAlign`, every principle synthesized from stakeholder feedback must satisfy three mandatory fields:

```text
┌────────────────────────────────────────────────────────┐
│               BossAlign Boundary Rule Schema           │
├────────────────────────────────────────────────────────┤
│ 1. Core Directive                                      │
│    - The synthesized positive or negative action       │
├────────────────────────────────────────────────────────┤
│ 2. Applicable Scope                                    │
│    - Eligible topic categories, audiences, goals      │
├────────────────────────────────────────────────────────┤
│ 3. Negative Boundary / Counter-Example                 │
│    - Explicit conditions where this rule is FORBIDDEN  │
└────────────────────────────────────────────────────────┘
```

### Production Example:

```json
{
  "rule_id": "RULE-SCOPE-042",
  "reviewer": "Boss_Victor",
  "directive": "Reduce macro assembly-line coverage; focus on finished handheld ergonomics and portability.",
  "applicable_scope": {
    "topic_types": ["Consumer Unboxing", "In-Store Selection Guide"],
    "target_audience": ["End Users", "Retail Distributors"]
  },
  "negative_boundary": {
    "prohibited_topics": ["Industrial Inspection Delivery", "National Lab R&D Credentials"],
    "rationale": "For enterprise B2B or scientific clients, manufacturing tolerances and machinery are cornerstones of trust. NEVER strip them!"
  }
}
```

---

## 3. Dynamic Intent-Based Retrieval

When a new prompt task arrives, the retriever executes a two-stage filter rather than a naive keyword search:

1. **Stage 1: Intent Filtering**  
   Checks whether the current task's `topic_type` matches the `applicable_scope`. If not, the rule is ignored.
2. **Stage 2: Boundary Clash Check**  
   Checks whether the task intersects the `negative_boundary`. If triggered, an active protective constraint is injected into the prompt:  
   `[SYSTEM GUARD]: Do NOT apply RULE-SCOPE-042 here. Retain full engineering specs.`
