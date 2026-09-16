---
name: plan-to-task
description: Compiles a Stage 4 Implementation Plan (pln_<ID>_<slug>.md) into a machine-executable, highly granular micro-task harness in docs/tasks/tsk_<ID>_<slug>.md. Decomposes work into tight micro-tasks (<80 lines of diff) with binary pass/fail verification commands.
---

# plan-to-task

## Purpose
`plan-to-task` operates as the **Task Compiler** bridging Stage 4 (Plan) to implementation. It consumes an authoritative Implementation Plan (`docs/plans/pln_<ID>_<slug>.md`) and generates a machine-executable micro-task harness in `docs/tasks/tsk_<ID>_<slug>.md`.

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
- Note the Origin Design and Issue to preserve DAG lineage.

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

## 0. Frontloader (DAG Context)
> **Metadata for Downstream Execution & Audits**
> - **Origin Plan**: [`docs/plans/pln_<ID>_<slug>.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/docs/plans/pln_<ID>_<slug>.md)
> - **Current Stage**: Stage 5 (Tasks)
> - **DAG Lineage**: Issue → Brainstorm → Design → Plan → Tasks → Implementation → Playbook
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
