---
type: Issue
title: "[#010] Strategic Framework Phase 0 - Foundational Data & Portfolio Ingestion"
description: "Multi-gameweek transfer planning, bank optimization, and rolling horizon setup."
tags: [issue, portfolio, transfers, strategy]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#010]: Strategic Framework Phase 0 - Foundational Data & Portfolio Ingestion

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P0-Critical
> - **Estimated Complexity**: L
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_010_strategic_framework_phase_0`

---

## 1. Context & Concept (The Why)
Optimal managerial decision-making requires accurate current squad equity, cash-in-bank tracking, selling price economics (50% profit tax calculation), and rolling multi-gameweek transfer schedules.

---

## 2. Goals & Objectives
- Build robust FPL API data ingestion for current picks, bank balance, and free transfer counts.
- Implement selling price and purchase price tracking honoring official FPL price-gain rules.
- Formulate rolling 5-gameweek transfer planning horizon.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] clients/fpl_client.py hydrating live squad data and bank balances
- [x] Accurate selling value calculation incorporating price rise retention
- [x] Strategic chessboard UI displaying rolling 5-GW squad roadmap

---

## 4. Technical Constraints & Context
Must handle cold-start and pre-season states when no gameweeks have completed.
