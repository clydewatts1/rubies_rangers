---
type: Issue
title: "[#016] Direct 1-Click FPL Transfer Application Popover"
description: "1-click online FPL transfer execution button in Two-Stage Optimization Tournament with name resolver, dry-run, and live API dispatch."
tags: [issue, feature, transfers, service, ui, client]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#016]: Direct 1-Click FPL Transfer Application Popover

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_016_fpl_direct_transfer_application`

---

## 1. Context & Concept (The Why)
Managers previously had to manually copy recommended transfers from the Two-Stage Tournament screen and execute them on the official FPL website. A 1-click execution popover directly bridges analytical recommendations to live squad submission.

---

## 2. Goals & Objectives
- Build FPLTransferService with fuzzy name-to-ID resolution and payload serialization.
- Add 1-click '⚡ Apply Transfers Online' popover to each of the 3 strategy panels in Two-Stage Tournament.
- Provide dry-run simulation mode and live authenticated API dispatch with safety confirmations.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] clients/fpl_transfer_service.py resolving player names and executing POST /api/my-team/
- [x] Interactive popover dialog in ui/tabs/tab_two_stage.py showing transfer diff, chip selection, and dry-run toggle
- [x] Automated test suite verifying payload construction and error handling

---

## 4. Technical Constraints & Context
Must enforce explicit confirmation before firing live transfers; auth session restored safely.
