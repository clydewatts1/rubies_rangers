---
type: Issue
title: "[#003] Codebase Modularization & Two-Stage Architectural Decoupling"
description: "Modular refactor decomposing app.py into domain packages: analytics, clients, ui, and automation."
tags: [issue, architecture, process, refactor]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#003]: Codebase Modularization & Two-Stage Architectural Decoupling

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P0-Critical
> - **Estimated Complexity**: XL
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_003_codebase_modularization_roadmap`

---

## 1. Context & Concept (The Why)
The initial prototype accumulated into a 2,641-line monolithic app.py mixing Streamlit UI, CSS injection, session state, solver logic, and API calls. Core trackers resided flat in the repository root, creating high coupling and circular dependency risks.

---

## 2. Goals & Objectives
- Decompose flat root cluster into 4 strictly layered domain packages: analytics/, automation/, clients/, and ui/.
- Isolate Streamlit UI components and tab modules into dedicated ui/ package.
- Protect in-flight hyperparameter tuning runs and maintain zero breaking changes to solvers.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] app.py reduced to a thin orchestrator routing to modular UI tabs
- [x] All root trackers moved to trackers/ package with backward-compatible aliases
- [x] Solvers and mathematical models cleanly located in analytics/
- [x] Pytest test harness verifies all imported modules and regression baselines

---

## 4. Technical Constraints & Context
Strict compliance with .agents/rules/python_standards.md inward dependency rule.
