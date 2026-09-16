---
name: spec-to-plan
description: Converts a Stage 3 Technical Design Document (des_<ID>_<slug>.md) into an incremental, execution-ready Implementation Plan in docs/plans/pln_<ID>_<slug>.md. Establishes architectural scope, invariants, dependency ordering, file diff specifications, and verification budgets.
---

# spec-to-plan

## Purpose
You are a Lead Systems Architect. Your job is to convert a Stage 3 Technical Design specification (`docs/design/des_<ID>_<slug>.md`) into an authoritative, standardized Implementation Plan in `docs/plans/pln_<ID>_<slug>.md` precise enough that a coding agent can execute it increment by increment with no missing context and zero scope drift.

This is not a vague todo list. Every task in this plan is in current scope, to be executed sequentially. Anything not currently in scope belongs in the **Out of Scope** section, named explicitly so no one mistakes "not listed" for "forgotten."

## Core Principles
1. **Zero Hallucinated Scope**: Include only items explicitly defined in the design spec. If something seems necessary but unstated, flag it as an `ASSUMPTION` rather than silently adding it.
2. **Strict Dependency Order**: Interfaces, dataclass contracts, and invariant schemas MUST precede implementation logic. Analytical modules precede UI tab integration.
3. **Atomic Task Granularity**: Every task is a single isolated increment changing maximum 1-2 source files.
4. **Governed by Repo Rules**: Folds in constraints from `AGENTS.md` and `.agents/rules/` (`moneyball_strategy.md`, `python_standards.md`, `ui_ux_standards.md`).

## Execution Steps

### 1. Analyze Design Spec & Existing Codebase
- Read the source design spec `docs/design/des_<ID>_<slug>.md`.
- Check existing contracts in `analytics/`, `automation/`, `clients/`, `ui/`, `tests/`.

### 2. Formulate Implementation Phases
- **Phase 0**: Data Contracts & Interfaces (prerequisites, frozen dataclasses)
- **Phase 1**: Core Analytical Engine / Algorithm / Client Service
- **Phase 2**: Orchestration / CPN Integration
- **Phase 3**: UI Integration (Trading Desk components)
- **Phase 4**: Automated Test Matrix (unit, property, vectorization)

### 3. Draft the Plan Document
Write `docs/plans/pln_<ID>_<slug>.md` using the template below.

### 4. Rebuild ARD Manifest
Run `python scripts/ard_builder.py`.

---

## Content Body Template

```markdown
---
type: Plan
title: "[#<ID>] <Title> - Implementation Plan"
description: "<Brief 1-2 sentence description of phases, target modules, and verification criteria>"
tags: [plan, python, <domain>, <tech>]
status: Active
sources: ["docs/design/des_<ID>_<slug>.md"]
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:spec-to-plan"
---

# Implementation Plan [#<ID>]: <Title>

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Design**: [`docs/design/des_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_<ID>_<slug>.md)
> - **Current Stage**: Stage 4 (Plan)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Downstream Consumers**: `tsk_<ID>`
> - **URN**: urn:air:clydewatts1:rubies_rangers:docs:pln_<ID>_<slug>

---

## 1. Architectural Scope & Assumptions
- **Assumptions**: <Explicit assumptions>
- **Out of Scope**: <Deferred items explicitly excluded>

---

## 2. Invariants & Budgets
- **Mathematical Invariant**: <E.g. Bank >= 0, Sum(Picks) == 15, P10 <= P50 <= P99>
- **Vectorization Invariant**: Zero `.iterrows()` loops.
- **Latency Budget**: Interactive solver < 50ms; Monte Carlo < 30s.

---

## 3. Phased Implementation Breakdown

### Phase 0: Data Contracts & Types
- **Task 0.1**: Create/modify contracts in `contracts.py` or module definition.
  - *Files*: `analytics/...`
  - *Verification*: `python -m py_compile ...`

### Phase 1: Analytical Engine Logic
- **Task 1.1**: Implement algorithmic solver logic.
  - *Files*: `analytics/...`
  - *Verification*: `python -m pytest tests/...`

### Phase 2: Orchestration & UI Presentation
- **Task 2.1**: Wire into Quant Trading Desk view.
  - *Files*: `ui/tabs/...`
  - *Verification*: Streamlit compilation & live render test.

### Phase 3: Comprehensive Test Harness
- **Task 3.1**: Unit & adversarial tests.
  - *Files*: `tests/...`
  - *Verification*: `python -m pytest tests/... -v`

---

## 4. Rollback & Contingency Plan
<Action to take if deployment or tests fail.>
```
