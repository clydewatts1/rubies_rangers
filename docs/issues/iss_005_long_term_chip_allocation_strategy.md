---
type: Issue
title: "[#005] Long-Term Chip Allocation Strategy & Optimal Stochastic Timing"
description: "Dynamic programming and Bellman optimality for timing Free Hit, Wildcard, Bench Boost, and Triple Captain chips."
tags: [issue, chips, strategy, optimization, monte-carlo]
status: Active
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#005]: Long-Term Chip Allocation Strategy & Optimal Stochastic Timing

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: L
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_005_long_term_chip_allocation_strategy`

---

## 1. Context & Concept (The Why)
Community chip strategies rely on rigid dogma (e.g., save Wildcard for GW8, Free Hit on BGW29). True mathematical optimization requires evaluating chips as American call options with stochastic opportunity costs across future double and blank gameweeks.

---

## 2. Goals & Objectives
- Formulate Bellman dynamic programming equations for optimal chip activation timing.
- Model option value and decay curves for Free Hit, Wildcard, Bench Boost, and Triple Captain.
- Implement Monte Carlo horizon simulation calculating marginal point expectation per chip.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] analytics/chip_strategy.py calculating chip option values across 5-gameweek horizons
- [x] UI Chip Strategy tab rendering tactical roadmap and activation recommendations
- [ ] Full 38-gameweek dynamic programming backward induction model

---

## 4. Technical Constraints & Context
Must account for rule updates (e.g. 2 Wildcards per season, separation of DGWs).
