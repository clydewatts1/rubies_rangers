---
type: Issue
title: "[#013] Two-Stage 'Screen & Simulate' Optimization Architecture"
description: "Chained MILP Stage 1 screening knapsack with Stage 2 2,500-draw Monte Carlo tournament."
tags: [issue, optimization, milp, monte-carlo, transfers]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#013]: Two-Stage 'Screen & Simulate' Optimization Architecture

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P0-Critical
> - **Estimated Complexity**: XL
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_013_two_stage_screen_and_simulate`

---

## 1. Context & Concept (The Why)
A single MILP solver cannot account for full joint distribution variance, while pure Monte Carlo cannot explore the massive 15-player combinatorial space. Chaining Stage 1 MILP screening with Stage 2 Monte Carlo tournament provides optimal tractability and tail-risk awareness.

---

## 2. Goals & Objectives
- Stage 1: Multi-objective MILP screens the top 50 Pareto-optimal transfer/lineup candidates.
- Stage 2: 2,500-draw stochastic Monte Carlo tournament simulates tail risks (P10, P50, P90, max upside).
- Present multi-archetype strategies (Max EV, Balanced, Risk Averse, High Ceiling) on the trading desk.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] analytics/two_stage_optimizer.py executing chained screening and tournament simulation
- [x] 4 distinct managerial archetype lineups presented in Streamlit UI
- [x] Automated test suite verifying runtime execution under 10 seconds

---

## 4. Technical Constraints & Context
NumPy vectorization for Stage 2 tournament; zero .iterrows() iteration.
