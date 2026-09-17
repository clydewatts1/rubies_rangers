---
type: TaskHarness
title: "[#024] Premier League Referee Historical Analytics - Task Harness"
description: "Execution task harness for building the referee tendencies store, referee client, penalty and card multipliers, and XP/Monte Carlo engine integration."
tags: [task, python, referee, penalties, cards, montecarlo, analytics, xp]
status: Active
sources: ["docs/design/des_024_referee_penalty_variance_modeling.md"]
generated:
  at: "2026-09-17T21:36:00Z"
  by: "agent:plan-to-task"
---

# Task Harness [#024]: Premier League Referee Historical Analytics

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_DESIGN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#024] -> Design [des_024] -> Tasks [tsk_024] -> Playbook [plb_024]
> - **Origin Design**: [`docs/design/des_024_referee_penalty_variance_modeling.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_024_referee_penalty_variance_modeling.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:tsk_024_referee_penalty_variance_modeling`

---

## Execution Progress
- Total Tasks: 4
- Completed: 4 / 4

---

## Phase 0: Data Store & Client Implementation

- [x] **Task 0.1: Build `data/referee_tendencies.json` Reference Store**
  - **File(s)**: `data/referee_tendencies.json`
  - **Action**: Curate historical penalties per match, yellow cards, red cards, and fouls per tackle for active Select Group 1 referees.
  - **Verification**: `python -c "import json; data=json.load(open('data/referee_tendencies.json')); print('Referees:', len(data['referees']))"`

- [x] **Task 0.2: Implement `clients/referee_client.py` Contracts & Formulas**
  - **File(s)**: `clients/referee_client.py`
  - **Action**: Implement `RefereeProfile`, `RefereeClient`, `compute_referee_penalty_multiplier()`, card risk multipliers, and baseline fallback.
  - **Verification**: `python -m py_compile clients/referee_client.py`

---

## Phase 1: Model Integration in `analytics/xp_model.py` & `analytics/montecarlo.py`

- [x] **Task 1.1: Integrate Referee Modulations into XPModel & Monte Carlo Engine**
  - **File(s)**: `analytics/xp_model.py`, `analytics/montecarlo.py`
  - **Action**: Wire `RefereeClient` into `XPModel.__init__` and `MonteCarloEngine`; modulate penalty award chance and card deductions.
  - **Verification**: `python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=4); print(xm.calculate_player_xp({'web_name': 'Haaland', 'position_name': 'FWD', 'club_short': 'MCI', 'penalties_order': 1}, {'avg_recent_mins': 90.0, 'minutes_status': 'SECURE_STARTER'}, {}))"`

---

## Phase 2: Pytest Suite & Verification

- [x] **Task 2.1: Author Comprehensive Pytest Suite**
  - **File(s)**: `tests/test_referee_client.py`
  - **Action**: Write unit and integration tests verifying penalty multipliers, card multipliers, baseline fallbacks, and model integration.
  - **Verification**: `python -m pytest tests/test_referee_client.py -v`
