---
name: brainstorm-facilitator
description: Takes an Issue document as input and generates a standardized Brainstorm document exploring 2-3 competing mathematical/architectural options with trade-offs. Initializes the Frontloader section for DAG metadata tracking and ensures OKF/ARD compliance.
---

# brainstorm-facilitator

## Purpose
This skill operates at Stage 2 (Brainstorm) of the development lifecycle. It takes a Stage 1 Issue document (`docs/issues/iss_<ID>_<slug>.md`) and generates a standardized Brainstorm document in `docs/brainstorm/brn_<ID>_<slug>.md`.

It initializes the **Frontloader** section to explicitly track document flow metadata and DAG (Directed Acyclic Graph) lineage, ensuring downstream skills (like Design or Playbook generators) have full context of the origin issue.

## Routing Guidance
The repository has two brainstorm skills:
- **`brainstorm-facilitator`** (this skill): Single-shot mode. Reads the Issue, evaluates 2-3 competing mathematical/technical options, analyzes trade-offs, and writes the Brainstorm. Best for straightforward initiatives.
- **`brainstorm-ideate-loop`**: Multi-turn Socratic sparring. Engages the user in back-and-forth trade-off exploration before committing to a final brainstorm document. Best for complex, ambiguous, or high-stakes algorithmic models.

## Scope Gate: Is a Brainstorm Needed?
Before drafting a brainstorm, evaluate whether the issue genuinely requires multi-option exploration:
- If the issue has an **obvious single solution** (e.g., bug fix, config toggle, typo fix, one-liner wiring, or Track B Fast-Track), inform the user that Stage 2 can be skipped and proceed directly to Stage 3 (Design) or implementation.

## Operational Constraints (CRITICAL)
- **Zero-Shell Mandate**: Do not use `run_command` unless explicitly ordered (except for running `python scripts/ard_builder.py`).
- **DAG Lineage Rule**: The Brainstorm document MUST link back to the source Issue in its OKF `sources` array: `sources: ["docs/issues/iss_<ID>_<slug>.md"]`.
- **Moneyball Strategy Invariant**: Competing algorithmic options must be evaluated against the core quantitative principles in [`.agents/rules/moneyball_strategy.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/.agents/rules/moneyball_strategy.md) (unconstrained optimization, full probability distribution propagation, multi-period dynamic utility).

## Execution Steps

### 1. Analyze the Source Issue
- Read the input Issue document using `view_file`.
- Extract Issue ID, Title, Context, Goals, and Acceptance Criteria.

### 2. Generate 2-3 Competing Options
Identify at least 2 distinct technical or mathematical approaches:
- **Option 1**: E.g., The direct / conservative approach.
- **Option 2**: E.g., The high-performance / vectorized / stochastic approach.
- **Option 3** (Optional): The radical / zero-overhead approach.

Compare them along:
- Mathematical rigor & Moneyball alignment
- Runtime latency & complexity
- Maintenance burden & failure risk

### 3. Recommend a Decision
Select the winning approach with clear technical justification.

### 4. Write Brainstorm Document
Write `docs/brainstorm/brn_<ID>_<slug>.md` using the template below.

### 5. Rebuild ARD Manifest
Run `python scripts/ard_builder.py`.

---

## Content Body Template

```markdown
---
type: Brainstorm
title: "[#<ID>] <Title> - Brainstorm"
description: "<Brief 1-2 sentence description of explored options and recommendation>"
tags: [brainstorm, <domain>, <tech>]
status: Active
sources: ["docs/issues/iss_<ID>_<slug>.md"]
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:brainstorm-facilitator"
---

# Brainstorm [#<ID>]: <Title>

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Issue**: [`docs/issues/iss_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_<ID>_<slug>.md)
> - **Current Stage**: Stage 2 (Brainstorm)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **URN**: urn:air:clydewatts1:rubies_rangers:docs:brn_<ID>_<slug>

## 1. Problem Space & Constraints
<Summary of the problem, constraints, and why exploration is required.>

## 2. Option Evaluation Matrix

| Criterion | Option 1: <Name> | Option 2: <Name> | Option 3: <Name> |
| :--- | :--- | :--- | :--- |
| **Mathematical Soundness** | ... | ... | ... |
| **Runtime Performance** | ... | ... | ... |
| **Implementation Complexity**| ... | ... | ... |
| **Moneyball Alignment** | ... | ... | ... |

## 3. Deep-Dive on Competing Options

### Option 1: <Name>
- **Mechanism**: ...
- **Pros**: ...
- **Cons**: ...

### Option 2: <Name>
- **Mechanism**: ...
- **Pros**: ...
- **Cons**: ...

## 4. Architectural Recommendation
<Clear declaration of the recommended option and the technical rationale.>

## 5. Next Steps
- Transition to Stage 3 (Design) via `/design-facilitator` to produce `des_<ID>_<slug>.md`.
```
