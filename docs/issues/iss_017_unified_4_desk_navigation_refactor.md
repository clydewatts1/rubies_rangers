---
type: Issue
title: "[#017] Streamlined 4-Desk Navigation Taxonomy Refactor"
description: "Consolidate Streamlit navigation into 4 unified trading desks, centralizing all robotic automation under Autonomous Operations desk."
tags: [issue, refactor, architecture, ui, component]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#017]: Streamlined 4-Desk Navigation Taxonomy Refactor

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_017_unified_4_desk_navigation_refactor`

---

## 1. Context & Concept (The Why)
Fast development cycles caused tab sprawl across 6+ disparate views, splitting automation between classic Fantasy CPN and Challenge CPN. A unified 4-desk navigation model standardizes user workflows into institutional trading desks.

---

## 2. Goals & Objectives
- Consolidate navigation into 4 desks: Portfolio & Balance Sheet, Quantitative Solvers, Autonomous Operations, and Alpha Signals.
- Merge Fantasy CPN and Challenge CPN into the unified Autonomous Operations desk.
- Preserve all existing tab controllers and telemetry headers without breakage.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] app.py updated with 4 unified desk radio buttons and sub-tab selection
- [x] ui_ux_standards.md updated with official 4-desk taxonomy
- [x] Clean dark-mode financial terminal styling preserved

---

## 4. Technical Constraints & Context
Strict compliance with .agents/rules/ui_ux_standards.md 4-zone page anatomy.
