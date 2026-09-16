---
name: design-to-task
description: Composite pipeline skill that converts a Stage 3 Technical Design document directly into both an authoritative Implementation Plan (pln_<ID>_<slug>.md) and an execution-ready task harness (tsk_<ID>_<slug>.md) in a single unified workflow.
---

# design-to-task

## Purpose
`design-to-task` is an end-to-end composite pipeline orchestrator bridging Stage 3 (Design) to execution readiness. It converts a technical design specification (`docs/design/des_<ID>_<slug>.md`) into both:
1. An authoritative **Implementation Plan** (`docs/plans/pln_<ID>_<slug>.md`) via `spec-to-plan`.
2. A machine-executable **Task Harness** (`docs/tasks/tsk_<ID>_<slug>.md`) via `plan-to-task`.

```
Stage 3 Design Document (docs/design/des_*.md)
                     │
                     ▼
       [Phase 1: spec-to-plan]
       Lead Systems Architect: Scope, Invariants, Budgets, Contracts
                     │
                     ▼
       docs/plans/pln_<ID>_<slug>.md
                     │
                     ▼
       [Phase 2: plan-to-task]
       Task Compiler: Tight Harness, Micro-Tasks (<80 lines), Rollbacks
                     │
                     ▼
       docs/tasks/tsk_<ID>_<slug>.md
```

## When to Activate
- When the user runs `/design-to-task` or says "turn this design into tasks".
- When transitioning from a completed Stage 3 Design document directly to implementation readiness.

## Execution Steps
1. **Analyze Design Spec**: Read `docs/design/des_<ID>_<slug>.md` using `view_file`.
2. **Execute `spec-to-plan`**: Author `docs/plans/pln_<ID>_<slug>.md` with zero hallucinated scope, phased breakdown, invariants, and rollback plan.
3. **Execute `plan-to-task`**: Author `docs/tasks/tsk_<ID>_<slug>.md` decomposing each phase into micro-tasks ($\le 80$ lines diff) with explicit pytest commands.
4. **Rebuild ARD Manifest**: Run `python scripts/ard_builder.py`.
5. **Report Readiness**: Present the generated plan and task harness to the user for execution approval.
