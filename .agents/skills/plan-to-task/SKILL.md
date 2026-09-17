---
name: plan-to-task
description: Acts as Transition T_PLAN_TO_TASK in the Agentic Coloured Petri Net (CPN), consuming a Plan token from P_PLAN_READY (and P_HUMAN_SEMAPHORE) and generating a machine-executable Task token harness in P_TASK_QUEUE (<80 lines diff per task).
---

# plan-to-task

## Purpose
`plan-to-task` fires as **Transition $T_{\text{PLAN\_TO\_TASK}}$** in the **Agentic Coloured Petri Net (CPN)**. Guarded by a human `ApprovalToken` in $P_{\text{HUMAN\_SEMAPHORE}}$, it consumes an approved `PlanToken` from $P_{\text{PLAN\_READY}}$ (`docs/plans/pln_<ID>_<slug>.md`) and generates a machine-executable micro-task harness, depositing strongly typed `TaskToken` items into the FIFO queue $P_{\text{TASK\_QUEUE}}$ (`docs/tasks/tsk_<ID>_<slug>.md`).

Each micro-task in the harness is strictly bounded:
- **Maximum Diff**: $\le 80$ lines of code change per task.
- **Maximum Files**: 1–2 files per task.
- **Definitive Pass/Fail**: Every single task specifies an exact command (e.g. `python -m pytest tests/test_foo.py -k test_bar`) that must exit code 0 before advancing.

## When to Activate
- When a user asks to "compile the plan into tasks" or runs `/plan-to-task`.
- When transitioning from Stage 4 (Plan) to Stage 5 (Tasks).
- When preparing an automated coding agent run.

## Execution Steps

### 1. Analyze Implementation Plan
- Read the source plan `docs/plans/pln_<ID>_<slug>.md` using `view_file`.
- Note the Origin Design and Issue to preserve unbroken CPN lineage trace.

### 2. Decompose into Micro-Tasks
Break each phase of the plan into bite-sized micro-tasks:
- Task 1.1: File creation or interface signature.
- Task 1.2: Core implementation logic (<80 lines).
- Task 1.3: Pytest unit test file.

### 3. Write Task Harness Document
Write `docs/tasks/tsk_<ID>_<slug>.md` using the template below.

### 4. Rebuild ARD Manifest
Run `python scripts/ard_builder.py`.

---

## Content Body Template

```markdown
---
type: TaskHarness
title: "[#<ID>] <Title> - Task Harness"
description: "<Execution harness with micro-tasks and verification commands>"
tags: [task, python, <domain>, <tech>]
status: Active
sources: ["docs/plans/pln_<ID>_<slug>.md"]
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:plan-to-task"
---

# Task Harness [#<ID>]: <Title>

## 0. Frontloader (CPN Lifecycle Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Place**: `P_PLAN_READY`
> - **Current Transition**: `T_PLAN_TO_TASK`
> - **Next Place**: `P_TASK_QUEUE`
> - **CPN Lineage**: Issue [#<ID>] -> [Brainstorm] -> Design [des_<ID>] -> Plan [pln_<ID>] -> Tasks [tsk_<ID>] -> Playbook
> - **Origin Plan**: [`docs/plans/pln_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/plans/pln_<ID>_<slug>.md)
> - **URN**: urn:air:clydewatts1:rubies_rangers:docs:tsk_<ID>_<slug>

---

## Execution Progress

- Total Tasks: $N$
- Completed: $0 / N$

---

## Phase 0: Prerequisite Contracts

- [ ] **Task 0.1: Define Dataclass Contracts**
  - **File(s)**: `analytics/contracts.py`
  - **Action**: Add `@dataclass(frozen=True)` definition for ...
  - **Max Diff**: < 40 lines
  - **Verification**: `python -m py_compile analytics/contracts.py`

---

## Phase 1: Implementation

- [ ] **Task 1.1: Core Solver Implementation**
  - **File(s)**: `analytics/optimizer.py`
  - **Action**: Implement method `solve_custom(...)`
  - **Max Diff**: < 75 lines
  - **Verification**: `python -m pytest tests/test_optimizer.py`

---

## Phase 2: UI Presentation

- [ ] **Task 2.1: Wire into Streamlit Tab**
  - **File(s)**: `ui/tabs/tab_foo.py`
  - **Action**: Add view component
  - **Verification**: `python -m py_compile ui/tabs/tab_foo.py`

---

## Phase 3: Verification & Playbook

- [ ] **Task 3.1: Full Regression Pass**
  - **Verification**: `python -m pytest tests/`
- [ ] **Task 3.2: Generate Playbook**
  - **Action**: Invoke `/playbook-facilitator` to produce `docs/playbooks/plb_<ID>_<slug>.md`
```
