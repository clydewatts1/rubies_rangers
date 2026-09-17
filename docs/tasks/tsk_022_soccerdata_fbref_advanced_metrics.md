---
type: TaskHarness
title: "[#022] FBref / StatsBomb Integration via soccerdata - Task Harness"
description: "Execution task harness for building the FBref client, goalkeeper PSxG save modeling, outfield SCA/GCA BPS calibration, and XPModel integration."
tags: [task, python, soccerdata, fbref, goalkeeper, psxg, sca, gca, analytics, xp]
status: Completed
sources: ["docs/design/des_022_soccerdata_fbref_advanced_metrics.md"]
generated:
  at: "2026-09-17T21:24:00Z"
  by: "agent:plan-to-task"
---

# Task Harness [#022]: FBref / StatsBomb Integration via soccerdata

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_DESIGN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#022] -> Design [des_022] -> Tasks [tsk_022] -> Playbook [plb_022]
> - **Origin Design**: [`docs/design/des_022_soccerdata_fbref_advanced_metrics.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_022_soccerdata_fbref_advanced_metrics.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:tsk_022_soccerdata_fbref_advanced_metrics`

---

## Execution Progress
- Total Tasks: 5
- Completed: 5 / 5

---

## Phase 0: Client & Contracts Implementation

- [x] **Task 0.1: Build `clients/fbref_client.py` Data Contracts & Formulas**
  - **File(s)**: `clients/fbref_client.py`
  - **Action**: Implement `GoalkeeperAdvancedMetrics`, `OutfieldAdvancedMetrics`, and mathematical functions for save points and BPS multipliers.
  - **Verification**: `python -m py_compile clients/fbref_client.py`

- [x] **Task 0.2: Implement Ingestion Engine & Local 72-Hour Disk Caching**
  - **File(s)**: `clients/fbref_client.py`
  - **Action**: Implement multi-tier data ingestion with baseline fallback and local `.fbref_cache.json` persistence.
  - **Verification**: `python -c "from clients.fbref_client import FBrefClient; c = FBrefClient(); print(len(c.get_goalkeeper_metrics()))"`

---

## Phase 1: Model Integration in `analytics/xp_model.py`

- [x] **Task 1.1: Integrate Goalkeeper Save Point Expectancy & PSxG Modulation**
  - **File(s)**: `analytics/xp_model.py`
  - **Action**: Update goalkeeper xP derivation to incorporate expected saves based on opponent goals $\lambda_{\text{opp}}$ and FBref save percentage.
  - **Verification**: `python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=4); print(xm.calculate_player_xp({'web_name': 'Raya', 'position_name': 'GKP', 'club_short': 'ARS'}, {'avg_recent_mins': 90.0, 'minutes_status': 'SECURE_STARTER'}, {}))"`

- [x] **Task 1.2: Integrate SCA/GCA Modulation into Outfield Bonus Points**
  - **File(s)**: `analytics/xp_model.py`
  - **Action**: Modulate outfield baseline BPS bonus expectation with FBref $\text{SCA}/90$ and $\text{GCA}/90$ multiplier.
  - **Verification**: `python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=4); print(xm.calculate_player_xp({'web_name': 'Saka', 'position_name': 'MID', 'club_short': 'ARS'}, {'avg_recent_mins': 90.0, 'minutes_status': 'SECURE_STARTER'}, {}))"`

---

## Phase 2: Pytest Suite & Verification

- [x] **Task 2.1: Author Comprehensive Pytest Suite**
  - **File(s)**: `tests/test_fbref_client.py`
  - **Action**: Write unit tests verifying save point math, SCA/GCA bonus multipliers, caching behavior, and XPModel integration.
  - **Verification**: `python -m pytest tests/test_fbref_client.py -v`
