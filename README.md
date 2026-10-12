# BossAlign (Codename: Roundworm) 🐛⚡

> **Turn ruthless managerial feedback into one-shot approvals.**  
> *Make your stakeholders exclaim: "Holy crap, that's EXACTLY what I wanted! How did you read my mind?!"*

<p align="center">
  <b>English</b> | 
  <a href="README_CN.md"><b>📖 简体中文文档</b></a> | 
  <a href="docs/01_boundary_guard_en.md">Architecture Docs</a> | 
  <a href="examples/skypulse_drone/output_script_en.md">Mock Showcase</a>
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Status: Battle-Tested](https://img.shields.io/badge/Status-Battle--Tested-orange.svg)](#)

---

## 💥 The Universal Creator Nightmare

Every professional and AI creator knows this brutal loop:

1. **You spend hours using LLMs to craft a pitch/script/proposal**, feeling confident.
2. **Your manager reviews it for 3 seconds and drops a furious 60-second voice memo**:  
   > *"What on earth is this? It's so stiff and reeks of generic AI fluff! I want premium and sleek, but not the boring old corporate video style! Make it punchy, you get me?! Redo it!"*
3. **You frantically feed the exact words into ChatGPT**: *"Make it premium, sleek, and not a boring corporate video."*
4. **You submit V2, and your manager explodes**:  
   > *"Who told you to strip away all the actual engineering benchmarks I asked for?! Are you even paying attention?!"*

---

### Why Standard AI Fails in Real Decision-Making

Standard LLMs suffer from severe **Over-fitting** and **Lack of Negative Boundary Constraints**:
- When a boss says *"Don't overcomplicate the factory tour in this 30s video"*, the AI completely erases manufacturing credentials in every future document.
- When a boss asks for *"a modern vibe"*, the AI injects cheap internet slang into a B2B enterprise deck.
- When two senior stakeholders disagree, the AI hallucinates into complete paralysis.

**Your executive is not being erratic—they are making intuitive, multi-variable aesthetic decisions. Your AI simply lacks an engineering framework to align with that intuition.**

---

## 🚀 Introducing BossAlign

`BossAlign` is not just another prompt template or superficial rewriter.  
It is a **production-grade "Boss-in-the-Loop" Preference Alignment Framework** designed for complex organizational review pipelines.

It tracks managerial feedback like Git commits, synthesizes strict **Applicability Scope & Negative Boundaries**, and runs a **Pre-Flight "Shadow Boss" Sandbox** before you hit send.

```mermaid
journey
    title The Evolution from Corporate Doormat to "Mind Reader"
    section Stage 1: De-noising
      Manager sends furious voice memo: 1: Creator
      De-noise emotions, isolate true intent: 4: BossAlign
    section Stage 2: Boundary Guard
      Standard AI over-corrects everything: 1: Standard AI
      Establish negative boundaries to avoid regression: 5: BossAlign
    section Stage 3: Dialect Compilation
      Decode ambiguous terms like 'sleek' and 'modern': 5: BossAlign
      Assemble copy with grounded operational evidence: 5: BossAlign
    section Stage 4: One-Shot Approval
      Executive previews the draft with a smile: 5: Executive
      "Holy crap, this is spot on! Are you in my head?!": 5: Executive, Creator
```

---

## 🛠️ Key Architectural Pillars

### 1. Emotion De-noiser
Executive rants are 80% venting and 20% critical signal.  
`BossAlign` strips conversational noise and captures:
- **Core Intent**: Shift from abstract corporate storytelling to grounded operational proof.
- **Evidence Anchor**: Retain empirical testing data; ban unverified superlative claims.

### 2. Negative Boundary Guard (The Anti-Overfitting Moat)
**The #1 reason AI fails in organizations is unchecked generalization.**  
Every learned preference rule must strictly define:
- **Core Directive**: Omit macro assembly-line walkthroughs.
- **Applicable Scope**: B2B product showcase overview clips.
- **Negative Boundary (Strict Prohibition)**: **NEVER** apply this rule to R&D capability or QA assurance documents!

### 3. Boss Dialect Compiler
Decodes ambiguous corporate speak into actionable creative execution:
| Executive Slang | Naive LLM Mistake | BossAlign Translation |
|---|---|---|
| **"Make it premium"** | Piles on flashy adjectives like "luxurious, unparalleled" | **Cinematic breathing pauses** + **Macro product closeups** + **Restrained, verifiable claims** |
| **"Make it appeal to Gen-Z"** | Stuffs cringe memes and hashtags | **Dynamic editing rhythm** + **Diegetic sound sync** + **Eliminates monotone broadcast narration** |
| **"I'm just giving you the rough idea"** | Copies the boss's broken sentences verbatim | **Extracts strategic skeleton**, LLM finishes continuous delivery flow |

### 4. Clean-Room Sanitizer
Deep tracking internally; zero trace externally.  
- Strips all internal metadata (e.g., `[Adjusted per Boss_Victor EVT-042]`);
- Exports spotless Markdown, Word, or Excel deliverables that look 100% human-crafted.

---

## ⚡ Quickstart in 30 Seconds

### Installation
```bash
pip install bossalign
# Or clone the repo
git clone https://github.com/davidmercer0620-ai/bossalign.git
cd bossalign && pip install -e .
```

### 1. Ingest Raw Managerial Feedback
```bash
bossalign ingest \
  --reviewer "Boss_Victor" \
  --raw "This draft feels completely fake! Stop praising our 'craftsmanship' and show actual flight endurance in gale-force winds!" \
  --context "SkyPulse_Drone_Episode02"
```

The system automatically parses the raw feedback into a standardized `feedback_event` and synthesizes the negative boundary:
```json
{
  "event_id": "EVT-202610-001",
  "reviewer": "Boss_Victor",
  "intent": "Replace abstract craftsmanship claims with empirical gale-force wind tests and flight endurance.",
  "boundary": {
    "applicable_to": ["Performance Showcase", "Hardcore Benchmark Testing"],
    "counter_example": "Strictly prohibited from stripping brand ethos in emotional brand manifesto pieces."
  }
}
```

### 2. Generate Draft & Run Pre-Flight Sandbox
```bash
bossalign generate \
  --topic "Episode03_All_Weather_Capability" \
  --persona "Boss_Victor" \
  --output "output/script_v1.md"
```

Terminal Output:
```text
[SandBox] Executing Shadow Boss review simulation...
[PASS] Zero banned superficial marketing slogans detected.
[PASS] Wind resistance metric pinned to lab report #TR-804.
[PASS] Pacing check: Word density aligned with Boss_Victor preference.
[CLEAN] Clean-room sanitization complete! Internal metadata stripped.
Deliverable ready: output/script_v1.md
```

---

## 📂 Project Structure

```text
bossalign/
├── bossalign/               # Python core engine code
│   ├── parser.py            # Emotion de-noiser & intent extraction
│   ├── boundary.py          # Negative boundary guard & regression check
│   ├── sandbox.py           # Pre-flight shadow boss review simulation
│   └── sanitizer.py         # Clean-room deliverable sanitizer
├── docs/                    # Architectural Whitepapers
│   ├── 01_boundary_guard_en.md # On Negative Boundaries: Ending AI Over-fitting
│   ├── 02_evidence_ladder_en.md# The Evidence Ladder: Isolating Quotes, Grounding & Speculation
│   └── 03_clean_room_en.md     # Clean-Room Delivery: The Ultimate Workplace Survival Law
└── examples/                # Benchmark Synthetic Showcase
    └── skypulse_drone/      # SkyPulse Drone Campaign (dual_review_rules_en.md, output_script_en.md)
```

---

## 🛡️ Privacy & Compliance Guarantee

All datasets, showcase materials, and rules in this repository are **100% synthetic mock examples** (e.g., the fictional smart hardware brand *SkyPulse Robotics*).  
**No confidential corporate data, real executive identities, proprietary formulas, or private recordings are included.**

---

## 🤝 Community & Contributing

Tired of getting rejected on draft revisions? Join us!
- Submit a PR with a Boss Dialect Decoder for your industry.
- Add mock industry templates (Healthcare, SaaS, Automotive, PR).

**If BossAlign saved your sanity at work, give us a ⭐ on GitHub!**
