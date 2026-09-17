---
type: Issue
title: "[#020] The Odds API Client for Live Vig-Removed Market Consensus"
description: "Lightweight client querying The Odds API free tier on deadline day to convert live bookmaker odds (Over/Under, BTTS, CS) into vig-free goal arrival rates and clean sheet probabilities."
tags: [issue, feature, odds, market, client, analytics, xp]
status: Open
sources: []
generated:
  at: "2026-09-17T19:56:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#020]: The Odds API Client for Live Vig-Removed Market Consensus

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#020] -> Design -> Tasks -> Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P1-High
> - **Estimated Complexity**: M
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_020_the_odds_api_market_consensus`

---

## 1. Context & Concept (The Why)
Sports betting markets aggregate vast institutional capital, insider information, tactical team news, and early lineup leaks into closing market prices. In football analytics literature, closing bookmaker consensus represents the most efficient short-term probability distribution available.

Currently, Rubies Rangers has static match odds configured for GW4 in `config.yaml`, requiring manual updates for each upcoming gameweek. The Odds API provides a free tier with 500 requests per month. With 10 Premier League matches per gameweek and 1 pre-deadline refresh, an automated client consumes only $\sim 10$ to $20$ requests/month, leaving ample quota while automating market probability ingestion.

---

## 2. Goals & Objectives
- Create `clients/odds_client.py` targeting The Odds API (`api.the-odds-api.com/v4/sports/soccer_epl/odds`).
- Ingest Premier League match odds across bookmakers (Pinnacle, Bet365, Betfair Exchange) for:
  - H2H (1X2) Match Winner
  - Over/Under 2.5 Total Goals
  - Both Teams to Score (BTTS)
- Apply Shin or proportional vig-removal algorithms to compute fair implied probabilities.
- Derive fair expected team goals ($\lambda_{\text{home}}, \lambda_{\text{away}}$) and Clean Sheet probabilities $P(\text{CS})$.
- Feed dynamically into `analytics/xp_model.py` and `analytics/matchday_hub.py`.

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation is considered complete when:*
- [ ] `clients/odds_client.py` fetches EPL match markets with graceful error handling, request quota tracking, and local caching (12-hour TTL, down to 1-hour within 6 hours of deadline).
- [ ] Vig-removal formula normalizes raw bookmaker odds into true risk-neutral probabilities $\sum p_i = 1.0$.
- [ ] Conversion pipeline derives $\lambda_{\text{home}}, \lambda_{\text{away}}$ and Clean Sheet odds dynamically for the active gameweek.
- [ ] Zero failure impact: if the API key is missing, network fails, or quota is exhausted, system gracefully falls back to ClubElo / historical Poisson baselines.
- [ ] Unit tests verify vig-removal and goal expectancy derivations with mocked API payloads.

---

## 4. Technical Constraints & Context
- Must operate within the free tier (500 requests/month) with strict cache governance.
- Optional API key configuration via environment variable (`ODDS_API_KEY`) or `config.yaml`.
