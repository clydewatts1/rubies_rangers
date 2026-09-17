---
name: brainstorm-facilitator
description: Acts as Transition T_BRAINSTORM in the Agentic Coloured Petri Net (CPN), taking an Issue token from P_ISSUE_READY and depositing a standardized Brainstorm token into P_BRAINSTORM_POOL exploring 2-3 competing options with trade-offs.
---

# brainstorm-facilitator

## Purpose
This skill fires as **Transition $T_{\text{BRAINSTORM}}$** in the **Agentic Coloured Petri Net (CPN)**. It consumes an `IssueToken` from $P_{\text{ISSUE\_READY}}$ (on Track A) and generates a standardized Brainstorm document in `docs/brainstorm/brn_<ID>_<slug>.md`, depositing a `BrainstormToken` into $P_{\text{BRAINSTORM\_POOL}}$.

It initializes the **Frontloader** section to explicitly track CPN lifecycle flow and provenance lineage, ensuring downstream transitions (like Design or Playbook generators) maintain unbroken context.

## Routing Guidance
The repository has two brainstorm skills:
- **`brainstorm-facilitator`** (this skill): Single-shot mode. Reads the Issue, evaluates 2-3 competing mathematical/technical options, analyzes trade-offs, and writes the Brainstorm. Best for straightforward initiatives.
- **`brainstorm-ideate-loop`**: Multi-turn Socratic sparring. Engages the user in back-and-forth trade-off exploration before committing to a final brainstorm document. Best for complex, ambiguous, or high-stakes algorithmic models.

## Scope Gate: Is a Brainstorm Needed?
Before drafting a brainstorm, evaluate whether the issue genuinely requires multi-option exploration:
- If the issue has an **obvious single solution** (e.g., bug fix, config toggle, typo fix, one-liner wiring, or Track B Fast-Track), inform the user that Stage 2 can be skipped and proceed directly to Stage 3 (Design) or implementation.

## Operational Constraints (CRITICAL)
- **Zero-Shell Mandate**: Do not use `run_command` unless explicitly ordered (except for running `python scripts/ard_builder.py`).
- **CPN Lineage Rule**: The Brainstorm document MUST link back to the source Issue in its OKF `sources` array: `sources: ["docs/issues/iss_<ID>_<slug>.md"]` to preserve the immutable acyclic provenance trace.
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

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_ISSUE_READY`
> - **Current Transition**: `T_BRAINSTORM`
> - **Next Place**: `P_BRAINSTORM_POOL`
> - **CPN Lineage**: Issue [#<ID>] -> Brainstorm [brn_<ID>] -> Design -> Plan -> Tasks -> Playbook
> - **Origin Issue**: [`docs/issues/iss_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/issues/iss_<ID>_<slug>.md)
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
