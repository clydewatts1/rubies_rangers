---
type: Issue
title: "[#012] Two-Stage Optimization: Measure Inclusion & Exclusion Criteria"
description: "Feature selection and mathematical weighting for Multi-Objective MILP and Monte Carlo Tournament stages."
tags: [issue, optimization, milp, monte-carlo, tactics]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#012]: Two-Stage Optimization: Measure Inclusion & Exclusion Criteria

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_012_two_stage_optimization_measures_inclusion_exclusion`

---

## 1. Context & Concept (The Why)
Feeding raw collinear features into optimization engines degrades solver performance. Clear criteria are required to partition metrics between Stage 1 deterministic screening and Stage 2 stochastic tournament simulation.

---

## 2. Goals & Objectives
- Define mathematical inclusion criteria for Stage 1 MILP (xP, price, fixture FDR, club quotas).
- Define mathematical inclusion criteria for Stage 2 Monte Carlo (volatility, minutes risk, teammate covariance, upside tail P90).
- Eliminate redundant or biased trailing metrics.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] Feature isolation documented and implemented in analytics/two_stage_optimizer.py
- [x] Linear constraints separated from non-linear stochastic objective functions
- [x] Hyperparameter tuner search space aligned with vetted feature weights

---

## 4. Technical Constraints & Context
Zero inclusion of subjective media sentiment.
