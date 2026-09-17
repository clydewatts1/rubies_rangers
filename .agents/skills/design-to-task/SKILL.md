---
name: design-to-task
description: Composite pipeline skill in the Agentic CPN that chains Transition T_SPEC_TO_PLAN (P_DESIGN_READY -> P_PLAN_READY) and Transition T_PLAN_TO_TASK (P_PLAN_READY -> P_TASK_QUEUE) to produce both an authoritative Plan and execution-ready Task harness in a unified workflow.
---

# design-to-task

## Purpose
`design-to-task` is an end-to-end composite pipeline orchestrator in the **Agentic Coloured Petri Net (CPN)** bridging design specification to execution readiness. It chains two consecutive net transitions:
1. **Transition $T_{\text{SPEC\_TO\_PLAN}}$**: Generates an authoritative **Implementation Plan** (`docs/plans/pln_<ID>_<slug>.md`) in $P_{\text{PLAN\_READY}}$ via `spec-to-plan`.
2. **Transition $T_{\text{PLAN\_TO\_TASK}}$**: Compiles a machine-executable **Task Harness** (`docs/tasks/tsk_<ID>_<slug>.md`) into $P_{\text{TASK\_QUEUE}}$ via `plan-to-task`.

```
Place P_DESIGN_READY (docs/design/des_*.md)
                     │
                     ▼
       [Transition T_SPEC_TO_PLAN]
       Lead Systems Architect: Scope, Invariants, Budgets, Contracts
                     │
                     ▼
Place P_PLAN_READY (docs/plans/pln_<ID>_<slug>.md)
                     │
                     ▼
       [Transition T_PLAN_TO_TASK]
       Task Compiler: Tight Harness, Micro-Tasks (<80 lines), Rollbacks
                     │
                     ▼
Place P_TASK_QUEUE (docs/tasks/tsk_<ID>_<slug>.md)
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
