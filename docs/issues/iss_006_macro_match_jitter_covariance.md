---
type: Issue
title: "[#006] Macro Match-State Jitter & Teammate Covariance Modeling"
description: "Full covariance matrix simulation modeling match-state blowouts, game script correlation, and variance."
tags: [issue, monte-carlo, optimization, tactics]
status: Active
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#006]: Macro Match-State Jitter & Teammate Covariance Modeling

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: L
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_006_macro_match_jitter_covariance`

---

## 1. Context & Concept (The Why)
Independent player point sampling assumes zero covariance between teammates and opponents. In reality, match pace, blowouts, and defensive game scripts induce heavy positive covariance between attacking teammates and negative covariance between defenders and opposing strikers.

---

## 2. Goals & Objectives
- Model macro match-state pace jitter using bivariate Poisson match score distributions.
- Construct block-covariance matrices for teammate attacking returns and defensive clean sheets.
- Simulate 2,500 correlated gameweek draws for portfolio downside (P10) and upside (P90) assessment.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] analytics/macro_covariance.py generating correlated player return distributions
- [x] Monte Carlo engine integrating macro match-state jitter vectors
- [x] UI Monte Carlo tab rendering joint return histograms and correlation matrices

---

## 4. Technical Constraints & Context
NumPy vectorization required; zero row-by-row iteration in simulation loops.
