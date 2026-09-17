---
type: TaskHarness
title: "[#021] Automated Premier Injuries Scraper for Pre-Deadline Availability Intel - Task Harness"
description: "Execution task harness for building the injury scraper client, availability mapping function, name resolution, and integration into Shane's Domain Intel desk."
tags: [task, python, injuries, availability, intel, domain, client]
status: Completed
sources: ["docs/design/des_021_premier_injuries_automated_intel.md"]
generated:
  at: "2026-09-17T20:25:00Z"
  by: "agent:plan-to-task"
---

# Task Harness [#021]: Automated Premier Injuries Scraper for Pre-Deadline Availability Intel

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_DESIGN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#021] -> Design [des_021] -> Tasks [tsk_021] -> Playbook [plb_021]
> - **Origin Design**: [`docs/design/des_021_premier_injuries_automated_intel.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/design/des_021_premier_injuries_automated_intel.md)
> - **URN**: `urn:air:clydewatts1:rubies_rangers:docs:tsk_021_premier_injuries_automated_intel`

---

## Execution Progress
- Total Tasks: 5
- Completed: 5 / 5

---

## Phase 0: Client & Contracts Implementation

- [x] **Task 0.1: Build Data Contracts & Availability Mapping Function ($\Phi$)**
  - **File(s)**: `clients/injury_client.py`
  - **Action**: Implement `RawInjuryRecord`, `ProcessedInjuryIntel`, and `map_injury_status_to_availability()`.
  - **Verification**: `python -m py_compile clients/injury_client.py`

- [x] **Task 0.2: Implement Player Name & Club Resolution Engine**
  - **File(s)**: `clients/injury_client.py`
  - **Action**: Implement resolver linking external player names and 3-letter club codes to official FPL element IDs.
  - **Verification**: `python -c "from clients.injury_client import InjuryClient; c = InjuryClient(); print(c.resolve_player('William Saliba', 'ARS'))"`

---

## Phase 1: Ingestion & Domain Intel Integration

- [x] **Task 1.1: Implement Ingestion Engine & Local Disk Caching**
  - **File(s)**: `clients/injury_client.py`
  - **Action**: Implement HTTP fetching from live EPL injury feed, error handling, and 2-hour disk cache (`.injury_cache.json`).
  - **Verification**: `python -c "from clients.injury_client import InjuryClient; c = InjuryClient(); print(len(c.get_injury_intel()))"`

- [x] **Task 1.2: Integrate Automated Sync into `ShaneIntelManager`**
  - **File(s)**: `analytics/domain_intel.py`
  - **Action**: Add `sync_injury_intel()` method converting active injury records into `PlayerOverride` objects with 1-GW TTL.
  - **Verification**: `python -c "from analytics.domain_intel import ShaneIntelManager; sm = ShaneIntelManager(); print(hasattr(sm, 'sync_injury_intel'))"`

---

## Phase 2: Pytest Suite & Verification

- [x] **Task 2.1: Author Comprehensive Pytest Suite**
  - **File(s)**: `tests/test_injury_client.py`
  - **Action**: Write unit tests verifying mapping function $\Phi$, player name resolution, caching, offline fallback, and domain intel sync.
  - **Verification**: `python -m pytest tests/test_injury_client.py -v`
