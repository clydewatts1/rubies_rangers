---
type: TaskHarness
title: "[#020] The Odds API Client for Live Vig-Removed Market Consensus - Task Harness"
description: "Execution task harness for building The Odds API client, vig-removal algorithms, Poisson goal derivation, and tiered integration into XPModel."
tags: [task, python, odds, market, client, analytics, xp]
status: Completed
sources: ["docs/design/des_020_the_odds_api_market_consensus.md"]
generated:
  at: "2026-09-17T20:17:00Z"
  by: "agent:plan-to-task"
---

# Task Harness [#020]: The Odds API Client for Live Vig-Removed Market Consensus

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_DESIGN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#020] -> Design [des_020] -> Tasks [tsk_020] -> Playbook [plb_020]
> - **Origin Design**: [`docs/design/des_020_the_odds_api_market_consensus.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_020_the_odds_api_market_consensus.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:tsk_020_the_odds_api_market_consensus`

---

## Execution Progress
- Total Tasks: 5
- Completed: 5 / 5

---

## Phase 0: Client & Contracts Implementation

- [x] **Task 0.1: Build `clients/odds_client.py` Data Contracts & Vig-Removal**
  - **File(s)**: `clients/odds_client.py`
  - **Action**: Implement `MarketOddsRecord`, `FairMarketExpectancy`, team name mapper, and proportional vig-removal logic.
  - **Verification**: `python -m py_compile clients/odds_client.py`

- [x] **Task 0.2: Implement Numerical Inversion & Poisson Derivation**
  - **File(s)**: `clients/odds_client.py`
  - **Action**: Implement solver inverting $P(\text{Under 2.5}) \rightarrow T$ and partitioning into $(\lambda_H, \lambda_A)$ and $P(\text{CS})$.
  - **Verification**: `python -c "from clients.odds_client import OddsClient; c = OddsClient(); print(c.solve_total_goals(0.45))"`

---

## Phase 1: Ingestion & Quota Governance

- [x] **Task 1.1: Implement API Fetcher, Quota Telemetry & Disk Caching**
  - **File(s)**: `clients/odds_client.py`
  - **Action**: Add network fetching with `x-requests-remaining` tracking, quota exhaustion guard, and local `.odds_cache.json`.
  - **Verification**: `python -c "from clients.odds_client import OddsClient; c = OddsClient(); print(c.get_quota_info())"`

- [x] **Task 1.2: Tiered Integration in `analytics/xp_model.py`**
  - **File(s)**: `analytics/xp_model.py`
  - **Action**: Update `_build_team_odds_map()` to check `OddsClient` first (Tier 1) before falling back to `ClubEloClient` (Tier 2).
  - **Verification**: `python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=4); print(len(xm.team_odds))"`

---

## Phase 2: Pytest Suite & Verification

- [x] **Task 2.1: Create Comprehensive Pytest Suite**
  - **File(s)**: `tests/test_odds_client.py`
  - **Action**: Write unit tests verifying vig removal, goal inversion, quota management, and XPModel fallback.
  - **Verification**: `python -m pytest tests/test_odds_client.py -v`
