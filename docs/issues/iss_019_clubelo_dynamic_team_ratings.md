---
type: Issue
title: "[#019] ClubElo API Dynamic Team Ratings & Bivariate Poisson Goals Engine"
description: "Integrate ClubElo API to compute objective, daily-updated team strength ratings and bivariate Poisson expected goals for all 38 gameweeks, replacing static match odds."
tags: [issue, feature, clubelo, ratings, poisson, analytics, client]
status: Open
sources: []
generated:
  at: "2026-09-17T19:56:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#019]: ClubElo API Dynamic Team Ratings & Bivariate Poisson Goals Engine

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#019] -> Design -> Tasks -> Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_019_clubelo_dynamic_team_ratings`

---

## 1. Context & Concept (The Why)
Currently, Rubies Rangers relies on hardcoded betting odds for Gameweek 4 (`gw4_match_odds` in `config.yaml`), while future gameweeks fall back to a coarse normalization of official FPL team strength ratings (`strength_attack_*`, `strength_defence_*`), which are slow to adjust to form shifts and tactical changes.

ClubElo (`http://api.clubelo.com/`) provides 100% free, daily-updated, objective Elo ratings for all European football clubs. By integrating ClubElo:
1. Every Premier League club receives a dynamically calibrated Elo rating updated after each match.
2. The rating difference $\Delta \text{Elo} = \text{Elo}_{\text{Home}} + 80 - \text{Elo}_{\text{Away}}$ maps mathematically into bivariate Poisson expected goals ($\lambda_{\text{Home}}, \lambda_{\text{Away}}$).
3. The multi-horizon trajectory engine and solver obtain high-fidelity fixture difficulty ratings and expected goals across all 38 gameweeks with zero manual configuration.

---

## 2. Goals & Objectives
- Build a resilient `ClubEloClient` in `clients/clubelo_client.py` with local disk caching (24-hour TTL) to fetch current Premier League club ratings.
- Map ClubElo team name conventions to standard FPL club three-letter codes (`t_code`).
- Formulate a calibrated bivariate Poisson goal expectancy function converting $\Delta \text{Elo}$ into $(\lambda_{\text{home}}, \lambda_{\text{away}})$ and Clean Sheet probability $P(\text{CS}) = \exp(-\lambda_{\text{opponent}})$.
- Integrate dynamic ratings into `analytics/strategic/trajectory_engine.py` and `analytics/xp_model.py`.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation is considered complete when:*
- [ ] `clients/clubelo_client.py` fetches and parses `http://api.clubelo.com/` with robust alias mapping and local caching.
- [ ] Mathematical transformation function $\Delta \text{Elo} \rightarrow (\lambda_{\text{home}}, \lambda_{\text{away}})$ is calibrated against Premier League historical goal averages ($\sim 1.35$ goals/team/match).
- [ ] `analytics/strategic/trajectory_engine.py` consumes ClubElo dynamic strength ratings across the planning horizon ($H = 4 \dots 8$ GWs).
- [ ] Fallback mechanism gracefully handles offline status or network drops by falling back to FPL API base strength.
- [ ] Pytest suite verifies client retrieval, name normalization, and Poisson goal calculations.

---

## 4. Technical Constraints & Context
- Zero paid dependencies or API keys; endpoint is open public CSV/REST.
- Strict type annotations and frozen dataclasses in accordance with `.agents/rules/python_standards.md`.
