---
type: TaskHarness
title: "[#019] ClubElo API Dynamic Team Ratings & Bivariate Poisson Goals Engine - Task Harness"
description: "Execution task harness for building ClubElo client, integrating dynamic Poisson team odds into XPModel and TrajectoryEngine, and validating with pytests."
tags: [task, python, clubelo, ratings, poisson, analytics, client]
status: Active
sources: ["docs/design/des_019_clubelo_dynamic_team_ratings.md"]
generated:
  at: "2026-09-17T20:00:00Z"
  by: "agent:plan-to-task"
---

# Task Harness [#019]: ClubElo API Dynamic Team Ratings & Bivariate Poisson Goals Engine

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_DESIGN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#019] -> Design [des_019] -> Tasks [tsk_019] -> Playbook [plb_019]
> - **Origin Design**: [`docs/design/des_019_clubelo_dynamic_team_ratings.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_019_clubelo_dynamic_team_ratings.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:tsk_019_clubelo_dynamic_team_ratings`

---

## Execution Progress
- Total Tasks: 5
- Completed: 5 / 5

---

## Phase 0: Client & Contracts Implementation

- [x] **Task 0.1: Build `clients/clubelo_client.py` Data Contracts & Name Resolver**
  - **File(s)**: `clients/clubelo_client.py`
  - **Action**: Implement `ClubEloRecord`, `FixtureExpectancy`, `CLUBELO_TO_FPL` mapping, and CSV fetching with local disk caching (`.clubelo_cache.json`).
  - **Verification**: `python -m py_compile clients/clubelo_client.py`

- [x] **Task 0.2: Implement Poisson Formulation & `build_team_odds_map()`**
  - **File(s)**: `clients/clubelo_client.py`
  - **Action**: Add `compute_fixture_expectancy()` and `build_team_odds_map()` with log-linear Poisson formulas ($\beta = 0.00231$, $H_a = 75.0$) and safety clipping.
  - **Verification**: `python -c "from clients.clubelo_client import ClubEloClient; c = ClubEloClient(); print(c.compute_fixture_expectancy('MCI', 'NFO'))"`

---

## Phase 1: Analytical Engine Integration

- [x] **Task 1.1: Integrate Dynamic Team Odds into `analytics/xp_model.py`**
  - **File(s)**: `analytics/xp_model.py`
  - **Action**: Update `XPModel._build_team_odds_map()` to consume `ClubEloClient` dynamically for any gameweek, retaining fallback to static config if offline.
  - **Verification**: `python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=4); print(list(xm.team_odds.keys()))"`

- [x] **Task 1.2: Integrate Dynamic Ratings into `analytics/strategic/trajectory_engine.py`**
  - **File(s)**: `analytics/strategic/trajectory_engine.py`
  - **Action**: Update `build_club_schedule_profiles()` to use continuous ClubElo attack/defense coefficients when available.
  - **Verification**: `python -c "from analytics.strategic.trajectory_engine import TrajectoryEngine; te = TrajectoryEngine(); print(len(te.get_club_profiles(horizon=4)))"`

---

## Phase 2: Pytest Suite & ARD Verification

- [x] **Task 2.1: Create Comprehensive Pytest Suite**
  - **File(s)**: `tests/test_clubelo_client.py`
  - **Action**: Write unit tests verifying CSV parsing, Poisson math, clipping bounds, cache management, and offline fallback.
  - **Verification**: `python -m pytest tests/test_clubelo_client.py -v`

