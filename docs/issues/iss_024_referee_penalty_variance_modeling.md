---
type: Issue
title: "[#024] Premier League Referee Historical Analytics & Penalty Tendency Modeling"
description: "Incorporate referee historical penalty award rates and card accumulation tendencies per 90 into the XP and Monte Carlo models, replacing the static 0.18 penalty assumption."
tags: [issue, feature, referee, penalties, cards, montecarlo, xp]
status: Open
sources: []
generated:
  at: "2026-09-17T19:56:00Z"
  by: "agent:issue-ingestion-parser"
---

# Issue [#024]: Premier League Referee Historical Analytics & Penalty Tendency Modeling

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Skills & Audits**
> - **Origin Place**: `P_BACKLOG`
> - **Current Transition**: `T_ISSUE_INGEST`
> - **Next Place**: `P_ISSUE_READY`
> - **CPN Lineage**: Issue [#024] -> Design -> Tasks -> Playbook
> - **Execution Track**: Track B (Fast-Track 4-Stage)
> - **Priority**: P2-Medium
> - **Estimated Complexity**: S
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:iss_024_referee_penalty_variance_modeling`

---

## 1. Context & Concept (The Why)
In official FPL, penalties are worth 4 points for forwards and 5 points for midfielders, making designated penalty takers high-leverage assets. Currently, `analytics/xp_model.py` and `config.yaml` model the chance of a penalty being awarded in a match as a flat constant:
```yaml
penalty:
  conversion_rate: 0.79
  match_award_chance: 0.18
```
In reality, Premier League referee variance is substantial. Across historical seasons:
- High-whistle referees (e.g., Anthony Taylor, Robert Jones) average $> 0.35$ penalties awarded per match.
- Strict referees (e.g., Paul Tierney, Michael Oliver) average $< 0.14$ penalties per match.
- High-card referees average $> 4.8$ yellow cards per match, significantly depressing baseline BPS scores ($-3$ BPS per yellow card) and increasing red card tail risk.

Official referee appointments are confirmed by the Premier League on Monday/Tuesday prior to each gameweek and are exposed in the official FPL fixtures endpoint (`fpl_fixture['pulse_id']` / match referee).

---

## 2. Goals & Objectives
- Ingest referee appointments from the FPL fixtures API in `clients/fpl_client.py`.
- Compile and maintain a curated historical referee tendencies dataset (`data/referee_tendencies.json` or CSV) based on public Premier League records:
  - `penalties_per_match`: historical penalty award frequency.
  - `yellows_per_match`: yellow card rate.
  - `reds_per_match`: straight/double yellow red card rate.
  - `fouls_per_tackle`: referee whistle threshold.
- Modulate the match penalty probability in `analytics/xp_model.py`:
  $$P(\text{penalty awarded}) = P_{\text{base}} \cdot \left(\frac{\text{RefPenRate}}{\text{LeagueAvgPenRate}}\right)$$
- Incorporate card risk into the Monte Carlo simulation engine (`analytics/montecarlo.py`).

---

## 3. Acceptance Criteria (Definition of Done)
*The implementation is considered complete when:*
- [ ] Curated referee dataset `data/referee_tendencies.json` covers active Premier League Select Group 1 referees.
- [ ] Referee appointment extractor in `FPLClient` retrieves the assigned referee for each fixture in the active gameweek.
- [ ] `analytics/xp_model.py` dynamically adjusts penalty taker xP based on the assigned referee's historical award rate.
- [ ] Monte Carlo simulation applies referee-specific yellow/red card probability distributions to tail outcome modeling.
- [ ] Pytest suite verifies referee matching, baseline fallbacks for newly promoted referees, and xP modulation.

---

## 4. Technical Constraints & Context
- Curated reference data can be stored locally with zero external API calls.
- Unassigned or newly appointed referees must gracefully fall back to the league baseline (0.18).
