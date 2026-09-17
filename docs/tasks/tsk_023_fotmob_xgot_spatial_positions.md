---
type: TaskHarness
title: "[#023] FotMob REST Client for xGOT Finishing Skill - Task Harness"
description: "Execution task harness for building the FotMob client, xGOT - xG finishing skill calculation, lineup verification, and XPModel integration."
tags: [task, python, fotmob, xgot, finishing, lineups, analytics, xp]
status: Active
sources: ["docs/design/des_023_fotmob_xgot_spatial_positions.md"]
generated:
  at: "2026-09-17T21:31:00Z"
  by: "agent:plan-to-task"
---

# Task Harness [#023]: FotMob REST Client for xGOT Finishing Skill

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_DESIGN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#023] -> Design [des_023] -> Tasks [tsk_023] -> Playbook [plb_023]
> - **Origin Design**: [`docs/design/des_023_fotmob_xgot_spatial_positions.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_023_fotmob_xgot_spatial_positions.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:tsk_023_fotmob_xgot_spatial_positions`

---

## Execution Progress
- Total Tasks: 4
- Completed: 4 / 4

---

## Phase 0: Client & Contracts Implementation

- [x] **Task 0.1: Build `clients/fotmob_client.py` Contracts & Finishing Formula**
  - **File(s)**: `clients/fotmob_client.py`
  - **Action**: Implement `FotMobPlayerStats`, `FotMobLineup`, and `compute_finishing_multiplier()`.
  - **Verification**: `python -m py_compile clients/fotmob_client.py`

- [x] **Task 0.2: Implement FotMob Data Ingestion & 24-Hour Disk Caching**
  - **File(s)**: `clients/fotmob_client.py`
  - **Action**: Implement retrieval of $xGOT$, $xG$, and goals prevented with local `.fotmob_cache.json` persistence.
  - **Verification**: `python -c "from clients.fotmob_client import FotMobClient; c = FotMobClient(); print(len(c.get_all_player_stats()))"`

---

## Phase 1: Model Integration in `analytics/xp_model.py`

- [x] **Task 1.1: Integrate FotMob Finishing Skill into Forward Metrics**
  - **File(s)**: `analytics/xp_model.py`
  - **Action**: Wire `FotMobClient` into `XPModel.__init__` and incorporate finishing delta into forward multiplier.
  - **Verification**: `python -c "from analytics.xp_model import XPModel; xm = XPModel(gameweek=4); print(xm.calculate_player_xp({'web_name': 'Haaland', 'position_name': 'FWD', 'club_short': 'MCI'}, {'avg_recent_mins': 90.0, 'minutes_status': 'SECURE_STARTER'}, {}))"`

---

## Phase 2: Pytest Suite & Verification

- [x] **Task 2.1: Author Comprehensive Pytest Suite**
  - **File(s)**: `tests/test_fotmob_client.py`
  - **Action**: Write unit tests verifying finishing delta math, multiplier clamping, caching behavior, and XPModel integration.
  - **Verification**: `python -m pytest tests/test_fotmob_client.py -v`
