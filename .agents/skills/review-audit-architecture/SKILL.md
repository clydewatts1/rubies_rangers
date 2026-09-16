---
name: review-audit-architecture
description: Audits the Python codebase against strict domain layering (UI -> Orchestration -> Analytical Engines -> Data Clients). Flags circular imports, god-object monoliths, leaky abstractions, and global state mutations.
---

# review-audit-architecture

## Purpose
This skill audits the repository against the architectural invariants defined in [`.agents/rules/python_standards.md`](file:///c:/Users/cw171001/OneDrive%20-%20Teradata/Documents/GitHub/rubies_rangers/.agents/rules/python_standards.md).

## Architectural Hierarchy
Every component in Rubies Rangers must strictly fit into one of 4 layers:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Presentation Layer (ui/): Streamlit Desks & Components   │
├─────────────────────────────────────────────────────────────┤
│ 2. Orchestration Layer (automation/): CPN Engines & Saga    │
├─────────────────────────────────────────────────────────────┤
│ 3. Analytical Engine Layer (analytics/): Solvers & Models   │
├─────────────────────────────────────────────────────────────┤
│ 4. Data Client Layer (clients/): External APIs & Caches     │
└─────────────────────────────────────────────────────────────┘
```

## Audit Rules & Anti-Patterns

### 1. Inward Dependency Rule (Strict Layering)
- `ui/` MAY call `analytics/`, `automation/`, and `clients/`.
- `automation/` MAY call `analytics/` and `clients/`.
- `analytics/` MAY call `clients/` (or receive data via dependency injection). `analytics/` MUST NEVER import from `ui/` or `automation/`.
- `clients/` MUST NEVER import from `analytics/`, `automation/`, or `ui/`.

### 2. Prohibited Anti-Patterns
- **No God Objects**: Classes exceeding 500 lines or orchestrating multiple disparate domains.
- **No Circular Imports**: Module A imports B imports A.
- **No Global Mutable State**: Modifying global variables across modules without explicit thread-safe container.
- **No Direct Network Calls in Analytical Modules**: Mathematical optimization engines must be pure functions or accept in-memory dataframes, not make ad-hoc HTTP requests.

## Audit Workflow
1. Run static analysis or inspect imports using `grep_search`.
2. Trace import trees for cross-layer bleed.
3. Generate an Architectural Audit Report highlighting any detected violations.
