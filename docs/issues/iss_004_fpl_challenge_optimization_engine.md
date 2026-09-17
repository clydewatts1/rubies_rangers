---
type: Issue
title: "[#004] FPL Challenge Quantitative Optimization Engine"
description: "Mathematical formulation and candidate screening for dynamic weekly FPL Challenge tournament formats."
tags: [issue, challenge, optimization, milp, knapsack]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#004]: FPL Challenge Quantitative Optimization Engine

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: L
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_004_fpl_challenge_optimization_engine`

---

## 1. Context & Concept (The Why)
Classic FPL is an infinite-horizon discounted Markov Decision Process, but FPL Challenge is a single-period dynamic tournament where rules mutate weekly (variable squad size N=6 to N=11, club limits C=1 to C=5, dynamic scoring multipliers, and rolling match-by-match deadlines).

---

## 2. Goals & Objectives
- Reverse-engineer and implement the official FPL Challenge API client.
- Formulate dynamic-constraint Single-Period MILP knapsack solver supporting arbitrary N, C, and budget.
- Build Streamlit Challenge trading desk for interactive tournament screening and lineup generation.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] FPLChallengeClient fetching gameweek event rules, overrides, and live entries
- [x] Two-Stage Challenge Optimizer screening candidate squads across Markowitz Pareto frontier
- [x] Dynamic position handling supporting 6-a-side outfield and full 11-a-side lineups
- [x] Automated unit test suite covering custom position quotas and club constraints

---

## 4. Technical Constraints & Context
Must handle missing or zero goalkeepers gracefully without solver infeasibility.
