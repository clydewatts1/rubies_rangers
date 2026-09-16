---
name: doc-frontmatter-generator
description: Generates and validates OKF YAML frontmatter for internal lifecycle documents (Issues, Brainstorms, Designs, Plans, Tasks, Playbooks). Use whenever authoring a new document in docs/ or auditing existing ones for ARD compliance.
---

# doc-frontmatter-generator

## Purpose
This skill standardizes and validates Open Knowledge Format (OKF) YAML frontmatter on all markdown documents across `docs/`. It ensures every document can be cataloged by the Agentic Resource Discovery (`scripts/ard_builder.py`) manifest builder.

## Valid Document Types by Stage

| Stage | Directory | Valid `type` Values | Mandatory `sources` Lineage |
| :--- | :--- | :--- | :--- |
| **Stage 1: Issue** | `docs/issues/` | `Issue` | `[]` (or prior audit doc if derived) |
| **Stage 2: Brainstorm** | `docs/brainstorm/` | `Brainstorm` | Link to parent Issue (`docs/issues/...`) |
| **Stage 3: Design** | `docs/design/` | `Design` | Link to parent Brainstorm (`docs/brainstorm/...`) |
| **Stage 4: Plan** | `docs/plans/` | `Plan` | Link to parent Design (`docs/design/...`) |
| **Stage 5: Tasks** | `docs/tasks/` | `TaskHarness` | Link to parent Plan (`docs/plans/...`) |
| **Stage 6: Playbook** | `docs/playbooks/` | `Playbook` | Link to parent Design (`docs/design/...`) |
| **Developer Tools** | `docs/tools/` | `Tool` | `[]` |

## Standard OKF Schema

```yaml
---
type: <ValidType>
title: "[#<ID>] <Display Title>"
description: "<Concise 1-2 sentence summary for search and embeddings>"
tags: [<tag1>, <tag2>, <tag3>]
status: Open | Active | Draft | Closed | Deprecated
sources: ["<relative/path/to/parent.md>"]
generated:
  at: "<ISO-8601-UTC-Timestamp>"
  by: "agent:<agent_or_skill_name>"
---
```

## Approved Tag Taxonomy
- **Process**: `issue`, `brainstorm`, `design`, `plan`, `task`, `playbook`, `process`, `architecture`, `derived`, `audit`, `idea`, `bug`, `feature`
- **Domain**: `optimization`, `monte-carlo`, `milp`, `knapsack`, `cpn`, `saga`, `transfers`, `hits`, `chips`, `balance-sheet`, `challenge`, `rolling-lock`, `fdr`, `weather`, `odds`, `tactics`, `setpieces`, `venue`, `moneyball`, `scout`, `telemetry`, `strategy`, `portfolio`
- **Technology**: `python`, `pandas`, `numpy`, `streamlit`, `pytest`, `asyncio`, `yaml`, `json`, `fastapi`, `pulp`, `scipy`
- **Component**: `engine`, `client`, `service`, `ui`, `component`, `solver`, `adapter`, `runner`, `daemon`, `validator`, `journal`, `tooling`, `registry`, `discovery`, `cli`
