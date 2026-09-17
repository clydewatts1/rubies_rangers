---
type: Issue
title: "[#022] FBref / StatsBomb Integration via soccerdata for Goalkeeper PSxG and Attacking SCA/GCA"
description: "Extract Goalkeeper Post-Shot xG (PSxG +/- per 90) and player Shot/Goal Creating Actions (SCA/GCA) via soccerdata to refine BPS bonus prediction and goalkeeper selection."
tags: [issue, feature, soccerdata, fbref, goalkeeper, psxg, sca, tactics]
status: Open
sources: []
generated:
  at: "2026-09-17T19:56:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#022]: FBref / StatsBomb Integration via soccerdata for Goalkeeper PSxG and Attacking SCA/GCA

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#022] -> Design -> Tasks -> Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_022_soccerdata_fbref_advanced_metrics`

---

## 1. Context & Concept (The Why)
Understat provides valuable shot and key pass data, but lacks two critical dimensions of football analytics:
1. **Goalkeeper Shot-Stopping Skill**: Understat cannot isolate whether a goalkeeper is conceding goals due to defensive collapses or poor shot-stopping. FBref/StatsBomb provides **Post-Shot Expected Goals (PSxG)** and **$\text{PSxG} - \text{Goals Conceded}$ (PSxG +/-)**, which measures true shot-stopping alpha. Elite shot-stoppers facing high shot volumes (e.g., Roefs, Verbruggen, Pickford, Raya) earn massive save points and bonus points.
2. **Shot-Creating Actions (SCA) & Goal-Creating Actions (GCA)**: Measures dribbles, tackles won, and secondary passes that lead to shots. In FPL, these actions directly drive the Bonus Point System (BPS) baseline for midfielders and wingers even in low-scoring matches.

The open-source Python library `soccerdata` provides a clean, cached interface to FBref data with zero API subscription costs.

---

## 2. Goals & Objectives
- Integrate `soccerdata.FBref` into a dedicated service (`clients/fbref_client.py`) with persistent disk caching.
- Ingest goalkeeper advanced metrics: PSxG/90, save percentage, clean sheet percentage, and aerial cross stopping %.
- Ingest outfield advanced metrics: SCA/90, GCA/90, progressive carries, and progressive passes.
- Refine the Goalkeeper xP model in `analytics/xp_model.py` using PSxG +/- to predict save volume and bonus point propensity.
- Enhance the Bonus Point System (BPS) predictor in `analytics/xp_model.py` with SCA/90.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation is considered complete when:*
- [ ] `clients/fbref_client.py` uses `soccerdata` (or FBref scraper) to retrieve seasonal advanced stats with multi-day disk caching to minimize traffic.
- [ ] Name matching normalizes FBref player names to FPL IDs via existing alias utilities in `clients/tactical_client.py`.
- [ ] Goalkeeper expected points in `analytics/xp_model.py` incorporates PSxG +/- as a multiplier on expected save points.
- [ ] BPS bonus estimation incorporates SCA/90 as a positive signal for outfield assets.
- [ ] Pytest suite validates data extraction, caching behavior, and mathematical bonus adjustments with synthetic DataFrames.

---

## 4. Technical Constraints & Context
- Must respect FBref scraping rate limits (minimum 3-second delay, strict local caching).
- Fully vectorized NumPy/pandas operations in accordance with `.agents/rules/python_standards.md`.
