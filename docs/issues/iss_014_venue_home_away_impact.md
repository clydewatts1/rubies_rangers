---
type: Issue
title: "[#014] Team & Positional Venue Impact (Home vs. Away) Modeling"
description: "Quantifying pitch dimensions, home venue bias, crowd noise, and venue FDR multipliers."
tags: [issue, venue, tactics, fdr, odds]
status: Closed
sources: []
generated:
  at: "2026-09-17T05:25:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#014]: Team & Positional Venue Impact (Home vs. Away) Modeling

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin**: `greenfield`
> - **Current Stage**: Stage 1 (Issue)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
> - **Execution Track**: Track A (Full 6-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_014_venue_home_away_impact`

---

## 1. Context & Concept (The Why)
Standard FDR treats home and away fixtures with naive static adjustments. Detailed venue dimensions (narrow vs. wide pitches), travel distance, and crowd pressure create asymmetric positional impacts (e.g. wingbacks penalized on narrow pitches).

---

## 2. Goals & Objectives
- Catalog stadium pitch dimensions, grass types, and historical home advantage coefficients.
- Formulate positional venue multipliers for defenders, midfielders, and forwards.
- Expose interactive venue intelligence tab in Streamlit dashboard.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation (or exploration) is considered complete when:*
- [x] analytics/venue_model.py computing empirical venue multipliers
- [x] ui/tabs/tab_venue.py rendering stadium specs and venue FDR heatmaps
- [x] Unit tests verifying multiplier bounds and consistency

---

## 4. Technical Constraints & Context
Data sourced from objective stadium specifications.
